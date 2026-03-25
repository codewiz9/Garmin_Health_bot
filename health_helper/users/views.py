from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from datetime import timedelta, date
from .forms import UserRegisterForm, GarminSettingsForm
from garmin_bot.garmin_api import link_garmin_account
from garmin_bot.garmin_api import fetch_and_update_garmin_data
from workout_plans.services import import_garmin_workouts_for_user_since

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
        if request.POST.get("full_sync") == "1":
            if not hasattr(request.user, "garmin_token") or not request.user.garmin_token.token_data:
                messages.error(request, "Link your Garmin account first before running a full sync.")
                return redirect("garmin_settings")

            try:
                # 6-month full sync: includes garmin_bot stats + imported activities, plus Garmin workout definitions.
                ok = fetch_and_update_garmin_data(
                    request.user,
                    overall_days=180,
                    lifting_details_limit=300,
                )
                if not ok:
                    raise RuntimeError("Garmin account not available or sync failed.")
                import_garmin_workouts_for_user_since(request.user, since_date=date.today() - timedelta(days=180))
                messages.success(request, "Full sync started/completed. Check your Garmin dashboard for updates.")
            except Exception as e:
                messages.error(request, f"Full sync failed: {e}")

            return redirect("garmin_settings")

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
