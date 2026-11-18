from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('trip', '0012_expense_location_trip_weather'),
    ]

    operations = [
        migrations.AddField(
            model_name='trip',
            name='cover_expense',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='+', to='trip.expense',
            ),
        ),
    ]
