from decimal import Decimal
import json
import re
from collections import defaultdict
from datetime import date, timedelta, timezone as dt_timezone

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from io import BytesIO

from django.db import models as db_models
from django.core.exceptions import PermissionDenied

from .models import Trip, Expense, SplitBill, SplitEntry, SettlementPayment, TripCollaborator

import pytesseract
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'


# ── Access control helpers ─────────────────────────────────────────────────────
# The owner (trip.created_by) always has full access.
# Superusers (the developer/site owner) automatically have full access to
# every trip too, without needing a TripCollaborator row.
# Everyone else needs a TripCollaborator row: 'view' = read-only, 'edit' = full edit.

def _collab_permission(trip, user):
    if not user.is_authenticated:
        return None
    if user.is_superuser:
        return "owner"
    if trip.created_by_id == user.id:
        return "owner"
    collab = TripCollaborator.objects.filter(trip=trip, user=user).first()
    return collab.permission if collab else None


def user_can_view(trip, user):
    return _collab_permission(trip, user) in ("owner", "view", "edit")


def user_can_edit(trip, user):
    return _collab_permission(trip, user) in ("owner", "edit")


def visible_trips_for(user):
    """Trips a user owns, has been given view/edit access to, or — if they're
    a superuser (the developer) — every trip in the app."""
    if not user.is_authenticated:
        return Trip.objects.none()
    if user.is_superuser:
        return Trip.objects.all()
    return Trip.objects.filter(
        db_models.Q(created_by=user) | db_models.Q(collaborators__user=user)
    ).distinct()


def is_trip_owner(trip, user):
    """True for the trip's actual creator, or for a superuser (developer)."""
    return user.is_authenticated and (trip.created_by_id == user.id or user.is_superuser)



# ── Home ──────────────────────────────────────────────────────────────────────

def home(request):
    ongoing_trip = None
    ongoing_trips = []
    if request.user.is_authenticated:
        ongoing_trips = (
            visible_trips_for(request.user)
            .filter(end_date__gte=date.today())
            .order_by('-created_at')
        )
        ongoing_trip = ongoing_trips.first()
    return render(request, 'trip/home.html', {
        'ongoing_trip': ongoing_trip,
        'ongoing_trips': ongoing_trips,
    })



# ── Login ─────────────────────────────────────────────────────────────────────

