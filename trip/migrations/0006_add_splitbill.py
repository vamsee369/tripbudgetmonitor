# trip/migrations/0006_add_splitbill.py
# Run: python manage.py makemigrations   OR  copy this file manually

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('trip', '0005_expense_is_favorite'),
    ]

    operations = [
        migrations.CreateModel(
            name='SplitBill',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=200)),
                ('total_amount', models.DecimalField(decimal_places=2, max_digits=10)),
                ('paid_by', models.CharField(max_length=100)),
                ('split_type', models.CharField(
                    choices=[
                        ('equal', 'Equal Split'),
                        ('percentage', 'Percentage'),
                        ('exact', 'Exact Amount'),
                        ('shares', 'Shares'),
                    ],
                    default='equal', max_length=12
                )),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('expense', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='splits', to='trip.expense'
                )),
                ('trip', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='splits', to='trip.trip'
                )),
            ],
        ),
        migrations.CreateModel(
            name='SplitEntry',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('person', models.CharField(max_length=100)),
                ('percentage', models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
                ('shares', models.PositiveIntegerField(blank=True, null=True)),
                ('amount_owed', models.DecimalField(decimal_places=2, max_digits=10)),
                ('split', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='entries', to='trip.splitbill'
                )),
            ],
        ),
    ]
