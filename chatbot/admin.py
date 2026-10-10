from django.contrib import admin

from .models import ChatLog


@admin.register(ChatLog)
class ChatLogAdmin(admin.ModelAdmin):
    list_display = ("created", "user", "intent", "status", "provider", "question")
    list_filter = ("status", "intent", "provider")
    readonly_fields = [f.name for f in ChatLog._meta.fields]