def login_view(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            next_url = request.GET.get('next', 'home')
            return redirect(next_url)
        else:
            return render(request, "accounts/login.html", {"error": "Invalid username or password"})
    return render(request, "accounts/login.html")


# ── Make trip ─────────────────────────────────────────────────────────────────

@login_required
def make_trip(request):
    if request.method == "POST":
        participants = []
        for i in range(1, 16):
            name = request.POST.get(f"friend{i}")
            if name:
                participants.append(name.strip())

        Trip.objects.create(
            name=request.POST.get("trip_name"),
            destination=request.POST.get("destination"),
            start_date=request.POST.get("start_date"),
            end_date=request.POST.get("end_date"),
            participants=json.dumps(participants),
            budget=request.POST.get("budget") or 0,
            created_by=request.user,
        )
        return redirect("trip_history")

    return render(request, "trip/make_trip.html", {"participant_range": range(1, 16)})


# ── Trip history ──────────────────────────────────────────────────────────────

@login_required
def trip_history(request):
    trips = visible_trips_for(request.user).order_by('-created_at', '-start_date')
    return render(request, "trip/trip_history.html", {"trips": trips})


# ── Completed trips list ──────────────────────────────────────────────────────

@login_required
def trip_list(request):
    today = timezone.now().date()
    completed_trips = visible_trips_for(request.user).filter(end_date__lt=today).order_by('-end_date')
    return render(request, 'trip/trip_list.html', {'trips': completed_trips})


# ── Trip dashboard ────────────────────────────────────────────────────────────

@login_required
def trip_dashboard(request, trip_id):
    trip = get_object_or_404(Trip, id=trip_id)
    if not user_can_view(trip, request.user):
        raise PermissionDenied("You don't have access to this trip.")
    can_edit = user_can_edit(trip, request.user)
    is_owner = is_trip_owner(trip, request.user)

    # Newest first — drives both the heatmap aggregation and "Recent Expenses"
    expenses = list(Expense.objects.filter(trip=trip).order_by('-created_at'))

    total_expenses   = sum(Decimal(str(exp.amount)) for exp in expenses)
    remaining_budget = trip.budget - total_expenses if trip.budget else Decimal('0')

    try:
        participants = trip.get_participants()
    except Exception:
        participants = []

    cost_per_person = round(total_expenses / len(participants), 2) if participants else None

    # ── Budget alert & percentage ─────────────────────────────────────────────
    budget_alert = get_budget_alert(trip, total_expenses)
    budget_pct = 0
    if trip.budget and trip.budget > 0:
        budget_pct = float(total_expenses) / float(trip.budget) * 100

    # ── Spending Heatmap ──────────────────────────────────────────────────────
    # FIX 1: Use IST (+05:30) when converting created_at to a date so that
    #         expenses logged after midnight IST land on the correct day.
    # FIX 2: Anchor the heatmap window to the trip's own dates, not to today.
    #         Without this, a completed trip (e.g. Aug 2025) always shows a
    #         blank grid because today's 30-day window has zero overlap.
    IST = dt_timezone(timedelta(hours=5, minutes=30))

    daily_totals = defaultdict(float)
    for exp in expenses:
        ist_date = exp.created_at.astimezone(IST).date()
        daily_totals[str(ist_date)] += float(exp.amount)

    hmap_start = trip.start_date
    hmap_end   = trip.end_date
    hmap_days  = (hmap_end - hmap_start).days + 1

    if hmap_days > 60:          # cap at 60 cells so the grid stays readable
        hmap_start = hmap_end - timedelta(days=59)
        hmap_days  = 60

    heatmap_data = []
    for i in range(hmap_days):
        d = hmap_start + timedelta(days=i)
        heatmap_data.append({
            "date":   str(d),
            "amount": round(daily_totals.get(str(d), 0), 2),
        })

    # ── Spending by Category ──────────────────────────────────────────────────
    cat_totals = defaultdict(float)
    for exp in expenses:
        cat_totals[exp.category] += float(exp.amount)

    categories_ranked = sorted(cat_totals.items(), key=lambda x: x[1], reverse=True)
    top_category      = categories_ranked[0] if categories_ranked else None
    category_labels   = [c[0] for c in categories_ranked]
    category_amounts  = [round(c[1], 2) for c in categories_ranked]

    # ── Top Spending Member ───────────────────────────────────────────────────
    member_totals = defaultdict(float)
    for exp in expenses:
        if exp.paid_by:
            member_totals[exp.paid_by] += float(exp.amount)

    members_ranked = sorted(member_totals.items(), key=lambda x: x[1], reverse=True)

    # ── Smart suggestions ─────────────────────────────────────────────────────
    smart_suggestions = get_smart_suggestions(trip, expenses)

    context = {
        'trip':               trip,
        'expenses':           expenses,          # already newest-first
        'total_expenses':     total_expenses,
        'remaining_budget':   remaining_budget,
        'participants':       participants,
        'cost_per_person':    cost_per_person,
        'budget_alert':       budget_alert,
        'budget_pct':         budget_pct,
        'heatmap_data':       heatmap_data,
        'category_labels':    category_labels,
        'category_amounts':   category_amounts,
        'top_category':       top_category,
        'categories_ranked':  categories_ranked,
        'members_ranked':     members_ranked,
        'smart_suggestions':  smart_suggestions,
        'can_edit':           can_edit,
        'is_owner':           is_owner,
        # Budget Forecast and Savings Tracker have been removed.
    }
    return render(request, 'trip/trip_dashboard.html', context)


# ── OCR receipt ───────────────────────────────────────────────────────────────

@login_required
def ocr_receipt(request, trip_id):
    """POST an image → returns extracted amount, GST, merchant as JSON."""
    trip = get_object_or_404(Trip, id=trip_id)
    if not user_can_edit(trip, request.user):
        return JsonResponse({"error": "You don't have edit access to this trip."}, status=403)
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=405)

    image_file = request.FILES.get("receipt")
    if not image_file:
        return JsonResponse({"error": "No file provided"}, status=400)

    try:
        from PIL import Image
        import io

        img = Image.open(io.BytesIO(image_file.read()))
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        raw_text = pytesseract.image_to_string(img)

        # Amount
        amount = None
        for pat in [
            r'(?:total|amount|subtotal|grand\s*total|net\s*amount)[^\d]*(\d[\d,]*\.?\d*)',
            r'[₹Rs\.]+\s*(\d[\d,]*\.?\d*)',
            r'(\d[\d,]*\.\d{2})\s*(?:INR|Rs|₹)?',
        ]:
            m = re.search(pat, raw_text, re.IGNORECASE)
            if m:
                amount = m.group(1).replace(",", "")
                break

        # GST
        gst = None
        for pat in [
            r'(?:gst|cgst\s*\+\s*sgst|igst|tax)[^\d]*(\d[\d,]*\.?\d*)',
            r'(?:cgst|sgst)[^\d]*(\d[\d,]*\.?\d*)',
        ]:
            matches = re.findall(pat, raw_text, re.IGNORECASE)
            if matches:
                gst = str(round(sum(float(x.replace(",", "")) for x in matches), 2))
                break

        # Merchant
        merchant = None
        skip_words = {"invoice", "receipt", "bill", "tax", "gst", "date", "time"}
        lines = [l.strip() for l in raw_text.splitlines() if len(l.strip()) > 3]
        for line in lines[:5]:
            if not re.match(r'^[\d\s\-\/\.:,]+$', line) and line.lower() not in skip_words:
                merchant = line[:100]
                break

        return JsonResponse({
            "amount":   amount or "",
            "gst":      gst or "",
            "merchant": merchant or "",
            "raw_text": raw_text[:500],
        })

    except ImportError:
        return JsonResponse({"error": "pytesseract not installed."}, status=500)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


# ── Add expense ───────────────────────────────────────────────────────────────

