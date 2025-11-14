/**
 * Модуль для работы с настройками сметы
 * Управляет модальным окном и API запросами для сохранения/загрузки настроек
 */

(function () {
    'use strict';

    // ====== КОНФИГУРАЦИЯ ======
    const CONFIG = {
        apiUrl: '/api/v1/estimates/{estimate_id}/settings/',
        estimateId: null,
    };

    // ====== DOM ЭЛЕМЕНТЫ ======
    const elements = {
        // Кнопка открытия
        openBtn: document.getElementById('btn-estimate-settings'),

        // Модальное окно
        modal: document.getElementById('estimate-settings-modal'),
        modalClose: document.getElementById('modal-close'),
        modalCancel: document.getElementById('modal-cancel'),
        modalApply: document.getElementById('modal-apply'),

        // Поля формы
        objectName: document.getElementById('estimate-object-name'),
        vatRate: document.getElementById('estimate-vat-rate'),
        laborHourRate: document.getElementById('estimate-labor-hour-rate'),
    };

    // ====== УТИЛИТЫ ======

    /**
     * Получение CSRF токена для Django
     */
    function getCsrfToken() {
        const input = document.querySelector('[name=csrfmiddlewaretoken]');
        if (input && input.value) return input.value;

        const match = document.cookie.match(/(?:^|;)\s*csrftoken=([^;]+)/);
        return match ? decodeURIComponent(match[1]) : '';
    }

    /**
     * Получение URL API для текущей сметы
     */
    function getApiUrl() {
        return CONFIG.apiUrl.replace('{estimate_id}', CONFIG.estimateId);
    }

    // ====== РАБОТА С МОДАЛЬНЫМ ОКНОМ ======

    /**
     * Открытие модального окна
     */
    function openModal() {
        if (!elements.modal) return;

        elements.modal.classList.add('active');
        document.body.style.overflow = 'hidden';

        loadSettings();
    }

    /**
     * Закрытие модального окна
     */
    function closeModal() {
        if (!elements.modal) return;

        elements.modal.classList.remove('active');
        document.body.style.overflow = '';
    }

    // ====== API ЗАПРОСЫ ======

    /**
     * Загрузка текущих настроек сметы
     */
    async function loadSettings() {
        const url = getApiUrl();
        console.log('📡 GET запрос:', url);

        try {
            const response = await fetch(url, {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken(),
                },
                credentials: 'include',
            });

            console.log('📊 GET ответ:', response.status, response.statusText);

            if (!response.ok) {
                const text = await response.text();
                console.error('❌ Ответ сервера:', text.substring(0, 500));
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            console.log('✅ Данные получены:', data);

            // Заполняем поля формы
            if (data.settings_data) {
                if (elements.objectName && data.settings_data.object_name !== undefined) {
                    elements.objectName.value = data.settings_data.object_name || '';
                }

                if (elements.vatRate && data.settings_data.vat_rate !== undefined) {
                    elements.vatRate.value = data.settings_data.vat_rate || '';
                }

                if (elements.laborHourRate && data.settings_data.labor_hour_rate !== undefined) {
                    elements.laborHourRate.value = data.settings_data.labor_hour_rate || '';
                }
            }

        } catch (error) {
            console.error('❌ Ошибка загрузки настроек:', error);
            alert('Ошибка загрузки настроек сметы. Проверьте консоль для деталей.');
        }
    }

    /**
     * Сохранение настроек сметы
     */
    async function saveSettings() {
        if (elements.modalApply) {
            elements.modalApply.disabled = true;
            elements.modalApply.textContent = 'Сохранение...';
        }

        try {
            const settings = {};

            if (elements.objectName) {
                const objectName = elements.objectName.value.trim();
                if (objectName) {
                    settings.object_name = objectName;
                }
            }

            if (elements.vatRate) {
                const vatRate = elements.vatRate.value.trim();
                if (vatRate) {
                    const vatRateNum = parseFloat(vatRate);
                    if (!isNaN(vatRateNum)) {
                        settings.vat_rate = vatRateNum;
                    }
                }
            }

            if (elements.laborHourRate) {
                const laborHourRate = elements.laborHourRate.value.trim();
                if (laborHourRate) {
                    const laborHourRateNum = parseFloat(laborHourRate);
                    if (!isNaN(laborHourRateNum) && laborHourRateNum > 0) {
                        settings.labor_hour_rate = laborHourRateNum;
                    }
                }
            }

            const payload = { settings_data: settings };
            const url = getApiUrl();

            console.log('📡 POST запрос:', url);
            console.log('📦 Данные:', payload);

            const response = await fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken(),
                },
                credentials: 'include',
                body: JSON.stringify(payload),
            });

            console.log('📊 POST ответ:', response.status, response.statusText);

            if (!response.ok) {
                const text = await response.text();
                console.error('❌ Ответ сервера:', text.substring(0, 500));
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            console.log('✅ Настройки сохранены:', data);

            alert('✅ Настройки сметы успешно сохранены!');
            closeModal();

            document.dispatchEvent(new CustomEvent('estimate-settings-updated', {
                detail: { settings: data.settings_data }
            }));

            // Перезагружаем для применения изменений к расчетам
            window.location.reload();

        } catch (error) {
            console.error('❌ Ошибка сохранения настроек:', error);
            alert('❌ Ошибка сохранения настроек. Проверьте консоль для деталей.');
        } finally {
            if (elements.modalApply) {
                elements.modalApply.disabled = false;
                elements.modalApply.textContent = 'Применить';
            }
        }
    }

    // ====== ОБРАБОТЧИКИ СОБЫТИЙ ======

    /**
     * Инициализация обработчиков событий
     */
    function initEventHandlers() {
        if (elements.openBtn) {
            elements.openBtn.addEventListener('click', openModal);
        }

        if (elements.modalClose) {
            elements.modalClose.addEventListener('click', closeModal);
        }

        if (elements.modalCancel) {
            elements.modalCancel.addEventListener('click', closeModal);
        }

        if (elements.modal) {
            elements.modal.addEventListener('click', (e) => {
                if (e.target === elements.modal) {
                    closeModal();
                }
            });
        }

        if (elements.modalApply) {
            elements.modalApply.addEventListener('click', saveSettings);
        }

        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && elements.modal?.classList.contains('active')) {
                closeModal();
            }
        });

        [elements.objectName, elements.vatRate, elements.laborHourRate].forEach(input => {
            if (input) {
                input.addEventListener('keydown', (e) => {
                    if (e.key === 'Enter' && elements.modal?.classList.contains('active')) {
                        e.preventDefault();
                        saveSettings();
                    }
                });
            }
        });
    }

    // ====== ИНИЦИАЛИЗАЦИЯ ======

    /**
     * Инициализация модуля
     * @param {number|string} estimateId - ID текущей сметы
     */
    function init(estimateId) {
        if (!estimateId) {
            console.error('Estimate ID не указан');
            return;
        }

        CONFIG.estimateId = estimateId;
        initEventHandlers();

        console.log('✅ Модуль настроек сметы инициализирован (ID:', estimateId + ')');
        console.log('📍 API URL:', getApiUrl());
    }

    // ====== ПУБЛИЧНЫЙ API ======

    window.EstimateSettings = {
        init: init,
        open: openModal,
        close: closeModal,
        load: loadSettings,
        save: saveSettings,
        getApiUrl: getApiUrl,
    };

})();