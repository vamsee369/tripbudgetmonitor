from django.urls import path
from . import views
from accounts import views as accounts_views

urlpatterns = [
    path('', views.home, name='home'),
    path('make-trip/', views.make_trip, name='make_trip'),
    path('trip-history/', views.trip_history, name='trip_history'),
    path('trip-list/', views.trip_list, name='trip_list'),
    # Delegates to the single authoritative login in accounts/views.py
    path('login/', accounts_views.login_view, name='login'),
    path('trip/<int:trip_id>/view-expenses/', views.view_expenses, name='view_expenses'),
    path('trip/<int:trip_id>/add-expense/', views.add_expense, name='add_expense'),
    path('trip/<int:trip_id>/edit/', views.edit_trip, name='edit_trip'),
    path('trip/<int:trip_id>/access/', views.manage_access, name='manage_access'),
    path('trip/<int:trip_id>/dashboard/', views.trip_dashboard, name='trip_dashboard'),
    path('trip/<int:trip_id>/photos/', views.trip_photos_videos, name='trip_photos_videos'),

    # ✅ NEW — OCR endpoint
    path('trip/<int:trip_id>/ocr-receipt/', views.ocr_receipt, name='ocr_receipt'),
    path('expense/<int:expense_id>/toggle-favorite/', views.toggle_favorite, name='toggle_favorite'),
    path('trip/<int:trip_id>/split-bill/', views.split_bill, name='split_bill'),
    path('trip/<int:trip_id>/settlement/', views.settlement, name='settlement'),
    path('trip/<int:trip_id>/settlement/mark-paid/', views.mark_settlement_paid, name='mark_settlement_paid'),
    path('trip/<int:trip_id>/settlement/unmark-paid/<int:payment_id>/', views.unmark_settlement_paid, name='unmark_settlement_paid'),
    path('trip/<int:trip_id>/export-pdf/', views.export_expenses_pdf, name='export_expenses_pdf'),
    # ✅ NEW — Spending Heatmap Analytics
    path('trip/<int:trip_id>/analytics/', views.spending_heatmap, name='spending_heatmap'),
    path('trip/<int:trip_id>/heatmap-ajax/', views.heatmap_ajax, name='heatmap_ajax'),
    path('trip/<int:trip_id>/activity/', views.activity_feed, name='activity_feed'),
    path('loading/', views.loading_view, name='loading'),
    path('offline/', views.offline_view, name='offline'),
    path('trip/<int:trip_id>/checklist/', views.trip_checklist, name='trip_checklist'),
]