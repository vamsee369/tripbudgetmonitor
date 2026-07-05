from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('trip', '0007_trip_member_birthdays'),
    ]

    operations = [
        migrations.CreateModel(
            name='SettlementPayment',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('from_person', models.CharField(max_length=100)),
                ('to_person', models.CharField(max_length=100)),
                ('amount', models.DecimalField(decimal_places=2, max_digits=10)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('trip', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='settlement_payments', to='trip.trip')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
