import os
from pathlib import Path
from datetime import date, timedelta, datetime, timezone as dt_timezone
from garminconnect import Garmin
from django.utils import timezone
from .models import GarminUserData, RunningStats, CyclingStats, SwimmingStats, LiftingStats, GarminActivity
from users.models import GarminToken


RUNNING_KEYS = {"running", "trail_running", "track_running", "treadmill_running", "virtual_run"}
CYCLING_KEYS = {"cycling", "road_biking", "indoor_cycling", "mountain_biking", "virtual_ride", "gravel_cycling"}
SWIMMING_KEYS = {"lap_swimming", "open_water_swimming", "swimming"}
LIFTING_KEYS = {"strength_training", "cardio_strength_training"}

_REPS_KEYS = {"reps", "repetitions", "repetitionsPerformed", "repsPerformed", "repCount", "count", "repetitionCount"}
_WEIGHT_KEYS = {
    "weight",
    "weightKg",
    "weight_in_kg",
    "weightInKg",
    "load",
    "loadKg",
    "loadInKg",
    "intensityWeight",
}


def _maybe_int(value, default=0) -> int:
    try:
        if value is None:
            return default
        return int(round(float(value)))
    except Exception:
        return default


def _maybe_float(value, default=0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _extract_activity_grade(activity: dict) -> float:
    """
    Best-effort average grade (unitless, e.g. 0.03 for 3%).

    Garmin payloads vary. We try explicit average grade fields first, then fall back to
    elevation gain divided by distance.
    """
    if not isinstance(activity, dict):
        return 0.0

    # Explicit average grade fields (often already unitless fraction).
    for k in (
        "avgGrade",
        "averageGrade",
        "avgGradePercent",
        "averageGradePercent",
        "avgSlope",
        "averageSlope",
    ):
        if k in activity and activity.get(k) is not None:
            g = _maybe_float(activity.get(k), 0.0)
            # If provided as percent (e.g. 3.2), convert to fraction.
            if abs(g) > 1.0 and abs(g) <= 40.0:
                return g / 100.0
            # If already fraction, keep it.
            if abs(g) <= 1.0:
                return g

    # Elevation gain fallback (meters gained / meters traveled).
    elev_gain = None
    for k in (
        "elevationGain",
        "elevationGainInMeters",
        "totalElevationGain",
        "totalElevationGainInMeters",
        "totalAscent",
    ):
        if k in activity and activity.get(k) is not None:
            elev_gain = _maybe_float(activity.get(k), None)
            break

    distance_m = _maybe_float(activity.get("distance"), 0.0)
    if elev_gain is None or elev_gain <= 0 or distance_m <= 0:
        return 0.0

    grade = float(elev_gain) / float(distance_m)
    # Guardrail: ignore absurd averages; mean grade over a run is typically small.
    if abs(grade) > 0.25:
        return 0.0
    return grade


def _estimate_vo2max_from_running_activities(activities) -> int:
    """
    Estimate VO2 max from recent running activities (no Garmin VO2 endpoint needed).

    Uses the ACSM running equation with optional average grade:
      VO2 (ml/kg/min) ≈ 0.2 * v + 0.9 * v * grade + 3.5
    (If grade=0, this reduces to the level-ground formula.)

    We compute per-activity VO2 and take the max across plausible steady runs.
    """
    best = 0.0
    if not isinstance(activities, list):
        return 0

    for a in activities:
        if not isinstance(a, dict):
            continue
        type_key = _get_activity_type_key(a)
        if not _is_running_type(type_key):
            continue

        distance_m = _maybe_float(a.get("distance"), 0.0)
        duration_s = _maybe_float(a.get("duration"), 0.0)
        if distance_m <= 0 or duration_s <= 0:
            continue

        duration_min = duration_s / 60.0
        # Avoid garbage values from very short/partial activities.
        if duration_min < 10.0:
            continue

        speed_m_min = distance_m / duration_min
        # Plausibility filter: ~4:00–20:00 min/mile range.
        if speed_m_min < 80 or speed_m_min > 400:
            continue

        grade = _extract_activity_grade(a)
        vo2 = (0.2 * speed_m_min) + (0.9 * speed_m_min * grade) + 3.5
        if vo2 > best:
            best = vo2

    # Clamp to a reasonable human range.
    if best <= 0:
        return 0
    return int(round(min(85.0, max(15.0, best))))


def _estimate_vo2max_from_heart_rate(activities, resting_hr: int) -> int:
    """
    Estimate VO2 max using a conservative HR relationship:
      VO2max ≈ 15.3 * (HRmax / HRrest)

    - HRrest: user's resting heart rate (bpm)
    - HRmax: max observed maxHR across recent activities
    """
    hr_rest = _maybe_int(resting_hr, 0)
    if hr_rest < 35 or hr_rest > 90:
        return 0
    if not isinstance(activities, list):
        return 0

    hr_max_observed = 0
    for a in activities:
        if not isinstance(a, dict):
            continue
        hr = _maybe_int(a.get("maxHR") or a.get("maxHr") or a.get("maxHeartRate"), 0)
        if hr > hr_max_observed:
            hr_max_observed = hr

    # Plausibility guardrails.
    if hr_max_observed < 140 or hr_max_observed > 220:
        return 0

    vo2 = 15.3 * (float(hr_max_observed) / float(hr_rest))
    if vo2 <= 0:
        return 0
    return int(round(min(85.0, max(15.0, vo2))))


def _blend_vo2_estimates(vo2_pace: int, vo2_hr: int) -> int:
    """
    Blend VO2 estimates conservatively.
    - If both exist, weight pace more (hills/pace) but keep HR as a sanity anchor.
    - If one exists, use it.
    """
    p = _maybe_int(vo2_pace, 0)
    h = _maybe_int(vo2_hr, 0)
    if p <= 0 and h <= 0:
        return 0
    if p > 0 and h <= 0:
        return p
    if h > 0 and p <= 0:
        return h

    blended = (0.7 * float(p)) + (0.3 * float(h))
    # Clamp.
    return int(round(min(85.0, max(15.0, blended))))

def _latest_activity_from_payload(activities):
    latest_dt = None
    latest_type = "None"
    latest_amount_minutes = 0
    for act in activities:
        act_dt = _parse_activity_datetime(act)
        if not act_dt:
            continue
        if latest_dt is None or act_dt > latest_dt:
            latest_dt = act_dt
            latest_type = _get_activity_type_key(act)
            latest_amount_minutes = _maybe_int((act.get("duration", 0) or 0) / 60)
    return latest_type, latest_amount_minutes


def _extract_lifting_exercise_sets_stats(exercise_sets_payload) -> dict:
    """
    Best-effort extraction of lifting volume/weight/reps/sets from the Garmin payload.
    We prefer structured keys (exerciseSets -> sets -> {weight, reps}) but fall back to recursion.
    """
    sets_total = 0
    reps_total = 0
    weight_sum = 0.0
    weight_count = 0
    volume_total = 0.0

    def first_number(d, keys):
        for k in keys:
            if k in d:
                v = d.get(k)
                if isinstance(v, (int, float)):
                    return v
                # Sometimes numbers arrive as strings
                try:
                    return float(v)
                except Exception:
                    continue
        return None

    def ingest_set_dict(d):
        nonlocal sets_total, reps_total, weight_sum, weight_count, volume_total
        reps = first_number(d, _REPS_KEYS)
        weight = first_number(d, _WEIGHT_KEYS)
        if reps is None or weight is None:
            return

        reps_i = int(round(float(reps)))
        weight_f = float(weight)
        if reps_i <= 0 or weight_f < 0:
            return

        sets_total += 1
        reps_total += reps_i
        weight_sum += weight_f
        weight_count += 1
        volume_total += (weight_f * reps_i)

    # 1) Targeted extraction for common payload layouts.
    if isinstance(exercise_sets_payload, dict):
        exercise_sets = None
        for k in ("exerciseSets", "exercise_sets", "exercises", "sets"):
            maybe = exercise_sets_payload.get(k) if isinstance(exercise_sets_payload, dict) else None
            if isinstance(maybe, list):
                exercise_sets = maybe
                break

        if isinstance(exercise_sets, list) and exercise_sets:
            for exercise in exercise_sets:
                if not isinstance(exercise, dict):
                    continue
                sets_list = None
                for sets_key in ("sets", "set", "exerciseSets", "exercise_sets"):
                    maybe = exercise.get(sets_key)
                    if isinstance(maybe, list):
                        sets_list = maybe
                        break
                # If this exercise object itself looks like a set dict, ingest it.
                if sets_list is None and any(k in exercise for k in _REPS_KEYS):
                    ingest_set_dict(exercise)
                elif isinstance(sets_list, list):
                    for set_d in sets_list:
                        if isinstance(set_d, dict):
                            ingest_set_dict(set_d)

    # 2) Fallback recursion if we didn't extract anything.
    if sets_total == 0 and exercise_sets_payload is not None:
        def walk(obj):
            nonlocal sets_total, reps_total, weight_sum, weight_count, volume_total
            if isinstance(obj, dict):
                ingest_set_dict(obj)
                for v in obj.values():
                    walk(v)
            elif isinstance(obj, list):
                for item in obj:
                    walk(item)

        walk(exercise_sets_payload)

    return {
        "sets": sets_total,
        "reps": reps_total,
        "weight": int(round(weight_sum / weight_count)) if weight_count else 0,
        "volume": int(round(volume_total)),
    }

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

def fetch_and_update_garmin_data(
    user,
    overall_days: int | None = None,
    lifting_details_limit: int | None = None,
):
    client = get_garmin_client(user)
    if not client:
        return False

    days = (
        int(overall_days)
        if overall_days is not None
        else int(os.getenv("GARMIN_OVERALL_DAYS", "30"))
    )
    end_date = date.today()
    start_date = end_date - timedelta(days=days)
    today_str = end_date.isoformat()
    today = end_date
    # Fetch basic stats
    vo2_max = 0
    heart_rate = 0
    try:
        # Preferred: training status contains most recent VO2 max for many accounts.
        training_status = client.get_training_status(today_str)
        if isinstance(training_status, dict):
            most_recent = training_status.get("mostRecentVO2Max") or {}
            if isinstance(most_recent, dict):
                generic = most_recent.get("generic") or {}
                if isinstance(generic, dict):
                    vo2_max = _maybe_int(
                        generic.get("vo2MaxValue")
                        or generic.get("vo2MaxPreciseValue")
                        or generic.get("value")
                    )
    except Exception:
        pass

    if not vo2_max:
        try:
            # Fallback: max metrics endpoint (may be empty for some accounts).
            max_metrics = client.get_max_metrics(today_str)
            if isinstance(max_metrics, list):
                for metric in max_metrics:
                    if not isinstance(metric, dict):
                        continue
                    name = str(metric.get("metricsTypeName") or metric.get("metricsType") or "").lower()
                    if name in {"vo2_max", "vo2max", "vo2 max", "vo2maxvalue"}:
                        vo2_max = _maybe_int(metric.get("metricsTypeValue") or metric.get("value"))
                        break
        except Exception:
            pass
        
    try:
        hr_data = client.get_heart_rates(today_str)
        if hr_data and hr_data.get("restingHeartRate"):
            heart_rate = int(hr_data.get("restingHeartRate", 0))
    except Exception:
        pass

    # Build "overall user stats" snapshot from last N days of activities.
    # This repurposes GarminUserData + related stats tables to represent aggregate activity volume.
    active_minutes = 0

    running_distance_total = 0
    running_time_total = 0
    running_avg_hr_sum = 0
    running_avg_hr_count = 0
    running_low_hr = 0
    running_high_hr = 0

    cycling_distance_total = 0
    cycling_time_total = 0
    cycling_avg_hr_sum = 0
    cycling_avg_hr_count = 0
    cycling_low_hr = 0
    cycling_high_hr = 0

    swimming_distance_total = 0
    swimming_time_total = 0
    swimming_avg_hr_sum = 0
    swimming_avg_hr_count = 0
    swimming_low_hr = 0
    swimming_high_hr = 0

    lifting_time_total = 0
    lifting_sets_total = 0
    lifting_reps_total = 0
    lifting_weight_sum = 0.0
    lifting_weight_count = 0
    lifting_volume_total = 0.0

    max_lifting_activity_details = (
        int(lifting_details_limit)
        if lifting_details_limit is not None
        else int(os.getenv("GARMIN_LIFTING_DETAILS_LIMIT", "20"))
    )
    lifting_details_loaded = 0

    all_activities_in_range = []

    activities = None
    try:
        activities = client.get_activities_by_date(start_date.isoformat(), end_date.isoformat()) or []
    except Exception:
        activities = []

    # Persist raw activities (for analysis screens), while aggregating overall stats.
    for activity in activities:
        act_dt = _parse_activity_datetime(activity)
        if not act_dt:
            continue
        act_day = timezone.localtime(act_dt).date()
        if act_day < start_date or act_day > end_date:
            continue

        all_activities_in_range.append(activity)

        raw_id = activity.get("activityId") or activity.get("activity_id") or activity.get("id")
        if raw_id is None:
            continue
        activity_id = str(raw_id)

        activity_type = _get_activity_type_key(activity)
        distance = int(activity.get("distance", 0) or 0)
        duration_minutes = int((activity.get("duration", 0) or 0) / 60)  # garminconnect returns seconds

        # Store/update activity for later dashboard analytics.
        GarminActivity.objects.update_or_create(
            user=user,
            activity_id=activity_id,
            defaults={
                "activity_name": (activity.get("activityName") or activity.get("activity_name") or "")[:255],
                "activity_type": str(activity_type)[:100],
                "start_time_local": act_dt,
                "distance_meters": float(activity.get("distance", 0) or 0),
                "duration_seconds": float(activity.get("duration", 0) or 0),
                "calories": float(activity.get("calories", 0) or 0),
                "payload": activity,
            },
        )

        active_minutes += duration_minutes

        avg_hr = int(activity.get("averageHR", 0) or 0)
        min_hr = int(activity.get("minHR", 0) or 0)
        max_hr = int(activity.get("maxHR", 0) or 0)

        if _is_running_type(activity_type):
            running_distance_total += distance
            running_time_total += duration_minutes
            if avg_hr > 0:
                running_avg_hr_sum += avg_hr
                running_avg_hr_count += 1
            if min_hr > 0:
                running_low_hr = min(running_low_hr, min_hr) if running_low_hr else min_hr
            if max_hr > 0:
                running_high_hr = max(running_high_hr, max_hr)

        if _is_cycling_type(activity_type):
            cycling_distance_total += distance
            cycling_time_total += duration_minutes
            if avg_hr > 0:
                cycling_avg_hr_sum += avg_hr
                cycling_avg_hr_count += 1
            if min_hr > 0:
                cycling_low_hr = min(cycling_low_hr, min_hr) if cycling_low_hr else min_hr
            if max_hr > 0:
                cycling_high_hr = max(cycling_high_hr, max_hr)

        if _is_swimming_type(activity_type):
            swimming_distance_total += distance
            swimming_time_total += duration_minutes
            if avg_hr > 0:
                swimming_avg_hr_sum += avg_hr
                swimming_avg_hr_count += 1
            if min_hr > 0:
                swimming_low_hr = min(swimming_low_hr, min_hr) if swimming_low_hr else min_hr
            if max_hr > 0:
                swimming_high_hr = max(swimming_high_hr, max_hr)

        if _is_lifting_type(activity_type):
            lifting_time_total += duration_minutes

            if lifting_details_loaded < max_lifting_activity_details:
                lifting_details_loaded += 1
                try:
                    exercise_sets_payload = client.get_activity_exercise_sets(activity_id)
                    lifting_stats = _extract_lifting_exercise_sets_stats(exercise_sets_payload)
                except Exception:
                    lifting_stats = {"weight": 0, "reps": 0, "sets": 0, "volume": 0}

                lifting_sets_total += int(lifting_stats.get("sets", 0) or 0)
                lifting_reps_total += int(lifting_stats.get("reps", 0) or 0)
                lifting_volume_total += float(lifting_stats.get("volume", 0) or 0)

                # `weight` is the average-per-set we extracted, so we approximate sums using count.
                extracted_weight = int(lifting_stats.get("weight", 0) or 0)
                if extracted_weight > 0:
                    lifting_weight_sum += float(extracted_weight * int(lifting_stats.get("sets", 0) or 0))
                    lifting_weight_count += int(lifting_stats.get("sets", 0) or 0)

    # If Garmin does not provide VO2, estimate from recent activities (pace/grade + HR).
    if not vo2_max:
        vo2_pace = _estimate_vo2max_from_running_activities(all_activities_in_range)
        vo2_hr = _estimate_vo2max_from_heart_rate(all_activities_in_range, resting_hr=heart_rate)
        vo2_max = _blend_vo2_estimates(vo2_pace, vo2_hr)

    running_avg_hr = int(round(running_avg_hr_sum / running_avg_hr_count)) if running_avg_hr_count else 0
    cycling_avg_hr = int(round(cycling_avg_hr_sum / cycling_avg_hr_count)) if cycling_avg_hr_count else 0
    swimming_avg_hr = int(round(swimming_avg_hr_sum / swimming_avg_hr_count)) if swimming_avg_hr_count else 0

    latest_act_type, latest_act_amount = _latest_activity_from_payload(all_activities_in_range)

    running_stats, _ = RunningStats.objects.get_or_create(
        user=user,
        date_recorded=today,
        defaults={"distance": 0, "avg_heart_rate": 0, "low_heart_rate": 0, "high_heart_rate": 0, "time": 0},
    )
    running_stats.distance = running_distance_total
    running_stats.avg_heart_rate = running_avg_hr
    running_stats.low_heart_rate = running_low_hr
    running_stats.high_heart_rate = running_high_hr
    running_stats.time = running_time_total
    running_stats.save(update_fields=["distance", "avg_heart_rate", "low_heart_rate", "high_heart_rate", "time"])

    cycling_stats, _ = CyclingStats.objects.get_or_create(
        user=user,
        date_recorded=today,
        defaults={"distance": 0, "avg_heart_rate": 0, "low_heart_rate": 0, "high_heart_rate": 0, "time": 0},
    )
    cycling_stats.distance = cycling_distance_total
    cycling_stats.avg_heart_rate = cycling_avg_hr
    cycling_stats.low_heart_rate = cycling_low_hr
    cycling_stats.high_heart_rate = cycling_high_hr
    cycling_stats.time = cycling_time_total
    cycling_stats.save(update_fields=["distance", "avg_heart_rate", "low_heart_rate", "high_heart_rate", "time"])

    swimming_stats, _ = SwimmingStats.objects.get_or_create(
        user=user,
        date_recorded=today,
        defaults={"distance": 0, "avg_heart_rate": 0, "low_heart_rate": 0, "high_heart_rate": 0, "time": 0},
    )
    swimming_stats.distance = swimming_distance_total
    swimming_stats.avg_heart_rate = swimming_avg_hr
    swimming_stats.low_heart_rate = swimming_low_hr
    swimming_stats.high_heart_rate = swimming_high_hr
    swimming_stats.time = swimming_time_total
    swimming_stats.save(update_fields=["distance", "avg_heart_rate", "low_heart_rate", "high_heart_rate", "time"])

    lifting_stats, _ = LiftingStats.objects.get_or_create(
        user=user,
        date_recorded=today,
        defaults={"weight": 0, "reps": 0, "sets": 0, "volume": 0, "time": 0},
    )
    lifting_stats.reps = lifting_reps_total
    lifting_stats.sets = lifting_sets_total
    lifting_stats.volume = int(round(lifting_volume_total))
    lifting_stats.weight = int(round(lifting_weight_sum / lifting_weight_count)) if lifting_weight_count else 0
    lifting_stats.time = lifting_time_total
    lifting_stats.save(update_fields=["weight", "reps", "sets", "volume", "time"])

    GarminUserData.objects.update_or_create(
        user=user,
        date_recorded=today,
        defaults={
            'VO2_max': vo2_max,
            'heart_rate': heart_rate,
            'active_minutes': active_minutes,
            'activty_type': latest_act_type,
            'activty_amount': latest_act_amount,
            'aggregation_days': days,
            'range_start_date': start_date,
            'range_end_date': end_date,
            'running': running_stats,
            'cycling': cycling_stats,
            'swimming': swimming_stats,
            'lifting': lifting_stats
        }
    )

    return True


def _parse_activity_datetime(activity):
    """
    Garmin payloads vary by endpoint/version. We accept:
    - startTimeLocal / startTimeGMT strings (ISO-ish, sometimes 'YYYY-mm-dd HH:MM:SS')
    - beginTimestamp (epoch milliseconds)
    """
    if not isinstance(activity, dict):
        return None

    source = "startTimeLocal" if activity.get("startTimeLocal") else ("startTimeGMT" if activity.get("startTimeGMT") else None)
    value = activity.get("startTimeLocal") or activity.get("startTimeGMT")
    if isinstance(value, str) and value.strip():
        s = value.strip()
        # Handle trailing Z, and also space-separated timestamps.
        s_norm = s.replace("Z", "+00:00")
        for attempt in (s_norm, s_norm.replace(" ", "T")):
            try:
                dt = datetime.fromisoformat(attempt)
                if dt.tzinfo:
                    return dt
                # Garmin often sends `startTimeLocal` without an offset; interpret it
                # in the project's current timezone (not UTC). `startTimeGMT` is UTC.
                if source == "startTimeLocal":
                    return timezone.make_aware(dt, timezone=timezone.get_current_timezone())
                return timezone.make_aware(dt, timezone=dt_timezone.utc)
            except Exception:
                continue

        # Last resort: common Garmin format without timezone.
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
            try:
                dt = datetime.strptime(s, fmt)
                if source == "startTimeLocal":
                    return timezone.make_aware(dt, timezone=timezone.get_current_timezone())
                return timezone.make_aware(dt, timezone=dt_timezone.utc)
            except Exception:
                continue

    # Some payloads provide beginTimestamp in milliseconds.
    ts = activity.get("beginTimestamp") or activity.get("startTimestamp") or activity.get("startTimeInSeconds")
    if isinstance(ts, (int, float)):
        # Heuristic: values > 10^12 are epoch ms.
        seconds = float(ts) / 1000.0 if float(ts) > 1_000_000_000_000 else float(ts)
        try:
            return datetime.fromtimestamp(seconds, tz=dt_timezone.utc)
        except Exception:
            return None

    return None


def _get_activity_type_key(activity):
    raw = activity.get("activityType", {})
    if isinstance(raw, dict):
        return (raw.get("typeKey") or "").lower()
    return str(raw or "").lower()


def _is_running_type(type_key):
    return type_key in RUNNING_KEYS or "running" in type_key


def _is_cycling_type(type_key):
    return type_key in CYCLING_KEYS or "cycling" in type_key or "biking" in type_key or "ride" in type_key


def _is_swimming_type(type_key):
    return type_key in SWIMMING_KEYS or "swimming" in type_key


def _is_lifting_type(type_key):
    return type_key in LIFTING_KEYS or "strength" in type_key


def fetch_and_store_recent_activities(user, days=30):
    client = get_garmin_client(user)
    if not client:
        return {"ok": False, "error": "garmin_not_linked"}

    end_date = date.today()
    start_date = end_date - timedelta(days=days)
    activities = client.get_activities_by_date(start_date.isoformat(), end_date.isoformat()) or []

    created = 0
    updated = 0
    seen = 0

    for activity in activities:
        act_dt = _parse_activity_datetime(activity)
        if not act_dt:
            continue
        act_day = timezone.localtime(act_dt).date()
        if act_day < start_date or act_day > end_date:
            continue

        seen += 1
        raw_id = activity.get("activityId") or activity.get("activity_id") or activity.get("id")
        if raw_id is None:
            continue
        activity_id = str(raw_id)

        activity_type = _get_activity_type_key(activity)

        _, was_created = GarminActivity.objects.update_or_create(
            user=user,
            activity_id=activity_id,
            defaults={
                "activity_name": (activity.get("activityName") or activity.get("activity_name") or "")[:255],
                "activity_type": str(activity_type)[:100],
                "start_time_local": act_dt,
                "distance_meters": float(activity.get("distance", 0) or 0),
                "duration_seconds": float(activity.get("duration", 0) or 0),
                "calories": float(activity.get("calories", 0) or 0),
                "payload": activity,
            },
        )

        if was_created:
            created += 1
        else:
            updated += 1

    return {"ok": True, "seen": seen, "created": created, "updated": updated}
