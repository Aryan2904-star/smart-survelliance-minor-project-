// ═══════════════════════════════════════════════════════════
//  Smart Surveillance Dashboard — Frontend Logic
//  Motion Detection Pipeline
//  Connected to Flask backend at http://127.0.0.1:5000
// ═══════════════════════════════════════════════════════════

const API_BASE = "http://127.0.0.1:5000";

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

// ─── Page Titles ────────────────────────────────────────────
const PAGE_META = {
    dashboard: { title: "Dashboard",       subtitle: "Real-time surveillance" },
    upload:    { title: "Upload & Analyze", subtitle: "Upload video for motion analysis" },
    alerts:    { title: "Alerts",           subtitle: "Motion detection history" },
    anomaly:   { title: "Anomaly AI",       subtitle: "Autoencoder anomaly detection — Fighting · Robbery · Stealing · Shooting · Burglary" },
};

// ═══════════════════════════════════════════════════════════
//  SECTION NAVIGATION
// ═══════════════════════════════════════════════════════════

function navigateTo(section) {
    // Hide all page sections
    document.querySelectorAll(".page-section").forEach(el => {
        el.style.display = "none";
    });

    // Show sections for this page
    document.querySelectorAll(`[data-page="${section}"]`).forEach(el => {
        el.style.display = "";
    });

    // Stats grid visible on dashboard only
    const statsGrid = document.getElementById("statsGrid");
    if (statsGrid) {
        statsGrid.style.display = section === "dashboard" ? "grid" : "none";
    }

    // Video container appears alongside upload when a video is loaded
    if (section === "upload" && videoPlayer.src) {
        videoContainer.style.display = "";
    }

    // Update topbar title
    const meta = PAGE_META[section] || PAGE_META.dashboard;
    const titleEl = document.getElementById("pageTitle");
    const subtitleEl = document.getElementById("pageSubtitle");
    if (titleEl) titleEl.textContent = meta.title;
    if (subtitleEl) subtitleEl.textContent = meta.subtitle;

    // Update nav active state
    document.querySelectorAll(".nav-item").forEach(n => n.classList.remove("active"));
    const activeNav = document.querySelector(`.nav-item[data-section="${section}"]`);
    if (activeNav) activeNav.classList.add("active");

    // Close mobile sidebar
    const sidebar = document.getElementById("sidebar");
    if (sidebar) sidebar.classList.remove("open");
}

// ─── Sidebar Nav Click Handlers ─────────────────────────────
document.querySelectorAll(".nav-item").forEach(item => {
    item.addEventListener("click", (e) => {
        e.preventDefault();
        const section = item.getAttribute("data-section");
        navigateTo(section);
    });
});

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

