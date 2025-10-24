// path: src/app_outlay/static/app_outlay/js/estimate_overheads.js
/**
 * Модуль управления накладными расходами
 */
(function (window) {
    'use strict';

    const EstimateOverheads = {
        OH_LIST_URL: '',
        OH_APPLY_URL: '',
        OH_TOGGLE_URL: '',
        OH_DEL_URL: '',
        OH_QTY_URL: '',

        ohSelect: null,
        ohAddBtn: null,
        ohRows: null,
        ohMeta: null,
        toggleOverheadActive: null,
        toggleOverheadLabel: null,

        init(urls) {
            this.OH_LIST_URL = urls.list;
            this.OH_APPLY_URL = urls.apply;
            this.OH_TOGGLE_URL = urls.toggle;
            this.OH_DEL_URL = urls.delete;
            this.OH_QTY_URL = urls.quantity;

            this.ohSelect = document.getElementById('oh-select');
            this.ohAddBtn = document.getElementById('oh-add');
            this.ohRows = document.getElementById('oh-rows');
            this.ohMeta = document.getElementById('oh-meta');
            this.toggleOverheadActive = document.getElementById('toggle-overhead-active');
            this.toggleOverheadLabel = document.getElementById('toggle-overhead-label');

            this._bindAddButton();
            this._bindToggleAll();
            this.loadOH();
        },

        _getCsrfToken() {
            const input = document.querySelector('[name=csrfmiddlewaretoken]');
            if (input && input.value) return input.value;

            const m = document.cookie.match(/(?:^|;)\s*csrftoken=([^;]+)/);
            return m ? decodeURIComponent(m[1]) : '';
        },

        async postJSON(url, payload) {
            try {
                const res = await fetch(url, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': this._getCsrfToken()
                    },
                    body: JSON.stringify(payload || {})
                });

                const ct = res.headers.get('content-type') || '';
                if (ct.includes('application/json')) return await res.json();

                const txt = await res.text();
                console.warn('postJSON: non-JSON response', res.status, txt.slice(0, 300));
                return { ok: false, status: res.status, error: 'non_json', html: txt };
            } catch (e) {
                console.warn('postJSON error', e);
                return { ok: false, error: String(e) };
            }
        },

        renderOH(data) {
            this._renderSelect(data);
            this._renderMeta(data);
            this._renderTable(data);
        },

        _renderSelect(data) {
            if (!this.ohSelect) return;

            this.ohSelect.innerHTML = '';
            const list = Array.isArray(data?.containers) ? data.containers : [];

            if (list.length) {
                list.forEach(c => {
                    const opt = document.createElement('option');
                    opt.value = String(c.id);
                    opt.textContent = `${c.name} · ${c.total.toLocaleString()} — МАТ ${c.materials_pct}% / РАБ ${c.works_pct}%`;
                    this.ohSelect.appendChild(opt);
                });
                this.ohAddBtn?.removeAttribute('disabled');
            } else {
                const opt = document.createElement('option');
                opt.disabled = true;
                opt.selected = true;
                opt.textContent = '— нет доступных контейнеров —';
                this.ohSelect.appendChild(opt);
                this.ohAddBtn?.setAttribute('disabled', 'disabled');
            }
        },

        _renderMeta(data) {
            if (!this.ohMeta) return;

            const t = Number(data?.overhead_total || 0);
            const mp = Number(data?.avg_materials_pct || 0).toFixed(1);
            const wp = Number(data?.avg_works_pct || 0).toFixed(1);
            const hasList = Array.isArray(data?.containers) && data.containers.length > 0;

            this.ohMeta.textContent = hasList
                ? `Всего НР: ${t.toLocaleString()} · средн. распределение: МАТ ${mp}% / РАБ ${wp}%`
                : 'Создайте контейнер НР и включите его (⚙️ Админка → Контейнеры НР).';
        },

        _renderTable(data) {
            if (!this.ohRows) return;

            this.ohRows.innerHTML = '';

            (data?.links || []).forEach((l, idx) => {
                const tr = document.createElement('tr');
                tr.dataset.id = String(l.id);
                tr.innerHTML = `
            <td class="col-slim">${idx + 1}</td>
            <td class="col-wide">${l.name}${l.has_changes ? ' <span class="muted">(изменён)</span>' : ''}</td>
            <td class="col-slim">${(l.snapshot_total || 0).toLocaleString()}</td>
            <td class="col-slim">${(l.current_total || 0).toLocaleString()}</td>
            <td class="col-slim">${(l.materials_pct || 0).toFixed(1)}%</td>
            <td class="col-slim">${(l.works_pct || 0).toFixed(1)}%</td>
            <td class="col-slim">
              <div class="oh-qty">
                <button type="button" class="button oh-qty-dec" title="Уменьшить">−</button>
                <input type="number" class="oh-qty-input" min="1" step="1" value="${l.quantity || 1}" title="Количество">
                <button type="button" class="button oh-qty-inc" title="Увеличить">+</button>
              </div>
            </td>
            <td class="col-slim">
              <label style="display:inline-flex;gap:6px;align-items:center">
                <input type="checkbox" class="oh-toggle" ${l.is_active ? 'checked' : ''}>
                <span class="muted">${l.is_active ? 'в расчёте' : 'игнор'}</span>
              </label>
            </td>
            <td class="col-slim">
              <button type="button" class="button oh-del" title="Удалить" style="background:#dc3545;color:#fff">✕</button>
            </td>`;

                this.ohRows.appendChild(tr);
            });

            this.bindOHEvents();
        },

        async loadOH() {
            try {
                const res = await fetch(this.OH_LIST_URL, { headers: { 'Accept': 'application/json' } });
                const ct = res.headers.get('content-type') || '';

                if (!res.ok) {
                    console.warn('OH load status', res.status);
                    if (this.ohMeta) this.ohMeta.textContent = 'Не удалось загрузить НР (' + res.status + ').';
                    return;
                }

                if (!ct.includes('application/json')) {
                    console.warn('OH: not JSON');
                    if (this.ohMeta) this.ohMeta.textContent = 'Ответ сервера не JSON.';
                    return;
                }

                const data = await res.json();
                if (data?.ok === false) {
                    console.warn('OH: ok=false', data);
                }

                this.renderOH(data);
            } catch (e) {
                console.warn('OH load error', e);
                if (this.ohMeta) this.ohMeta.textContent = 'Ошибка загрузки НР.';
            }
        },

        bindOHEvents() {
            this._bindToggleCheckboxes();
            this._bindQuantityInputs();
            this._bindQuantityButtons();
            this._bindDeleteButtons();
        },

        _bindToggleCheckboxes() {
            this.ohRows.querySelectorAll('.oh-toggle').forEach(input => {
                input.addEventListener('change', async () => {
                    const tr = input.closest('tr');
                    if (!tr) return;

                    const id = parseInt(tr.dataset.id || '0', 10) || 0;
                    const res = await this.postJSON(this.OH_TOGGLE_URL, {
                        link_id: id,
                        is_active: input.checked
                    });

                    if (res.ok) {
                        this.renderOH(res);
                        this._recalcAllRowsAndSummary();
                    }
                });
            });
        },

        _bindQuantityInputs() {
            this.ohRows.querySelectorAll('.oh-qty-input').forEach(inp => {
                const apply = async () => {
                    const tr = inp.closest('tr');
                    if (!tr) return;

                    const id = parseInt(tr.dataset.id || '0', 10) || 0;
                    let q = parseInt(inp.value || '1', 10) || 1;
                    if (q < 1) q = 1;
                    if (q > 1000) q = 1000;

                    const res = await this.postJSON(this.OH_QTY_URL, {
                        link_id: id,
                        quantity: q
                    });

                    if (res.ok) {
                        this.renderOH(res);
                        this._recalcAllRowsAndSummary();
                    }
                };

                inp.addEventListener('change', apply);
                inp.addEventListener('blur', apply);
            });
        },

        _bindQuantityButtons() {
            this.ohRows.querySelectorAll('.oh-qty-inc, .oh-qty-dec').forEach(btn => {
                btn.addEventListener('click', async () => {
                    const tr = btn.closest('tr');
                    if (!tr) return;

                    const id = parseInt(tr.dataset.id || '0', 10) || 0;
                    const field = tr.querySelector('.oh-qty-input');
                    let q = parseInt(field.value || '1', 10) || 1;

                    q += btn.classList.contains('oh-qty-inc') ? 1 : -1;
                    if (q < 1) q = 1;
                    if (q > 1000) q = 1000;

                    field.value = String(q);

                    const res = await this.postJSON(this.OH_QTY_URL, {
                        link_id: id,
                        quantity: q
                    });

                    if (res.ok) {
                        this.renderOH(res);
                        this._recalcAllRowsAndSummary();
                    }
                });
            });
        },

        _bindDeleteButtons() {
            this.ohRows.querySelectorAll('.oh-del').forEach(btn => {
                btn.addEventListener('click', async () => {
                    const tr = btn.closest('tr');
                    if (!tr) return;

                    const id = parseInt(tr.dataset.id || '0', 10) || 0;
                    const res = await this.postJSON(this.OH_DEL_URL, { link_id: id });

                    if (res.ok) {
                        this.renderOH(res);
                        this._recalcAllRowsAndSummary();
                    }
                });
            });
        },

        _bindAddButton() {
            if (!this.ohAddBtn) return;

            this.ohAddBtn.addEventListener('click', async () => {
                const id = parseInt(this.ohSelect.value || '0', 10) || 0;
                if (!id) return;

                const res = await this.postJSON(this.OH_APPLY_URL, { container_id: id });

                if (res && res.ok) {
                    this.renderOH(res);
                    this._recalcAllRowsAndSummary();
                } else {
                    if (this.ohMeta) {
                        this.ohMeta.textContent = 'Ошибка добавления НР' +
                            (res?.status ? ' (' + res.status + ')' : '') +
                            (res?.error ? ': ' + res.error : '');
                    }
                }
            });
        },

        _bindToggleAll() {
            if (!this.toggleOverheadActive) return;

            this.toggleOverheadActive.addEventListener('change', async () => {
                const checkboxes = document.querySelectorAll('#oh-rows .oh-toggle');
                if (checkboxes.length === 0) return;

                const newState = this.toggleOverheadActive.checked;

                if (this.toggleOverheadLabel) {
                    this.toggleOverheadLabel.textContent = newState ? 'НР активны' : 'НР выключены';
                }

                const promises = [];
                checkboxes.forEach(cb => {
                    const tr = cb.closest('tr');
                    if (!tr) return;

                    const id = parseInt(tr.dataset.id || '0', 10) || 0;
                    if (!id) return;

                    cb.checked = newState;
                    promises.push(this.postJSON(this.OH_TOGGLE_URL, {
                        link_id: id,
                        is_active: newState
                    }));
                });

                await Promise.all(promises);

                try {
                    const res = await fetch(this.OH_LIST_URL, {
                        headers: { 'Accept': 'application/json' }
                    });

                    if (!res.ok) {
                        console.warn('OH reload status', res.status);
                        return;
                    }

                    const data = await res.json();

                    if (data && data.ok) {
                        this.renderOH(data);
                        this._recalcAllRowsAndSummary();
                    }
                } catch (e) {
                    console.warn('OH reload error', e);
                }
            });
        },

        async _recalcAllRowsAndSummary() {
            if (window.EstimateCalc) {
                await window.EstimateCalc.recalcAllRows();
            }
        }
    };

    window.EstimateOverheads = EstimateOverheads;
})(window);