@login_required
def add_expense(request, trip_id):
    trip = get_object_or_404(Trip, id=trip_id)
    if not user_can_edit(trip, request.user):
        raise PermissionDenied("You don't have edit access to this trip.")

    if request.method == "POST":
        title        = request.POST.get("title")
        amount       = request.POST.get("amount")
        paid_by      = request.POST.get("paid_by")
        category     = request.POST.get("category")
        payment_mode = request.POST.get("payment_mode")

        if not all([title, amount, paid_by, category, payment_mode]):
            return render(request, "trip/add_expense.html", {
                "trip": trip,
                "participants": trip.get_participants(),
                "error": "Please fill all required fields",
            })

        gst_str      = request.POST.get("gst_amount", "").strip()
        is_recurring = request.POST.get("is_recurring") == "on"
        recurrence   = request.POST.get("recurrence_type", "") or None

        expense = Expense.objects.create(
            trip=trip,
            title=title,
            amount=float(amount),
            paid_by=paid_by,
            category=category,
            custom_category=request.POST.get("custom_category", ""),
            payment_mode=payment_mode,
            description=request.POST.get("description", ""),
            merchant_name=request.POST.get("merchant_name", "").strip() or None,
            gst_amount=float(gst_str) if gst_str else None,
            is_recurring=is_recurring,
            recurrence_type=recurrence if is_recurring else None,
        )

        receipt = request.FILES.get("receipt")
        print("FILES:", request.FILES)
        print("receipt:", request.FILES.get("receipt"))
        receipt = request.FILES.get("receipt")
        if receipt:
            expense.receipt      = receipt
            expense.receipt_type = request.POST.get("receipt_type", "")
            expense.save()

        return redirect("trip_dashboard", trip_id=trip.id)

    return render(request, "trip/add_expense.html", {
        "trip": trip,
        "participants": trip.get_participants(),
    })


# ── View / filter expenses ────────────────────────────────────────────────────

@login_required
def view_expenses(request, trip_id):
    trip     = get_object_or_404(Trip, id=trip_id)
    if not user_can_view(trip, request.user):
        raise PermissionDenied("You don't have access to this trip.")
    expenses = Expense.objects.filter(trip=trip).order_by('-created_at')

    date_from    = request.GET.get('date_from', '')
    date_to      = request.GET.get('date_to', '')
    member       = request.GET.get('member', '')
    category     = request.GET.get('category', '')
    payment_mode = request.GET.get('payment_mode', '')
    amount_min   = request.GET.get('amount_min', '')
    amount_max   = request.GET.get('amount_max', '')
    recurring    = request.GET.get('recurring', '')
    favorites    = request.GET.get('favorites', '')
    receipt_type = request.GET.get('receipt_type', '')
    search_q     = request.GET.get('q', '').strip()

    if date_from:    expenses = expenses.filter(created_at__date__gte=date_from)
    if date_to:      expenses = expenses.filter(created_at__date__lte=date_to)
    if member:       expenses = expenses.filter(paid_by__iexact=member)
    if category:     expenses = expenses.filter(category=category)
    if payment_mode: expenses = expenses.filter(payment_mode=payment_mode)
    if amount_min:   expenses = expenses.filter(amount__gte=Decimal(amount_min))
    if amount_max:   expenses = expenses.filter(amount__lte=Decimal(amount_max))
    if recurring == 'yes':     expenses = expenses.filter(is_recurring=True)
    elif recurring == 'no':    expenses = expenses.filter(is_recurring=False)
    if favorites == 'yes':     expenses = expenses.filter(is_favorite=True)
    if receipt_type:           expenses = expenses.filter(receipt_type=receipt_type)

    if search_q:
        from django.db.models import Q
        expenses = expenses.filter(
            Q(title__icontains=search_q) |
            Q(description__icontains=search_q) |
            Q(merchant_name__icontains=search_q) |
            Q(paid_by__icontains=search_q)
        )

    all_expenses     = Expense.objects.filter(trip=trip)
    total_expenses   = sum(Decimal(e.amount) for e in all_expenses)
    filtered_total   = sum(Decimal(e.amount) for e in expenses)
    remaining_budget = trip.budget - total_expenses if trip.budget else None

    context = {
        "trip":             trip,
        "expenses":         expenses,
        "total_expenses":   total_expenses,
        "filtered_total":   filtered_total,
        "remaining_budget": remaining_budget,
        "participants":     trip.get_participants(),
        "categories":       [c[0] for c in Expense.CATEGORY_CHOICES],
        "payment_modes":    [p[0] for p in Expense.PAYMENT_CHOICES],
        "budget_alert":     get_budget_alert(trip, total_expenses),
        "smart_suggestions": get_smart_suggestions(trip, list(all_expenses)),
        "f_date_from":      date_from,
        "f_date_to":        date_to,
        "f_member":         member,
        "f_category":       category,
        "f_payment_mode":   payment_mode,
        "f_amount_min":     amount_min,
        "f_amount_max":     amount_max,
        "f_recurring":      recurring,
        "f_favorites":      favorites,
        "f_receipt_type":   receipt_type,
        "f_search_q":       search_q,
        "can_edit":         user_can_edit(trip, request.user),
        "any_filter_active": any([
            date_from, date_to, member, category, payment_mode,
            amount_min, amount_max, recurring, favorites, receipt_type, search_q,
        ]),
    }
    return render(request, "trip/view_expenses.html", context)