// Set start time on dashboard
const startTimeEl = document.getElementById("startTime");
if (startTimeEl) {
    startTimeEl.textContent = new Date().toLocaleTimeString("en-US", {
        hour: "2-digit", minute: "2-digit"
    });
}

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
    const results = document.getElementById("detectionResults");
    if (results) results.style.display = "none";
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

    if (progressContainer) progressContainer.style.display = "block";
    if (uploadActions) uploadActions.style.display = "none";
    uploadStatus.innerText = "";

    const xhr = new XMLHttpRequest();

    xhr.upload.addEventListener("progress", (e) => {
        if (e.lengthComputable) {
            const pct = Math.round((e.loaded / e.total) * 100);
            if (progressBar) progressBar.style.width = pct + "%";
            if (progressPercent) progressPercent.textContent = pct + "%";
            if (progressLabel) progressLabel.textContent = pct < 100 ? "Uploading..." : "Processing video...";
        }
    });

    xhr.addEventListener("load", () => {
        if (progressContainer) progressContainer.style.display = "none";
        try {
            const data = JSON.parse(xhr.responseText);
            if (data.error && !data.message) {
                uploadStatus.innerText = "❌ Error: " + data.error;
                return;
            }
            uploadStatus.innerText = "✅ " + data.message;

            // Update stats
            const statVideos = document.getElementById("statVideos");
            if (statVideos) statVideos.textContent = parseInt(statVideos.textContent || 0) + 1;

            // Add to activity timeline
            let summaryText = data.motion_detected ? "Motion found" : "No motion";
            if (data.detection_summary && Object.keys(data.detection_summary).length > 0) {
                const keys = Object.keys(data.detection_summary).map(k => `${k} (${data.detection_summary[k]})`);
                summaryText += ` | Detected: ${keys.join(", ")}`;
            }
            addActivity(`Video processed: ${file.name} — ${summaryText}`);

            // Play processed video
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

            const alertBadge = document.getElementById("alertBadge");
            const alertCount = document.getElementById("alertCount");
            const statAlerts = document.getElementById("statAnomalies");

            if (alertBadge) alertBadge.textContent = alerts.length;
            if (alertCount) alertCount.textContent = alerts.length + " alerts today";
            if (statAlerts) statAlerts.textContent = alerts.length;

            // Only update alerts container if we're on the alerts page
            const alertsSection = document.getElementById("alertsSection");
            if (!alertsSection || alertsSection.style.display === "none") return;

            alertsContainer.innerHTML = "";
            if (alerts.length === 0) {
                alertsContainer.innerHTML = `
                    <div class="empty-state">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                            <path d="M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z"/>
                            <path d="M8 14s1.5 2 4 2 4-2 4-2"/>
                            <line x1="9" y1="9" x2="9.01" y2="9"/>
                            <line x1="15" y1="9" x2="15.01" y2="9"/>
                        </svg>
                        <p>No motion detected — all clear!</p>
                    </div>`;
                return;
            }

            alerts.forEach(alert => {
                const card = document.createElement("div");
                card.className = "alert-card";
                const imgPath = alert.snapshot
                    ? (alert.snapshot.startsWith('http') ? alert.snapshot : `${API_BASE}/${alert.snapshot}`)
                    : (alert.frame_path ? `${API_BASE}/alerts/${alert.frame_path}` : "");

                const clsName = alert.class || "motion";
                const confText = alert.confidence ? `${Math.round(alert.confidence*100)}%` : "N/A";
                
                let speedHTML = "";
                
                let badgeStyle = "background-color: #ef4444; color: white;"; // red default
                if (clsName === "person") badgeStyle = "background-color: #10b981; color: white;"; // green
                else if (clsName === "car") badgeStyle = "background-color: #f97316; color: white;"; // orange
                else if (clsName === "dog") badgeStyle = "background-color: #06b6d4; color: white;"; // cyan
                else if (clsName === "cell phone") badgeStyle = "background-color: #d946ef; color: white;"; // magenta
                else if (clsName === "motion") badgeStyle = "background-color: #eab308; color: black;"; // yellow

                // Build snapshot or clip media element
                const clipUrl  = alert.clip  ? `${API_BASE}/${alert.clip}`  : "";
                const snapUrl  = alert.snapshot
                    ? (alert.snapshot.startsWith('http') ? alert.snapshot : `${API_BASE}/${alert.snapshot}`)
                    : (alert.frame_path ? `${API_BASE}/alerts/${alert.frame_path}` : "");

                let mediaHTML = "";
                if (clipUrl) {
                    // Show video clip with snapshot as poster
                    mediaHTML = `
                        <div class="alert-media">
                            <video
                                src="${clipUrl}"
                                poster="${snapUrl}"
                                controls
                                muted
                                preload="metadata"
                                style="width:100%;max-height:180px;border-radius:8px;cursor:pointer;background:#000;"
                                title="Detection clip — click to play"
                            ></video>
                            <span class="clip-badge">📹 Clip</span>
                        </div>`;
                } else if (snapUrl) {
                    mediaHTML = `<img src="${snapUrl}" onerror="this.style.display='none'" style="width:100%;max-height:180px;object-fit:cover;border-radius:8px;">`;
                }

                card.innerHTML = `
                    ${mediaHTML}
                    <div class="alert-info">
                        <h3 style="display:flex; align-items:center; gap:6px;">
                            <span class="alert-type-badge" style="${badgeStyle} text-transform: capitalize;">${clsName}</span>
                            ${speedHTML}
                        </h3>
                        <p>${(alert.timestamp || "").replace('T', ' ')}</p>
                        <p style="font-size: 12px; color: #94a3b8;">${alert.confidence ? 'Confidence: ' + confText : (alert.description || 'Motion detected')}</p>
                        ${clipUrl ? `<a href="${clipUrl}" download style="font-size:12px;color:#60a5fa;text-decoration:none;">⬇ Download clip</a>` : ""}
                    </div>
                `;
                alertsContainer.appendChild(card);
            });
        })
        .catch(() => {});
}

// ─── Initial Load & Polling ─────────────────────────────────
fetchAlerts();
setInterval(fetchAlerts, 5000);

// ═══════════════════════════════════════════════════════════
//  ANOMALY AI PANEL
// ═══════════════════════════════════════════════════════════

