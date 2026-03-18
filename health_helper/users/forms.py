from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from django.utils.html import escape
from django import forms


class UserRegisterForm(UserCreationForm):
    class Meta:
        model = User
        fields = ['username']

    def clean_username(self):
        username = self.cleaned_data.get('username')
        # Prevent XSS by escaping HTML characters
        # e.g., <script> becomes &lt;script&gt;
        sanitized_username = escape(username)
        return sanitized_username


class GarminSettingsForm(forms.Form):
    garmin_username = forms.CharField(max_length=255, required=True, label="Garmin Username")
    garmin_password = forms.CharField(
        widget=forms.PasswordInput,
        required=True,
        label="Garmin Password",
        help_text="Used once to connect to Garmin. We do not store your password."
    )
