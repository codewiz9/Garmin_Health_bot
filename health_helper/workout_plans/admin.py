from django.contrib import admin
from .models import GarminWorkout, WorkoutPlan, WorkoutPlanDay, WorkoutPlanItem


@admin.register(WorkoutPlan)
class WorkoutPlanAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "name", "is_active", "active_total_weeks", "created_at", "updated_at")
    list_filter = ("created_at", "updated_at")
    search_fields = ("user__username", "name")


@admin.register(GarminWorkout)
class GarminWorkoutAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "garmin_workout_id", "name", "updated_at_garmin", "imported_at")
    list_filter = ("updated_at_garmin", "imported_at")
    search_fields = ("user__username", "garmin_workout_id", "name")


@admin.register(WorkoutPlanDay)
class WorkoutPlanDayAdmin(admin.ModelAdmin):
    list_display = ("id", "plan", "day", "notes")
    list_filter = ("day",)
    search_fields = ("plan__name", "plan__user__username", "notes")


@admin.register(WorkoutPlanItem)
class WorkoutPlanItemAdmin(admin.ModelAdmin):
    list_display = ("id", "day", "position", "workout", "cardio_activity", "completed")
    list_filter = ("completed", "cardio_activity")
    search_fields = ("day__plan__name", "day__plan__user__username", "workout__name", "workout__garmin_workout_id")
