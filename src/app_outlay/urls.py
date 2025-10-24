from django.urls import path

from app_outlay.views import views as view_estimate_settings
from app_outlay.views.autocomplete_view import views as autocomplete_view
from app_outlay.views.estimate_calc_view import views as estimate_calc_view
from app_outlay.views.estimate_mappings_view import views as estimate_mappings_view
from app_outlay.views.estimate_overheads_view import views as estimate_overheads_view

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
    # URL конфигурация для модуля расчёта сметы.
    path(
        "<int:estimate_id>/calc/",
        estimate_calc_view.EstimateCalcAPIView.as_view(),
        name="calculate",
    ),
    # созранение сметы
    path(
        "save-mappings/",
        estimate_mappings_view.EstimateMappingsSaveAPIView.as_view(),
        name="save_mappings",
    ),
    #  НР
    path(
        "list-oh/",
        estimate_overheads_view.EstimateOverheadsListAPIView.as_view(),
        name="list",
    ),
    path(
        "apply/",
        estimate_overheads_view.EstimateOverheadsApplyAPIView.as_view(),
        name="apply",
    ),
    path(
        "toggle/",
        estimate_overheads_view.EstimateOverheadsToggleAPIView.as_view(),
        name="toggle",
    ),
    path(
        "delete/",
        estimate_overheads_view.EstimateOverheadsDeleteAPIView.as_view(),
        name="delete",
    ),
    path(
        "quantity/",
        estimate_overheads_view.EstimateOverheadsQuantityAPIView.as_view(),
        name="quantity",
    ),
]
