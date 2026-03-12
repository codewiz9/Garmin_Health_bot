import csv
import logging
import os
import sys
from datetime import date, timedelta
from getpass import getpass
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from garth.exc import GarthHTTPError
from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)

# Suppress garminconnect library logging to avoid tracebacks in normal operation
logging.getLogger("garminconnect").setLevel(logging.CRITICAL)

def get_credentials():
    """Get email and password from environment or user input."""
    email = os.getenv("GARMIN_EMAIL")
    password = os.getenv("GARMIN_PASSWORD")

    if not email:
        email = input("Garmin Login email: ")
    if not password:
        password = getpass("Enter Garmin password: ")

    return email, password

def init_api():
    """Initialize Garmin API with authentication and token management."""
    # Configure token storage
    tokenstore = os.getenv("GARMINTOKENS", "~/.garminconnect")
    tokenstore_path = Path(tokenstore).expanduser()

    # First try to login with stored tokens
    try:
        garmin = Garmin()
        garmin.login(str(tokenstore_path))
        return garmin
    except (
        FileNotFoundError,
        GarthHTTPError,
        GarminConnectAuthenticationError,
        GarminConnectConnectionError,
    ):
        print("Login with stored tokens failed, falling back to credentials.")

    # Loop for credential entry with retry on auth failure
    while True:
        try:
            email, password = get_credentials()

            garmin = Garmin(
                email=email, password=password, is_cn=False, return_on_mfa=True
            )
            result1, result2 = garmin.login()

            if result1 == "needs_mfa":
                mfa_code = input("Please enter your MFA code: ")
                garmin.resume_login(result2, mfa_code)

            # Save tokens for next time
            garmin.garth.dump(str(tokenstore_path))
            print(f"Login successful! Tokens saved to {tokenstore_path}")
            return garmin

        except GarminConnectAuthenticationError as e:
            print(f"Authentication failed: {e}. Please try again.")
            # Clear credentials to prompt again
            if "GARMIN_EMAIL" in os.environ:
                del os.environ["GARMIN_EMAIL"]
            if "GARMIN_PASSWORD" in os.environ:
                del os.environ["GARMIN_PASSWORD"]
        except Exception as e:
            print(f"Login failed: {e}")
            sys.exit(1)

def fetch_day_data(api, today):
    """Fetch all metrics for a single day."""
    data = {
        "Date": today,
        "Sleep Time (hrs)": "Not Recorded",
        "Total Steps": "Not Recorded",
        "Total Calories": "Not Recorded",
        "Resting Heart Rate": "Not Recorded",
        "HRV (ms)": "Not Recorded",
        "VO2 Max": "Not Recorded",
        "Respiration Rate": "Not Recorded",
        "Blood Ox (SpO2) %": "Not Recorded",
        "Activities": []
    }

    # 1. User Summary (Steps, Calories)
    try:
        summary = api.get_user_summary(today)
        if summary:
            steps = summary.get("totalSteps")
            calories = summary.get("totalKilocalories")
            if steps is not None: data["Total Steps"] = steps
            if calories is not None: data["Total Calories"] = calories
    except Exception as e:
        if "403" not in str(e) and "Too Many Requests" not in str(e):
            print(f"  [{today}] Error fetching user summary: {e}")

    # 2. Sleep Data
    try:
        sleep_data = api.get_sleep_data(today)
        if sleep_data and "dailySleepDTO" in sleep_data:
            sleep_time_seconds = sleep_data["dailySleepDTO"].get("sleepTimeSeconds")
            if sleep_time_seconds:
                data["Sleep Time (hrs)"] = round(sleep_time_seconds / 3600, 2)
    except Exception as e:
        if "403" not in str(e) and "Too Many Requests" not in str(e):
            print(f"  [{today}] Error fetching sleep data: {e}")

    # 3. Heart Rate
    try:
        hr_data = api.get_heart_rates(today)
        if hr_data:
            rhr = hr_data.get("restingHeartRate")
            if rhr is not None: data["Resting Heart Rate"] = rhr
    except Exception as e:
        if "403" not in str(e) and "Too Many Requests" not in str(e):
            print(f"  [{today}] Error fetching heart rate data: {e}")

    # 4. HRV
    try:
        hrv_data = api.get_hrv_data(today)
        if hrv_data and "hrvSummary" in hrv_data:
            hrv = hrv_data["hrvSummary"].get("lastNightAvg")
            if hrv is not None: data["HRV (ms)"] = hrv
    except Exception as e:
        if "403" not in str(e) and "Too Many Requests" not in str(e):
            print(f"  [{today}] Error fetching HRV data: {e}")

    # 5. VO2 Max
    try:
        max_metrics = api.get_max_metrics(today)
        if max_metrics:
            for metric in max_metrics:
                if metric.get("metricsTypeName") == "vo2_max":
                    data["VO2 Max"] = metric.get("metricsTypeValue")
    except Exception as e:
        if "403" not in str(e) and "Too Many Requests" not in str(e):
            print(f"  [{today}] Error fetching max metrics (VO2 Max): {e}")

    # 6. Respiration
    try:
        respiration_data = api.get_respiration_data(today)
        if respiration_data and "respirationValuesArray" in respiration_data and len(respiration_data["respirationValuesArray"]) > 0:
            values = [v[1] for v in respiration_data["respirationValuesArray"] if v and len(v) > 1 and v[1] is not None]
            if values:
                data["Respiration Rate"] = round(sum(values) / len(values), 2)
    except Exception as e:
        if "403" not in str(e) and "Too Many Requests" not in str(e):
            print(f"  [{today}] Error fetching respiration data: {e}")

    # 7. Blood Ox (SpO2)
    try:
        spo2_data = api.get_spo2_data(today)
        if spo2_data and "spo2ValuesArray" in spo2_data and len(spo2_data["spo2ValuesArray"]) > 0:
            values = [v[1] for v in spo2_data["spo2ValuesArray"] if v and len(v) > 1 and v[1] is not None]
            if values:
                data["Blood Ox (SpO2) %"] = round(sum(values) / len(values), 2)
    except Exception as e:
        if "403" not in str(e) and "Too Many Requests" not in str(e):
            print(f"  [{today}] Error fetching SpO2 data: {e}")

    # 8. Activity Data
    try:
        activities = api.get_activities_fordate(today)
        if activities and "payload" in activities:
            for act in activities["payload"]:
                activity_str = f"{act.get('activityName')} ({act.get('activityType', {}).get('typeKey')}) - {act.get('distance', 0)/1000:.2f}km"
                data["Activities"].append(activity_str)
    except Exception as e:
        if "403" not in str(e) and "Too Many Requests" not in str(e):
            print(f"  [{today}] Error fetching activities: {e}")

    # Convert activities list to a simple string
    if not data["Activities"]:
        data["Activities"] = "Not Recorded"
    else:
        data["Activities"] = " | ".join(data["Activities"])
        
    return data

