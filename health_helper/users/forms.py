from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from django.utils.html import escape

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
