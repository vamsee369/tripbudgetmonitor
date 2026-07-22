from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('trip', '0010_tripcollaborator'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='TripChecklist',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('manual_items', models.JSONField(blank=True, default=dict)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('trip', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='checklists', to='trip.trip')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='checklists', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'unique_together': {('trip', 'user')},
            },
        ),
    ]
