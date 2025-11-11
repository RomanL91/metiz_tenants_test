document.addEventListener('DOMContentLoaded', () => {
    const container = document.getElementById('workImportContainer');
    if (!container) {
        return;
    }

    const form = container.querySelector('#workImportForm');
    const fileInput = container.querySelector('#workFileInput');
    const submitBtn = container.querySelector('#workSubmitBtn');
    const messageDiv = container.querySelector('#workImportMessage');
    const progressBar = container.querySelector('#workImportProgress');
    const progressBarFill = container.querySelector('#workImportProgressFill');
    const csrfTokenInput = form.querySelector('[name=csrfmiddlewaretoken]');

    const {
        endpoint,
        selectFileError,
        uploading,
        submitLabel,
        importError,
        importErrorPrefix,
        createdLabel,
        updatedLabel,
        skippedLabel,
    } = container.dataset;

    function showMessage(text, type) {
        messageDiv.textContent = text;
        messageDiv.className = `message ${type}`;
        messageDiv.style.display = 'block';
        setTimeout(() => {
            messageDiv.style.display = 'none';
        }, 5000);
    }

    function showDetailedResult(result) {
        messageDiv.innerHTML = '';
        const statusClass =
            result.status === 'success'
                ? 'success'
                : result.status === 'error'
                    ? 'error'
                    : 'info';
        messageDiv.className = `message ${statusClass}`;
        messageDiv.style.display = 'block';

        const messageText = document.createElement('div');
        messageText.textContent = result.message;
        messageDiv.appendChild(messageText);

        if (result.created > 0 || result.updated > 0 || result.skipped > 0) {
            const stats = document.createElement('div');
            stats.className = 'stats';
            stats.innerHTML = `
                <div class="stat-item">✓ ${createdLabel}: <strong>${result.created}</strong></div>
                <div class="stat-item">↻ ${updatedLabel}: <strong>${result.updated}</strong></div>
                <div class="stat-item">⊘ ${skippedLabel}: <strong>${result.skipped}</strong></div>
            `;
            messageDiv.appendChild(stats);
        }

        if (Array.isArray(result.errors) && result.errors.length > 0) {
            const errorsList = document.createElement('div');
            errorsList.className = 'errors-list';

            result.errors.forEach((error) => {
                const errorItem = document.createElement('div');
                errorItem.className = 'error-item';
                errorItem.innerHTML = `
                    <div class="error-row">Строка ${error.row}</div>
                    ${error.field ? `<div class="error-field">Поле: ${error.field}</div>` : ''}
                    <div class="error-text">${error.error}</div>
                `;
                errorsList.appendChild(errorItem);
            });

            messageDiv.appendChild(errorsList);
        }

        setTimeout(() => {
            if (result.status === 'success') {
                messageDiv.style.display = 'none';
            }
        }, 10000);
    }

    function setProgress(percent) {
        progressBar.style.display = 'block';
        progressBarFill.style.width = `${percent}%`;
        progressBarFill.textContent = `${percent}%`;
    }

    function hideProgress() {
        progressBar.style.display = 'none';
        progressBarFill.style.width = '0%';
        progressBarFill.textContent = '0%';
    }

    form.addEventListener('submit', async (event) => {
        event.preventDefault();

        if (!fileInput.files || !fileInput.files[0]) {
            showMessage(selectFileError, 'error');
            return;
        }

        const formData = new FormData();
        formData.append('file', fileInput.files[0]);

        submitBtn.disabled = true;
        submitBtn.textContent = uploading;
        setProgress(0);

        try {
            const response = await fetch(endpoint, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': csrfTokenInput ? csrfTokenInput.value : '',
                },
                body: formData,
            });

            setProgress(50);

            const result = await response.json();

            setProgress(100);

            if (response.ok) {
                showDetailedResult(result);
                fileInput.value = '';
            } else {
                showMessage(result.message || importError, 'error');
            }

            setTimeout(() => {
                if (result.status === 'success') {
                    hideProgress();
                }
            }, 2000);
        } catch (error) {
            const message = error && error.message ? error.message : String(error);
            showMessage(`${importErrorPrefix} ${message}`, 'error');
            hideProgress();
        } finally {
            submitBtn.disabled = false;
            submitBtn.textContent = submitLabel;
        }
    });
});