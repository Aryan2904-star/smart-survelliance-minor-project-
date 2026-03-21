// ═══════════════════════════════════════════════════════════
//  Smart Surveillance Dashboard — Frontend Logic
//  Connected to Flask backend at http://127.0.0.1:5000
// ═══════════════════════════════════════════════════════════

const API_BASE = "";

// ─── DOM References ─────────────────────────────────────────
const alertsContainer = document.getElementById("alertsContainer");
const uploadStatus    = document.getElementById("uploadStatus");
const videoPlayer     = document.getElementById("resultVideo");
const videoContainer  = document.getElementById("videoContainer");
const dropZone        = document.getElementById("dropZone");
const fileInput       = document.getElementById("videoUpload");
const browseBtn       = document.getElementById("browseBtn");
const fileInfo        = document.getElementById("fileInfo");
const fileName        = document.getElementById("fileName");
const fileSize        = document.getElementById("fileSize");
const removeFileBtn   = document.getElementById("removeFileBtn");
const uploadActions   = document.getElementById("uploadActions");
const progressContainer = document.getElementById("progressContainer");
const progressBar     = document.getElementById("progressBar");
const progressPercent = document.getElementById("progressPercent");
const progressLabel   = document.getElementById("progressLabel");

// ─── Sidebar Toggle (mobile) ───────────────────────────────
const sidebar    = document.getElementById("sidebar");
const menuToggle = document.getElementById("menuToggle");

if (menuToggle && sidebar) {
    menuToggle.addEventListener("click", () => sidebar.classList.toggle("open"));
    document.addEventListener("click", (e) => {
        if (sidebar.classList.contains("open") &&
            !sidebar.contains(e.target) &&
            !menuToggle.contains(e.target)) {
            sidebar.classList.remove("open");
        }
    });
}

// ─── Sidebar Nav Active State ───────────────────────────────
document.querySelectorAll(".nav-item").forEach(item => {
    item.addEventListener("click", (e) => {
        e.preventDefault();
        document.querySelectorAll(".nav-item").forEach(n => n.classList.remove("active"));
        item.classList.add("active");
    });
});

// ─── Live Clock ─────────────────────────────────────────────
const currentTimeEl = document.getElementById("currentTime");
function updateClock() {
    if (currentTimeEl) {
        const now = new Date();
        currentTimeEl.textContent = now.toLocaleTimeString("en-US", {
            hour: "2-digit", minute: "2-digit", second: "2-digit"
        });
    }
}
updateClock();
setInterval(updateClock, 1000);

// ─── File Helpers ───────────────────────────────────────────
function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + " KB";
    return (bytes / 1048576).toFixed(1) + " MB";
}

let selectedFile = null;

function showFileInfo(file) {
    selectedFile = file;
    if (fileName) fileName.textContent = file.name;
    if (fileSize) fileSize.textContent = formatFileSize(file.size);
    if (fileInfo) fileInfo.style.display = "flex";
    if (uploadActions) uploadActions.style.display = "block";
    if (dropZone) {
        const content = dropZone.querySelector(".upload-zone-content");
        if (content) content.style.display = "none";
    }

    // Auto-preview
    const previewURL = URL.createObjectURL(file);
    videoPlayer.src = previewURL;
    videoContainer.style.display = "block";
    videoPlayer.play();
}

function clearFile() {
    selectedFile = null;
    if (fileInput) fileInput.value = "";
    if (fileInfo) fileInfo.style.display = "none";
    if (uploadActions) uploadActions.style.display = "none";
    if (dropZone) {
        const content = dropZone.querySelector(".upload-zone-content");
        if (content) content.style.display = "";
    }
    videoContainer.style.display = "none";
    videoPlayer.src = "";
    uploadStatus.innerText = "";
}

// ─── Browse Button ──────────────────────────────────────────
if (browseBtn) browseBtn.addEventListener("click", () => fileInput.click());

// ─── File Input Change ──────────────────────────────────────
if (fileInput) {
    fileInput.addEventListener("change", function () {
        if (this.files[0]) showFileInfo(this.files[0]);
    });
}

// ─── Remove File ────────────────────────────────────────────
if (removeFileBtn) removeFileBtn.addEventListener("click", clearFile);