def main():
    print("Initializing Garmin API...")
    try:
        api = init_api()
    except Exception as e:
        print(f"Failed to initialize Garmin API: {e}")
        return

    csv_file = "garmin_data.csv"
    headers = [
        "Date",
        "Sleep Time (hrs)",
        "Total Steps",
        "Total Calories",
        "Resting Heart Rate",
        "HRV (ms)",
        "VO2 Max",
        "Respiration Rate",
        "Blood Ox (SpO2) %",
        "Activities"
    ]

    # Initialize CSV if needed
    file_exists = os.path.isfile(csv_file)
    try:
        with open(csv_file, mode='a', newline='', encoding='utf-8') as file:
            writer = csv.DictWriter(file, fieldnames=headers)
            if not file_exists:
                writer.writeheader()
    except Exception as e:
        print(f"Error creating/accessing CSV: {e}")
        return

    end_date = date.today()
    start_date = end_date - timedelta(days=30)
    
    print(f"Fetching data from {start_date} to {end_date} concurrently...")

    # Build list of days
    dates_to_fetch = []
    current_date = start_date
    while current_date <= end_date:
        dates_to_fetch.append(current_date.strftime('%Y-%m-%d'))
        current_date += timedelta(days=1)

    all_data = []
    
    # Use ThreadPoolExecutor to fetch multiple days in parallel.
    # Max workers set to 5 to avoid overwhelming the Garmin API rate limits too quickly.
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_date = {executor.submit(fetch_day_data, api, d): d for d in dates_to_fetch}
        
        for future in as_completed(future_to_date):
            d = future_to_date[future]
            try:
                data = future.result()
                all_data.append(data)
                print(f"Successfully processed {d}")
            except Exception as exc:
                print(f"[{d}] generated an exception: {exc}")

    # Sort data by date before writing to keep chronological order
    all_data.sort(key=lambda x: x["Date"])

    # Append all gathered data to CSV
    try:
        with open(csv_file, mode='a', newline='', encoding='utf-8') as file:
            writer = csv.DictWriter(file, fieldnames=headers)
            for row in all_data:
                writer.writerow(row)
        print(f"\nData successfully exported to {csv_file}")
    except Exception as e:
        print(f"Error writing to CSV: {e}")

if __name__ == "__main__":
    main()
