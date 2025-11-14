from django.urls import path

from app_outlay.views import views as view_estimate_settings
from app_outlay.views.analysis_view import views as analysis_view
from app_outlay.views.autocomplete_view import views as autocomplete_view
from app_outlay.views.estimate_calc_view import views as estimate_calc_view
from app_outlay.views.estimate_mappings_view import \
    views as estimate_mappings_view
from app_outlay.views.estimate_overheads_view import \
    views as estimate_overheads_view
from app_outlay.views.estimate_vat_view import views as estimate_vat_view
from app_outlay.views.export_excel_view import views as export_excel_view

app_name = "app_outlay"

urlpatterns = [
    # API для работы с настройками сметы (GET и POST на один URL)
    path(
        "estimates/<int:estimate_id>/settings/",
        view_estimate_settings.estimate_settings,
        name="estimate-settings",
    ),
    # Расчёт ТК в контексте сметы
    path(
        "estimates/<int:estimate_id>/calc/",
        estimate_calc_view.EstimateCalcAPIView.as_view(),
        name="calculate",
    ),
    # Сохранение сопоставлений
    path(
        "estimates/<int:estimate_id>/save-mappings/",
        estimate_mappings_view.EstimateMappingsSaveAPIView.as_view(),
        name="save-mappings",
    ),
    # Накладные расходы
    path(
        "estimates/<int:estimate_id>/overheads/",
        estimate_overheads_view.EstimateOverheadsListAPIView.as_view(),
        name="overheads-list",
    ),
    path(
        "estimates/<int:estimate_id>/overheads/apply/",
        estimate_overheads_view.EstimateOverheadsApplyAPIView.as_view(),
        name="overheads-apply",
    ),
    path(
        "estimates/<int:estimate_id>/overheads/toggle/",
        estimate_overheads_view.EstimateOverheadsToggleAPIView.as_view(),
        name="overheads-toggle",
    ),
    path(
        "estimates/<int:estimate_id>/overheads/delete/",
        estimate_overheads_view.EstimateOverheadsDeleteAPIView.as_view(),
        name="overheads-delete",
    ),
    path(
        "estimates/<int:estimate_id>/overheads/quantity/",
        estimate_overheads_view.EstimateOverheadsQuantityAPIView.as_view(),
        name="overheads-quantity",
    ),
    # НДС
    path(
        "estimates/<int:estimate_id>/vat/",
        estimate_vat_view.EstimateVatStatusAPIView.as_view(),
        name="vat-status",
    ),
    path(
        "estimates/<int:estimate_id>/vat/toggle/",
        estimate_vat_view.EstimateVatToggleAPIView.as_view(),
        name="vat-toggle",
    ),
    path(
        "estimates/<int:estimate_id>/vat/set-rate/",
        estimate_vat_view.EstimateVatSetRateAPIView.as_view(),
        name="vat-set-rate",
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
    # Экспорт сметы в Excel
    path(
        "estimates/<int:estimate_id>/export-excel/",
        export_excel_view.EstimateExportExcelView.as_view(),
        name="export-excel",
    ),
    # Анализ сметы (данные для графиков)
    path(
        "estimates/<int:estimate_id>/analysis-data/",
        analysis_view.EstimateAnalysisDataView.as_view(),
        name="analysis-data",
    ),
]
