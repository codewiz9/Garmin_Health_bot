from django.urls import path
from . import views

urlpatterns = [
    path('', views.WorkoutPlanListView.as_view(), name='workout_plan_list'),
    path('create/', views.WorkoutPlanCreateView.as_view(), name='workout_plan_create'),
    path('<int:pk>/update/', views.WorkoutPlanUpdateView.as_view(), name='workout_plan_update'),
    path('<int:pk>/delete/', views.WorkoutPlanDeleteView.as_view(), name='workout_plan_delete'),
    path('<int:pk>/complete/', views.WorkoutPlanCompleteView.as_view(), name='workout_plan_complete'),
]
