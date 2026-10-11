from django.contrib import admin
from django.urls import include, path
from django.conf import settings
from django.conf.urls.static import static

admin.site.site_header = "Shopphi - Quản trị sàn"
admin.site.site_title = "Shopphi"
admin.site.index_title = "Quản trị sàn"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("accounts.urls")),
    path("", include("shopping.urls")),
    path("", include("chatbot.urls")),
    path("", include("catalog.urls")),
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
