from django.db import migrations

# The four Drive folders that used to be hard-coded in trip_photos_videos.html
# now live in the database — attached to trip id 7.
TRIP_ID = 7
LINKS = [
    ("photos", "Photos",   "https://drive.google.com/drive/folders/14TN1Jq7CnjWV3nkuPruJ5qepv39GPPN6"),
    ("videos", "Videos",   "https://drive.google.com/drive/folders/1tRA3jPeILBkyApxlvd-CbPjAPD3nuE-5"),
    ("photos", "Photos 2", "https://drive.google.com/drive/folders/1-9r4IZ6KThLYTQmR2QrKITElj-rCXx8p"),
    ("videos", "Videos 2", "https://drive.google.com/drive/folders/1-AfBxUbCgD0fhSuzFVHBbz1gNZffYXEU"),
]


def seed(apps, schema_editor):
    Trip = apps.get_model("trip", "Trip")
    MemoryLink = apps.get_model("trip", "MemoryLink")
    trip = Trip.objects.filter(id=TRIP_ID).first()
    if not trip or MemoryLink.objects.filter(trip=trip).exists():
        return  # trip 7 not in this database, or already has links: do nothing
    for i, (kind, label, url) in enumerate(LINKS):
        MemoryLink.objects.create(trip=trip, kind=kind, label=label, url=url, position=i)


class Migration(migrations.Migration):

    dependencies = [
        ('trip', '0014_trip_cover_image_memorylink'),
    ]

    operations = [
        migrations.RunPython(seed, migrations.RunPython.noop),
    ]
