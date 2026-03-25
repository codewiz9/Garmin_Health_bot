from __future__ import annotations

from datetime import datetime
from typing import Any

from django.utils import timezone

from garmin_bot.garmin_api import get_garmin_client

from .models import GarminWorkout


def _parse_garmin_updated_at(payload: dict[str, Any]) -> datetime | None:
    # Garmin payloads vary; try a few common keys.
    for key in ("updateDate", "updatedDate", "lastUpdatedDate", "updatedAt", "modifiedDate"):
        value = payload.get(key)
        if not value:
            continue
        # Sometimes it's ms since epoch, sometimes ISO string.
        if isinstance(value, (int, float)):
            try:
                return datetime.fromtimestamp(float(value) / 1000.0, tz=timezone.utc)
            except Exception:
                continue
        if isinstance(value, str):
            try:
                # Python 3.11+: fromisoformat handles many ISO variants
                dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
                return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
            except Exception:
                continue
    return None


def import_garmin_workouts_for_user(user) -> dict[str, Any]:
    """
    Imports workouts the user created on Garmin Connect into local DB.

    Uses garminconnect's `get_workouts()` (paged list) and `get_workout_by_id()` (full payload).
    """
    client = get_garmin_client(user)
    if not client:
        return {"ok": False, "error": "garmin_not_linked"}

    created = 0
    updated = 0
    seen = 0

    start = 0
    limit = 100

    while True:
        listing = client.get_workouts(start=start, limit=limit)
        # Some versions return {"workouts": [...], ...}, others return list directly.
        workouts = listing.get("workouts") if isinstance(listing, dict) else listing
        if not workouts:
            break

        for w in workouts:
            seen += 1
            # Heuristics for ID + name across payload shapes.
            workout_id = w.get("workoutId") or w.get("workout_id") or w.get("id")
            if workout_id is None:
                continue
            workout_id_str = str(workout_id)

            try:
                full_payload = client.get_workout_by_id(workout_id_str)
            except Exception:
                # Fall back to summary payload if details fail.
                full_payload = w

            name = (
                (full_payload.get("workoutName") if isinstance(full_payload, dict) else None)
                or (w.get("workoutName") if isinstance(w, dict) else None)
                or (full_payload.get("name") if isinstance(full_payload, dict) else None)
                or (w.get("name") if isinstance(w, dict) else None)
                or ""
            )
            updated_at_garmin = _parse_garmin_updated_at(full_payload if isinstance(full_payload, dict) else {})

            obj, was_created = GarminWorkout.objects.update_or_create(
                user=user,
                garmin_workout_id=workout_id_str,
                defaults={
                    "name": name[:255],
                    "updated_at_garmin": updated_at_garmin,
                    "payload": full_payload,
                },
            )
            if was_created:
                created += 1
            else:
                updated += 1

        if len(workouts) < limit:
            break
        start += limit

    return {"ok": True, "seen": seen, "created": created, "updated": updated}


def import_garmin_workouts_for_user_since(user, since_date) -> dict[str, Any]:
    """
    Imports Garmin workout definitions updated since `since_date` (best effort).

    This is intended for the settings "Full Sync" button so we don't pull
    the user's entire Garmin library every time.
    """
    client = get_garmin_client(user)
    if not client:
        return {"ok": False, "error": "garmin_not_linked"}

    created = 0
    updated = 0
    seen = 0

    start = 0
    limit = 100

    while True:
        listing = client.get_workouts(start=start, limit=limit)
        workouts = listing.get("workouts") if isinstance(listing, dict) else listing
        if not workouts:
            break

        for w in workouts:
            seen += 1
            workout_id = w.get("workoutId") or w.get("workout_id") or w.get("id")
            if workout_id is None:
                continue
            workout_id_str = str(workout_id)

            # If we can determine updated_at_garmin from the listing payload, skip old entries
            # to reduce unnecessary detail calls.
            maybe_updated = _parse_garmin_updated_at(w if isinstance(w, dict) else {})
            if maybe_updated is not None and maybe_updated.date() < since_date:
                continue

            try:
                full_payload = client.get_workout_by_id(workout_id_str)
            except Exception:
                full_payload = w

            updated_at_garmin = _parse_garmin_updated_at(full_payload if isinstance(full_payload, dict) else {})
            if updated_at_garmin is not None and updated_at_garmin.date() < since_date:
                continue

            name = (
                (full_payload.get("workoutName") if isinstance(full_payload, dict) else None)
                or (w.get("workoutName") if isinstance(w, dict) else None)
                or (full_payload.get("name") if isinstance(full_payload, dict) else None)
                or (w.get("name") if isinstance(w, dict) else None)
                or ""
            )

            obj, was_created = GarminWorkout.objects.update_or_create(
                user=user,
                garmin_workout_id=workout_id_str,
                defaults={
                    "name": name[:255],
                    "updated_at_garmin": updated_at_garmin,
                    "payload": full_payload,
                },
            )
            if was_created:
                created += 1
            else:
                updated += 1

        if len(workouts) < limit:
            break
        start += limit

    return {"ok": True, "seen": seen, "created": created, "updated": updated}

