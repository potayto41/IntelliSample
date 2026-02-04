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

// Attach to CSV upload form
window.addEventListener('DOMContentLoaded', function() {
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
