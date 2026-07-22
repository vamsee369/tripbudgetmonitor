from django.contrib import admin
from django.utils.html import format_html
from .models import Trip, Expense, SplitBill, SplitEntry, SettlementPayment, TripCollaborator, TripChecklist


@admin.register(Trip)
class TripAdmin(admin.ModelAdmin):
    list_display = ('name', 'destination', 'start_date', 'end_date', 'budget', 'created_by')
    search_fields = ('name', 'destination')


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = (
        'title', 'amount', 'gst_amount', 'merchant_name',
        'category', 'payment_mode', 'paid_by',
        'receipt_type', 'is_recurring', 'recurrence_type',
        'receipt_preview', 'trip', 'created_at',
    )
    list_filter = ('category', 'payment_mode', 'receipt_type', 'is_recurring', 'recurrence_type')
    search_fields = ('title', 'paid_by', 'merchant_name')
    readonly_fields = ('receipt_preview', 'created_at')

    def receipt_preview(self, obj):
        if obj.receipt:
            return format_html(
                '<a href="{}" target="_blank">'
                '<img src="{}" style="height:60px;border-radius:6px;border:1px solid #eee;" />'
                '</a>',
                obj.receipt.url, obj.receipt.url
            )
        return "—"
    receipt_preview.short_description = "Receipt"


class SplitEntryInline(admin.TabularInline):
    model = SplitEntry
    extra = 0


@admin.register(SplitBill)
class SplitBillAdmin(admin.ModelAdmin):
    list_display = ('title', 'trip', 'total_amount', 'paid_by', 'split_type', 'created_at')
    list_filter = ('split_type', 'trip')
    search_fields = ('title', 'paid_by')
    inlines = [SplitEntryInline]


@admin.register(SettlementPayment)
class SettlementPaymentAdmin(admin.ModelAdmin):
    list_display = ('trip', 'from_person', 'to_person', 'amount', 'created_at')
    list_filter = ('trip',)
    search_fields = ('from_person', 'to_person')


@admin.register(TripCollaborator)
class TripCollaboratorAdmin(admin.ModelAdmin):
    list_display = ('trip', 'user', 'permission', 'added_at')
    list_filter = ('permission',)
    search_fields = ('trip__name', 'user__username')


@admin.register(TripChecklist)
class TripChecklistAdmin(admin.ModelAdmin):
    list_display = ('trip', 'user', 'manual_items_summary', 'updated_at')
    list_filter = ('trip',)
    search_fields = ('trip__name', 'user__username')
    readonly_fields = ('updated_at',)

    def manual_items_summary(self, obj):
        if not obj.manual_items:
            return "—"
        done = sum(1 for v in obj.manual_items.values() if v)
        total = len(obj.manual_items)
        return f"{done}/{total} done"
    manual_items_summary.short_description = "Progress"