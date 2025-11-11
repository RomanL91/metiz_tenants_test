from django.urls import path

from app_works.views.import_view.views import WorkImportViewSet


app_name = "app_works"

urlpatterns = [
    path(
        "import/",
        WorkImportViewSet.as_view(),
        name="work-import",
    ),
]
