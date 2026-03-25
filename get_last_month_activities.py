import json
import os
import sys
from datetime import date, timedelta, datetime
from getpass import getpass
from pathlib import Path

from garth.exc import GarthHTTPError
from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
)


def get_credentials():
    email = os.getenv("GARMIN_EMAIL")
    password = os.getenv("GARMIN_PASSWORD")

    if not email:
        email = input("Garmin Login email: ").strip()
    if not password:
        password = getpass("Garmin password: ")
    return email, password


def init_api():
    tokenstore = os.getenv("GARMINTOKENS", "~/.garminconnect")
    tokenstore_path = Path(tokenstore).expanduser()

    try:
        api = Garmin()
        api.login(str(tokenstore_path))
        return api
    except (FileNotFoundError, GarthHTTPError, GarminConnectAuthenticationError, GarminConnectConnectionError):
        print("Stored token login failed, using credentials...")

    email, password = get_credentials()
    api = Garmin(email=email, password=password, is_cn=False, return_on_mfa=True)
    step, payload = api.login()
    if step == "needs_mfa":
        mfa_code = input("Enter MFA code: ").strip()
        api.resume_login(payload, mfa_code)
    api.garth.dump(str(tokenstore_path))
    return api


def get_last_month_activities(api):
    end_date = date.today()
    start_date = end_date - timedelta(days=30)
    print(f"Fetching activities from {start_date} to {end_date}...")

    # Use paginated activity fetch and local date filtering because
    # get_activities_by_date can sometimes return activities outside the window.
    all_activities = []
    start = 0
    limit = 100

    while True:
        page = api.get_activities(start, limit) or []
        if not page:
            break
        all_activities.extend(page)
        if len(page) < limit:
            break
        start += limit

    filtered = []
    for activity in all_activities:
        start_local = activity.get("startTimeLocal") or ""
        activity_day = None
        if isinstance(start_local, str):
            try:
                # Format returned by Garmin often uses "YYYY-MM-DD HH:MM:SS".
                activity_day = datetime.fromisoformat(start_local.replace("Z", "+00:00")).date()
            except ValueError:
                try:
                    activity_day = datetime.strptime(start_local[:10], "%Y-%m-%d").date()
                except ValueError:
                    activity_day = None
        if activity_day and start_date <= activity_day <= end_date:
            filtered.append(activity)

    filtered.sort(key=lambda a: a.get("startTimeLocal", ""), reverse=True)
    return filtered


def main():
    output_file = "garmin_last_month_activities.json"
    try:
        api = init_api()
        activities = get_last_month_activities(api)
    except Exception as exc:
        print(f"Failed to fetch activities: {exc}")
        sys.exit(1)

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(activities, f, indent=2, ensure_ascii=False)

    print(f"Fetched {len(activities)} activities.")
    print(f"Saved to {output_file}")


if __name__ == "__main__":
    main()

