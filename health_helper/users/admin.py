from django.contrib import admin
from .models import GarminToken

@admin.register(GarminToken)
class GarminTokenAdmin(admin.ModelAdmin):
    list_display = ('user', 'garmin_username')
    search_fields = ('user__username', 'garmin_username')
    readonly_fields = ('token_data',)
