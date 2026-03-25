from django.conf import settings
from django.db import models
from django.utils import timezone


class WorkoutPlan(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="workout_plans")
    name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    # Activation tracking:
    # - When activated, `active_started_at` is set to the activation time.
    # - When deactivated, the elapsed time since `active_started_at` is accumulated into `active_total_weeks`.
    is_active = models.BooleanField(default=False)
    active_started_at = models.DateTimeField(blank=True, null=True)
    active_total_weeks = models.FloatField(default=0)

    @property
    def weeks_active(self) -> float:
        total = float(self.active_total_weeks or 0)
        if self.is_active and self.active_started_at:
            delta = timezone.now() - self.active_started_at
            total += delta.total_seconds() / (7 * 24 * 60 * 60)
        return total

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

    class CardioActivity(models.TextChoices):
        RUNNING = "running", "Running"
        CYCLING = "cycling", "Cycling"
        SWIMMING = "swimming", "Swimming"
        WALKING = "walking", "Walking"
        ROWING = "rowing", "Rowing"
        REST = "rest", "Rest day"

    plan = models.ForeignKey(WorkoutPlan, on_delete=models.CASCADE, related_name="days")
    day = models.CharField(max_length=3, choices=DayOfWeek.choices)
    notes = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["plan", "day"], name="uniq_plan_day"),
        ]

    def __str__(self) -> str:
        return f"{self.plan} - {self.get_day_display()}"


class WorkoutPlanItem(models.Model):
    """
    A single workout entry within a specific plan day.

    Each item can be either:
    - an imported Garmin workout (`workout`), or
    - a cardio activity (`cardio_activity`).
    """

    day = models.ForeignKey(WorkoutPlanDay, on_delete=models.CASCADE, related_name="items")
    position = models.PositiveIntegerField(default=0)
    workout = models.ForeignKey(GarminWorkout, on_delete=models.SET_NULL, blank=True, null=True)
    cardio_activity = models.CharField(
        max_length=20,
        choices=WorkoutPlanDay.CardioActivity.choices,
        blank=True,
        default="",
    )
    notes = models.CharField(max_length=255, blank=True, default="")
    completed = models.BooleanField(default=False)

    class Meta:
        ordering = ["position", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["day", "position"],
                name="uniq_plan_day_item_position",
            )
        ]

    def __str__(self) -> str:
        label = self.workout.name if self.workout and self.workout.name else (self.workout.garmin_workout_id if self.workout else "")
        if not label and self.cardio_activity:
            label = self.get_cardio_activity_display()
        return f"{self.day} - {label or 'Workout'}"