function fetchAnomalyStatus() {
    fetch(`${API_BASE}/api/anomaly/status`)
        .then(r => r.json())
        .then(data => {
            const pill     = document.getElementById('anomalyModelStatus');
            const dot      = document.getElementById('anomalyModelDot');
            const text     = document.getElementById('anomalyModelText');
            const banner   = document.getElementById('anomalyInfoBanner');
            const catPills = document.getElementById('anomalyCategoryPills');

            if (data.model_loaded) {
                if (pill)  pill.className = 'anomaly-model-pill anomaly-model-pill--ready';
                if (dot)   dot.classList.add('pulse');
                if (text)  text.textContent = `Model Active — threshold: ${data.threshold ? data.threshold.toFixed(5) : 'n/a'}`;
                if (banner) banner.style.display = 'none';
                if (catPills && data.detects && data.detects.length) {
                    catPills.style.display = 'flex';
                    catPills.innerHTML = data.detects
                        .map(c => `<span class="anomaly-category-pill">${c}</span>`)
                        .join('');
                }
            } else {
                if (pill)  pill.className = 'anomaly-model-pill anomaly-model-pill--missing';
                if (text)  text.textContent = 'Model Not Loaded';
                if (banner) banner.style.display = 'flex';
                if (catPills) catPills.style.display = 'none';
            }
        })
        .catch(() => {});
}

