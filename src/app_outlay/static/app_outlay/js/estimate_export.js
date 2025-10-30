// path: src/app_outlay/static/app_outlay/js/estimate_export.js
/**
 * Модуль экспорта в Excel
 * 
 * Использует стандартный подход Django:
 * - Success: скачивание файла
 * - Error: редирект с Django messages
 */
(function (window) {
    'use strict';

    const EstimateExport = {
        EXPORT_EXCEL_URL: '',

        /**
         * Инициализация модуля экспорта.
         * 
         * @param {string} exportExcelUrl - URL для экспорта Excel
         * 
         * @example
         * EstimateExport.init('/api/outlay/estimates/123/export-excel/');
         */
        init(exportExcelUrl) {
            this.EXPORT_EXCEL_URL = exportExcelUrl;
            this._bindExportButton();
            console.log('✅ Модуль экспорта инициализирован');
        },

        /**
         * Привязка обработчика к кнопке экспорта.
         * 
         * При клике:
         * 1. Показывает индикатор загрузки
         * 2. Инициирует скачивание файла
         * 3. Скрывает индикатор через 2 секунды
         * 
         * Если возникла ошибка - Django перезагрузит страницу
         * с сообщением об ошибке через messages framework.
         */
        _bindExportButton() {
            const btnExportExcel = document.getElementById('btn-export-excel');
            const statusSpan = document.getElementById('auto-match-status');

            if (!btnExportExcel) {
                console.warn('⚠️ Кнопка экспорта не найдена');
                return;
            }

            btnExportExcel.addEventListener('click', () => {
                // Показываем индикатор загрузки
                if (statusSpan) {
                    statusSpan.textContent = '⏳ Формирование файла...';
                    statusSpan.style.color = '#666';
                }
                btnExportExcel.disabled = true;

                // Инициируем скачивание
                // При успехе - браузер скачает файл
                // При ошибке - Django сделает редирект с messages
                window.location.href = this.EXPORT_EXCEL_URL;

                // Скрываем индикатор через 2 секунды
                // (если была ошибка - страница перезагрузится раньше)
                setTimeout(() => {
                    if (statusSpan) {
                        statusSpan.textContent = '';
                    }
                    btnExportExcel.disabled = false;
                }, 2000);
            });

            console.log('✅ Обработчик кнопки экспорта установлен');
        }
    };

    window.EstimateExport = EstimateExport;
})(window);