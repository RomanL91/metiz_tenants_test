/**
 * Модуль расчётов технических карт
 */
(function (window) {
    'use strict';

    const EstimateCalc = {
        CALC_ORDER: [],
        CALC_URL: '',
        BATCH_CALC_URL: '',

        init(calcOrder, calcUrl, batchCalcUrl) {
            this.CALC_ORDER = calcOrder;
            this.CALC_URL = calcUrl;
            this.BATCH_CALC_URL = batchCalcUrl;
            this._bindQtyInputs();
        },

        _bindQtyInputs() {
            document.querySelectorAll('#tc-map .qty-input').forEach(inp => {
                inp.addEventListener('change', () => this.triggerRowCalc(inp.closest('tr')));
                inp.addEventListener('blur', () => this.triggerRowCalc(inp.closest('tr')));
            });
        },

        async triggerRowCalc(tr) {
            if (!tr) return;

            const inpTC = tr.querySelector('.js-tc-autocomplete');
            const inpQty = tr.querySelector('.qty-input');
            const tcId = parseInt(inpTC?.dataset.id || '0', 10) || 0;
            const qty = parseFloat((inpQty?.value || '').replace(',', '.')) || 0;

            // Очищаем ячейки и данные
            tr.querySelectorAll('.opt-cell .sys').forEach(el => el.textContent = '—');
            delete tr.dataset.calcData;

            if (!tcId || !isFinite(qty) || qty === 0) return;

            try {
                const resp = await fetch(this.CALC_URL + '?tc=' + tcId + '&qty=' + encodeURIComponent(qty));
                const data = await resp.json();

                if (!data.ok) return;

                const calc = data.calc || {};

                // КРИТИЧНО: Сохраняем ПОЛНЫЕ данные расчёта в data-атрибут строки
                tr.dataset.calcData = JSON.stringify(calc);

                // Заполняем ячейки ПО КЛЮЧУ (data-rid), а не по индексу!
                tr.querySelectorAll('.opt-cell[data-rid]').forEach(td => {
                    const rid = td.dataset.rid;
                    if (!rid) return;

                    // Проверяем, есть ли такой ключ в calc
                    if (!(rid in calc)) return;

                    const val = (calc[rid] != null && calc[rid] !== undefined)
                        ? this._formatNumber(calc[rid])
                        : '—';

                    td.querySelector('.sys').textContent = val;
                });

                setTimeout(() => this.updateSummary(), 100);
            } catch (e) {
                console.error('Calc error:', e);
            }
        },

        /**
         * Безопасное форматирование чисел (включая большие суммы).
         */
        _formatNumber(value) {
            if (value == null) return '—';

            const num = Number(value);
            if (!isFinite(num)) return '—';

            // Для больших чисел используем более строгий формат
            return num.toLocaleString('ru-RU', {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2,
                useGrouping: true
            });
        },

        /**
         * Вычисление итогов из data-атрибутов строк (независимо от размеченных колонок).
         * Читаем ПОЛНЫЕ данные расчёта, сохранённые бэкендом.
         */
        computeBaseTotals() {
            const rows = document.querySelectorAll('#tc-map tbody tr:not(.sec-hdr)');

            // Фиксированные ключи для итогового табло (независимо от разметки)
            const totals = {
                PRICE_FOR_ALL_MATERIAL: 0,
                PRICE_FOR_ALL_WORK: 0,
                TOTAL_PRICE_WITHOUT_VAT: 0,
                VAT_AMOUNT: 0,
                TOTAL_PRICE: 0,
                PRICE_FOR_ALL_MATERIAL_WITHOUT_VAT: 0,
                PRICE_FOR_ALL_WORK_WITHOUT_VAT: 0
            };

            let calculatedRows = 0;

            rows.forEach(tr => {
                if (tr.style.display === 'none') return;

                // Читаем ПОЛНЫЕ данные из data-атрибута (где хранится весь calc)
                const calcDataStr = tr.dataset.calcData;
                if (!calcDataStr) return;

                try {
                    const calc = JSON.parse(calcDataStr);

                    // Суммируем нужные ключи
                    // Используем Number() вместо parseFloat() для точности с большими числами
                    const mat = Number(calc.PRICE_FOR_ALL_MATERIAL || 0);
                    const work = Number(calc.PRICE_FOR_ALL_WORK || 0);

                    const matBase = Number(calc.PRICE_FOR_ALL_MATERIAL_WITHOUT_VAT ?? calc.PRICE_FOR_ALL_MATERIAL ?? 0);
                    const workBase = Number(calc.PRICE_FOR_ALL_WORK_WITHOUT_VAT ?? calc.PRICE_FOR_ALL_WORK ?? 0);

                    const withoutVat = Number(calc.TOTAL_PRICE_WITHOUT_VAT || 0);
                    const vat = Number(calc.VAT_AMOUNT || 0);
                    const withVat = Number(calc.TOTAL_PRICE || 0);

                    if (mat > 0 || work > 0 || withoutVat > 0 || withVat > 0) {
                        totals.PRICE_FOR_ALL_MATERIAL += mat;
                        totals.PRICE_FOR_ALL_WORK += work;
                        totals.TOTAL_PRICE_WITHOUT_VAT += withoutVat;
                        totals.VAT_AMOUNT += vat;
                        totals.TOTAL_PRICE += withVat;
                        totals.PRICE_FOR_ALL_MATERIAL_WITHOUT_VAT += matBase;
                        totals.PRICE_FOR_ALL_WORK_WITHOUT_VAT += workBase;
                        calculatedRows++;
                    }
                } catch (e) {
                    console.warn('Parse calcData error:', e);
                }
            });

            return {
                rows: rows.length,
                calculatedRows,
                materialsWithoutVat: totals.PRICE_FOR_ALL_MATERIAL_WITHOUT_VAT,
                worksWithoutVat: totals.PRICE_FOR_ALL_WORK_WITHOUT_VAT,
                materialsWithVat: totals.PRICE_FOR_ALL_MATERIAL,
                worksWithVat: totals.PRICE_FOR_ALL_WORK,
                totalWithoutVat: totals.TOTAL_PRICE_WITHOUT_VAT,
                vatAmount: totals.VAT_AMOUNT,
                totalWithVat: totals.TOTAL_PRICE
            };
        },

        /**
         * Batch расчёт множества строк за один запрос.
         * Оптимизирован для загрузки больших смет.
         */
        async batchCalc(items) {
            if (!items || items.length === 0) return [];

            try {
                const response = await fetch(this.BATCH_CALC_URL, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': this._getCsrfToken()
                    },
                    body: JSON.stringify({ items })
                });

                if (!response.ok) {
                    console.error('Batch calc HTTP error:', response.status);
                    return [];
                }

                const data = await response.json();

                if (!data.ok) {
                    console.error('Batch calc error:', data.error);
                    return [];
                }

                return data.results || [];
            } catch (e) {
                console.error('Batch calc fetch error:', e);
                return [];
            }
        },

        _getCsrfToken() {
            const input = document.querySelector('[name=csrfmiddlewaretoken]');
            if (input && input.value) return input.value;

            const m = document.cookie.match(/(?:^|;)\s*csrftoken=([^;]+)/);
            return m ? decodeURIComponent(m[1]) : '';
        },

        /**
         * Применить результаты batch расчёта к строкам таблицы.
         */
        applyBatchResults(results) {
            results.forEach(result => {
                if (result.error) {
                    console.warn(`Ошибка расчёта tc_id=${result.tc_id}:`, result.error);
                    return;
                }

                const rowIndex = result.row_index;
                if (rowIndex == null) return;

                const tr = document.querySelector(`tr[data-row="${rowIndex}"]`);
                if (!tr) return;

                const calc = result.calc || {};

                // Сохраняем полные данные в data-атрибут
                tr.dataset.calcData = JSON.stringify(calc);

                // Заполняем ячейки по ключам
                tr.querySelectorAll('.opt-cell[data-rid]').forEach(td => {
                    const rid = td.dataset.rid;
                    if (!rid || !(rid in calc)) return;

                    const val = (calc[rid] != null && calc[rid] !== undefined)
                        ? this._formatNumber(calc[rid])
                        : '—';

                    td.querySelector('.sys').textContent = val;
                });
            });

            // Обновляем итоговое табло
            setTimeout(() => this.updateSummary(), 100);
        },

        renderMetricCards(container, cards) {
            const card = (title, main, extraClass = '') => `
          <div class="metric-card ${extraClass}">
            <div class="metric-title">${title}</div>
            <div class="metric-value">${this._formatNumber(main)}</div>
          </div>`;

            container.innerHTML = cards.map(c => card(c.title, c.value, c.extraClass || '')).join('');
        },

        /**
         * Обновление итогового табло "📋 Текущие расчеты".
         * Всегда показываем 5 метрик независимо от размеченных колонок.
         */
        updateSummary() {
            const base = this.computeBaseTotals();
            const noteBase = document.getElementById('summary-note-base');
            const boxBase = document.getElementById('metrics-base');
            const vatSection = document.getElementById('summary-section-with-vat');
            const vatBox = document.getElementById('metrics-vat');
            const vatNote = document.getElementById('summary-note-vat');

            if (noteBase) {
                noteBase.textContent = `Рассчитано строк: ${base.calculatedRows} из ${base.rows}`;
            }

            if (boxBase) {
                const cards = [
                    { title: 'Материалы', value: base.materialsWithoutVat },
                    { title: 'Работы', value: base.worksWithoutVat },
                    { title: 'Итого (без НДС)', value: base.totalWithoutVat, extraClass: 'metric-total' },
                ];

                // Проверяем состояние toggle НДС
                const vatToggle = document.getElementById('toggle-vat-active');
                const isVatActive = vatToggle ? vatToggle.checked : false;

                this.renderMetricCards(boxBase, cards);

                if (vatSection && vatBox) {
                    if (isVatActive) {
                        vatSection.style.display = '';

                        if (vatNote) {
                            const rate = window.EstimateVat?.currentRate ?? 0;
                            vatNote.textContent = rate ? `Ставка НДС: ${rate}%` : '';
                        }

                        const vatCards = [
                            { title: 'Материалы', value: base.materialsWithVat },
                            { title: 'Работы', value: base.worksWithVat },
                            { title: 'НДС', value: base.vatAmount, extraClass: 'metric-vat' },
                            { title: 'Итого с НДС', value: base.totalWithVat, extraClass: 'metric-total' }
                        ];

                        this.renderMetricCards(vatBox, vatCards);
                    } else {
                        vatSection.style.display = 'none';
                        if (vatBox) {
                            vatBox.innerHTML = '';
                        }
                        if (vatNote) {
                            vatNote.textContent = '';
                        }
                    }
                }
            }

            // Триггер для других модулей
            if (window.EstimateSections) {
                window.EstimateSections.updateSectionTotals();
            }
        },

        async prefillExistingMappings(existingMappings) {
            const mappingEntries = Object.entries(existingMappings);

            if (mappingEntries.length === 0) {
                this.updateSummary();
                return;
            }

            // Собираем элементы для batch расчёта
            const batchItems = [];

            mappingEntries.forEach(([rowIndex, mapping]) => {
                const tr = document.querySelector(`tr[data-row="${rowIndex}"]`);
                if (!tr) return;

                const tcInput = tr.querySelector('.js-tc-autocomplete');
                const qtyInput = tr.querySelector('.qty-input');

                const tcId = mapping.tc_id || 0;

                if (tcInput && tcId && mapping.tc_name) {
                    tcInput.value = mapping.tc_name;
                    tcInput.dataset.id = tcId;
                    tcInput.dataset.text = mapping.tc_name;
                    tcInput.style.background = '#e7f3ff';

                    const openLink = tcInput.parentElement?.querySelector('.tc-open-link');
                    if (openLink) {
                        const id = parseInt(tcId || '0', 10) || 0;
                        if (id > 0) {
                            openLink.href = window.tcChangeUrl ? window.tcChangeUrl(id) : '#';
                            openLink.style.display = 'block';
                        } else {
                            openLink.removeAttribute('href');
                            openLink.style.display = 'none';
                        }
                    }

                    const clearBtn = tcInput.parentElement?.querySelector('.tc-clear-btn');
                    if (clearBtn) clearBtn.style.display = 'block';
                }

                if (qtyInput && mapping.quantity) {
                    qtyInput.value = mapping.quantity;
                }

                if (tcId && mapping.quantity > 0) {
                    batchItems.push({
                        tc_id: tcId,
                        quantity: parseFloat(mapping.quantity),
                        row_index: parseInt(rowIndex, 10)
                    });
                }
            });

            // Batch расчёт вместо множества одиночных запросов
            if (batchItems.length > 0) {
                console.log(`🚀 Запуск batch расчёта для ${batchItems.length} строк...`);
                const results = await this.batchCalc(batchItems);
                this.applyBatchResults(results);
                console.log(`✅ Batch расчёт завершён: ${results.length} результатов`);
            }

            this.updateSummary();
        },

        async recalcAllRows() {
            const rows = document.querySelectorAll('#tc-map tbody tr:not(.sec-hdr)');
            const batchItems = [];

            rows.forEach(tr => {
                const qtyInput = tr.querySelector('.qty-input');
                const tcInput = tr.querySelector('.js-tc-autocomplete');
                const tcId = parseInt(tcInput?.dataset.id || '0', 10) || 0;
                const qty = parseFloat((qtyInput?.value || '').replace(',', '.')) || 0;

                if (tcId > 0 && qty > 0) {
                    const rowIndex = tr.dataset.row;
                    batchItems.push({
                        tc_id: tcId,
                        quantity: qty,
                        row_index: parseInt(rowIndex, 10)
                    });
                }
            });

            if (batchItems.length > 0) {
                console.log(`🔄 Пересчёт ${batchItems.length} строк...`);
                const results = await this.batchCalc(batchItems);
                this.applyBatchResults(results);
                console.log(`✅ Пересчёт завершён`);
            }
            this.updateSummary();
        }
    };

    window.EstimateCalc = EstimateCalc;
})(window);