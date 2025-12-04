from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('make-trip/', views.make_trip, name='make_trip'),
    path('trip-history/', views.trip_history, name='trip_history'),
    path('trip-list/', views.trip_list, name='trip_list'),
    path('login/', views.login_view, name='login'),
    path('trip/<int:trip_id>/view-expenses/',
         views.view_expenses, name='view_expenses'),
    path('trip/<int:trip_id>/add-expense/',
         views.add_expense, name='add_expense'),
    path('trip/<int:trip_id>/edit/', views.edit_trip, name='edit_trip'),
    path('trip/<int:trip_id>/dashboard/',
         views.trip_dashboard, name='trip_dashboard'),
    # urls.py
    path('trip/<int:trip_id>/photos/',
         views.trip_photos_videos, name='trip_photos_videos'),


]
