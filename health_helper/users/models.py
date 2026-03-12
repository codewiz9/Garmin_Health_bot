from django.db import models
from django.contrib.auth.models import User

class GarminToken(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='garmin_token')
    garmin_username = models.CharField(max_length=255, blank=True, null=True)
    token_data = models.TextField(blank=True, null=True, help_text="Serialized OAuth token data from Garmin")

    def __str__(self):
        return f"Garmin Token for {self.user.username}"