// ─── Drag & Drop ────────────────────────────────────────────
if (dropZone) {
    dropZone.addEventListener("click", (e) => {
        if (e.target === dropZone || e.target.closest(".upload-zone-content")) {
            fileInput.click();
        }
    });

    dropZone.addEventListener("dragover", (e) => {
        e.preventDefault();
        dropZone.classList.add("drag-over");
    });
    dropZone.addEventListener("dragleave", () => dropZone.classList.remove("drag-over"));
    dropZone.addEventListener("drop", (e) => {
        e.preventDefault();
        dropZone.classList.remove("drag-over");
        const file = e.dataTransfer.files[0];
        if (file && file.type.startsWith("video/")) {
            fileInput.files = e.dataTransfer.files;
            showFileInfo(file);
        }
    });
}

// ─── Upload & Detect ────────────────────────────────────────
function uploadVideo() {
    const file = selectedFile || (fileInput && fileInput.files[0]);

    if (!file) {
        alert("Please select a video file!");
        return;
    }

    const formData = new FormData();
    formData.append("video", file);

    // Show progress
    if (progressContainer) progressContainer.style.display = "block";
    if (uploadActions) uploadActions.style.display = "none";
    uploadStatus.innerText = "";

    const xhr = new XMLHttpRequest();

    xhr.upload.addEventListener("progress", (e) => {
        if (e.lengthComputable) {
            const pct = Math.round((e.loaded / e.total) * 100);
            if (progressBar) progressBar.style.width = pct + "%";
            if (progressPercent) progressPercent.textContent = pct + "%";
            if (progressLabel) progressLabel.textContent = pct < 100 ? "Uploading..." : "Processing...";
        }
    });

    xhr.addEventListener("load", () => {
        if (progressContainer) progressContainer.style.display = "none";
        try {
            const data = JSON.parse(xhr.responseText);
            if (data.error) {
                uploadStatus.innerText = "❌ Error: " + data.error;
                return;
            }
            uploadStatus.innerText = "✅ " + data.message;

            // Update stats
            const statVideos = document.getElementById("statVideos");
            if (statVideos) statVideos.textContent = parseInt(statVideos.textContent || 0) + 1;

            // Play processed video if available
            if (data.output_video_url) {
                videoPlayer.src = API_BASE + data.output_video_url;
                videoContainer.style.display = "block";
                videoPlayer.load();
                videoPlayer.play();
            }
        } catch {
            uploadStatus.innerText = "✅ Upload complete!";
        }
    });

    xhr.addEventListener("error", () => {
        if (progressContainer) progressContainer.style.display = "none";
        uploadStatus.innerText = "❌ Upload failed. Is the backend running?";
    });

    xhr.open("POST", `${API_BASE}/api/upload`);
    xhr.send(formData);
}

// ─── Fetch Alerts ───────────────────────────────────────────
function fetchAlerts() {
    fetch(`${API_BASE}/api/alerts`)
        .then(response => {
            if (!response.ok) return;
            return response.json();
        })
        .then(alerts => {
            if (!alerts || !Array.isArray(alerts)) return;

            // Update badge & count
            const alertBadge = document.getElementById("alertBadge");
            const alertCount = document.getElementById("alertCount");
            const emptyAlerts = document.getElementById("emptyAlerts");
            const statAnomalies = document.getElementById("statAnomalies");

            if (alertBadge) alertBadge.textContent = alerts.length;
            if (alertCount) alertCount.textContent = alerts.length + " alerts today";
            if (statAnomalies) statAnomalies.textContent = alerts.length;

            // Clear and rebuild
            alertsContainer.innerHTML = "";
            if (alerts.length === 0 && emptyAlerts) {
                alertsContainer.innerHTML = `
                    <div class="empty-state">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                            <path d="M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z"/>
                            <path d="M8 14s1.5 2 4 2 4-2 4-2"/>
                            <line x1="9" y1="9" x2="9.01" y2="9"/>
                            <line x1="15" y1="9" x2="15.01" y2="9"/>
                        </svg>
                        <p>No anomalies detected — all clear!</p>
                    </div>`;
                return;
            }

            alerts.forEach(alert => {
                const card = document.createElement("div");
                card.className = "alert-card";
                const imgPath = alert.frame_path
                    ? `${API_BASE}/alerts/${alert.frame_path}`
                    : "https://via.placeholder.com/400x250?text=Anomaly";

                card.innerHTML = `
                    <img src="${imgPath}" onerror="this.src='https://via.placeholder.com/400x250?text=Anomaly'">
                    <div class="alert-info">
                        <h3>Anomaly Detected</h3>
                        <p>${alert.timestamp}</p>
                        <p style="font-size: 12px; color: #94a3b8;">${alert.description}</p>
                    </div>
                `;
                alertsContainer.appendChild(card);
            });
        })
        .catch(() => { /* alerts endpoint may not exist yet */ });
}

