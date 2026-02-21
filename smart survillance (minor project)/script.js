const alertsContainer = document.getElementById("alertsContainer");
const uploadStatus = document.getElementById("uploadStatus");
const videoPlayer = document.getElementById("resultVideo");
const videoContainer = document.getElementById("videoContainer");

function uploadVideo() {
    const fileInput = document.getElementById('videoUpload');
    const file = fileInput.files[0];

    if (!file) {
        alert("Please select a video file!");
        return;
    }

    const formData = new FormData();
    formData.append('video', file);

    uploadStatus.innerText = "Uploading...";

    fetch('/upload', {
        method: 'POST',
        body: formData
    })
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                uploadStatus.innerText = "Error: " + data.error;
            } else {
                uploadStatus.innerText = "Upload successful! Processing started...";
                startProcessing(data.video_id);
            }
        })
        .catch(error => {
            console.error('Error:', error);
            uploadStatus.innerText = "Upload failed.";
        });
}

function startProcessing(videoId) {
    fetch(`/process/${videoId}`, { method: 'POST' })
        .then(response => response.json())
        .then(data => {
            console.log("Processing started:", data);
            pollForVideo(videoId);
        })
        .catch(error => console.error("Processing error:", error));
}

function pollForVideo(videoId) {
    // Check every 2 seconds if video is ready
    const interval = setInterval(() => {
        fetch(`/stream/${videoId}`)
            .then(response => {
                if (response.ok) {
                    clearInterval(interval);
                    uploadStatus.innerText = "Processing Complete! Playing video...";
                    videoContainer.style.display = "block";
                    videoPlayer.src = `/stream/${videoId}`;
                    videoPlayer.play();
                } else {
                    uploadStatus.innerText = "Processing... " + new Date().toLocaleTimeString();
                }
            });
    }, 2000);
}

// Poll for alerts every 5 seconds
function fetchAlerts() {
    fetch('/api/alerts')
        .then(response => response.json())
        .then(alerts => {
            alertsContainer.innerHTML = ''; // Clear current alerts
            alerts.forEach(alert => {
                const card = document.createElement("div");
                card.className = "alert-card";
                // Uses a placeholder image for alert or extracted frame if available
                // For now, using a placeholder icon or similar
                const imgPath = alert.frame_path ? `/static/uploads/${alert.frame_path}` : "https://via.placeholder.com/400x250?text=Anomaly";

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
        });
}

// Initial fetch and periodic polling
fetchAlerts();
setInterval(fetchAlerts, 5000);