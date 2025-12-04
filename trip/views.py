from decimal import Decimal
import json
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from .models import Trip, Expense

# Home page


def home(request):
    return render(request, 'trip/home.html')

# Login view


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
            error = "Invalid username or password"
            return render(request, "accounts/login.html", {"error": error})
    return render(request, "accounts/login.html")

# Trip creation


@login_required
def make_trip(request):
    if request.method == "POST":
        trip_name = request.POST.get("trip_name")
        destination = request.POST.get("destination")
        start_date = request.POST.get("start_date")
        end_date = request.POST.get("end_date")
        budget = request.POST.get("budget") or 0

        participants = []
        for i in range(1, 16):
            name = request.POST.get(f"friend{i}")
            if name:
                participants.append(name.strip())

        Trip.objects.create(
            name=trip_name,
            destination=destination,
            start_date=start_date,
            end_date=end_date,
            participants=json.dumps(participants),
            budget=budget,
            created_by=request.user
        )

        return redirect("trip_history")

    return render(request, "trip/make_trip.html", {
        "participant_range": range(1, 16)
    })

# Trip history (all trips)


def trip_history(request):
    trips = Trip.objects.all().order_by('-created_at')
    return render(request, "trip/trip_history.html", {"trips": trips})

# Completed trips list


def trip_list(request):
    today = timezone.now().date()
    completed_trips = Trip.objects.filter(end_date__lt=today)
    return render(request, 'trip/trip_list.html', {'trips': completed_trips})

# Trip dashboard


def trip_dashboard(request, trip_id):
    trip = get_object_or_404(Trip, id=trip_id)
    expenses = Expense.objects.filter(trip=trip)

    total_expenses = sum(Decimal(exp.amount) for exp in expenses)
    remaining_budget = trip.budget - total_expenses if trip.budget else None

    try:
        participants = trip.get_participants()
    except:
        participants = []

    cost_per_person = total_expenses / \
        len(participants) if participants else None

    context = {
        'trip': trip,
        'expenses': expenses,
        'total_expenses': total_expenses,
        'remaining_budget': remaining_budget,
        'participants': participants,
        'cost_per_person': cost_per_person,
    }
    return render(request, 'trip/trip_dashboard.html', context)

# Add expense


@login_required
def add_expense(request, trip_id):
    trip = get_object_or_404(Trip, id=trip_id)

    if request.method == "POST":
        title = request.POST.get("title")
        amount = request.POST.get("amount")
        paid_by = request.POST.get("paid_by")
        category = request.POST.get("category")
        custom_category = request.POST.get("custom_category")
        payment_mode = request.POST.get("payment_mode")
        description = request.POST.get("description")

        if not title or not amount or not paid_by or not category or not payment_mode:
            error = "Please fill all required fields"
            return render(request, "trip/add_expense.html", {
                "trip": trip,
                "participants": trip.get_participants(),
                "error": error
            })

        Expense.objects.create(
            trip=trip,
            title=title,
            amount=float(amount),
            paid_by=paid_by,
            category=category,
            custom_category=custom_category,
            payment_mode=payment_mode,
            description=description
        )
        return redirect("trip_history")

    return render(request, "trip/add_expense.html", {"trip": trip, "participants": trip.get_participants()})

# View expenses


def view_expenses(request, trip_id):
    trip = get_object_or_404(Trip, id=trip_id)
    expenses = Expense.objects.filter(trip=trip)

    total_expenses = sum(Decimal(exp.amount) for exp in expenses)
    remaining_budget = trip.budget - total_expenses if trip.budget else None

    context = {
        "trip": trip,
        "expenses": expenses,
        "total_expenses": total_expenses,
        "remaining_budget": remaining_budget,
    }
    return render(request, "trip/view_expenses.html", context)

# Edit trip


@login_required
def edit_trip(request, trip_id):
    trip = get_object_or_404(Trip, id=trip_id)

    participants = trip.get_participants()
    while len(participants) < 15:
        participants.append("")

    if request.method == "POST":
        trip.name = request.POST.get("trip_name")
        trip.destination = request.POST.get("destination")
        trip.start_date = request.POST.get("start_date")
        trip.end_date = request.POST.get("end_date")
        trip.budget = request.POST.get("budget")

        participant_list = []
        for i in range(1, 16):
            name = request.POST.get(f"friend{i}", "")
            participant_list.append(name)
        trip.participants = json.dumps(participant_list)

        trip.save()
        return redirect("trip_history")

    return render(request, "trip/edit_trip.html", {"trip": trip, "participants": participants})


def trip_photos_videos(request, trip_id):
    trip = get_object_or_404(Trip, id=trip_id)

    drive_links = {
        "trip_photos": "https://drive.google.com/drive/folders/xxx1",
        "trip_videos": "https://drive.google.com/drive/folders/xxx2",
        "trip_expenses": "https://drive.google.com/drive/folders/xxx3",
        "trip_documents": "https://drive.google.com/drive/folders/xxx4",
    }

    return render(request, 'trip/trip_photos_videos.html', {"trip": trip, "drive_links": drive_links})
