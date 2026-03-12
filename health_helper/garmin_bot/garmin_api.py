import os
from pathlib import Path
from datetime import date
from garminconnect import Garmin
from garth.exc import GarthHTTPError
from .models import GarminUserData, RunningStats, CyclingStats, SwimmingStats, LiftingStats, GarminToken

def link_garmin_account(user, username, plaintext_password):
    try:
        garmin = Garmin(username, plaintext_password)
        garmin.login()
        token_data_str = garmin.garth.dumps()
        GarminToken.objects.update_or_create(
            user=user,
            defaults={
                'garmin_username': username,
                'token_data': token_data_str
            }
        )
        return True
    except Exception as e:
        print(f"Failed to link Garmin account: {e}")
        return False

def get_garmin_client(user=None):
    if user and hasattr(user, 'garmin_token') and user.garmin_token.token_data:
        try:
            garmin = Garmin()
            try:
                # Some versions of garth loads the token natively via loads
                garmin.garth.loads(user.garmin_token.token_data)
            except AttributeError:
                # If garth does not have loads natively on instance
                garmin.garth = garmin.garth.__class__.loads(user.garmin_token.token_data)
            
            # Garminconnect sometimes requires initializing internal variables after load
            garmin.display_name = garmin.garth.profile.get("displayName")
            garmin.full_name = garmin.garth.profile.get("fullName")
            return garmin
        except Exception as e:
            print(f"Failed to login using database token: {e}")

    tokenstore = os.getenv("GARMINTOKENS", "~/.garminconnect")
    tokenstore_path = Path(tokenstore).expanduser()
    if tokenstore_path.exists():
        try:
            garmin = Garmin()
            garmin.login(str(tokenstore_path))
            return garmin
        except Exception as e:
            print(f"Failed to login using file token: {e}")
            pass
            
    return None

def fetch_and_update_garmin_data(user):
    client = get_garmin_client(user)
    if not client:
        return False

    today_str = date.today().isoformat()
    today = date.today()
    # Fetch basic stats
    vo2_max = 0
    heart_rate = 0
    active_minutes = 0
    try:
        max_metrics = client.get_max_metrics(today_str)
        if max_metrics:
            for metric in max_metrics:
                if metric.get("metricsTypeName") == "vo2_max":
                    vo2_max = int(metric.get("metricsTypeValue", 0))
    except Exception:
        pass
        
    try:
        hr_data = client.get_heart_rates(today_str)
        if hr_data and hr_data.get("restingHeartRate"):
            heart_rate = int(hr_data.get("restingHeartRate", 0))
    except Exception:
        pass

    latest_activities = None
    try:
        latest_activities = client.get_activities(0, 20)
    except Exception:
        pass

    # Parse activities to find the latest of each type
    running_act = None
    cycling_act = None
    swimming_act = None
    lifting_act = None
    latest_act_type = "None"
    latest_act_amount = 0

    if latest_activities:
        for act in latest_activities:
            act_type = act.get('activityType', {}).get('typeKey', '')
            distance = int(act.get("distance", 0))
            duration = int(act.get("duration", 0) / 60) # duration is usually in seconds, convert to minutes
            avg_hr = int(act.get("averageHR", 0))
            # Garmin API doesn't always expose low/high HR directly here, sometimes it's maxHR
            max_hr = int(act.get("maxHR", 0))
            low_hr = 0 # Defaulting, maybe calculation needed

            if act_type == "running" and not running_act:
                running_act = act
                RunningStats.objects.update_or_create(
                    user=user,
                    date_recorded=today,
                    defaults={
                        'distance': distance,
                        'avg_heart_rate': avg_hr,
                        'low_heart_rate': low_hr,
                        'high_heart_rate': max_hr,
                        'time': duration
                    }
                )
            elif act_type == "cycling" and not cycling_act:
                cycling_act = act
                CyclingStats.objects.update_or_create(
                    user=user,
                    date_recorded=today,
                    defaults={
                        'distance': distance,
                        'avg_heart_rate': avg_hr,
                        'low_heart_rate': low_hr,
                        'high_heart_rate': max_hr,
                        'time': duration
                    }
                )
            elif act_type in ["lap_swimming", "open_water_swimming"] and not swimming_act:
                swimming_act = act
                SwimmingStats.objects.update_or_create(
                    user=user,
                    date_recorded=today,
                    defaults={
                        'distance': distance,
                        'avg_heart_rate': avg_hr,
                        'low_heart_rate': low_hr,
                        'high_heart_rate': max_hr,
                        'time': duration
                    }
                )
            elif act_type == "strength_training" and not lifting_act:
                lifting_act = act
                # Note: weight, reps, sets might not be available at summary level without fetching activity details
                # For now put dummy or 0 values as placeholders if unavailable
                LiftingStats.objects.update_or_create(
                    user=user,
                    date_recorded=today,
                    defaults={
                        'weight': 0,
                        'reps': 0,
                        'sets': 0,
                        'volume': 0,
                        'time': duration
                    }
                )
                
        if len(latest_activities) > 0:
            latest = latest_activities[0]
            latest_act_type = latest.get('activityType', {}).get('typeKey', '')
            latest_act_amount = int(latest.get("duration", 0) / 60)
            active_minutes = latest_act_amount # Simplified for now

    # Ensure all related objects exist for today to prevent foreign key errors when creating GarminUserData
    running_stats, _ = RunningStats.objects.get_or_create(user=user, date_recorded=today, defaults={'distance':0, 'avg_heart_rate':0, 'low_heart_rate':0, 'high_heart_rate':0, 'time':0})
    cycling_stats, _ = CyclingStats.objects.get_or_create(user=user, date_recorded=today, defaults={'distance':0, 'avg_heart_rate':0, 'low_heart_rate':0, 'high_heart_rate':0, 'time':0})
    swimming_stats, _ = SwimmingStats.objects.get_or_create(user=user, date_recorded=today, defaults={'distance':0, 'avg_heart_rate':0, 'low_heart_rate':0, 'high_heart_rate':0, 'time':0})
    lifting_stats, _ = LiftingStats.objects.get_or_create(user=user, date_recorded=today, defaults={'weight':0, 'reps':0, 'sets':0, 'volume':0, 'time':0})

    GarminUserData.objects.update_or_create(
        user=user,
        date_recorded=today,
        defaults={
            'VO2_max': vo2_max,
            'heart_rate': heart_rate,
            'active_minutes': active_minutes,
            'activty_type': latest_act_type,
            'activty_amount': latest_act_amount,
            'running': running_stats,
            'cycling': cycling_stats,
            'swimming': swimming_stats,
            'lifting': lifting_stats
        }
    )

    return True
