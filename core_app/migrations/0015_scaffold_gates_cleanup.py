from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core_app', '0014_problemprogress_excess_remaining_json_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='problemprogress',
            name='exit_checkpoint_cleared',
            field=models.BooleanField(default=False),
        ),
        migrations.RemoveField(
            model_name='problemprogress',
            name='accuracy_gate_passed',
        ),
        migrations.RemoveField(
            model_name='problemprogress',
            name='retrieval_check_passed',
        ),
        migrations.RemoveField(
            model_name='userprofile',
            name='quickharvest_mastery_count',
        ),
    ]
