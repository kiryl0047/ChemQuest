from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core_app', '0010_userprofile_quickharvest_mastery_count_and_more'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='partprogress',
            name='worked_example_shown',
        ),
    ]
