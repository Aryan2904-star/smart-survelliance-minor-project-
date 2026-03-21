import os
import cv2
import threading
import time
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory, Response
from flask_cors import CORS
from werkzeug.utils import secure_filename

# ─── Path to frontend folder ─────────────────────────────────────
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(os.path.dirname(BACKEND_DIR), "smart survillance (minor project)")

app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path="")
CORS(app)

# ─── Configuration ───────────────────────────────────────────────
UPLOAD_FOLDER = os.path.join(BACKEND_DIR, "uploads")
ALERTS_FOLDER = os.path.join(BACKEND_DIR, "alerts")
ALLOWED_EXTENSIONS = {"mp4", "mov", "avi", "mkv"}

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024  # 500 MB max upload

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(ALERTS_FOLDER, exist_ok=True)


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# ═══════════════════════════════════════════════════════════════════
#  LIVE CAMERA — OpenCV Motion Detection
# ═══════════════════════════════════════════════════════════════════

class CameraStream:
    def __init__(self):
        self.camera = None
        self.is_running = False
        self.lock = threading.Lock()
        self.frame = None
        self.prev_frame = None
        self.motion_detected = False
        self.anomaly_count = 0
        self.alerts = []

    def start(self):
        if self.is_running:
            return {"status": "already running"}
        self.camera = cv2.VideoCapture(0)
        if not self.camera.isOpened():
            return {"error": "Could not open camera. Make sure a webcam is connected."}
        self.is_running = True
        self.anomaly_count = 0
        # Start capture thread
        thread = threading.Thread(target=self._capture_loop, daemon=True)
        thread.start()
        return {"status": "started"}

    def stop(self):
        self.is_running = False
        time.sleep(0.3)
        if self.camera:
            self.camera.release()
            self.camera = None
        self.frame = None
        self.prev_frame = None
        return {"status": "stopped"}

    def _capture_loop(self):
        """Continuously capture frames and run motion detection."""
        while self.is_running and self.camera and self.camera.isOpened():
            ret, raw_frame = self.camera.read()
            if not ret:
                break

            # Resize for performance
            raw_frame = cv2.resize(raw_frame, (640, 480))

            # ─── Motion Detection ────────────────────────────
            gray = cv2.cvtColor(raw_frame, cv2.COLOR_BGR2GRAY)
            gray = cv2.GaussianBlur(gray, (21, 21), 0)

            processed = raw_frame.copy()
            self.motion_detected = False

            if self.prev_frame is not None:
                # Compute difference between current and previous frame
                delta = cv2.absdiff(self.prev_frame, gray)
                thresh = cv2.threshold(delta, 30, 255, cv2.THRESH_BINARY)[1]
                thresh = cv2.dilate(thresh, None, iterations=2)

                # Find contours (areas of motion)
                contours, _ = cv2.findContours(
                    thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
                )

                for contour in contours:
                    area = cv2.contourArea(contour)
                    if area < 3000:
                        continue  # Skip tiny movements

                    self.motion_detected = True
                    (x, y, w, h) = cv2.boundingRect(contour)

                    # Draw green bounding box around motion
                    cv2.rectangle(processed, (x, y), (x + w, y + h), (0, 255, 0), 2)
                    cv2.putText(
                        processed, "Motion Detected", (x, y - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2
                    )

                # If significant motion, generate alert
                if self.motion_detected:
                    self.anomaly_count += 1
                    # Save alert frame every 30 detections (avoid flooding)
                    if self.anomaly_count % 30 == 1:
                        self._save_alert(processed)

            self.prev_frame = gray

            # ─── Overlay status info ─────────────────────────
            status_color = (0, 0, 255) if self.motion_detected else (0, 255, 0)
            status_text = "MOTION DETECTED" if self.motion_detected else "Normal"
            cv2.putText(
                processed, status_text, (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, status_color, 2
            )
            cv2.putText(
                processed,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                (10, processed.shape[0] - 15),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1
            )

            with self.lock:
                self.frame = processed

            time.sleep(0.03)  # ~30 FPS

    def _save_alert(self, frame):
        """Save a frame as an alert."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"alert_{timestamp}.jpg"
        filepath = os.path.join(ALERTS_FOLDER, filename)
        cv2.imwrite(filepath, frame)
        self.alerts.append({
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "description": "Motion detected in surveillance area",
            "frame_path": filename
        })
        # Keep only last 50 alerts
        if len(self.alerts) > 50:
            self.alerts = self.alerts[-50:]

    def get_frame_bytes(self):
        """Get current frame as JPEG bytes."""
        with self.lock:
            if self.frame is None:
                return None
            _, buffer = cv2.imencode(".jpg", self.frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            return buffer.tobytes()


# Global camera instance
camera_stream = CameraStream()


def generate_mjpeg():
    """Generator that yields MJPEG frames for streaming."""
    while camera_stream.is_running:
        frame_bytes = camera_stream.get_frame_bytes()
        if frame_bytes:
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n"
            )
        time.sleep(0.033)  # ~30 FPS


# ═══════════════════════════════════════════════════════════════════
#  ROUTES — Serve Frontend
# ═══════════════════════════════════════════════════════════════════

@app.route("/")
def serve_index():
    return send_from_directory(FRONTEND_DIR, "index.html")


# ═══════════════════════════════════════════════════════════════════
#  ROUTES — API
# ═══════════════════════════════════════════════════════════════════

@app.route("/api/test", methods=["GET"])
def test():
    return jsonify({"message": "Backend working"})


# ─── Live Camera Endpoints ───────────────────────────────────────

@app.route("/api/live", methods=["GET"])
def live_stream():
    """MJPEG video stream endpoint."""
    if not camera_stream.is_running:
        return jsonify({"error": "Camera is not running"}), 400
    return Response(
        generate_mjpeg(),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )


@app.route("/api/live/start", methods=["POST"])
def start_camera():
    result = camera_stream.start()
    if "error" in result:
        return jsonify(result), 500
    return jsonify(result)


@app.route("/api/live/stop", methods=["POST"])
def stop_camera():
    result = camera_stream.stop()
    return jsonify(result)


@app.route("/api/live/status", methods=["GET"])
def camera_status():
    return jsonify({
        "is_running": camera_stream.is_running,
        "motion_detected": camera_stream.motion_detected,
        "anomaly_count": camera_stream.anomaly_count
    })


# ─── Video Upload Endpoints ─────────────────────────────────────

@app.route("/api/upload", methods=["POST"])
def upload_video():
    if "video" not in request.files:
        return jsonify({"error": "No video file provided. Use field name 'video'."}), 400

    file = request.files["video"]

    if file.filename == "":
        return jsonify({"error": "No file selected."}), 400

    if not allowed_file(file.filename):
        return jsonify({
            "error": f"File type not allowed. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
        }), 400

    filename = secure_filename(file.filename)
    save_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file.save(save_path)

    return jsonify({
        "message": "Video uploaded successfully",
        "saved_as": filename,
        "saved_path": f"uploads/{filename}",
        "output_video_url": f"/api/output/{filename}"
    }), 200


@app.route("/api/output/<filename>", methods=["GET"])
def serve_output_video(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


# ─── Alerts Endpoints ───────────────────────────────────────────

@app.route("/api/alerts", methods=["GET"])
def get_alerts():
    return jsonify(camera_stream.alerts)


@app.route("/alerts/<filename>", methods=["GET"])
def serve_alert_frame(filename):
    return send_from_directory(ALERTS_FOLDER, filename)


# ═══════════════════════════════════════════════════════════════════
#  Run Server
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print(f"[OK] Upload folder: {UPLOAD_FOLDER}")
    print(f"[OK] Alerts folder: {ALERTS_FOLDER}")
    print(f"[OK] Frontend folder: {FRONTEND_DIR}")
    print("[START] Flask server running on http://127.0.0.1:5000")
    app.run(debug=True, host="127.0.0.1", port=5000, threaded=True)
