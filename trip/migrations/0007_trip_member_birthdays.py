from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('trip', '0006_add_splitbill'),
    ]

    operations = [
        migrations.AddField(
            model_name='trip',
            name='member_birthdays',
            field=models.TextField(blank=True, default='{}'),
        ),
    ]
