import json
from datetime import timedelta
from urllib.error import URLError
from urllib.request import urlopen

from django.utils import timezone
from django.db.models import Q

from .models import GarminActivity, GarminUserData, METERS_PER_MILE

EXERCISE_DB_URL = "https://raw.githubusercontent.com/yuhonas/free-exercise-db/main/dist/exercises.json"

FALLBACK_RECOMMENDATIONS = [
    {
        "name": "Zone 2 Easy Run",
        "category": "cardio",
        "level": "beginner",
        "reason": "Build aerobic base when running load is low.",
    },
    {
        "name": "Cycling Tempo Intervals",
        "category": "cardio",
        "level": "intermediate",
        "reason": "Improve endurance and training efficiency.",
    },
    {
        "name": "Goblet Squat",
        "category": "strength",
        "level": "beginner",
        "reason": "Strengthen lower body for running and lifting progress.",
    },
    {
        "name": "Romanian Deadlift",
        "category": "strength",
        "level": "intermediate",
        "reason": "Improve posterior chain and reduce fatigue risk.",
    },
]


def _activity_bucket(activity_type: str) -> str:
    kind = (activity_type or "").lower()
    if "running" in kind:
        return "running"
    if "cycling" in kind or "biking" in kind or "ride" in kind:
        return "cycling"
    if "swimming" in kind:
        return "swimming"
    if "strength" in kind or "lifting" in kind:
        return "lifting"
    return "other"


def _safe_percent(numerator: float, denominator: float) -> int:
    if not denominator:
        return 0
    return int(round((numerator / denominator) * 100))


def _compute_training_load_signal(latest_snapshot, activities_14d):
    active_minutes_14d = int(sum((a.duration_seconds or 0) for a in activities_14d) / 60)
    avg_daily_minutes = active_minutes_14d / 14 if activities_14d else 0
    resting_hr = getattr(latest_snapshot, "heart_rate", 0) if latest_snapshot else 0

    flags = []
    status = "balanced"
    rationale = "Training load appears balanced for current activity volume."

    if avg_daily_minutes < 20:
        status = "undertraining"
        rationale = "Recent activity volume is low for adaptation."
        flags.append("Low weekly training volume")
    elif avg_daily_minutes > 120 and resting_hr >= 70:
        status = "overtraining_risk"
        rationale = "High activity volume plus elevated resting HR suggests recovery strain."
        flags.append("High load with elevated resting heart rate")
    elif avg_daily_minutes > 120:
        status = "high_load"
        rationale = "Training load is high; prioritize recovery and sleep."
        flags.append("High weekly training volume")

    return {
        "status": status,
        "active_minutes_14d": active_minutes_14d,
        "avg_daily_minutes": round(avg_daily_minutes, 1),
        "resting_hr": resting_hr,
        "flags": flags,
        "rationale": rationale,
    }


def _compute_running_analysis(activities_30d):
    running = [a for a in activities_30d if _activity_bucket(a.activity_type) == "running"]
    if not running:
        return {
            "score": 20,
            "status": "needs_data",
            "frequency_30d": 0,
            "total_distance_m": 0,
            "total_distance_miles": 0,
            "avg_duration_min": 0,
            "recommendation": "Add 2-3 easy runs per week to build consistency.",
        }

    frequency = len(running)
    total_distance = sum((a.distance_meters or 0) for a in running)
    avg_duration_min = sum((a.duration_seconds or 0) for a in running) / max(frequency, 1) / 60
    total_distance_miles = float(total_distance or 0) / METERS_PER_MILE

    score = 35
    score += min(30, frequency * 3)
    score += min(20, int(total_distance / 3000))
    score += min(15, int(avg_duration_min / 8))
    score = max(0, min(100, int(score)))

    status = "good" if score >= 70 else "moderate" if score >= 45 else "low"
    recommendation = (
        "Keep a mix of easy and quality sessions; add one recovery day."
        if score >= 70
        else "Increase frequency gradually and keep most sessions easy."
    )

    return {
        "score": score,
        "status": status,
        "frequency_30d": frequency,
        "total_distance_m": int(total_distance),
        "total_distance_miles": total_distance_miles,
        "avg_duration_min": round(avg_duration_min, 1),
        "recommendation": recommendation,
    }


def _compute_lifting_analysis(activities_30d):
    lifting = [a for a in activities_30d if _activity_bucket(a.activity_type) == "lifting"]
    if not lifting:
        return {
            "score": 20,
            "status": "needs_data",
            "sessions_30d": 0,
            "total_duration_min": 0,
            "recommendation": "Start with 2 full-body lifting sessions per week.",
        }

    sessions = len(lifting)
    total_duration_min = int(sum((a.duration_seconds or 0) for a in lifting) / 60)
    avg_session = total_duration_min / max(sessions, 1)

    score = 35
    score += min(40, sessions * 4)
    score += min(25, int(avg_session / 5))
    score = max(0, min(100, int(score)))
    status = "good" if score >= 70 else "moderate" if score >= 45 else "low"
    recommendation = (
        "Maintain progressive overload and include a deload week each 4-6 weeks."
        if score >= 70
        else "Build consistency first, then add volume gradually."
    )

    return {
        "score": score,
        "status": status,
        "sessions_30d": sessions,
        "total_duration_min": total_duration_min,
        "recommendation": recommendation,
    }


