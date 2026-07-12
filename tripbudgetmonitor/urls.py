"""
URL configuration for tripbudgetmonitor project.
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.http import FileResponse
import os


def serve_sw(request):
    sw_path = os.path.join(settings.BASE_DIR, 'static', 'service-worker.js')
    return FileResponse(open(sw_path, 'rb'), content_type='application/javascript')


urlpatterns = [
    path("vamsee/", admin.site.urls),
    path("", include("trip.urls")),
    path("accounts/", include("accounts.urls")),
    path("service-worker.js", serve_sw),
]

# NOTE: No media() route needed — files are served directly from Cloudinary CDN.

handler404 = 'trip.views.custom_404'
handler403 = 'trip.views.custom_403'