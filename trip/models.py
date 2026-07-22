import json
from django.db import models
from django.contrib.auth.models import User
from decimal import Decimal


class Trip(models.Model):
    name = models.CharField(max_length=200)
    destination = models.CharField(max_length=200)
    start_date = models.DateField()
    end_date = models.DateField()
    participants = models.TextField(default="[]")  # store as JSON string
    budget = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)  # ✅ Trip timestamp

    # ✅ NEW — Member birthdays, stored as {"Name": "MM-DD"} JSON
    member_birthdays = models.TextField(default="{}", blank=True)

    def get_participants(self):
        """Return participants as a clean list (no empty strings)."""
        try:
            participants = json.loads(self.participants)
            return [p.strip() for p in participants if p.strip()]
        except Exception:
            return []

    def get_member_birthdays(self):
        """Return {"Name": "MM-DD"} dict, ignoring any bad/missing entries."""
        try:
            data = json.loads(self.member_birthdays or "{}")
            return {k: v for k, v in data.items() if k and v}
        except Exception:
            return {}

    @property
    def status(self):
        """Check if trip is ongoing or completed."""
        from datetime import date
        return "Ongoing" if self.end_date >= date.today() else "Completed"

    def __str__(self):
        return f"{self.name} - {self.destination}"


class Expense(models.Model):
    trip = models.ForeignKey(
        Trip, on_delete=models.CASCADE, related_name="expenses"
    )
    title = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    paid_by = models.CharField(max_length=100)

    CATEGORY_CHOICES = [
        ("Accommodation", "Accommodation"),
        ("Transport", "Transport"),
        ("Food & Dining", "Food & Dining"),
        ("Drinks", "Drinks"),
        ("Activities & Entertainment", "Activities & Entertainment"),
        ("Shopping & Souvenirs", "Shopping & Souvenirs"),
        ("Emergency / Medical", "Emergency / Medical"),
        ("Tips & Service Charges", "Tips & Service Charges"),
        ("Other", "Other"),
    ]
    category = models.CharField(
        max_length=50, choices=CATEGORY_CHOICES, default="Other"
    )
    custom_category = models.CharField(max_length=100, blank=True)

    PAYMENT_CHOICES = [
        ("UPI", "UPI"),
        ("Cash", "Cash"),
        ("Card", "Card"),
    ]
    payment_mode = models.CharField(
        max_length=20, choices=PAYMENT_CHOICES, default="Cash"
    )
    description = models.TextField(blank=True)

    # From Part 1 — Receipt upload
    RECEIPT_TYPE_CHOICES = [
        ("bill", "Bill"),
        ("receipt", "Receipt"),
        ("photo", "Photo"),
    ]
    receipt = models.ImageField(upload_to="receipts/", blank=True, null=True)
    receipt_type = models.CharField(
        max_length=10, choices=RECEIPT_TYPE_CHOICES, blank=True, null=True
    )

    # ✅ NEW — OCR Extracted Fields
    merchant_name = models.CharField(max_length=200, blank=True, null=True)
    gst_amount = models.DecimalField(
        max_digits=10, decimal_places=2, blank=True, null=True
    )

    # ✅ NEW — Recurring Expense
    is_recurring = models.BooleanField(default=False)
    RECURRENCE_CHOICES = [
        ("daily", "Daily"),
        ("weekly", "Weekly"),
        ("monthly", "Monthly"),
    ]
    recurrence_type = models.CharField(
        max_length=10, choices=RECURRENCE_CHOICES, blank=True, null=True
    )
    is_favorite = models.BooleanField(default=False)
    # ✅ Timestamp — auto-set at creation, never changes
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)       # updates every save
    

    def __str__(self):
        return f"{self.title} - ₹{self.amount}"
# ─────────────────────────────────────────────────────────────────────────────
# ADD THIS BLOCK AT THE BOTTOM OF  trip/models.py
# ─────────────────────────────────────────────────────────────────────────────

class SplitBill(models.Model):
    """Represents one bill that needs to be split among participants."""
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name="splits")
    expense = models.ForeignKey(
        Expense, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="splits",
        help_text="Link to an existing expense (optional)"
    )
    title       = models.CharField(max_length=200)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    paid_by     = models.CharField(max_length=100)

    SPLIT_TYPE_CHOICES = [
        ("equal",      "Equal Split"),
        ("percentage", "Percentage"),
        ("exact",      "Exact Amount"),
        ("shares",     "Shares"),
    ]
    split_type = models.CharField(max_length=12, choices=SPLIT_TYPE_CHOICES, default="equal")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title} – ₹{self.total_amount} ({self.split_type})"

    @property
    def total_owed_back(self):
        """Sum of what everyone owes the payer (everyone except the payer)."""
        return sum(
            e.amount_owed
            for e in self.entries.all()
            if e.person != self.paid_by
        )


class SplitEntry(models.Model):
    """One person's share inside a SplitBill."""
    split  = models.ForeignKey(SplitBill, on_delete=models.CASCADE, related_name="entries")
    person = models.CharField(max_length=100)

    # For percentage split → store the percentage (e.g. 33.33)
    percentage  = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    # For shares split → store the number of shares (e.g. 2)
    shares      = models.PositiveIntegerField(null=True, blank=True)
    # Always stored: the final ₹ amount this person owes
    amount_owed = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.person}: ₹{self.amount_owed}"


class SettlementPayment(models.Model):
    """
    A recorded real-world payment between two people for a trip.
    Used to net out 'Who Owes Whom' so Mark Paid actually persists.
    """
    trip        = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name="settlement_payments")
    from_person = models.CharField(max_length=100)   # who paid (the debtor)
    to_person   = models.CharField(max_length=100)   # who received (the creditor)
    amount      = models.DecimalField(max_digits=10, decimal_places=2)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.from_person} → {self.to_person}: ₹{self.amount}"


class TripCollaborator(models.Model):
    """
    Grants a specific user access to a trip they don't own.
    'view'  -> can see the trip, expenses, dashboards, exports (read-only).
    'edit'  -> can also add/edit expenses, splits, settlements, and trip details.
    The trip owner (Trip.created_by) always has full access and never needs a row here.
    """
    PERMISSION_CHOICES = [
        ("view", "View only"),
        ("edit", "Can edit"),
    ]
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name="collaborators")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="shared_trips")
    permission = models.CharField(max_length=10, choices=PERMISSION_CHOICES, default="view")
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("trip", "user")

    def __str__(self):
        return f"{self.user.username} → {self.trip.name} ({self.permission})"


class TripChecklist(models.Model):
    """
    Stores the checklist state for a specific user on a specific trip.
    - manual_items: JSON dict of {key: bool} for user-toggled checklist items.
    - Auto-checked items (budget set, participants added, etc.) are computed
      dynamically in views and never stored here.
    One row per (trip, user) pair — enforced by unique_together.
    """
    trip = models.ForeignKey(
        Trip, on_delete=models.CASCADE, related_name="checklists"
    )
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="checklists"
    )
    # {"id_docs": true, "hotel_booked": false, ...}
    manual_items = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("trip", "user")

    def __str__(self):
        return f"Checklist — {self.user.username} / {self.trip.name}"