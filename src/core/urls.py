from django.contrib import admin
from django.urls import path, include
from django.conf.urls.i18n import i18n_patterns
from django.views.i18n import JavaScriptCatalog

from core.settings import CustomAdminSite

# urlpatterns = [
#     path("i18n/", include("django.conf.urls.i18n")),  # /i18n/setlang/ — встроенный переключатель
# ]


urlpatterns = [
    path("i18n/", include("django.conf.urls.i18n")),
    path("api/v1/", include("app_outlay.urls")),
]

urlpatterns += i18n_patterns(
    path("admin/", admin.site.urls),
)

admin.site.site_header = CustomAdminSite.site_header
admin.site.site_title = CustomAdminSite.site_title
admin.site.index_title = CustomAdminSite.index_title
