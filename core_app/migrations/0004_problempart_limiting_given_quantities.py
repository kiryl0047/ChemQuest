from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('core_app', '0003_remove_problempart_unique_problem_part_label_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='problempart',
            name='limiting_given_quantities',
            field=models.JSONField(
                default=dict,
                blank=True,
                help_text=(
                    'For limiting-reagent parts only. Maps reactant formula → '
                    'given mass/mol. e.g. {"Al": 35.0, "Cl2": 45.0}'
                ),
            ),
        ),
    ]