# ── Toggle favourite ──────────────────────────────────────────────────────────

@login_required
def toggle_favorite(request, expense_id):
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=405)
    expense = get_object_or_404(Expense, id=expense_id)
    if not user_can_edit(expense.trip, request.user):
        return JsonResponse({"error": "You don't have edit access to this trip."}, status=403)
    expense.is_favorite = not expense.is_favorite
    expense.save(update_fields=["is_favorite"])
    return JsonResponse({"is_favorite": expense.is_favorite})


# ── Edit trip ─────────────────────────────────────────────────────────────────

@login_required
def edit_trip(request, trip_id):
    trip = get_object_or_404(Trip, id=trip_id)
    if not user_can_edit(trip, request.user):
        raise PermissionDenied("You don't have edit access to this trip.")

    participants = trip.get_participants()
    while len(participants) < 15:
        participants.append("")

    if request.method == "POST":
        trip.name        = request.POST.get("trip_name")
        trip.destination = request.POST.get("destination")
        trip.start_date  = request.POST.get("start_date")
        trip.end_date    = request.POST.get("end_date")
        trip.budget      = request.POST.get("budget")
        trip.participants = json.dumps([
            request.POST.get(f"friend{i}", "") for i in range(1, 16)
        ])
        trip.save()
        return redirect("trip_history")

    return render(request, "trip/edit_trip.html", {
        "trip": trip,
        "participants": participants,
        "is_owner": is_trip_owner(trip, request.user),
    })


# ── Manage access (owner only) ────────────────────────────────────────────────

@login_required
def manage_access(request, trip_id):
    trip = get_object_or_404(Trip, id=trip_id)
    if not is_trip_owner(trip, request.user):
        raise PermissionDenied("Only the trip owner can manage access.")

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "add":
            username = (request.POST.get("username") or "").strip()
            permission = request.POST.get("permission", "view")
            if permission not in ("view", "edit"):
                permission = "view"

            if not username:
                return render(request, "trip/manage_access.html", {
                    "trip": trip,
                    "collaborators": trip.collaborators.select_related("user"),
                    "error": "Enter a username.",
                })

            from django.contrib.auth.models import User
            target = User.objects.filter(username=username).first()

            if not target:
                error = "No user with that username."
            elif target.id == request.user.id:
                error = "You already own this trip."
            else:
                error = None
                TripCollaborator.objects.update_or_create(
                    trip=trip, user=target,
                    defaults={"permission": permission},
                )

            if error:
                return render(request, "trip/manage_access.html", {
                    "trip": trip,
                    "collaborators": trip.collaborators.select_related("user"),
                    "error": error,
                })

        elif action == "remove":
            collab_id = request.POST.get("collab_id")
            TripCollaborator.objects.filter(id=collab_id, trip=trip).delete()

        return redirect("manage_access", trip_id=trip.id)

    return render(request, "trip/manage_access.html", {
        "trip": trip,
        "collaborators": trip.collaborators.select_related("user"),
    })


# ── Trip photos/videos ────────────────────────────────────────────────────────

@login_required
def trip_photos_videos(request, trip_id):
    trip = get_object_or_404(Trip, id=trip_id)
    if not user_can_view(trip, request.user):
        raise PermissionDenied("You don't have access to this trip.")
    drive_links = {
        "trip_photos":    "https://drive.google.com/drive/folders/xxx1",
        "trip_videos":    "https://drive.google.com/drive/folders/xxx2",
        "trip_expenses":  "https://drive.google.com/drive/folders/xxx3",
        "trip_documents": "https://drive.google.com/drive/folders/xxx4",
    }
    return render(request, 'trip/trip_photos_videos.html', {"trip": trip, "drive_links": drive_links})


# ── Budget alert helper ───────────────────────────────────────────────────────

def get_budget_alert(trip, total_expenses):
    if not trip.budget or trip.budget == 0:
        return None
    pct = float(total_expenses) / float(trip.budget) * 100
    if pct >= 100:
        return {"level": "danger",  "pct": round(pct, 1), "msg": "⛔ Budget Reached! You've used 100% of your budget."}
    elif pct >= 90:
        return {"level": "danger",  "pct": round(pct, 1), "msg": f"🚨 Critical! You've used {pct:.1f}% of your budget."}
    elif pct >= 80:
        return {"level": "warning", "pct": round(pct, 1), "msg": f"⚠️ Warning: {pct:.1f}% of budget used."}
    elif pct >= 70:
        return {"level": "caution", "pct": round(pct, 1), "msg": f"📊 Heads up: {pct:.1f}% of budget used."}
    return None


# ── Smart suggestions helper ──────────────────────────────────────────────────

