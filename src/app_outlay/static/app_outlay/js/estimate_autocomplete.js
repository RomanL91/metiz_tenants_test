/**
 * Модуль автокомплита и автосопоставления технических карт
 * 
 * Функционал:
 * - Автокомплит поиска ТК (ручной ввод)
 * - Batch-сопоставление всех строк (кнопка "Автосопоставить ТК")
 * - Интеграция с основным скриптом через triggerRowCalc() и updateSummary()
 */

(function () {
    'use strict';

    // ========== КОНФИГУРАЦИЯ ==========
    const API_BASE = '/api/v1';
    const AUTOCOMPLETE_URL = `${API_BASE}/search/`;
    const BATCH_MATCH_URL = `${API_BASE}/batch-match/`;

    // ========== УТИЛИТЫ ==========

    /**
     * Получить CSRF токен из cookie или из формы
     */
    function getCsrfToken() {
        const input = document.querySelector('[name=csrfmiddlewaretoken]');
        if (input && input.value) return input.value;
        const m = document.cookie.match(/(?:^|;)\s*csrftoken=([^;]+)/);
        return m ? decodeURIComponent(m[1]) : '';
    }

    /**
     * Поиск ТК по запросу (GET /api/v1/search/?q=...)
     * @param {string} q - Поисковый запрос
     * @returns {Promise<Array>} - Массив результатов [{id, text}, ...]
     */
    async function searchTC(q) {
        try {
            const url = `${AUTOCOMPLETE_URL}?q=${encodeURIComponent(q)}`;
            const response = await fetch(url, {
                method: 'GET',
                headers: {
                    'Accept': 'application/json',
                }
            });

            if (!response.ok) {
                console.error('Search failed:', response.status);
                return [];
            }

            const data = await response.json();
            return data.results || [];
        } catch (e) {
            console.error('Search error:', e);
            return [];
        }
    }

    /**
     * Batch-сопоставление строк с ТК (POST /api/v1/batch-match/)
     * @param {Array} items - Массив элементов [{row_index, name, unit}, ...]
     * @returns {Promise<Object>} - {ok: boolean, results: Array, error?: string}
     */
    async function batchMatch(items) {
        try {
            const response = await fetch(BATCH_MATCH_URL, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken(),
                },
                body: JSON.stringify({ items })
            });

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                return {
                    ok: false,
                    error: errorData.error || `HTTP ${response.status}`,
                    results: []
                };
            }

            const data = await response.json();
            return {
                ok: true,
                results: data.results || [],
                error: null
            };
        } catch (e) {
            console.error('Batch match error:', e);
            return {
                ok: false,
                error: String(e),
                results: []
            };
        }
    }

    // ========== АВТОКОМПЛИТ (ручной ввод) ==========

    function triggerRowCalc(tr) {
        if (!tr) return Promise.resolve();

        if (window.EstimateCalc && typeof window.EstimateCalc.triggerRowCalc === 'function') {
            return window.EstimateCalc.triggerRowCalc(tr);
        }

        console.warn('EstimateCalc.triggerRowCalc недоступен');
        return Promise.resolve();
    }

    function requestSummaryUpdate(delay = 0) {
        if (window.EstimateCalc && typeof window.EstimateCalc.updateSummary === 'function') {
            if (delay > 0) {
                setTimeout(() => window.EstimateCalc.updateSummary(), delay);
            } else {
                window.EstimateCalc.updateSummary();
            }
        } else {
            console.warn('EstimateCalc.updateSummary недоступен');
        }
    }

    /**
     * Инициализация автокомплита для одного input поля
     * @param {HTMLInputElement} input - Поле ввода
     */
    function attachAutocomplete(input) {
        let autocompleteBox = null;

        input.addEventListener('input', async function () {
            const query = input.value.trim();

            // Удаляем старый автокомплит
            if (autocompleteBox) {
                autocompleteBox.remove();
                autocompleteBox = null;
            }

            // Минимум 2 символа для поиска
            if (query.length < 2) return;

            // Ищем ТК
            const items = await searchTC(query);
            if (items.length === 0) return;

            // Создаём dropdown
            const rect = input.getBoundingClientRect();
            autocompleteBox = document.createElement('div');
            Object.assign(autocompleteBox.style, {
                position: 'absolute',
                background: '#fff',
                border: '1px solid #ddd',
                borderRadius: '4px',
                boxShadow: '0 2px 8px rgba(0,0,0,0.15)',
                zIndex: '10000',
                maxHeight: '220px',
                overflow: 'auto',
                left: (rect.left + window.scrollX) + 'px',
                top: (rect.bottom + window.scrollY) + 'px',
                minWidth: rect.width + 'px'
            });

            // Заполняем результатами
            items.forEach(item => {
                const option = document.createElement('div');
                option.textContent = item.text;
                option.style.cssText = 'padding:8px 12px; cursor:pointer; transition:background 0.1s;';

                option.addEventListener('mouseenter', function () {
                    this.style.background = '#f0f0f0';
                });

                option.addEventListener('mouseleave', function () {
                    this.style.background = '';
                });

                option.addEventListener('mousedown', function (e) {
                    e.preventDefault(); // Предотвращаем blur

                    // Устанавливаем значение
                    input.value = item.text;
                    input.dataset.id = item.id;
                    input.dataset.text = item.text;

                    // Показываем кнопку очистки
                    const clearBtn = input.parentElement?.querySelector('.tc-clear-btn');
                    if (clearBtn) clearBtn.style.display = 'block';

                    // Пересчитываем строку
                    const tr = input.closest('tr');

                    triggerRowCalc(tr);

                    // Закрываем автокомплит
                    if (autocompleteBox) {
                        autocompleteBox.remove();
                        autocompleteBox = null;
                    }
                });

                autocompleteBox.appendChild(option);
            });

            document.body.appendChild(autocompleteBox);

            // Закрытие по клику вне
            const clickAway = (ev) => {
                if (autocompleteBox && !autocompleteBox.contains(ev.target) && ev.target !== input) {
                    autocompleteBox.remove();
                    autocompleteBox = null;
                    document.removeEventListener('mousedown', clickAway);
                }
            };

            setTimeout(() => {
                document.addEventListener('mousedown', clickAway);
            }, 0);
        });
    }

    /**
     * Инициализация обёртки для input (кнопка очистки)
     * @param {HTMLInputElement} input - Поле ввода
     */
    function wrapInputWithClearButton(input) {
        // Проверяем, не обёрнут ли уже
        if (input.parentElement?.classList.contains('tc-input-wrapper')) {
            return;
        }

        // Создаём обёртку
        const wrapper = document.createElement('div');
        wrapper.className = 'tc-input-wrapper';
        input.parentNode.insertBefore(wrapper, input);
        wrapper.appendChild(input);

        // Кнопка очистки
        const clearBtn = document.createElement('button');
        clearBtn.innerHTML = '✕';
        clearBtn.type = 'button';
        clearBtn.className = 'tc-clear-btn';
        clearBtn.title = 'Очистить';
        wrapper.appendChild(clearBtn);

        // Показываем/скрываем кнопку
        const toggleClearBtn = () => {
            clearBtn.style.display = input.value.trim() ? 'block' : 'none';
        };

        // Обработчик очистки
        clearBtn.addEventListener('click', () => {
            input.value = '';
            input.dataset.id = '';
            input.dataset.text = '';
            input.style.background = '';
            clearBtn.style.display = 'none';

            // Очищаем расчёты в строке
            const tr = input.closest('tr');
            if (tr) {
                tr.querySelectorAll('.opt-cell .sys').forEach(el => {
                    el.textContent = '—';
                });
            }

            // Обновляем итоги
            requestSummaryUpdate(100);
        });

        // Отслеживаем изменения
        input.addEventListener('input', () => {
            const currentValue = input.value.trim();
            const datasetText = input.dataset.text || '';

            // Если значение изменилось вручную - сбрасываем ID
            if (currentValue !== datasetText) {
                input.dataset.id = '';
                input.dataset.text = '';

                const tr = input.closest('tr');
                if (tr) {
                    tr.querySelectorAll('.opt-cell .sys').forEach(el => {
                        el.textContent = '—';
                    });
                }

                requestSummaryUpdate(100);

            }

            toggleClearBtn();
        });

        input.addEventListener('blur', () => {
            if (!input.value.trim()) {
                input.dataset.id = '';
                input.dataset.text = '';
                input.style.background = '';

                const tr = input.closest('tr');
                if (tr) {
                    tr.querySelectorAll('.opt-cell .sys').forEach(el => {
                        el.textContent = '—';
                    });
                }

                requestSummaryUpdate(100);

            }
        });

        toggleClearBtn();
    }

    // ========== BATCH-СОПОСТАВЛЕНИЕ ==========

    /**
     * Обработчик кнопки "Автосопоставить ТК"
     */
    function initBatchMatch() {
        const btnAutoMatch = document.getElementById('btn-auto-match');
        const statusSpan = document.getElementById('auto-match-status');

        if (!btnAutoMatch) return;

        btnAutoMatch.addEventListener('click', async function () {
            btnAutoMatch.disabled = true;

            if (statusSpan) {
                statusSpan.textContent = 'Ищу совпадения...';
                statusSpan.style.color = '#666';
            }

            // Собираем все строки таблицы
            const rows = document.querySelectorAll('#tc-map tbody tr:not(.sec-hdr)');
            const items = [];

            rows.forEach(tr => {
                const rowIndex = tr.dataset.row;
                const nameCell = tr.querySelector('td:nth-child(1)');
                const unitCell = tr.querySelector('td:nth-child(2)');

                if (nameCell && unitCell && rowIndex) {
                    items.push({
                        row_index: parseInt(rowIndex),
                        name: nameCell.textContent.trim(),
                        unit: unitCell.textContent.trim()
                    });
                }
            });

            if (items.length === 0) {
                if (statusSpan) {
                    statusSpan.textContent = '❌ Нет строк для сопоставления';
                    statusSpan.style.color = '#721c24';
                }
                btnAutoMatch.disabled = false;
                return;
            }

            // Выполняем batch-сопоставление
            const response = await batchMatch(items);

            if (!response.ok) {
                if (statusSpan) {
                    statusSpan.textContent = '❌ Ошибка: ' + (response.error || 'unknown');
                    statusSpan.style.color = '#721c24';
                }
                btnAutoMatch.disabled = false;
                return;
            }

            // Применяем результаты
            let matchedCount = 0;
            const calcPromises = [];

            response.results.forEach(result => {
                const tr = document.querySelector(`tr[data-row="${result.row_index}"]`);
                if (!tr) return;

                const tcInput = tr.querySelector('.js-tc-autocomplete');
                const qtyInput = tr.querySelector('.qty-input');

                if (!tcInput) return;

                const existingMappings = (window.EstimateMappingsSave && window.EstimateMappingsSave.EXISTING_MAPPINGS) || {};
                const existingMapping = existingMappings[String(result.row_index)];
                if (existingMapping && existingMapping.tc_id) {
                    // Сохраняем уже сохранённые сопоставления без изменений
                    return;
                }

                if (result.matched_tc_id && result.matched_tc_text) {
                    // Устанавливаем значение
                    tcInput.value = result.matched_tc_text;
                    tcInput.dataset.id = result.matched_tc_id;
                    tcInput.dataset.text = result.matched_tc_text;

                    // Цвет фона в зависимости от схожести
                    if (result.similarity >= 0.9) {
                        tcInput.style.background = '#d4edda'; // Зелёный
                    } else if (result.similarity >= 0.5) {
                        tcInput.style.background = '#fff3cd'; // Жёлтый
                    } else {
                        tcInput.style.background = '#f8d7da'; // Красный
                    }

                    // Показываем кнопку очистки
                    const clearBtn = tcInput.parentElement?.querySelector('.tc-clear-btn');
                    if (clearBtn) clearBtn.style.display = 'block';

                    // Пересчитываем строку если есть количество
                    if (qtyInput && qtyInput.value && parseFloat(qtyInput.value) > 0) {
                        calcPromises.push(triggerRowCalc(tr));
                    }

                    matchedCount++;
                }
            });

            // Ждём завершения всех пересчётов
            if (calcPromises.length > 0) {
                await Promise.all(calcPromises);
            }

            // Обновляем итоги
            requestSummaryUpdate(500);

            // Статус
            if (statusSpan) {
                statusSpan.textContent = `✅ Сопоставлено: ${matchedCount} из ${items.length}`;
                statusSpan.style.color = '#155724';
            }

            btnAutoMatch.disabled = false;
        });
    }

    // ========== ИНИЦИАЛИЗАЦИЯ ==========

    /**
     * Главная функция инициализации
     */
    function init() {
        console.log('🤖 Инициализация модуля автокомплита ТК');

        // Инициализируем автокомплит для всех полей
        const inputs = document.querySelectorAll('.js-tc-autocomplete, .tc-lookup');
        inputs.forEach(input => {
            wrapInputWithClearButton(input);
            attachAutocomplete(input);
        });

        // Инициализируем batch-сопоставление
        initBatchMatch();

        console.log(`✅ Автокомплит инициализирован для ${inputs.length} полей`);
    }

    // Экспортируем в глобальную область
    window.EstimateAutocomplete = {
        init,
        searchTC,
        batchMatch,
        attachAutocomplete,
        wrapInputWithClearButton
    };

    // Автоматическая инициализация при загрузке DOM
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();