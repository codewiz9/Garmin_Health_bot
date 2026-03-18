from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from .forms import UserRegisterForm, GarminSettingsForm
from garmin_bot.garmin_api import link_garmin_account

def register(request):
    if request.method == 'POST':
        form = UserRegisterForm(request.POST)
        if form.is_valid():
            form.save()
            username = form.cleaned_data.get('username')
            messages.success(request, f'Account created for {username}! You can now log in.')
            return redirect('login')
    else:
        form = UserRegisterForm()
    return render(request, 'users/register.html', {'form': form})

def home(request):
    return render(request, 'home.html')


@login_required
def garmin_settings(request):
    if request.method == 'POST':
        form = GarminSettingsForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['garmin_username']
            password = form.cleaned_data['garmin_password']

            # Use the password only to create/update the token; do not store it.
            success = link_garmin_account(request.user, username, password)
            if success:
                messages.success(request, "Your Garmin account has been linked successfully.")
            else:
                messages.error(request, "Failed to link your Garmin account. Please check your credentials and try again.")
            return redirect('garmin_settings')
    else:
        # Pre-fill username if we already have a GarminToken
        initial = {}
        if hasattr(request.user, 'garmin_token') and request.user.garmin_token.garmin_username:
            initial['garmin_username'] = request.user.garmin_token.garmin_username
        form = GarminSettingsForm(initial=initial)

    return render(request, 'users/garmin_settings.html', {'form': form})
