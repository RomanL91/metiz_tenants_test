from django.contrib import admin
from django.urls import path

from core.settings import CustomAdminSite

urlpatterns = [
    path("admin/", admin.site.urls),
]

admin.site.site_header = CustomAdminSite.site_header
admin.site.site_title = CustomAdminSite.site_title
admin.site.index_title = CustomAdminSite.index_title
