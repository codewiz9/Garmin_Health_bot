from django.contrib import admin
from .models import (
    GarminUserData,
    RunningStats,
    SwimmingStats,
    CyclingStats,
    LiftingStats,
    GarminActivity,
)


@admin.register(GarminUserData)
class GarminUserDataAdmin(admin.ModelAdmin):
    list_display = ("user", "date_recorded", "VO2_max", "heart_rate", "active_minutes", "activty_type")
    list_filter = ("date_recorded", "activty_type")
    search_fields = ("user__username",)


@admin.register(RunningStats)
class RunningStatsAdmin(admin.ModelAdmin):
    list_display = ("user", "date_recorded", "distance", "avg_heart_rate", "time")
    list_filter = ("date_recorded",)
    search_fields = ("user__username",)


@admin.register(SwimmingStats)
class SwimmingStatsAdmin(admin.ModelAdmin):
    list_display = ("user", "date_recorded", "distance", "avg_heart_rate", "time")
    list_filter = ("date_recorded",)
    search_fields = ("user__username",)


@admin.register(CyclingStats)
class CyclingStatsAdmin(admin.ModelAdmin):
    list_display = ("user", "date_recorded", "distance", "avg_heart_rate", "time")
    list_filter = ("date_recorded",)
    search_fields = ("user__username",)


@admin.register(LiftingStats)
class LiftingStatsAdmin(admin.ModelAdmin):
    list_display = ("user", "date_recorded", "weight", "reps", "sets", "volume", "time")
    list_filter = ("date_recorded",)
    search_fields = ("user__username",)


@admin.register(GarminActivity)
class GarminActivityAdmin(admin.ModelAdmin):
    list_display = ("user", "activity_id", "activity_name", "activity_type", "start_time_local", "imported_at")
    list_filter = ("activity_type", "start_time_local", "imported_at")
    search_fields = ("user__username", "activity_id", "activity_name")
