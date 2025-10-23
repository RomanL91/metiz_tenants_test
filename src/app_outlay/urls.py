from django.urls import path
from app_outlay.views import views

app_name = "app_outlay"

urlpatterns = [
    # API для работы с настройками сметы (GET и POST на один URL)
    path(
        "estimates/<int:estimate_id>/settings/",
        views.estimate_settings,
        name="estimate-settings",
    ),
]
