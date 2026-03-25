from datetime import timedelta
from unittest.mock import patch
from urllib.error import URLError

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import (
    GarminActivity,
    GarminUserData,
    RunningStats,
    CyclingStats,
    SwimmingStats,
    LiftingStats,
)
from .services import FALLBACK_RECOMMENDATIONS, build_analysis_for_user
from .garmin_api import (
    _estimate_vo2max_from_running_activities,
    _estimate_vo2max_from_heart_rate,
    _blend_vo2_estimates,
)


class GarminBotAnalysisViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="password123")
        self.other = User.objects.create_user(username="bob", password="password123")

    def _create_snapshot(self, user, heart_rate=55, active_minutes=70):
        now = timezone.now().date()
        running = RunningStats.objects.create(
            user=user,
            date_recorded=now,
            distance=0,
            avg_heart_rate=0,
            low_heart_rate=0,
            high_heart_rate=0,
            time=0,
        )
        cycling = CyclingStats.objects.create(
            user=user,
            date_recorded=now,
            distance=0,
            avg_heart_rate=0,
            low_heart_rate=0,
            high_heart_rate=0,
            time=0,
        )
        swimming = SwimmingStats.objects.create(
            user=user,
            date_recorded=now,
            distance=0,
            avg_heart_rate=0,
            low_heart_rate=0,
            high_heart_rate=0,
            time=0,
        )
        lifting = LiftingStats.objects.create(
            user=user,
            date_recorded=now,
            weight=0,
            reps=0,
            sets=0,
            volume=0,
            time=0,
        )
        return GarminUserData.objects.create(
            user=user,
            date_recorded=now,
            VO2_max=45,
            heart_rate=heart_rate,
            active_minutes=active_minutes,
            activty_type="running",
            activty_amount=30,
            running=running,
            cycling=cycling,
            swimming=swimming,
            lifting=lifting,
        )

    def _create_activity(self, user, days_ago=1, activity_type="running", duration_seconds=1800, distance=5000):
        return GarminActivity.objects.create(
            user=user,
            activity_id=f"{user.pk}-{activity_type}-{days_ago}-{duration_seconds}",
            activity_name=f"{activity_type} session",
            activity_type=activity_type,
            start_time_local=timezone.now() - timedelta(days=days_ago),
            distance_meters=distance,
            duration_seconds=duration_seconds,
            calories=300,
            payload={"ok": True},
        )

    def _create_activity_missing_start_time(self, user, days_ago=1, activity_type="running", duration_seconds=1800):
        # Some older imports may have no `start_time_local`; analysis should fall back to `imported_at`.
        activity = GarminActivity.objects.create(
            user=user,
            activity_id=f"{user.pk}-{activity_type}-missing-{days_ago}-{duration_seconds}",
            activity_name=f"{activity_type} session",
            activity_type=activity_type,
            start_time_local=None,
            distance_meters=0,
            duration_seconds=duration_seconds,
            calories=0,
            payload={"ok": True},
        )
        GarminActivity.objects.filter(pk=activity.pk).update(
            imported_at=timezone.now() - timedelta(days=days_ago)
        )
        return GarminActivity.objects.get(pk=activity.pk)

    def test_analysis_requires_login(self):
        response = self.client.get(reverse("garmin_bot_analysis"))
        self.assertEqual(response.status_code, 302)

    @patch("garmin_bot.services.urlopen", side_effect=URLError("network down"))
    def test_analysis_view_context_shape(self, _mock_urlopen):
        self._create_snapshot(self.user)
        self._create_activity(self.user, days_ago=2, activity_type="running", duration_seconds=2100, distance=6000)
        self._create_activity(self.user, days_ago=3, activity_type="strength_training", duration_seconds=2400, distance=0)
        self._create_activity(self.other, days_ago=2, activity_type="running", duration_seconds=4000, distance=10000)

        self.client.login(username="alice", password="password123")
        response = self.client.get(reverse("garmin_bot_analysis"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("overall_score", response.context)
        self.assertIn("running_analysis", response.context)
        self.assertIn("lifting_analysis", response.context)
        self.assertIn("risk_flags", response.context)
        self.assertIn("recommendations", response.context)

        running_analysis = response.context["running_analysis"]
        self.assertEqual(running_analysis["frequency_30d"], 1)
        self.assertGreaterEqual(response.context["overall_score"], 0)
        self.assertLessEqual(response.context["overall_score"], 100)

    @patch("garmin_bot.services.urlopen", side_effect=URLError("network down"))
    def test_api_failure_uses_fallback_recommendations(self, _mock_urlopen):
        self._create_snapshot(self.user)
        self._create_activity(self.user, days_ago=1, activity_type="running", duration_seconds=1800, distance=5000)
        self.client.login(username="alice", password="password123")
        response = self.client.get(reverse("garmin_bot_analysis"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["recommendations"][0]["name"], FALLBACK_RECOMMENDATIONS[0]["name"])

    @patch("garmin_bot.services.urlopen", side_effect=URLError("network down"))
    def test_undertraining_boundary(self, _mock_urlopen):
        self._create_snapshot(self.user, heart_rate=52, active_minutes=5)
        self._create_activity(self.user, days_ago=1, activity_type="running", duration_seconds=600, distance=1000)

        analysis = build_analysis_for_user(self.user)
        self.assertEqual(analysis["training_load"]["status"], "undertraining")

    @patch("garmin_bot.services.urlopen", side_effect=URLError("network down"))
    def test_overtraining_risk_boundary(self, _mock_urlopen):
        self._create_snapshot(self.user, heart_rate=78, active_minutes=180)
        for i in range(1, 8):
            self._create_activity(self.user, days_ago=i, activity_type="running", duration_seconds=16000, distance=12000)

        analysis = build_analysis_for_user(self.user)
        self.assertEqual(analysis["training_load"]["status"], "overtraining_risk")

    @patch("garmin_bot.services.urlopen", side_effect=URLError("network down"))
    def test_analysis_falls_back_to_imported_at_when_start_missing(self, _mock_urlopen):
        self._create_snapshot(self.user)
        self._create_activity_missing_start_time(self.user, days_ago=2, activity_type="running", duration_seconds=1200)
        self._create_activity_missing_start_time(self.user, days_ago=3, activity_type="strength_training", duration_seconds=1800)

        analysis = build_analysis_for_user(self.user)
        self.assertGreaterEqual(analysis["training_load"]["active_minutes_14d"], 1)
        self.assertEqual(analysis["running_analysis"]["frequency_30d"], 1)
        self.assertEqual(analysis["lifting_analysis"]["sessions_30d"], 1)


class GarminTimeParsingTests(TestCase):
    def test_start_time_local_naive_interpreted_in_current_timezone(self):
        from datetime import datetime as py_datetime
        from django.utils import timezone
        from garmin_bot.garmin_api import _parse_activity_datetime

        tz = timezone.get_current_timezone()
        payload = {"startTimeLocal": "2026-03-25 01:30:00"}
        dt = _parse_activity_datetime(payload)
        self.assertIsNotNone(dt)
        self.assertTrue(timezone.is_aware(dt))
        self.assertEqual(dt.tzinfo, tz)
        self.assertEqual(dt.replace(tzinfo=None), py_datetime(2026, 3, 25, 1, 30, 0))

    def test_start_time_gmt_naive_interpreted_as_utc(self):
        from datetime import datetime as py_datetime
        from django.utils import timezone
        from garmin_bot.garmin_api import _parse_activity_datetime
        from datetime import timezone as py_tz

        payload = {"startTimeGMT": "2026-03-25 01:30:00"}
        dt = _parse_activity_datetime(payload)
        self.assertIsNotNone(dt)
        self.assertTrue(timezone.is_aware(dt))
        self.assertEqual(dt.tzinfo, py_tz.utc)
        self.assertEqual(dt.replace(tzinfo=None), py_datetime(2026, 3, 25, 1, 30, 0))


class Vo2EstimatorTests(TestCase):
    def test_vo2_estimator_uses_fastest_plausible_run(self):
        activities = [
            # 5 km in 30 min => ~166.7 m/min => VO2 ~ 36.8
            {"activityType": {"typeKey": "running"}, "distance": 5000, "duration": 1800},
            # 10 km in 50 min => 200 m/min => VO2 ~ 43.5
            {"activityType": {"typeKey": "running"}, "distance": 10000, "duration": 3000},
            # Too short (<6 min) should be ignored
            {"activityType": {"typeKey": "running"}, "distance": 1200, "duration": 300},
            # Non-running should be ignored
            {"activityType": {"typeKey": "cycling"}, "distance": 20000, "duration": 3600},
        ]
        # Note: estimator now ignores runs <10 min, so the 5k/30m and 10k/50m remain valid.
        self.assertEqual(_estimate_vo2max_from_running_activities(activities), 44)

    def test_vo2_estimator_grade_adjusted_increases_vo2(self):
        # Same speed, but one run has elevation gain -> positive grade -> higher VO2.
        flat = [{"activityType": {"typeKey": "running"}, "distance": 10000, "duration": 3000}]
        hilly = [
            {
                "activityType": {"typeKey": "running"},
                "distance": 10000,
                "duration": 3000,
                "totalElevationGain": 200,  # avg grade 2%
            }
        ]
        self.assertGreater(_estimate_vo2max_from_running_activities(hilly), _estimate_vo2max_from_running_activities(flat))

    def test_hr_based_vo2_requires_plausible_inputs(self):
        activities = [
            {"activityType": {"typeKey": "running"}, "distance": 5000, "duration": 1800, "maxHR": 190},
            {"activityType": {"typeKey": "cycling"}, "distance": 20000, "duration": 3600, "maxHR": 175},
        ]
        self.assertEqual(_estimate_vo2max_from_heart_rate(activities, resting_hr=0), 0)
        self.assertGreater(_estimate_vo2max_from_heart_rate(activities, resting_hr=50), 0)

    def test_blending_rules(self):
        self.assertEqual(_blend_vo2_estimates(0, 0), 0)
        self.assertEqual(_blend_vo2_estimates(42, 0), 42)
        self.assertEqual(_blend_vo2_estimates(0, 45), 45)
        blended = _blend_vo2_estimates(50, 40)
        self.assertGreater(blended, 40)
        self.assertLess(blended, 50)