function renderAnomalyCard(alert) {
    const sev = alert.severity || 'unknown';
    const sevColors = { low: '#f97316', medium: '#ef4444', high: '#dc2626' };
    const sevColor = sevColors[sev] || '#6b7280';

    const snapUrl = alert.snapshot
        ? (alert.snapshot.startsWith('http') ? alert.snapshot : `${API_BASE}/${alert.snapshot}`)
        : '';
    const clipUrl = alert.clip && alert.clip !== ''
        ? (alert.clip.startsWith('http') ? alert.clip : `${API_BASE}/${alert.clip}`)
        : '';

    let mediaHTML = '';
    if (clipUrl) {
        mediaHTML = `
            <div class="alert-media">
                <video src="${clipUrl}" poster="${snapUrl}" controls muted preload="metadata"
                       style="width:100%;max-height:180px;border-radius:8px 8px 0 0;background:#000;"
                       title="Anomaly clip"></video>
                <span class="clip-badge">📹 Clip</span>
            </div>`;
    } else if (snapUrl) {
        mediaHTML = `<img src="${snapUrl}" onerror="this.style.display='none'"
            style="width:100%;max-height:180px;object-fit:cover;border-radius:8px 8px 0 0;">`;
    }

    const conf = Math.round((alert.confidence || 0) * 100);
    const ts   = (alert.timestamp || '').replace('T', ' ').slice(0, 19);
    const err  = alert.reconstruction_error ? alert.reconstruction_error.toFixed(5) : 'n/a';
    const thr  = alert.threshold            ? alert.threshold.toFixed(5)            : 'n/a';

    return `
        <div class="alert-card anomaly-card" style="border-left: 3px solid ${sevColor};">
            ${mediaHTML}
            <div class="alert-info">
                <h3 style="display:flex;align-items:center;gap:6px;">
                    <span class="alert-type-badge" style="background:${sevColor};color:#fff;">
                        ${sev.toUpperCase()}
                    </span>
                    <span style="font-size:0.75rem;color:var(--text-muted);font-weight:600;">ANOMALY</span>
                </h3>
                <p>${ts}</p>
                <p style="font-size:12px;color:#94a3b8;">Confidence: ${conf}%</p>
                <p style="font-size:11px;color:var(--text-muted);">Error: ${err} &nbsp;/&nbsp; Threshold: ${thr}</p>
                ${clipUrl ? `<a href="${clipUrl}" download style="font-size:12px;color:#60a5fa;text-decoration:none;">&#11015; Download clip</a>` : ''}
            </div>
        </div>`;
}

function fetchAnomalyAlerts() {
    fetch(`${API_BASE}/api/alerts/anomaly`)
        .then(r => r.json())
        .then(data => {
            const count   = data.count || 0;
            const alerts  = data.alerts || [];

            const statEl  = document.getElementById('statAnomalyCount');
            const badge   = document.getElementById('anomalyNavBadge');
            const countEl = document.getElementById('anomalyCount');
            if (statEl)  statEl.textContent  = count;
            if (countEl) countEl.textContent = `${count} event${count !== 1 ? 's' : ''}`;
            if (badge) {
                badge.textContent   = count;
                badge.style.display = count > 0 ? '' : 'none';
            }

            const section = document.getElementById('anomalySection');
            if (!section || section.style.display === 'none') return;
            const container = document.getElementById('anomalyAlertsContainer');
            if (!container) return;

            if (alerts.length === 0) {
                container.innerHTML = `
                    <div class="empty-state">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                            <path d="M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z"/>
                            <path d="M8 14s1.5 2 4 2 4-2 4-2"/>
                            <line x1="9" y1="9" x2="9.01" y2="9"/>
                            <line x1="15" y1="9" x2="15.01" y2="9"/>
                        </svg>
                        <p>No anomalies detected &mdash; all clear!</p>
                    </div>`;
                return;
            }
            container.innerHTML = alerts.map(renderAnomalyCard).join('');
        })
        .catch(() => {});
}

// Start anomaly polling
fetchAnomalyStatus();
fetchAnomalyAlerts();
setInterval(fetchAnomalyStatus, 30000);
setInterval(fetchAnomalyAlerts, 10000);



// ═══════════════════════════════════════════════════════════
//  LIVE CAMERA CONTROLS
// ═══════════════════════════════════════════════════════════

const liveFeedImage      = document.getElementById("liveFeedImage");
const liveFeedPlaceholder = document.getElementById("liveFeedPlaceholder");
const startCameraBtn     = document.getElementById("startCameraBtn");
const stopCameraBtn      = document.getElementById("stopCameraBtn");
const cameraStatus       = document.getElementById("cameraStatus");
const cameraStatusText   = document.getElementById("cameraStatusText");
const motionStatusEl     = document.getElementById("motionStatus");

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

            liveFeedPlaceholder.style.display = "none";
            liveFeedImage.style.display = "block";
            liveFeedImage.src = `${API_BASE}/api/live?t=` + Date.now();

            startCameraBtn.style.display = "none";
            stopCameraBtn.style.display = "inline-flex";

            cameraStatus.className = "camera-status active";
            cameraStatusText.textContent = "Camera Active";

            addActivity("Live camera started");
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
            liveFeedImage.style.display = "none";
            liveFeedImage.src = "";
            liveFeedPlaceholder.style.display = "";

            stopCameraBtn.style.display = "none";
            startCameraBtn.style.display = "inline-flex";
            startCameraBtn.disabled = false;
            startCameraBtn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="23 7 16 12 23 17 23 7"/><rect x="1" y="5" width="15" height="14" rx="2" ry="2"/></svg> Start Camera';

            cameraStatus.className = "camera-status";
            cameraStatusText.textContent = "Camera Off";
            motionStatusEl.textContent = "—";
            motionStatusEl.className = "feed-stat-value";

            if (cameraStatusInterval) {
                clearInterval(cameraStatusInterval);
                cameraStatusInterval = null;
            }
            addActivity("Live camera stopped");
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

            if (data.motion_detected) {
                motionStatusEl.textContent = "⚠ Motion Detected";
                motionStatusEl.className = "feed-stat-value motion-active";
                cameraStatus.className = "camera-status active";
                cameraStatusText.textContent = "Motion Detected";
            } else {
                motionStatusEl.textContent = "✓ Normal";
                motionStatusEl.className = "feed-stat-value motion-normal";
                cameraStatus.className = "camera-status active";
                cameraStatusText.textContent = "Camera Active";
            }
        })
        .catch(() => {});
}

// ═══════════════════════════════════════════════════════════
//  DASHBOARD HELPERS
// ═══════════════════════════════════════════════════════════

function addActivity(text) {
    const timeline = document.getElementById("activityTimeline");
    if (!timeline) return;

    const item = document.createElement("div");
    item.className = "activity-item activity-item--new";
    item.innerHTML = `
        <span class="activity-dot"></span>
        <span class="activity-text">${text}</span>
        <span class="activity-time">${new Date().toLocaleTimeString("en-US", {
            hour: "2-digit", minute: "2-digit"
        })}</span>
    `;

    // Insert at the top
    if (timeline.children.length > 0) {
        timeline.insertBefore(item, timeline.children[0]);
    } else {
        timeline.appendChild(item);
    }

    // Keep only last 20 activities
    while (timeline.children.length > 20) {
        timeline.removeChild(timeline.lastChild);
    }
}

// ─── Initialize: Show dashboard by default ──────────────────
navigateTo("dashboard");