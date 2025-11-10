/**
 * Модуль управления НДС
 */
(function (window) {
    'use strict';

    const EstimateVat = {
        VAT_STATUS_URL: '',
        VAT_TOGGLE_URL: '',
        VAT_SET_RATE_URL: '',

        toggleVatActive: null,
        toggleVatLabel: null,
        currentRate: 0,

        init(urls) {
            this.VAT_STATUS_URL = urls.status;
            this.VAT_TOGGLE_URL = urls.toggle;
            this.VAT_SET_RATE_URL = urls.setRate;

            this.toggleVatActive = document.getElementById('toggle-vat-active');
            this.toggleVatLabel = document.getElementById('toggle-vat-label');

            this._bindToggle();
            this.loadStatus();
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

        async loadStatus() {
            try {
                const res = await fetch(this.VAT_STATUS_URL, {
                    headers: { 'Accept': 'application/json' }
                });

                if (!res.ok) {
                    console.warn('VAT load status', res.status);
                    return;
                }

                const ct = res.headers.get('content-type') || '';
                if (!ct.includes('application/json')) {
                    console.warn('VAT: not JSON');
                    return;
                }

                const data = await res.json();

                if (data.ok) {
                    this._updateUI(data.vat_active, data.vat_rate);
                }
            } catch (e) {
                console.warn('VAT load error', e);
            }
        },

        _updateUI(isActive, rate) {
            this.currentRate = typeof rate === 'number' ? rate : this.currentRate;

            if (this.toggleVatActive) {
                this.toggleVatActive.checked = isActive;
            }

            if (this.toggleVatLabel) {
                const rateText = this.currentRate ? ` · ${this.currentRate}%` : '';
                this.toggleVatLabel.textContent = isActive
                    ? `НДС активен${rateText}`
                    : 'НДС выключен';
            }

            console.log(`ℹ️ НДС: ${isActive ? 'включён' : 'выключен'}, ставка: ${rate}%`);
            if (window.EstimateCalc && typeof window.EstimateCalc.updateSummary === 'function') {
                window.EstimateCalc.updateSummary();
            }
        },

        _bindToggle() {
            if (!this.toggleVatActive) return;

            this.toggleVatActive.addEventListener('change', async () => {
                const isActive = this.toggleVatActive.checked;

                if (this.toggleVatLabel) {
                    const rateText = this.currentRate ? ` · ${this.currentRate}%` : '';
                    this.toggleVatLabel.textContent = !isActive
                        ? `НДС активен${rateText}`
                        : 'НДС выключен';
                }

                const res = await this.postJSON(this.VAT_TOGGLE_URL, {
                    is_active: isActive
                });

                if (res.ok) {
                    console.log(`✅ НДС ${isActive ? 'включён' : 'выключен'}`);
                    this._recalcAllRowsAndSummary();
                } else {
                    console.error('❌ Ошибка переключения НДС:', res.error);
                    // Откатываем UI
                    this.toggleVatActive.checked = !isActive;
                    if (this.toggleVatLabel) {
                        this.toggleVatLabel.textContent = !isActive ? 'НДС активен' : 'НДС выключен';
                    }
                }
            });
        },

        async _recalcAllRowsAndSummary() {
            if (window.EstimateCalc) {
                await window.EstimateCalc.recalcAllRows();
            }
        }
    };

    window.EstimateVat = EstimateVat;
})(window);