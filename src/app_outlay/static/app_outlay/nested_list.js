document.addEventListener('DOMContentLoaded', () => {
    const KEY = 'estimate_tree_state';
    let state = {};
    try { state = JSON.parse(localStorage.getItem(KEY) || '{}'); } catch (e) { }

    function setExpanded(id, exp) {
        state[id] = !!exp;
        localStorage.setItem(KEY, JSON.stringify(state));
    }

    function applyInitial() {
        document.querySelectorAll('.toggle').forEach(btn => {
            const target = btn.dataset.target;
            const container = document.querySelector(`[data-node="${target}"]`);
            const expanded = state[target] !== false; // по умолчанию раскрыто
            btn.setAttribute('aria-expanded', expanded ? 'true' : 'false');
            btn.textContent = expanded ? '▾' : '▸';
            if (container) container.style.display = expanded ? '' : 'none';
        });
    }

    document.body.addEventListener('click', (e) => {
        const btn = e.target.closest('.toggle');
        if (!btn) return;
        const target = btn.dataset.target;
        const container = document.querySelector(`[data-node="${target}"]`);
        const expanded = btn.getAttribute('aria-expanded') === 'true';
        const next = !expanded;
        btn.setAttribute('aria-expanded', next ? 'true' : 'false');
        btn.textContent = next ? '▾' : '▸';
        if (container) container.style.display = next ? '' : 'none';
        setExpanded(target, next);
    });

    applyInitial();
});
