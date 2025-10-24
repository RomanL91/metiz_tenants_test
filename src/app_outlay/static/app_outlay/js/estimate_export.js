// path: src/app_outlay/static/app_outlay/js/estimate_export.js
/**
 * Модуль экспорта в Excel
 */
(function (window) {
    'use strict';

    const EstimateExport = {
        EXPORT_EXCEL_URL: '',

        init(exportExcelUrl) {
            this.EXPORT_EXCEL_URL = exportExcelUrl;
            this._bindExportButton();
        },

        _bindExportButton() {
            const btnExportExcel = document.getElementById('btn-export-excel');
            const statusSpan = document.getElementById('auto-match-status');

            if (!btnExportExcel) return;

            btnExportExcel.addEventListener('click', () => {
                statusSpan.textContent = '⏳ Формирование файла...';
                statusSpan.style.color = '#666';
                btnExportExcel.disabled = true;

                window.location.href = this.EXPORT_EXCEL_URL;

                setTimeout(() => {
                    statusSpan.textContent = '';
                    btnExportExcel.disabled = false;
                }, 2000);
            });
        }
    };

    window.EstimateExport = EstimateExport;
})(window);