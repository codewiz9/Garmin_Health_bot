from django.db import models
from django.contrib.auth.models import User



class WorkOutPlan(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    #days is a list of all the days in the workout plan up to 7 days
    days = models.ForeignKey(WorkOutPlanDay, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)

#uptaded every time the user makes a new weekly workout plan
class WorkOutImported(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    #This is fetched from the users garmin account. 
    garmin_workout = models.JSONField()

class WorkOutPlanDay(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    activties = models.CharField(choices=activties_choices)
    workout = models.ForeignKey(WorkOutImported, on_delete=models.CASCADE)
    day = models.CharField(max_length=10)
    completed = models.BooleanField(default=False)