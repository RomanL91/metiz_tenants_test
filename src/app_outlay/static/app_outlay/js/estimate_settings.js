/**
 * Модуль для работы с настройками сметы
 * Управляет модальным окном и API запросами для сохранения/загрузки настроек
 */

(function () {
    'use strict';

    // ====== КОНФИГУРАЦИЯ ======
    const CONFIG = {
        // Попробуйте изменить на нужный путь:
        // Вариант 1: apiUrl: '/api/estimates/{estimate_id}/settings/',
        // Вариант 2: apiUrl: '/api/v1/estimates/{estimate_id}/settings/',
        apiUrl: '/api/v1/estimates/{estimate_id}/settings/',
        estimateId: null, // будет установлен при инициализации
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

        // Загружаем текущие настройки при каждом открытии
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
        // Отключаем кнопку на время запроса
        if (elements.modalApply) {
            elements.modalApply.disabled = true;
            elements.modalApply.textContent = 'Сохранение...';
        }

        try {
            // Собираем данные из формы
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

            const payload = { settings_data: settings };
            const url = getApiUrl();

            console.log('📡 POST запрос:', url);
            console.log('📦 Данные:', payload);

            // Отправляем запрос
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

            // Успешно сохранено
            alert('✅ Настройки сметы успешно сохранены!');
            closeModal();

            // Можно вызвать событие для обновления других частей интерфейса
            document.dispatchEvent(new CustomEvent('estimate-settings-updated', {
                detail: { settings: data.settings_data }
            }));

            // Перезагружаем страницу для отображения изменений
            window.location.reload();

        } catch (error) {
            console.error('❌ Ошибка сохранения настроек:', error);
            alert('❌ Ошибка сохранения настроек. Проверьте консоль для деталей.');
        } finally {
            // Возвращаем кнопку в исходное состояние
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
        // Открытие модального окна
        if (elements.openBtn) {
            elements.openBtn.addEventListener('click', openModal);
        }

        // Закрытие модального окна
        if (elements.modalClose) {
            elements.modalClose.addEventListener('click', closeModal);
        }

        if (elements.modalCancel) {
            elements.modalCancel.addEventListener('click', closeModal);
        }

        // Клик вне модального окна
        if (elements.modal) {
            elements.modal.addEventListener('click', (e) => {
                if (e.target === elements.modal) {
                    closeModal();
                }
            });
        }

        // Сохранение настроек
        if (elements.modalApply) {
            elements.modalApply.addEventListener('click', saveSettings);
        }

        // Закрытие по Escape
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && elements.modal?.classList.contains('active')) {
                closeModal();
            }
        });

        // Enter в полях формы - сохранение
        [elements.objectName, elements.vatRate].forEach(input => {
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

    // Экспортируем функцию инициализации в глобальную область
    window.EstimateSettings = {
        init: init,
        open: openModal,
        close: closeModal,
        load: loadSettings,
        save: saveSettings,
        getApiUrl: getApiUrl, // для отладки
    };

})();