// ─── Initial Load & Polling ─────────────────────────────────
fetchAlerts();
setInterval(fetchAlerts, 5000);

// ═══════════════════════════════════════════════════════════
//  LIVE CAMERA CONTROLS
// ═══════════════════════════════════════════════════════════

const liveFeedImage    = document.getElementById("liveFeedImage");
const liveFeedPlaceholder = document.getElementById("liveFeedPlaceholder");
const startCameraBtn   = document.getElementById("startCameraBtn");
const stopCameraBtn    = document.getElementById("stopCameraBtn");
const cameraStatus     = document.getElementById("cameraStatus");
const cameraStatusText = document.getElementById("cameraStatusText");
const motionStatusEl   = document.getElementById("motionStatus");
const liveAnomalyCount = document.getElementById("liveAnomalyCount");

let cameraStatusInterval = null;

function startCamera() {
    startCameraBtn.disabled = true;
    startCameraBtn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg> Starting...';

    fetch(`${API_BASE}/api/live/start`, { method: "POST" })
        .then(r => r.json())
        .then(data => {
            if (data.error) {
                alert("Camera Error: " + data.error);
                startCameraBtn.disabled = false;
                startCameraBtn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="23 7 16 12 23 17 23 7"/><rect x="1" y="5" width="15" height="14" rx="2" ry="2"/></svg> Start Camera';
                return;
            }

            // Show live feed
            liveFeedPlaceholder.style.display = "none";
            liveFeedImage.style.display = "block";
            liveFeedImage.src = `${API_BASE}/api/live?t=` + Date.now();

            // Toggle buttons
            startCameraBtn.style.display = "none";
            stopCameraBtn.style.display = "inline-flex";

            // Update status
            cameraStatus.className = "camera-status active";
            cameraStatusText.textContent = "Camera Active";

            // Start polling camera status
            cameraStatusInterval = setInterval(pollCameraStatus, 1000);
        })
        .catch(err => {
            console.error(err);
            alert("Failed to start camera. Is the backend running?");
            startCameraBtn.disabled = false;
            startCameraBtn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="23 7 16 12 23 17 23 7"/><rect x="1" y="5" width="15" height="14" rx="2" ry="2"/></svg> Start Camera';
        });
}

function stopCamera() {
    fetch(`${API_BASE}/api/live/stop`, { method: "POST" })
        .then(r => r.json())
        .then(() => {
            // Hide feed
            liveFeedImage.style.display = "none";
            liveFeedImage.src = "";
            liveFeedPlaceholder.style.display = "";

            // Toggle buttons
            stopCameraBtn.style.display = "none";
            startCameraBtn.style.display = "inline-flex";
            startCameraBtn.disabled = false;
            startCameraBtn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="23 7 16 12 23 17 23 7"/><rect x="1" y="5" width="15" height="14" rx="2" ry="2"/></svg> Start Camera';

            // Update status
            cameraStatus.className = "camera-status";
            cameraStatusText.textContent = "Camera Off";
            motionStatusEl.textContent = "—";
            motionStatusEl.className = "feed-stat-value";

            // Stop polling
            if (cameraStatusInterval) {
                clearInterval(cameraStatusInterval);
                cameraStatusInterval = null;
            }
        });
}

function pollCameraStatus() {
    fetch(`${API_BASE}/api/live/status`)
        .then(r => r.json())
        .then(data => {
            if (!data.is_running) {
                stopCamera();
                return;
            }

            // Update motion status
            if (data.motion_detected) {
                motionStatusEl.textContent = "⚠ Motion Detected";
                motionStatusEl.className = "feed-stat-value motion-active";
                cameraStatus.className = "camera-status motion";
                cameraStatusText.textContent = "Motion Detected";
            } else {
                motionStatusEl.textContent = "✓ Normal";
                motionStatusEl.className = "feed-stat-value motion-normal";
                cameraStatus.className = "camera-status active";
                cameraStatusText.textContent = "Camera Active";
            }

            // Update anomaly count
            liveAnomalyCount.textContent = data.anomaly_count;
            const statAnomalies = document.getElementById("statAnomalies");
            if (statAnomalies) statAnomalies.textContent = data.anomaly_count;
        })
        .catch(() => {});
}