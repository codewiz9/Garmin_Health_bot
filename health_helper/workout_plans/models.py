from django.conf import settings
from django.db import models


class WorkoutPlan(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="workout_plans")
    name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.name} ({self.user})"


class GarminWorkout(models.Model):
    """
    A workout definition created/stored in the user's Garmin account.
    """

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="garmin_workouts")
    garmin_workout_id = models.CharField(max_length=64)
    name = models.CharField(max_length=255, blank=True, default="")
    updated_at_garmin = models.DateTimeField(blank=True, null=True)
    payload = models.JSONField()
    imported_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "garmin_workout_id"],
                name="uniq_user_garmin_workout_id",
            )
        ]

    def __str__(self) -> str:
        return f"{self.name or self.garmin_workout_id} ({self.user})"


class WorkoutPlanDay(models.Model):
    class DayOfWeek(models.TextChoices):
        MONDAY = "mon", "Monday"
        TUESDAY = "tue", "Tuesday"
        WEDNESDAY = "wed", "Wednesday"
        THURSDAY = "thu", "Thursday"
        FRIDAY = "fri", "Friday"
        SATURDAY = "sat", "Saturday"
        SUNDAY = "sun", "Sunday"

    plan = models.ForeignKey(WorkoutPlan, on_delete=models.CASCADE, related_name="days")
    day = models.CharField(max_length=3, choices=DayOfWeek.choices)
    notes = models.CharField(max_length=255, blank=True, default="")
    workout = models.ForeignKey(GarminWorkout, on_delete=models.SET_NULL, blank=True, null=True)
    completed = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["plan", "day"], name="uniq_plan_day"),
        ]

    def __str__(self) -> str:
        return f"{self.plan} - {self.get_day_display()}"