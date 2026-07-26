from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('trip', '0011_tripchecklist'),
    ]

    operations = [
        # Feature 12: GPS Location on Expense
        migrations.AddField(
            model_name='expense',
            name='latitude',
            field=models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True),
        ),
        migrations.AddField(
            model_name='expense',
            name='longitude',
            field=models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True),
        ),
        migrations.AddField(
            model_name='expense',
            name='location_name',
            field=models.CharField(max_length=300, blank=True, null=True),
        ),
        # Feature 13: Weather history on Trip (stored as JSON)
        migrations.AddField(
            model_name='trip',
            name='weather_history',
            field=models.JSONField(default=list, blank=True,
                                   help_text='List of daily weather records fetched after trip completion'),
        ),
    ]
