from django.test import TestCase, Client
from django.urls import reverse
from .forms import UserRegisterForm
from django.utils.html import escape

class UserRegistrationTest(TestCase):
    def test_xss_sanitization_in_username(self):
        # Username with XSS payload
        malicious_username = '<script>alert("xss")</script>'
        form_data = {
            'username': malicious_username,
            'password': 'testpassword123',
            'password_confirmation': 'testpassword123',
        }
        form = UserRegisterForm(data=form_data)
        
        # Form should be invalid due to Django's strict username validators 
        # (only letters, digits and @/./+/-/_ are allowed)
        self.assertFalse(form.is_valid())
        
        # Verify the username validation error exists
        self.assertIn('username', form.errors)
        
        # If we try to clean it directly, it should escape it so no raw HTML is returned
        form.cleaned_data = {'username': malicious_username}
        sanitized = form.clean_username()
        self.assertNotIn('<script>', sanitized)
        self.assertIn('&lt;script&gt;', sanitized)

