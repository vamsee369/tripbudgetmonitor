from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('trip', '0013_trip_cover_expense'),
    ]

    operations = [
        migrations.AddField(
            model_name='trip',
            name='cover_image',
            field=models.ImageField(blank=True, null=True, upload_to='covers/'),
        ),
        migrations.AddField(
            model_name='trip',
            name='cover_pos_x',
            field=models.FloatField(default=50.0),
        ),
        migrations.AddField(
            model_name='trip',
            name='cover_pos_y',
            field=models.FloatField(default=50.0),
        ),
        migrations.AddField(
            model_name='trip',
            name='cover_zoom',
            field=models.FloatField(default=1.0),
        ),
        migrations.CreateModel(
            name='MemoryLink',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('kind', models.CharField(choices=[('photos', 'Photos'), ('videos', 'Videos'), ('documents', 'Documents'), ('other', 'Other')], default='photos', max_length=12)),
                ('label', models.CharField(max_length=60)),
                ('url', models.URLField(max_length=500)),
                ('position', models.PositiveSmallIntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('trip', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='memory_links', to='trip.trip')),
            ],
            options={'ordering': ['position', 'id']},
        ),
    ]
