from django.contrib import admin

# Register your models here.
from .models import Trip, Expense
# admin.site.register(Trip)
# admin.site.register(Expense)


@admin.register(Trip)
class TripAdmin(admin.ModelAdmin):
    list_display = ('name', 'destination', 'start_date',
                    'end_date', 'budget', 'created_by', 'created_at')
    search_fields = ('name', 'destination', 'created_by__username')
    list_filter = ('start_date', 'end_date')


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ('title', 'trip', 'amount', 'paid_by',
                    'category', 'payment_mode', 'created_at')
    search_fields = ('title', 'trip__name', 'paid_by')
    list_filter = ('category', 'payment_mode')
