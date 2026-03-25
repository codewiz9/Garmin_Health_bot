from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

METERS_PER_MILE = 1609.344


def _meters_to_miles(meters: float | int) -> float:
    # Keep conversion logic centralized so templates can stay simple.
    return float(meters or 0) / METERS_PER_MILE


class GarminUserData(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    date_recorded = models.DateField(default=timezone.now)
    # These fields clarify what the snapshot represents.
    # Example: if `aggregation_days=30`, then running/cycling/swimming/lifting stats are totals from
    # `range_start_date..range_end_date` and `date_recorded` is the sync/snapshot date.
    aggregation_days = models.IntegerField(default=30)
    range_start_date = models.DateField(null=True, blank=True)
    range_end_date = models.DateField(null=True, blank=True)
    VO2_max = models.IntegerField()
    heart_rate = models.IntegerField()
    active_minutes = models.IntegerField()
    activty_type = models.CharField(max_length=255)
    activty_amount = models.IntegerField()
    #The following are gotten from the classes below
    running = models.ForeignKey('RunningStats', on_delete=models.CASCADE)
    cycling = models.ForeignKey('CyclingStats', on_delete=models.CASCADE)
    swimming = models.ForeignKey('SwimmingStats', on_delete=models.CASCADE)
    lifting = models.ForeignKey('LiftingStats', on_delete=models.CASCADE)
    
    def __str__(self):
        return f"{self.user.username}'s Garmin Profile on {self.date_recorded}" 


class RunningStats(models.Model ):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    date_recorded = models.DateField(default=timezone.now)
    distance = models.IntegerField()
    avg_heart_rate = models.IntegerField()
    low_heart_rate = models.IntegerField()
    high_heart_rate = models.IntegerField()
    time = models.IntegerField()

    @property
    def distance_miles(self) -> float:
        return _meters_to_miles(self.distance)
    
class SwimmingStats(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    date_recorded = models.DateField(default=timezone.now)
    distance = models.IntegerField()
    avg_heart_rate = models.IntegerField()
    low_heart_rate = models.IntegerField()
    high_heart_rate = models.IntegerField()
    time = models.IntegerField()

    @property
    def distance_miles(self) -> float:
        return _meters_to_miles(self.distance)
    
class CyclingStats(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    date_recorded = models.DateField(default=timezone.now)
    distance = models.IntegerField()
    avg_heart_rate = models.IntegerField()
    low_heart_rate = models.IntegerField()
    high_heart_rate = models.IntegerField()
    time = models.IntegerField()

    @property
    def distance_miles(self) -> float:
        return _meters_to_miles(self.distance)
    
class LiftingStats(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    date_recorded = models.DateField(default=timezone.now)
    weight = models.IntegerField()
    reps = models.IntegerField()
    sets = models.IntegerField()
    volume = models.IntegerField()
    time = models.IntegerField()


class GarminActivity(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="garmin_activities")
    activity_id = models.CharField(max_length=64)
    activity_name = models.CharField(max_length=255, blank=True, default="")
    activity_type = models.CharField(max_length=100, blank=True, default="")
    start_time_local = models.DateTimeField(blank=True, null=True)
    distance_meters = models.FloatField(default=0)
    duration_seconds = models.FloatField(default=0)
    calories = models.FloatField(default=0)
    payload = models.JSONField()
    imported_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "activity_id"], name="uniq_user_activity_id")
        ]
        ordering = ["-start_time_local", "-id"]

    @property
    def distance_miles(self) -> float:
        return _meters_to_miles(self.distance_meters)

    @property
    def effective_start_time(self):
        """
        Some imported activities may be missing `start_time_local` (e.g. older imports).
        Fall back to `imported_at` so dashboards/analysis can still work with time windows.
        """
        return self.start_time_local or self.imported_at

    @property
    def duration_minutes(self) -> float:
        return float(self.duration_seconds or 0) / 60.0

    def __str__(self):
        return f"{self.user.username} - {self.activity_name or self.activity_id}"