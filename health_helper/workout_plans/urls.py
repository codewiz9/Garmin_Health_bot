from django.urls import path
from . import views

urlpatterns = [
    path('', views.WorkoutPlanListView.as_view(), name='workout_plan_list'),
    path('create/', views.WorkoutPlanCreateView.as_view(), name='workout_plan_create'),
    path('<int:pk>/update/', views.WorkoutPlanUpdateView.as_view(), name='workout_plan_update'),
    path('<int:pk>/delete/', views.WorkoutPlanDeleteView.as_view(), name='workout_plan_delete'),
    path('<int:pk>/progress/', views.WorkOutPLanProgress.as_view(), name='workout_plan_progress'),
    path('<int:pk>/toggle-active/', views.WorkoutPlanToggleActiveView.as_view(), name='workout_plan_toggle_active'),
    path('<int:pk>/complete/', views.WorkoutPlanCompleteView.as_view(), name='workout_plan_complete'),
    path('import/garmin/', views.ImportGarminWorkoutsView.as_view(), name='import_garmin_workouts'),
]
