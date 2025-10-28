from django.urls import path

from app_materials.views.import_view.views import MaterialImportViewSet


app_name = "app_materials"

urlpatterns = [
    path(
        "import/",
        MaterialImportViewSet.as_view(),
        name="material-import",
    ),
]
