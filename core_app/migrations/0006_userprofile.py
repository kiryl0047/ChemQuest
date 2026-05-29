from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('core_app', '0002_substance_problempart'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='UserProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name='ID')),
                ('total_xp', models.IntegerField(default=0)),
                ('user', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='profile',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
        ),
        # Widen part_label from max_length=5 to 10 to support 'lane_A', 'lane_B'
        migrations.AlterField(
            model_name='problempart',
            name='part_label',
            field=models.CharField(max_length=10),
        ),
        migrations.AlterField(
            model_name='studenttelemetrylog',
            name='part_label',
            field=models.CharField(default='a', max_length=10),
        ),
    ]