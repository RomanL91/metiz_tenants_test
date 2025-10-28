from django.contrib import admin
from django.urls import path, include
from django.conf.urls.i18n import i18n_patterns

from core.settings import CustomAdminSite

# from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView


# urlpatterns = [
#     path("i18n/", include("django.conf.urls.i18n")),  # /i18n/setlang/ — встроенный переключатель
# ]


urlpatterns = [
    path("i18n/", include("django.conf.urls.i18n")),
    # path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    # path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
    path("api/v1/", include("app_outlay.urls")),
    path("api/v1/materials/", include("app_materials.urls")),
]

urlpatterns += i18n_patterns(
    path("admin/", admin.site.urls),
)

admin.site.site_header = CustomAdminSite.site_header
admin.site.site_title = CustomAdminSite.site_title
admin.site.index_title = CustomAdminSite.index_title
