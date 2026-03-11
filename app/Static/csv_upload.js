// Progress bar logic for CSV upload
function showUploadProgressBar() {
    let bar = document.getElementById('csv-upload-progress');
    if (!bar) {
        bar = document.createElement('div');
        bar.id = 'csv-upload-progress';
        bar.innerHTML = `
            <div class="progress-bar-bg">
                <div class="progress-bar-fill" style="width:0%"></div>
            </div>
            <div class="progress-bar-label">Uploading...</div>
        `;
        document.body.appendChild(bar);
    }
    bar.style.display = 'block';
}

function updateUploadProgressBar(percent, label) {
    const bar = document.getElementById('csv-upload-progress');
    if (bar) {
        bar.querySelector('.progress-bar-fill').style.width = percent + '%';
        bar.querySelector('.progress-bar-label').textContent = label || `Uploading... ${percent}%`;
    }
}

function hideUploadProgressBar() {
    const bar = document.getElementById('csv-upload-progress');
    if (bar) bar.style.display = 'none';
}

// Manual add-site state container keeps timer and result list wiring in one place.
const addSiteState = {
    notificationTimer: null,
};

function showAddSiteNotification(message, type = 'success') {
    const resultDiv = document.getElementById('add-site-result');
    if (!resultDiv) return;

    if (addSiteState.notificationTimer) {
        clearTimeout(addSiteState.notificationTimer);
    }

    const typeClass = type === 'success' ? 'notification--success' : 'notification--error';
    resultDiv.innerHTML = `<div class="notification ${typeClass}">${message}</div>`;

    // Product requirement: auto-dismiss after 3 seconds.
    addSiteState.notificationTimer = setTimeout(() => {
        resultDiv.innerHTML = '';
    }, 3000);
}

function renderRecentSites(sites) {
    const list = document.getElementById('recent-sites-list');
    if (!list) return;

    if (!sites || sites.length === 0) {
        list.innerHTML = '<li class="recent-sites-empty">No sites yet.</li>';
        return;
    }

    list.innerHTML = sites.map((site) => {
        const platform = site.platform || 'Unknown platform';
        const industry = site.industry || 'Unknown industry';
        return `<li><span class="recent-site-url">${site.website_url}</span><span class="recent-site-meta">${platform} • ${industry}</span></li>`;
    }).join('');
}

function refreshRecentSites() {
    fetch('/api/sites/recent?limit=10')
        .then((response) => response.json())
        .then((data) => renderRecentSites(data.sites || []))
        .catch(() => {
            // Keep UX resilient: failing to refresh list should not block add-site success flow.
        });
}

// Handle manual add site form
function handleAddSiteForm() {
    const form = document.querySelector('.add-form');
    if (!form) return;

    form.onsubmit = function(e) {
        e.preventDefault();
        const formData = new FormData(form);
        const submitBtn = form.querySelector('button[type="submit"]');
        submitBtn.disabled = true;
        submitBtn.textContent = 'Adding...';

        fetch('/add-site', {
            method: 'POST',
            body: formData
        })
        .then(async (response) => {
            const data = await response.json();
            return { ok: response.ok, status: response.status, data };
        })
        .then(({ ok, status, data }) => {
            if (ok && data.status === 'success') {
                showAddSiteNotification('Site added successfully.', 'success');
                form.reset();
                refreshRecentSites();
                return;
            }

            if (status === 409) {
                showAddSiteNotification(data.error || 'Site already exists.', 'error');
                return;
            }

            showAddSiteNotification(data.error || 'Unable to add site.', 'error');
        })
        .catch(error => {
            showAddSiteNotification(`Network error: ${error.message}`, 'error');
        })
        .finally(() => {
            submitBtn.disabled = false;
            submitBtn.textContent = 'Add site';
        });
    };
}

// Attach to CSV upload form
window.addEventListener('DOMContentLoaded', function() {
    handleAddSiteForm();
    refreshRecentSites();

    const form = document.querySelector('.upload-form');
    if (!form) return;
    const fileInput = form.querySelector('input[type="file"]');
    const submitBtn = form.querySelector('button[type="submit"]');
    if (!fileInput || !submitBtn) return;
    fileInput.disabled = false;
    submitBtn.disabled = false;
    form.onsubmit = function(e) {
        e.preventDefault();
        const file = fileInput.files[0];
        if (!file) return;
        showUploadProgressBar();
        // Step 1: Upload file with XHR and show upload progress
        const xhr = new XMLHttpRequest();
        xhr.open('POST', '/upload-csv', true);
        xhr.upload.onprogress = function(e) {
            if (e.lengthComputable) {
                const percent = Math.round((e.loaded / e.total) * 100);
                updateUploadProgressBar(percent, `Uploading... ${percent}%`);
            }
        };
        xhr.onload = function() {
            if (xhr.status === 200) {
                // Step 2: Listen for server-side processing progress via SSE
                updateUploadProgressBar(100, 'Processing on server...');
                const evtSource = new EventSource('/upload-csv');
                evtSource.onmessage = function(event) {
                    try {
                        const data = JSON.parse(event.data);
                        if (data.progress !== undefined) {
                            updateUploadProgressBar(data.progress, `Processing... ${data.progress}%`);
                        }
                        if (data.status === 'complete' || data.progress === 100) {
                            updateUploadProgressBar(100, 'Complete!');
                            setTimeout(hideUploadProgressBar, 1200);
                            evtSource.close();
                        }
                        if (data.status === 'error') {
                            updateUploadProgressBar(0, 'Error: ' + (data.error || 'Server error'));
                            setTimeout(hideUploadProgressBar, 2000);
                            evtSource.close();
                        }
                    } catch (err) {}
                };
            } else {
                updateUploadProgressBar(0, 'Upload failed: ' + xhr.responseText);
                setTimeout(hideUploadProgressBar, 2000);
            }
        };
        const formData = new FormData();
        formData.append('file', file);
        xhr.send(formData);
    };
});
