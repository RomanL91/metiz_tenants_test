// path: src/app_outlay/static/app_outlay/js/estimate_main.js
/**
 * Главный модуль инициализации сметы
 */
(function () {
    'use strict';

    // Ждём загрузки DOM
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    function init() {
        // Получаем данные из шаблона
        const CALC_ORDER = window.ESTIMATE_CALC_ORDER || [];
        const EXISTING_MAPPINGS = window.ESTIMATE_EXISTING_MAPPINGS || {};
        const ESTIMATE_ID = window.ESTIMATE_ID || null;

        if (!ESTIMATE_ID) {
            console.error('ESTIMATE_ID не определён');
            return;
        }

        // Формируем URLs (все на /api/v1/)
        const CALC_URL = `/api/v1/estimates/${ESTIMATE_ID}/calc/`;
        const SAVE_MAPPINGS_URL = `/api/v1/estimates/${ESTIMATE_ID}/save-mappings/`;
        const EXPORT_EXCEL_URL = `/api/v1/estimates/${ESTIMATE_ID}/export-excel/`;

        const OH_URLS = {
            list: `/api/v1/estimates/${ESTIMATE_ID}/overheads/`,
            apply: `/api/v1/estimates/${ESTIMATE_ID}/overheads/apply/`,
            toggle: `/api/v1/estimates/${ESTIMATE_ID}/overheads/toggle/`,
            delete: `/api/v1/estimates/${ESTIMATE_ID}/overheads/delete/`,
            quantity: `/api/v1/estimates/${ESTIMATE_ID}/overheads/quantity/`
        };

        const VAT_URLS = {
            status: `/api/v1/estimates/${ESTIMATE_ID}/vat/`,
            toggle: `/api/v1/estimates/${ESTIMATE_ID}/vat/toggle/`,
            setRate: `/api/v1/estimates/${ESTIMATE_ID}/vat/set-rate/`
        };

        // Инициализация модулей
        if (window.EstimateCalc) {
            window.EstimateCalc.init(CALC_ORDER, CALC_URL);
            window.EstimateCalc.prefillExistingMappings(EXISTING_MAPPINGS);
        }

        if (window.EstimateSections) {
            window.EstimateSections.init(CALC_ORDER);
        }

        if (window.EstimateMappingsSave) {
            window.EstimateMappingsSave.init(SAVE_MAPPINGS_URL, EXISTING_MAPPINGS);
        }

        if (window.EstimateOverheads) {
            window.EstimateOverheads.init(OH_URLS);
        }

        if (window.EstimateVat) {
            window.EstimateVat.init(VAT_URLS);
        }

        if (window.EstimateFilters) {
            window.EstimateFilters.init();
        }

        if (window.EstimateExport) {
            window.EstimateExport.init(EXPORT_EXCEL_URL);
        }

        console.log('✅ Все модули сметы инициализированы');
    }
})();