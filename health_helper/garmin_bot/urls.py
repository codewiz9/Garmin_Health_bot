from django.urls import path
from . import views

urlpatterns = [
    path('', views.GarminBotDetailView.as_view(), name='garmin_bot_detail'),
    path('update/', views.GarminBotUpdateData.as_view(), name='garmin_bot_update_data'),
    path('list/', views.GarminBotListData.as_view(), name='garmin_bot_list_data'),
    path('analysis/', views.GarminBotAnlysis.as_view(), name='garmin_bot_analysis'),
]
