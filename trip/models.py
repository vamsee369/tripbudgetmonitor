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

    def get_participants(self):
        """Return participants as a clean list (no empty strings)."""
        try:
            participants = json.loads(self.participants)
            return [p.strip() for p in participants if p.strip()]
        except Exception:
            return []

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
    amount = models.DecimalField(
        max_digits=10, decimal_places=2)  # ✅ use Decimal
    paid_by = models.CharField(max_length=100)  # Must be one of participants

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
    custom_category = models.CharField(
        max_length=100, blank=True
    )  # optional if Other

    PAYMENT_CHOICES = [
        ("UPI", "UPI"),
        ("Cash", "Cash"),
        ("Card", "Card"),
    ]
    payment_mode = models.CharField(
        max_length=20, choices=PAYMENT_CHOICES, default="Cash"
    )
    description = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)  # ✅ Expense timestamp

    def __str__(self):
        return f"{self.title} - {self.amount}"
