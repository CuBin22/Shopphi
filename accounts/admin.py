from django.contrib import admin

from .models import Profile


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "phone", "failed_logins", "locked_until")
    list_filter = ("role",)
    search_fields = ("user__username", "user__first_name", "phone")