def get_smart_suggestions(trip, expenses):
    tips = []
    if not expenses:
        return tips

    total = float(sum(Decimal(e.amount) for e in expenses))
    if total == 0:
        return tips

    cat_totals = defaultdict(float)
    for e in expenses:
        cat_totals[e.category] += float(e.amount)

    top_cat = max(cat_totals, key=cat_totals.get)
    top_pct = cat_totals[top_cat] / total * 100
    tips.append(f"💸 You spend {top_pct:.0f}% on {top_cat}. That's your biggest category.")

    person_totals = defaultdict(float)
    for e in expenses:
        person_totals[e.paid_by] += float(e.amount)

    if len(person_totals) > 1:
        top_person = max(person_totals, key=person_totals.get)
        top_person_pct = person_totals[top_person] / total * 100
        tips.append(f"👤 {top_person} paid the most — {top_person_pct:.0f}% of all expenses.")

    recurring_count = sum(1 for e in expenses if e.is_recurring)
    if recurring_count:
        recurring_total = sum(float(e.amount) for e in expenses if e.is_recurring)
        tips.append(f"🔁 You have {recurring_count} recurring expense(s) totalling ₹{recurring_total:.0f}.")

    if trip.budget and trip.budget > 0:
        daily_budget = float(trip.budget) / max((trip.end_date - trip.start_date).days, 1)
        IST = dt_timezone(timedelta(hours=5, minutes=30))
        unique_days = len(set(e.created_at.astimezone(IST).date() for e in expenses))
        daily_spend = total / max(unique_days, 1)
        if daily_spend > daily_budget:
            tips.append(f"📅 You're spending ₹{daily_spend:.0f}/day — daily budget is ₹{daily_budget:.0f}.")

    most_exp = max(expenses, key=lambda e: e.amount)
    tips.append(f"🏆 Biggest single expense: {most_exp.title} (₹{most_exp.amount}).")

    return tips


# ── Split bill ────────────────────────────────────────────────────────────────

@login_required
def split_bill(request, trip_id):
    trip = get_object_or_404(Trip, id=trip_id)
    if not user_can_edit(trip, request.user):
        raise PermissionDenied("You don't have edit access to this trip.")
    participants = trip.get_participants()
    past_splits  = SplitBill.objects.filter(trip=trip).prefetch_related("entries").order_by("-created_at")

    if request.method == "POST":
        title        = request.POST.get("title", "").strip()
        total_amount = request.POST.get("total_amount", "").strip()
        paid_by      = request.POST.get("paid_by", "").strip()
        split_type   = request.POST.get("split_type", "equal")
        people       = request.POST.getlist("people")

        if not title or not total_amount or not paid_by or not people:
            return render(request, "trip/split_bill.html", {
                "trip": trip, "participants": participants,
                "past_splits": past_splits,
                "error": "Fill in all required fields and select at least one person.",
            })

        total        = Decimal(total_amount)
        entries_data = []

        if split_type == "equal":
            per_person = round(total / len(people), 2)
            for p in people:
                entries_data.append((p, per_person, None, None))

        elif split_type == "percentage":
            for p in people:
                pct = Decimal(request.POST.get(f"pct_{p}", "0") or "0")
                entries_data.append((p, round(total * pct / 100, 2), pct, None))

        elif split_type == "exact":
            for p in people:
                amt = Decimal(request.POST.get(f"exact_{p}", "0") or "0")
                entries_data.append((p, amt, None, None))

        elif split_type == "shares":
            share_values = {p: int(request.POST.get(f"shares_{p}", "1") or "1") for p in people}
            total_shares = sum(share_values.values())
            for p in people:
                entries_data.append((p, round(total * share_values[p] / total_shares, 2), None, share_values[p]))

        split = SplitBill.objects.create(
            trip=trip, title=title, total_amount=total,
            paid_by=paid_by, split_type=split_type,
        )
        for person, amount_owed, pct, shares in entries_data:
            SplitEntry.objects.create(
                split=split, person=person,
                amount_owed=amount_owed, percentage=pct, shares=shares,
            )
        return redirect("settlement", trip_id=trip.id)

    return render(request, "trip/split_bill.html", {
        "trip": trip, "participants": participants, "past_splits": past_splits,
    })


# ── Settlement ────────────────────────────────────────────────────────────────

@login_required
def settlement(request, trip_id):
    trip = get_object_or_404(Trip, id=trip_id)
    if not user_can_view(trip, request.user):
        raise PermissionDenied("You don't have access to this trip.")
    splits = SplitBill.objects.filter(trip=trip).prefetch_related("entries")

    net = defaultdict(Decimal)
    for split in splits:
        payer = split.paid_by
        for entry in split.entries.all():
            if entry.person == payer:
                continue
            net[payer]        += entry.amount_owed
            net[entry.person] -= entry.amount_owed

    # ── Net out any payments that have already been recorded as paid ───────
    # A payment from A to B means A (debtor) settled part of what they owed B.
    payments = SettlementPayment.objects.filter(trip=trip)
    for pay in payments:
        net[pay.from_person] += pay.amount   # debtor's debt shrinks
        net[pay.to_person]   -= pay.amount   # creditor's credit shrinks

    creditors = [[v, k] for v, k in sorted([(v, k) for k, v in net.items() if v > 0], reverse=True)]
    debtors   = [[v, k] for v, k in sorted([(abs(v), k) for k, v in net.items() if v < 0], reverse=True)]

    transactions = []
    ci = di = 0
    while ci < len(creditors) and di < len(debtors):
        credit_amt, creditor = creditors[ci]
        debt_amt,   debtor   = debtors[di]
        settled = min(credit_amt, debt_amt)
        if settled > 0:
            transactions.append({"from_person": debtor, "to_person": creditor, "amount": round(settled, 2)})
        creditors[ci][0] -= settled
        debtors[di][0]   -= settled
        if creditors[ci][0] == 0: ci += 1
        if debtors[di][0]   == 0: di += 1

    return render(request, "trip/settlement.html", {
        "trip": trip, "splits": splits, "net": dict(net), "transactions": transactions,
        "payments": payments, "can_edit": user_can_edit(trip, request.user),
    })


