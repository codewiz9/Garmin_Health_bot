from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse, HttpRequest
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, TemplateView
from datetime import date

from django.utils import timezone

from .models import WorkoutPlan, WorkoutPlanDay, WorkoutPlanItem, GarminWorkout
from .services import import_garmin_workouts_for_user

DAY_CHOICES = [choice[0] for choice in WorkoutPlanDay.DayOfWeek.choices]
CARDIO_CHOICES = list(WorkoutPlanDay.CardioActivity.choices)


def _upsert_plan_days_from_request(request: HttpRequest, plan: WorkoutPlan) -> None:
    for day_code in DAY_CHOICES:
        notes = request.POST.get(f"day_{day_code}_notes", "").strip()
        selected_activities = [
            (v or "").strip()
            for v in request.POST.getlist(f"day_{day_code}_workouts")
        ]
        selected_activities = [v for v in selected_activities if v]

        day_obj, _ = WorkoutPlanDay.objects.update_or_create(
            plan=plan,
            day=day_code,
            defaults={
                "notes": notes,
            },
        )

        existing_items = list(day_obj.items.select_related("workout").order_by("position", "id"))
        keep_ids: list[int] = []

        for position, selected_activity in enumerate(selected_activities):
            workout = None
            cardio_activity = ""
            if selected_activity.startswith("garmin:"):
                workout_id = selected_activity.split(":", 1)[1]
                workout = GarminWorkout.objects.filter(
                    pk=workout_id,
                    user=request.user,
                ).first()
            elif selected_activity.startswith("cardio:"):
                cardio_value = selected_activity.split(":", 1)[1]
                if cardio_value in dict(CARDIO_CHOICES):
                    cardio_activity = cardio_value

            # Skip invalid entries.
            if not workout and not cardio_activity:
                continue

            previous = existing_items[position] if position < len(existing_items) else None
            if previous:
                same_workout = (previous.workout_id == (workout.pk if workout else None))
                same_cardio = (previous.cardio_activity or "") == (cardio_activity or "")
                completed = previous.completed if (same_workout and same_cardio) else False

                previous.position = position
                previous.workout = workout
                previous.cardio_activity = cardio_activity
                previous.completed = completed
                previous.save(update_fields=["position", "workout", "cardio_activity", "completed"])
                keep_ids.append(previous.id)
            else:
                created = WorkoutPlanItem.objects.create(
                    day=day_obj,
                    position=position,
                    workout=workout,
                    cardio_activity=cardio_activity,
                    notes="",
                    completed=False,
                )
                keep_ids.append(created.id)

        # Delete extras (if user removed rows).
        qs = WorkoutPlanItem.objects.filter(day=day_obj)
        if keep_ids:
            qs = qs.exclude(id__in=keep_ids)
        qs.delete()


# this view will display all the users workout plans
class WorkoutPlanListView(LoginRequiredMixin, ListView):
    model = WorkoutPlan
    template_name = "workout_plans/workout_plan_list.html"
    context_object_name = "plans"

    def get_queryset(self):
        return (
            WorkoutPlan.objects.filter(user=self.request.user)
            .prefetch_related("days__items__workout")
            .order_by("-created_at")
        )


