from django.urls import path

from . import views

urlpatterns = [
    path("api/chatbot/", views.chat, name="chatbot"),
    path("api/chatbot/lich-su/", views.chat_history, name="chatbot_history"),
]
