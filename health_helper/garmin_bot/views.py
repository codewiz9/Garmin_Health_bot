from django.views.generic import TemplateView, ListView, RedirectView
from django.urls import reverse_lazy
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.utils import timezone
from datetime import timedelta
from .models import GarminUserData, GarminActivity, METERS_PER_MILE
from .garmin_api import fetch_and_update_garmin_data
from .services import build_analysis_for_user

# this view will display the garmin bot detail page
class GarminBotDetailView(LoginRequiredMixin, TemplateView):
    template_name = 'garmin_bot/garmin_bot_detail.html'

    @staticmethod
    def _meters_to_miles(meters: float | int) -> float:
        return float(meters or 0) / METERS_PER_MILE

    @staticmethod
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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Get the latest daily snapshot for the logged in user
        latest_data = GarminUserData.objects.filter(user=self.request.user).order_by('-date_recorded').first()
        context['latest_data'] = latest_data
        vo2 = getattr(latest_data, "VO2_max", 0) if latest_data else 0
        if vo2 and vo2 >= 50:
            context["vo2_rating"] = "Good"
            context["vo2_rating_variant"] = "success"
        elif vo2 and vo2 >= 40:
            context["vo2_rating"] = "Fair"
            context["vo2_rating_variant"] = "warning"
        elif vo2:
            context["vo2_rating"] = "Poor"
            context["vo2_rating_variant"] = "danger"
        else:
            context["vo2_rating"] = None
            context["vo2_rating_variant"] = "secondary"

        activities = (
            GarminActivity.objects.filter(user=self.request.user)
            .order_by("-start_time_local", "-imported_at")[:25]
        )
        context["recent_activities"] = activities

        summary = {
            "running": {"count": 0, "distance_meters": 0, "distance_miles": 0, "duration_seconds": 0},
            "cycling": {"count": 0, "distance_meters": 0, "distance_miles": 0, "duration_seconds": 0},
            "swimming": {"count": 0, "distance_meters": 0, "distance_miles": 0, "duration_seconds": 0},
            "lifting": {"count": 0, "distance_meters": 0, "distance_miles": 0, "duration_seconds": 0},
        }
        # Match the header copy: "Last 30 days", using import time as a fallback
        # when the activity is missing `start_time_local`.
        now = timezone.now()
        window_30d = now - timedelta(days=30)
        activity_qs = GarminActivity.objects.filter(user=self.request.user).filter(
            Q(start_time_local__gte=window_30d)
            | Q(start_time_local__isnull=True, imported_at__gte=window_30d)
        )
        for activity in activity_qs:
            bucket = self._activity_bucket(activity.activity_type)
            if bucket not in summary:
                continue
            summary[bucket]["count"] += 1
            summary[bucket]["distance_meters"] += activity.distance_meters or 0
            summary[bucket]["distance_miles"] += self._meters_to_miles(activity.distance_meters or 0)
            summary[bucket]["duration_seconds"] += activity.duration_seconds or 0
        # Convert seconds -> minutes for display (imperial output requirement).
        for bucket in summary:
            summary[bucket]["duration_minutes"] = float(summary[bucket].get("duration_seconds", 0) or 0) / 60.0
        context["activity_summary"] = summary
        return context

# this view will display all the garmnin data day by day and week by week and month by both 
class GarminBotListData(LoginRequiredMixin, ListView):
    model = GarminUserData
    template_name = 'garmin_bot/garmin_bot_data_list.html'
    context_object_name = 'garmin_data_list'
    
    def get_queryset(self):
        return GarminUserData.objects.filter(user=self.request.user).order_by('-date_recorded')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        latest = self.get_queryset().first()
        context["last_synced"] = getattr(latest, "date_recorded", None)
        context["last_aggregation_days"] = getattr(latest, "aggregation_days", None)
        return context

# this view will display all the users workout plans 
class GarminBotListPlan(ListView):
    pass

# this view will update the modle and the users data in the database
class GarminBotUpdateData(LoginRequiredMixin, RedirectView):
    url = reverse_lazy('garmin_bot_detail') # Redirect to detail view, update this URL name if necessary

    def get(self, request, *args, **kwargs):
        fetch_and_update_garmin_data(request.user)
        return super().get(request, *args, **kwargs)

#this view will display the stats of the users activity and progress
#It breaks down all importat stats related to overall fitness
class GarminBotStatsView(LoginRequiredMixin, TemplateView):
    pass

#this view will do the following anlysis:
#1. Looks at the users heart rate stress sleep and workout metrics to see if the user is overtraining or undertraining
#2. Look at the users running and useing Aerobic Decoupling Training Stress Score and Efficiency Factor and give the user a sorce and recmonadtion to improve their running
#3. Look at the users lifting stats using Brzycki Formula RPE & RIR and Tonnage and give them workouts and impovemts bases on the caulations use https://github.com/yuhonas/free-exercise-db for the workouts
class GarminBotAnlysis(LoginRequiredMixin, TemplateView):
    template_name = "garmin_bot/garmin_bot_analysis.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(build_analysis_for_user(self.request.user))
        return context