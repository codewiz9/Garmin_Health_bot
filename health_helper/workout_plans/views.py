from django.shortcuts import render
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin

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