def _build_recommendation_intents(training_load, running_analysis, lifting_analysis):
    intents = []
    if training_load["status"] in {"undertraining", "needs_data"}:
        intents.append("cardio_base")
    if training_load["status"] in {"overtraining_risk", "high_load"}:
        intents.append("recovery_mobility")
    if running_analysis["score"] < 60:
        intents.append("running_efficiency")
    if lifting_analysis["score"] < 60:
        intents.append("strength_foundation")
    if not intents:
        intents.append("balanced_maintenance")
    return intents


def _matches_intents(exercise, intents):
    category = str(exercise.get("category", "")).lower()
    level = str(exercise.get("level", "")).lower()
    force = str(exercise.get("force", "")).lower()
    muscles = " ".join(exercise.get("primaryMuscles", []) + exercise.get("secondaryMuscles", [])).lower()

    text_blob = " ".join([category, level, force, muscles, str(exercise.get("name", "")).lower()])
    if "cardio_base" in intents and "cardio" in text_blob:
        return True
    if "running_efficiency" in intents and ("calves" in text_blob or "hamstrings" in text_blob or "cardio" in text_blob):
        return True
    if "strength_foundation" in intents and ("compound" in text_blob or "quadriceps" in text_blob or "back" in text_blob):
        return True
    if "recovery_mobility" in intents and ("stretch" in text_blob or "core" in text_blob):
        return True
    return False


def fetch_tailored_workouts(intents, limit=6):
    try:
        with urlopen(EXERCISE_DB_URL, timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8"))
        exercises = payload if isinstance(payload, list) else []
        picked = []
        for exercise in exercises:
            if not isinstance(exercise, dict):
                continue
            if _matches_intents(exercise, intents):
                picked.append(
                    {
                        "name": exercise.get("name", "Unknown exercise"),
                        "category": str(exercise.get("category", "general")).lower(),
                        "level": str(exercise.get("level", "mixed")).lower(),
                        "reason": f"Matched analysis intents: {', '.join(intents)}",
                    }
                )
            if len(picked) >= limit:
                break
        if picked:
            return picked
    except (URLError, TimeoutError, json.JSONDecodeError, ValueError):
        pass
    return FALLBACK_RECOMMENDATIONS[:limit]


def build_analysis_for_user(user):
    latest_snapshot = GarminUserData.objects.filter(user=user).order_by("-date_recorded").first()
    now = timezone.now()
    # Activities may be missing `start_time_local` (older imports, partial payloads).
    # Fall back to `imported_at` so time-windowed analysis still reflects the DB.
    window_14d = now - timedelta(days=14)
    window_30d = now - timedelta(days=30)

    activities_14d = list(
        GarminActivity.objects.filter(user=user).filter(
            Q(start_time_local__gte=window_14d)
            | Q(start_time_local__isnull=True, imported_at__gte=window_14d)
        ).order_by("-start_time_local", "-imported_at")
    )
    activities_30d = list(
        GarminActivity.objects.filter(user=user).filter(
            Q(start_time_local__gte=window_30d)
            | Q(start_time_local__isnull=True, imported_at__gte=window_30d)
        ).order_by("-start_time_local", "-imported_at")
    )

    training_load = _compute_training_load_signal(latest_snapshot, activities_14d)
    running_analysis = _compute_running_analysis(activities_30d)
    lifting_analysis = _compute_lifting_analysis(activities_30d)

    overall_score = int(
        (running_analysis["score"] * 0.45)
        + (lifting_analysis["score"] * 0.35)
        + (_safe_percent(min(training_load["avg_daily_minutes"], 90), 90) * 0.2)
    )

    risk_flags = list(training_load["flags"])
    if running_analysis["status"] == "low":
        risk_flags.append("Low running consistency")
    if lifting_analysis["status"] == "low":
        risk_flags.append("Low strength training consistency")

    intents = _build_recommendation_intents(training_load, running_analysis, lifting_analysis)
    recommendations = fetch_tailored_workouts(intents, limit=6)

    data_warnings = []
    if latest_snapshot is None:
        data_warnings.append("No daily Garmin snapshot available yet.")
    if len(activities_30d) < 5:
        data_warnings.append("Limited activity history in the last 30 days; recommendations may be less precise.")
    missing_start_times = GarminActivity.objects.filter(user=user, start_time_local__isnull=True).count()
    if missing_start_times:
        data_warnings.append(
            f"{missing_start_times} imported activities are missing a start time; "
            "analysis will use import time as a fallback."
        )

    return {
        "latest_snapshot": latest_snapshot,
        "training_load": training_load,
        "running_analysis": running_analysis,
        "lifting_analysis": lifting_analysis,
        "overall_score": overall_score,
        "risk_flags": risk_flags,
        "recommendations": recommendations,
        "data_warnings": data_warnings,
    }
