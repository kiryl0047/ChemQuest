from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core_app', '0001_initial'),
        migrations.swappable_dependency('auth.user'),
    ]

    replaces = []  # standalone second migration

    operations = [

        # ------------------------------------------------------------------
        # 1. Substance registry
        # ------------------------------------------------------------------
        migrations.CreateModel(
            name='Substance',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name='ID')),
                ('formula',      models.CharField(max_length=30, unique=True)),
                ('display_name', models.CharField(max_length=80)),
                ('molar_mass',   models.DecimalField(max_digits=10, decimal_places=4)),
            ],
        ),

        # ------------------------------------------------------------------
        # 2. Expand StoichiometryProblem
        # ------------------------------------------------------------------
        migrations.AddField(
            model_name='stoichiometryproblem',
            name='title',
            field=models.CharField(max_length=200, default=''),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='stoichiometryproblem',
            name='reactants_str',
            field=models.CharField(max_length=200, default=''),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='stoichiometryproblem',
            name='products_str',
            field=models.CharField(max_length=200, default=''),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='stoichiometryproblem',
            name='is_limiting_problem',
            field=models.BooleanField(default=False),
        ),

        # Legacy single-reactant / single-product columns are kept for now
        # (reactant_a_mass, product_mass) — they can be removed in a later migration
        # once all views exclusively use ProblemPart.

        # ------------------------------------------------------------------
        # 3. ProblemPart sub-question model
        # ------------------------------------------------------------------
        migrations.CreateModel(
            name='ProblemPart',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name='ID')),
                ('part_label',       models.CharField(max_length=5)),
                ('part_prompt',      models.TextField()),
                ('given_quantity',   models.DecimalField(max_digits=12, decimal_places=4)),
                ('given_unit',       models.CharField(max_length=10, default='g')),
                ('target_unit',      models.CharField(max_length=10, default='g')),
                ('conversion_type',  models.CharField(max_length=20, default='g_to_g',
                    choices=[
                        ('mol_to_mol', 'mol A → mol B'),
                        ('mol_to_g',   'mol A → g B'),
                        ('g_to_mol',   'g A  → mol B'),
                        ('g_to_g',     'g A  → g B'),
                    ])),
                ('correct_answer',   models.DecimalField(max_digits=14, decimal_places=4)),
                ('is_limiting_part', models.BooleanField(default=False)),
                ('order',            models.PositiveSmallIntegerField(default=0)),
                ('problem', models.ForeignKey(
                    to='core_app.StoichiometryProblem',
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='parts',
                )),
                ('given_substance', models.ForeignKey(
                    to='core_app.Substance',
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='given_parts',
                )),
                ('target_substance', models.ForeignKey(
                    to='core_app.Substance',
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='target_parts',
                )),
            ],
            options={'ordering': ['order'],},
        ),
        migrations.AddConstraint(
            model_name='problempart',
            constraint=models.UniqueConstraint(
                fields=['problem', 'part_label'],
                name='unique_problem_part_label',
            ),
        ),

        # ------------------------------------------------------------------
        # 4. Extend StudentTelemetryLog with part_label
        # ------------------------------------------------------------------
        migrations.AddField(
            model_name='studenttelemetrylog',
            name='part_label',
            field=models.CharField(max_length=5, default='a'),
        ),
    ]