@login_required
def mark_settlement_paid(request, trip_id):
    """Record a real payment so it persists across reloads (Splitwise-style)."""
    trip = get_object_or_404(Trip, id=trip_id)
    if not user_can_edit(trip, request.user):
        raise PermissionDenied("You don't have edit access to this trip.")
    if request.method == "POST":
        from_person = request.POST.get("from_person", "").strip()
        to_person   = request.POST.get("to_person", "").strip()
        amount      = request.POST.get("amount", "").strip()
        if from_person and to_person and amount:
            try:
                SettlementPayment.objects.create(
                    trip=trip, from_person=from_person,
                    to_person=to_person, amount=Decimal(amount),
                )
            except Exception:
                pass
    return redirect("settlement", trip_id=trip.id)


@login_required
def unmark_settlement_paid(request, trip_id, payment_id):
    """Undo a recorded payment — puts the debt back."""
    trip = get_object_or_404(Trip, id=trip_id)
    if not user_can_edit(trip, request.user):
        raise PermissionDenied("You don't have edit access to this trip.")
    payment = get_object_or_404(SettlementPayment, id=payment_id, trip=trip)
    if request.method == "POST":
        payment.delete()
    return redirect("settlement", trip_id=trip.id)


# ── Export PDF ────────────────────────────────────────────────────────────────

