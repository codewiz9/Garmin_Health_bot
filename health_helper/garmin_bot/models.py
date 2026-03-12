from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

class GarminUserData(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    date_recorded = models.DateField(default=timezone.now)
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
    
class SwimmingStats(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    date_recorded = models.DateField(default=timezone.now)
    distance = models.IntegerField()
    avg_heart_rate = models.IntegerField()
    low_heart_rate = models.IntegerField()
    high_heart_rate = models.IntegerField()
    time = models.IntegerField()
    
class CyclingStats(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    date_recorded = models.DateField(default=timezone.now)
    distance = models.IntegerField()
    avg_heart_rate = models.IntegerField()
    low_heart_rate = models.IntegerField()
    high_heart_rate = models.IntegerField()
    time = models.IntegerField()
    
class LiftingStats(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    date_recorded = models.DateField(default=timezone.now)
    weight = models.IntegerField()
    reps = models.IntegerField()
    sets = models.IntegerField()
    volume = models.IntegerField()
    time = models.IntegerField()