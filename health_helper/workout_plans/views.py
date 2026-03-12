from django.shortcuts import render
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin

# this view will display all the users workout plans 
class WorkoutPlanListView(ListView):
    pass

# this view will create a weekly workout plan for the user
class WorkoutPlanCreateView(CreateView):
    pass

# this view will update the weekly workout plan for  the user
class WorkoutPlanUpdateView(UpdateView):
    pass

# this view will delete the weekly workout plan for the user
class WorkoutPlanDeleteView(DeleteView):
    pass

# this view will allow the user to mark a workout plan as complete for the spcific day of the week
class WorkoutPlanCompleteView(UpdateView):
    pass