@login_required
def export_expenses_pdf(request, trip_id):
    from weasyprint import HTML
    from django.template.loader import render_to_string

    trip = get_object_or_404(Trip, id=trip_id)
    if not user_can_view(trip, request.user):
        raise PermissionDenied("You don't have access to this trip.")
    expenses = Expense.objects.filter(trip=trip).order_by('-created_at')

    total_expenses   = sum(Decimal(e.amount) for e in expenses)
    remaining_budget = trip.budget - total_expenses if trip.budget else None
    participants     = trip.get_participants()
    cost_per_person  = total_expenses / len(participants) if participants else None

    cat_totals = defaultdict(float)
    for e in expenses:
        cat_totals[e.category] += float(e.amount)

    html_string = render_to_string('trip/export_pdf.html', {
        'trip':             trip,
        'expenses':         expenses,
        'total_expenses':   total_expenses,
        'remaining_budget': remaining_budget,
        'participants':     participants,
        'cost_per_person':  cost_per_person,
        'cat_totals':       dict(cat_totals),
        'total':            float(total_expenses),
    })

    pdf_file = BytesIO()
    HTML(string=html_string, base_url=request.build_absolute_uri()).write_pdf(pdf_file)
    pdf_file.seek(0)

    filename = f"{trip.name.replace(' ', '_')}_expenses.pdf"
    response = HttpResponse(pdf_file, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response
## ─────────────────────────────────────────────────────────────────
## ADD THIS ENTIRE BLOCK AT THE VERY BOTTOM OF  trip/views.py
## ─────────────────────────────────────────────────────────────────

import calendar as cal_module
from django.db.models import Sum, Count, Max, Min, Avg
from django.db.models.functions import TruncDate


def _heatmap_build(trip, year, month):
    """
    Returns a plain dict with everything the analytics page needs.
    All DB work is done here with ORM aggregation — no Python loops over expenses.
    """
    IST = dt_timezone(timedelta(hours=5, minutes=30))
    all_exp = Expense.objects.filter(trip=trip)

    # ── Available years for the dropdown ───────────────────────────────────
    year_vals = list(
        all_exp.dates('created_at', 'year')
               .values_list('created_at__year', flat=True)
               .distinct()
    )
    if not year_vals:
        year_vals = [date.today().year]

    # ── Daily totals for the chosen month ──────────────────────────────────
    month_exp = all_exp.filter(created_at__year=year, created_at__month=month)

    daily_qs = (
        month_exp
        .annotate(day=TruncDate('created_at'))
        .values('day')
        .annotate(total=Sum('amount'), count=Count('id'))
        .order_by('day')
    )
    daily_map = {str(r['day']): {'total': float(r['total']), 'count': r['count']}
                 for r in daily_qs}

    # Category breakdown per day (for tooltip)
    cat_qs = (
        month_exp
        .annotate(day=TruncDate('created_at'))
        .values('day', 'category')
        .annotate(cat_total=Sum('amount'))
    )
    cat_by_day = defaultdict(dict)
    for r in cat_qs:
        cat_by_day[str(r['day'])][r['category']] = float(r['cat_total'])

    # ── Build calendar grid (Mon–Sun) ───────────────────────────────────────
    mycal    = cal_module.Calendar(firstweekday=0)
    weeks    = mycal.monthdatescalendar(year, month)
    cal_days = []
    for week in weeks:
        for d in week:
            ds   = str(d)
            data = daily_map.get(ds, {})
            cal_days.append({
                'date':       ds,
                'day_num':    d.day,
                'in_month':   d.month == month,
                'total':      data.get('total', 0.0),
                'count':      data.get('count', 0),
                'weekday':    d.strftime('%a'),
                'categories': cat_by_day.get(ds, {}),
            })

    # ── All-time stats ──────────────────────────────────────────────────────
    all_daily_qs = (
        all_exp
        .annotate(day=TruncDate('created_at'))
        .values('day')
        .annotate(total=Sum('amount'), cnt=Count('id'))
        .order_by('day')
    )
    all_daily = list(all_daily_qs)
    spend_rows = [r for r in all_daily if float(r['total']) > 0]
    totals     = [float(r['total']) for r in spend_rows]

    highest = max(spend_rows, key=lambda x: x['total'], default=None)
    lowest  = min(spend_rows, key=lambda x: x['total'], default=None)
    avg_day = round(sum(totals) / len(totals), 2) if totals else 0

    # No-spend streak
    streak = best_streak = 0
    for r in all_daily:
        if float(r['total']) == 0:
            streak += 1
            best_streak = max(best_streak, streak)
        else:
            streak = 0

    top_cat = (
        all_exp.values('category')
               .annotate(s=Sum('amount'))
               .order_by('-s')
               .first()
    )
    largest_exp = all_exp.order_by('-amount').first()
    avg_val     = float(all_exp.aggregate(a=Avg('amount'))['a'] or 0)

    # Most expensive week
    week_map = defaultdict(float)
    for r in all_daily:
        wk = r['day'].strftime('%Y-W%W')
        week_map[wk] += float(r['total'])
    top_week = max(week_map.items(), key=lambda x: x[1], default=('—', 0))

    total_spent = float(all_exp.aggregate(s=Sum('amount'))['s'] or 0)

    stats = {
        'highest_day':      {'date': str(highest['day'])  if highest else '—', 'total': float(highest['total'])  if highest else 0},
        'lowest_day':       {'date': str(lowest['day'])   if lowest  else '—', 'total': float(lowest['total'])   if lowest  else 0},
        'avg_daily':        avg_day,
        'expense_days':     len(spend_rows),
        'no_spend_days':    len(all_daily) - len(spend_rows),
        'best_streak':      best_streak,
        'top_week':         top_week[0],
        'top_week_amt':     round(top_week[1], 2),
        'top_cat':          top_cat['category']  if top_cat else '—',
        'top_cat_amt':      float(top_cat['s'])  if top_cat else 0,
        'largest_title':    largest_exp.title    if largest_exp else '—',
        'largest_amt':      float(largest_exp.amount) if largest_exp else 0,
        'avg_expense':      round(avg_val, 2),
        'total_spent':      total_spent,
    }

    # ── Smart insights ──────────────────────────────────────────────────────
    insights = []
    weekend = sum(float(r['total']) for r in all_daily if r['day'].weekday() >= 5)
    weekday = sum(float(r['total']) for r in all_daily if r['day'].weekday() <  5)
    if weekend > weekday:
        insights.append("📅 You spend more on weekends than weekdays.")
    elif weekday > weekend:
        insights.append("📅 You spend more on weekdays than weekends.")
    if top_cat:
        pct = round(float(top_cat['s']) / total_spent * 100, 1) if total_spent else 0
        insights.append(f"🏷️ {top_cat['category']} is your top category — {pct}% of total spend.")
    if highest:
        insights.append(f"🔥 Highest day: {highest['day'].strftime('%d %b')} with ₹{float(highest['total']):.0f}.")
    above = sum(1 for t in totals if t > avg_day)
    if above:
        insights.append(f"📈 You spent above your daily average on {above} day{'s' if above != 1 else ''}.")
    if best_streak >= 2:
        insights.append(f"✅ Best no-spend streak: {best_streak} consecutive days!")
    bud = float(trip.budget) if trip.budget else 0
    if bud > 0:
        rem = bud - total_spent
        if rem >= 0:
            insights.append(f"💚 ₹{rem:.0f} remaining from your ₹{bud:.0f} budget.")
        else:
            insights.append(f"⚠️ Over budget by ₹{abs(rem):.0f}.")

    # ── Expense list per day for modal (this month only) ───────────────────
    exp_by_day = defaultdict(list)
    for e in (month_exp.order_by('created_at')
                       .values('id','title','amount','category',
                               'payment_mode','paid_by','description','created_at')):
        # Convert to IST
        ist_dt = e['created_at'].astimezone(IST)
        key    = ist_dt.strftime('%Y-%m-%d')
        exp_by_day[key].append({
            'id':           e['id'],
            'title':        e['title'],
            'amount':       float(e['amount']),
            'category':     e['category'],
            'payment_mode': e['payment_mode'],
            'paid_by':      e['paid_by'],
            'description':  e['description'] or '',
            'time':         ist_dt.strftime('%I:%M %p'),
        })

    # ── Category totals for pie chart (this month) ──────────────────────────
    pie_cats = (
        month_exp.values('category')
                 .annotate(s=Sum('amount'))
                 .order_by('-s')
    )
    pie_labels  = [r['category'] for r in pie_cats]
    pie_amounts = [float(r['s']) for r in pie_cats]

    # ── Payment mode totals (all-time, for Payment Mode chart) ─────────────
    pay_qs = (
        all_exp.values('payment_mode')
               .annotate(s=Sum('amount'))
               .order_by('-s')
    )
    payment_mode_totals = {r['payment_mode']: float(r['s']) for r in pay_qs}

    # ── Member contribution totals (all-time, for Member Contribution chart) ─
    mem_qs = (
        all_exp.exclude(paid_by='')
               .values('paid_by')
               .annotate(s=Sum('amount'))
               .order_by('-s')
    )
    member_totals = {r['paid_by']: float(r['s']) for r in mem_qs}

    # ── Month navigation ────────────────────────────────────────────────────
    prev_m = month - 1 if month > 1 else 12
    prev_y = year  if month > 1 else year - 1
    next_m = month + 1 if month < 12 else 1
    next_y = year  if month < 12 else year + 1

    return {
        'cal_days':    cal_days,
        'stats':       stats,
        'insights':    insights,
        'years':       sorted(year_vals),
        'year':        year,
        'month':       month,
        'month_name':  cal_module.month_name[month],
        'prev_month':  prev_m, 'prev_year': prev_y,
        'next_month':  next_m, 'next_year': next_y,
        'exp_by_day':  dict(exp_by_day),
        'pie_labels':  pie_labels,
        'pie_amounts': pie_amounts,
        'trip_budget': float(trip.budget) if trip.budget else 0,
        'payment_mode_totals': payment_mode_totals,
        'member_totals':       member_totals,
        'member_birthdays':    trip.get_member_birthdays(),
    }


@login_required
def spending_heatmap(request, trip_id):
    """Full analytics page."""
    import json as _json
    trip  = get_object_or_404(Trip, id=trip_id)
    if not user_can_view(trip, request.user):
        raise PermissionDenied("You don't have access to this trip.")
    today = date.today()
    year  = int(request.GET.get('year',  trip.start_date.year))
    month = int(request.GET.get('month', trip.start_date.month))
    ctx   = _heatmap_build(trip, year, month)
    ctx['trip'] = trip

    # ── Upcoming Trips — this user's other trips that haven't started yet ──
    # Only shown to the trip's owner, so collaborators never see a list of
    # the owner's other (unrelated) trips.
    if trip.created_by_id == request.user.id:
        upcoming_trips_qs = (
            Trip.objects.filter(created_by=trip.created_by, start_date__gte=today)
                        .exclude(id=trip.id)
                        .order_by('start_date')[:5]
        )
    else:
        upcoming_trips_qs = Trip.objects.none()
    upcoming_trips = [
        {
            'id':          t.id,
            'name':        t.name,
            'destination': t.destination,
            'start_date':  str(t.start_date),
            'end_date':    str(t.end_date),
            'days_away':   (t.start_date - today).days,
        }
        for t in upcoming_trips_qs
    ]
    ctx['upcoming_trips'] = upcoming_trips

    # ✅ Pre-serialize all JS data to safe JSON strings (avoids the classic
    #    Django-list-renders-with-single-quotes bug that breaks JSON.parse)
    ctx['cal_days_json']        = _json.dumps(ctx['cal_days'])
    ctx['exp_by_day_json']      = _json.dumps(ctx['exp_by_day'])
    ctx['pie_labels_json']      = _json.dumps(ctx['pie_labels'])
    ctx['pie_amounts_json']     = _json.dumps(ctx['pie_amounts'])
    ctx['participants_json']    = _json.dumps(trip.get_participants())
    ctx['payment_totals_json']  = _json.dumps(ctx['payment_mode_totals'])
    ctx['member_totals_json']   = _json.dumps(ctx['member_totals'])
    ctx['member_bdays_json']    = _json.dumps(ctx['member_birthdays'])
    ctx['upcoming_trips_json']  = _json.dumps(upcoming_trips)
    return render(request, 'trip/spending_heatmap.html', ctx)
@login_required
def heatmap_ajax(request, trip_id):
    """AJAX — returns JSON for month navigation without page reload."""
    trip = get_object_or_404(Trip, id=trip_id)
    if not user_can_view(trip, request.user):
        return JsonResponse({"error": "You don't have access to this trip."}, status=403)
    today = date.today()
    year  = int(request.GET.get('year',  today.year))
    month = int(request.GET.get('month', today.month))
    data  = _heatmap_build(trip, year, month)
    return JsonResponse(data)
def loading_view(request):
    next_url    = request.GET.get('next', '/')
    redirect_ms = int(request.GET.get('ms', 800))
    return render(request, 'trip/loading.html', {
        'next_url': next_url, 'redirect_ms': redirect_ms,
    })

def offline_view(request):
    return render(request, 'offline.html')

def custom_404(request, exception=None):
    return render(request, '404.html', status=404)


def custom_403(request, exception=None):
    return render(request, '403.html', status=403)