# this view will create a weekly workout plan for the user
class WorkoutPlanCreateView(LoginRequiredMixin, CreateView):
    model = WorkoutPlan
    template_name = "workout_plans/workout_plan_form.html"
    fields = ["name"]
    success_url = reverse_lazy("workout_plan_list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        garmin_workouts = GarminWorkout.objects.filter(user=self.request.user).order_by("name")
        context["garmin_workout_options"] = [
            {
                "value": f"garmin:{workout.pk}",
                "label": workout.name or workout.garmin_workout_id,
            }
            for workout in garmin_workouts
        ]
        context["cardio_activities"] = CARDIO_CHOICES
        context["day_rows"] = [
            {
                "value": value,
                "label": label,
                "existing": None,
                "selected_activities": [""],
            }
            for value, label in WorkoutPlanDay.DayOfWeek.choices
        ]
        return context

    def form_valid(self, form):
        form.instance.user = self.request.user
        response = super().form_valid(form)
        _upsert_plan_days_from_request(self.request, self.object)
        return response


# this view will update whether a day of the workout plan was completed or not
class WorkoutPlanUpdateView(LoginRequiredMixin, UpdateView):
    model = WorkoutPlan
    template_name = "workout_plans/workout_plan_form.html"
    fields = ["name"]
    success_url = reverse_lazy("workout_plan_list")

    def get_queryset(self):
        return WorkoutPlan.objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        garmin_workouts = GarminWorkout.objects.filter(user=self.request.user).order_by("name")
        context["garmin_workout_options"] = [
            {
                "value": f"garmin:{workout.pk}",
                "label": workout.name or workout.garmin_workout_id,
            }
            for workout in garmin_workouts
        ]
        context["cardio_activities"] = CARDIO_CHOICES
        day_initial = {
            d.day: d
            for d in self.object.days.all()
        }
        day_rows = []
        for value, label in WorkoutPlanDay.DayOfWeek.choices:
            existing = day_initial.get(value)
            selected_activities = [""]
            if existing:
                items = list(existing.items.select_related("workout").all())
                selected_activities = []
                for item in items:
                    if item.workout_id:
                        selected_activities.append(f"garmin:{item.workout_id}")
                    elif item.cardio_activity:
                        selected_activities.append(f"cardio:{item.cardio_activity}")
                if not selected_activities:
                    selected_activities = [""]
            day_rows.append(
                {
                    "value": value,
                    "label": label,
                    "existing": existing,
                    "selected_activities": selected_activities,
                }
            )
        context["day_rows"] = day_rows
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        _upsert_plan_days_from_request(self.request, self.object)
        return response


# this view will delete the workout plan
class WorkoutPlanDeleteView(LoginRequiredMixin, DeleteView):
    model = WorkoutPlan
    template_name = "workout_plans/workout_plan_confirm_delete.html"
    success_url = reverse_lazy("workout_plan_list")

    def get_queryset(self):
        return WorkoutPlan.objects.filter(user=self.request.user)


class WorkoutPlanCompleteView(LoginRequiredMixin, View):
    def post(self, request: HttpRequest, pk: int):
        item = get_object_or_404(WorkoutPlanItem, pk=pk, day__plan__user=request.user)
        item.completed = True
        item.save(update_fields=["completed"])
        return JsonResponse({"ok": True, "item_id": item.pk, "completed": item.completed})


class WorkoutPlanToggleActiveView(LoginRequiredMixin, View):
    """
    Toggle a workout plan between active/inactive.

    While active, `active_started_at` marks when the current activation began.
    When deactivating, elapsed time is accumulated into `active_total_weeks`.
    """

    def post(self, request: HttpRequest, pk: int):
        plan = get_object_or_404(WorkoutPlan, pk=pk, user=request.user)
        now = timezone.now()

        if plan.is_active:
            # Accumulate elapsed time into the total.
            delta_weeks = 0.0
            if plan.active_started_at:
                delta_weeks = (now - plan.active_started_at).total_seconds() / (7 * 24 * 60 * 60)

            plan.active_total_weeks = float(plan.active_total_weeks or 0) + delta_weeks
            plan.is_active = False
            plan.active_started_at = None
            plan.save(update_fields=["active_total_weeks", "is_active", "active_started_at", "updated_at"])
        else:
            plan.is_active = True
            plan.active_started_at = now
            plan.save(update_fields=["is_active", "active_started_at", "updated_at"])

        return JsonResponse(
            {
                "ok": True,
                "is_active": plan.is_active,
                "weeks_active": plan.weeks_active,
            }
        )


class ImportGarminWorkoutsView(LoginRequiredMixin, View):
    def post(self, request: HttpRequest):
        result = import_garmin_workouts_for_user(request.user)
        wants_json = request.headers.get("x-requested-with") == "XMLHttpRequest"
        if wants_json:
            status = 200 if result["ok"] else 400
            return JsonResponse(result, status=status)

        if result.get("ok"):
            return redirect("workout_plan_list")
        return JsonResponse(result, status=400)

#this view will display the progress of the users workout plan it will
#show missed days and link to to graphs for each workout that show 
#relvant stats about the workout
class WorkOutPLanProgress(LoginRequiredMixin, TemplateView):
    template_name = "workout_plans/workout_plan_progress.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        plan = get_object_or_404(WorkoutPlan, pk=self.kwargs["pk"], user=self.request.user)
        day_items = list(plan.days.prefetch_related("items__workout").all())
        day_by_code = {item.day: item for item in day_items}

        weekday_index = {
            "mon": 0,
            "tue": 1,
            "wed": 2,
            "thu": 3,
            "fri": 4,
            "sat": 5,
            "sun": 6,
        }
        today_weekday = date.today().weekday()

        progress_days = []
        completed_count = 0
        missed_count = 0
        rest_count = 0

        for day_code, day_label in WorkoutPlanDay.DayOfWeek.choices:
            day_entry = day_by_code.get(day_code)
            items = list(day_entry.items.all()) if day_entry else []
            non_rest_items = [
                i for i in items
                if not (not i.workout_id and i.cardio_activity == WorkoutPlanDay.CardioActivity.REST)
            ]
            is_rest = bool(items) and len(non_rest_items) == 0
            is_completed = bool(non_rest_items) and all(i.completed for i in non_rest_items)
            is_missed = bool(non_rest_items) and (not is_completed) and (weekday_index[day_code] < today_weekday)
            if is_rest:
                rest_count += 1
            elif is_completed:
                completed_count += 1
            if is_missed:
                missed_count += 1

            workout_label = "No workout assigned"
            if items:
                labels = []
                for i in items:
                    if i.workout:
                        labels.append(i.workout.name or i.workout.garmin_workout_id)
                    elif i.cardio_activity:
                        labels.append(i.get_cardio_activity_display())
                workout_label = ", ".join([l for l in labels if l]) or workout_label

            progress_days.append(
                {
                    "day_label": day_label,
                    "workout_label": workout_label,
                    "notes": day_entry.notes if day_entry else "",
                    "completed": is_completed,
                    "missed": is_missed,
                    "rest": is_rest,
                }
            )

        total_days = len(progress_days)
        trackable_days = max(total_days - rest_count, 0)
        completion_percent = int((completed_count / trackable_days) * 100) if trackable_days else 0

        context.update(
            {
                "plan": plan,
                "progress_days": progress_days,
                "completed_count": completed_count,
                "missed_count": missed_count,
                "total_days": total_days,
                "trackable_days": trackable_days,
                "rest_count": rest_count,
                "completion_percent": completion_percent,
            }
        )
        return context
