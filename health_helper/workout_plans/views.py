from django.http import JsonResponse, HttpRequest
from django.shortcuts import get_object_or_404
from django.views import View
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin

from .models import WorkoutPlanDay
from .services import import_garmin_workouts_for_user

# this view will display all the users workout plans 
class WorkoutPlanListView(ListView):
    pass

# this view will create a weekly workout plan for the user
class WorkoutPlanCreateView(CreateView):
    pass

# this view will update wether a day of the workout plan was completed or not
# check every day defult to not complet if user dose not log
class WorkoutPlanUpdateView(UpdateView):
    pass

# this view will delete the workoout pkan
class WorkoutPlanDeleteView(DeleteView):
    pass


class WorkoutPlanCompleteView(LoginRequiredMixin, View):
    def post(self, request: HttpRequest, pk: int):
        day = get_object_or_404(WorkoutPlanDay, pk=pk, plan__user=request.user)
        day.completed = True
        day.save(update_fields=["completed"])
        return JsonResponse({"ok": True, "day_id": day.pk, "completed": day.completed})


class ImportGarminWorkoutsView(LoginRequiredMixin, View):
    def post(self, request: HttpRequest):
        result = import_garmin_workouts_for_user(request.user)
        status = 200 if result["ok"] else 400
        return JsonResponse(result, status=status)

