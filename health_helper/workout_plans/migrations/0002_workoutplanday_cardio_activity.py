from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("workout_plans", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="workoutplanday",
            name="cardio_activity",
            field=models.CharField(
                blank=True,
                choices=[
                    ("running", "Running"),
                    ("cycling", "Cycling"),
                    ("swimming", "Swimming"),
                    ("walking", "Walking"),
                    ("rowing", "Rowing"),
                ],
                default="",
                max_length=20,
            ),
        ),
    ]
