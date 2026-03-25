from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("workout_plans", "0002_workoutplanday_cardio_activity"),
    ]

    operations = [
        migrations.AddField(
            model_name="workoutplan",
            name="is_active",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="workoutplan",
            name="active_started_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="workoutplan",
            name="active_total_weeks",
            field=models.FloatField(default=0),
        ),
    ]

