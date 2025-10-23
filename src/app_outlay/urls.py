from django.urls import path

from app_outlay.views import views as view_estimate_settings
from app_outlay.views.autocomplete_view import views as autocomplete_view

app_name = "app_outlay"

urlpatterns = [
    # API для работы с настройками сметы (GET и POST на один URL)
    path(
        "estimates/<int:estimate_id>/settings/",
        view_estimate_settings.estimate_settings,
        name="estimate-settings",
    ),
    # Автокомплит: поиск ТК по названию
    path(
        "search/",
        autocomplete_view.TechnicalCardAutocompleteView.as_view(),
        name="search",
    ),
    # Batch-сопоставление строк с ТК
    path(
        "batch-match/",
        autocomplete_view.TechnicalCardBatchMatchView.as_view(),
        name="batch-match",
    ),
]
