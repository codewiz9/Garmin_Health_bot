from django.shortcuts import render
from django.views.generic import TemplateView, DetailView, ListView, RedirectView, FormView, CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from django.contrib.auth.mixins import LoginRequiredMixin
from .models import GarminUserData, RunningStats, CyclingStats, SwimmingStats, LiftingStats
from .garmin_api import fetch_and_update_garmin_data

# this view will display the garmin bot detail page
class GarminBotDetailView(LoginRequiredMixin, TemplateView):
    template_name = 'garmin_bot/garmin_bot_detail.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Get the latest daily snapshot for the logged in user
        latest_data = GarminUserData.objects.filter(user=self.request.user).order_by('-date_recorded').first()
        context['latest_data'] = latest_data
        return context

# this view will display all the garmnin data day by day and week by week and month by both 
class GarminBotListData(LoginRequiredMixin, ListView):
    model = GarminUserData
    template_name = 'garmin_bot/garmin_bot_data_list.html'
    context_object_name = 'garmin_data_list'
    
    def get_queryset(self):
        return GarminUserData.objects.filter(user=self.request.user).order_by('-date_recorded')

# this view will display all the users workout plans 
class GarminBotListPlan(ListView):
    pass

# this view will update the modle and the users data in the database
class GarminBotUpdateData(LoginRequiredMixin, RedirectView):
    url = reverse_lazy('garmin_bot_detail') # Redirect to detail view, update this URL name if necessary

    def get(self, request, *args, **kwargs):
        fetch_and_update_garmin_data(request.user)
        return super().get(request, *args, **kwargs)