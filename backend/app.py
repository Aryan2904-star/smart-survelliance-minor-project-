"""
app.py — Smart Surveillance System (Flask Backend)

Pipeline:
  Motion detected (OpenCV MOG2) → Save snapshot → Run YOLOv8 → Generate alert
"""

import os
import cv2
import json
import threading
import time
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory, Response
from flask_cors import CORS
from werkzeug.utils import secure_filename

from detector import MotionDetector, YOLODetector, Detection

# ─── Paths ────────────────────────────────────────────────────
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(os.path.dirname(BACKEND_DIR), "smart survillance (minor project)")

app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path="")
CORS(app)

# ─── Configuration ───────────────────────────────────────────
UPLOAD_FOLDER = os.path.join(BACKEND_DIR, "uploads")
OUTPUT_FOLDER = os.path.join(BACKEND_DIR, "outputs")
ALERTS_FOLDER = os.path.join(BACKEND_DIR, "alerts")
ALLOWED_EXTENSIONS = {"mp4", "mov", "avi", "mkv"}

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024  # 500 MB

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)
os.makedirs(ALERTS_FOLDER, exist_ok=True)

# ─── App Settings ────────────────────────────────────────────
app_settings = {
    "conf_threshold": 0.50,
}

# ─── Detectors (initialized once) ───────────────────────────
motion_det = MotionDetector(min_area=1000)
yolo_det = YOLODetector(model_name="yolov8n.pt", conf_threshold=app_settings["conf_threshold"])


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def get_color(class_name):
    """Color in BGR for bounding box drawing."""
    colors = {
        "person": (0, 255, 0),       # Green
        "cell phone": (255, 0, 255), # Magenta
    }
    return colors.get(class_name, (255, 255, 255))


# ═══════════════════════════════════════════════════════════════
#  LIVE CAMERA STREAM
# ═══════════════════════════════════════════════════════════════

class CameraStream:
    def __init__(self):
        self.camera = None
        self.is_running = False
        self.lock = threading.Lock()
        self.raw_frame = None
        self.raw_frame_id = 0
        self.frame = None
        self.motion_detected = False
        self.alerts = []
        self._last_alert_per_class = {}  # class_name -> timestamp (float)

    def start(self):
        if self.is_running:
            return {"status": "already running"}

        # Try DirectShow first (more stable on Windows)
        self.camera = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        if not self.camera.isOpened():
            self.camera = cv2.VideoCapture(0)

        if not self.camera.isOpened():
            return {"error": "Could not open camera. Make sure a webcam is connected."}

        self.is_running = True
        self._last_alert_per_class = {}

        # Dual-thread: capture + process (prevents OpenCV/PyTorch deadlocks)
        threading.Thread(target=self._capture_loop, daemon=True).start()
        threading.Thread(target=self._process_loop, daemon=True).start()
        return {"status": "started"}

    def stop(self):
        self.is_running = False
        time.sleep(0.3)
        if self.camera:
            self.camera.release()
            self.camera = None
        self.raw_frame = None
        self.frame = None
        return {"status": "stopped"}

    # ─── Capture Thread ──────────────────────────────────────
    def _capture_loop(self):
        while self.is_running and self.camera and self.camera.isOpened():
            ret, frame = self.camera.read()
            if ret:
                frame = cv2.resize(frame, (640, 480))
                with self.lock:
                    self.raw_frame = frame
                    self.raw_frame_id += 1
            time.sleep(0.01)

    # ─── Processing Thread ───────────────────────────────────
    def _process_loop(self):
        from concurrent.futures import ThreadPoolExecutor

        last_processed_id = -1
        frame_count = 0

        # Async YOLO so it doesn't block the video stream
        yolo_executor = ThreadPoolExecutor(max_workers=1)
        yolo_future = None
        last_yolo_boxes = []       # persist YOLO boxes between frames
        last_yolo_time = 0

        def run_yolo(frame_copy):
            """Worker function for thread pool."""
            return yolo_det.detect(frame_copy)

        while self.is_running:
            # Grab latest frame
            with self.lock:
                if self.raw_frame is None or self.raw_frame_id == last_processed_id:
                    frame_to_process = None
                else:
                    frame_to_process = self.raw_frame.copy()
                    last_processed_id = self.raw_frame_id

            if frame_to_process is None:
                time.sleep(0.005)
                continue

            processed = frame_to_process.copy()
            current_time = time.time()

            # ── Step 1: Motion Detection (returns list of bbox tuples) ──
            motion_boxes = motion_det.detect(frame_to_process)
            has_motion = len(motion_boxes) > 0
            self.motion_detected = has_motion

            # ── Step 2: Draw GREEN rectangles around motion regions ──
            for (mx1, my1, mx2, my2) in motion_boxes:
                cv2.rectangle(processed, (mx1, my1), (mx2, my2), (0, 255, 0), 2)

            # ── Step 3: Async YOLO ───────────────────────────
            # Collect finished YOLO results
            if yolo_future is not None and yolo_future.done():
                try:
                    result_dets = yolo_future.result()
                    last_yolo_boxes = result_dets[:5]
                    # Save alert
                    self._save_alert(frame_to_process, last_yolo_boxes)
                except Exception as e:
                    print(f"[YOLO ERROR] {e}", flush=True)
                    last_yolo_boxes = []
                yolo_future = None

            # Dispatch new YOLO when motion detected, no job pending,
            # and at least 0.3s since last run
            if has_motion and yolo_future is None and (current_time - last_yolo_time) > 0.3:
                yolo_det.conf_threshold = app_settings["conf_threshold"]
                frame_copy = frame_to_process.copy()
                yolo_future = yolo_executor.submit(run_yolo, frame_copy)
                last_yolo_time = current_time
                print(f"[YOLO] Dispatched at frame {frame_count}", flush=True)

            # If motion but no YOLO result yet, still save motion-only alert
            if has_motion and len(last_yolo_boxes) == 0 and yolo_future is None:
                self._save_alert(frame_to_process, [])

            # Clear YOLO boxes after 2s of no motion
            if not has_motion and (current_time - last_yolo_time) > 2.0:
                last_yolo_boxes = []

            # ── Step 4: Draw YOLO bounding boxes (on top of motion) ──
            for det in last_yolo_boxes:
                x1, y1, x2, y2 = det.bbox
                color = get_color(det.class_name)

                cv2.rectangle(processed, (x1, y1), (x2, y2), color, 2)

                label = f"{det.class_name} {int(det.confidence * 100)}%"
                (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
                cv2.rectangle(processed, (x1, y1 - th - 5), (x1 + tw, y1), color, -1)
                cv2.putText(processed, label, (x1, y1 - 3),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)

            # ── Status overlay ───────────────────────────────
            if last_yolo_boxes:
                status_text = "Tracking Active"
                status_color = (0, 200, 255)
            elif has_motion:
                status_text = "Motion Detected"
                status_color = (0, 255, 255)
            else:
                status_text = "Normal"
                status_color = (0, 255, 0)

            cv2.putText(processed, status_text, (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, status_color, 2)

            cv2.putText(processed, datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        (10, processed.shape[0] - 15),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

            with self.lock:
                self.frame = processed

            frame_count += 1
            time.sleep(0.005)


    # ─── Alert Saving ────────────────────────────────────────
    def _save_alert(self, frame, detections):
        """Save snapshot + JSON alert. Debounces per class (30 seconds)."""
        now = time.time()

        # Determine the alert class
        if detections:
            # Take the highest-confidence detection
            best = max(detections, key=lambda d: d.confidence)
            alert_class = best.class_name
            alert_conf = best.confidence
        else:
            alert_class = "unknown"
            alert_conf = 0.0

        # Debounce: skip if same class was alerted within 30 seconds
        if alert_class in self._last_alert_per_class:
            if (now - self._last_alert_per_class[alert_class]) < 30.0:
                return
        self._last_alert_per_class[alert_class] = now

        # File names
        now_dt = datetime.now()
        ts = now_dt.strftime("%Y%m%d_%H%M%S")
        iso = now_dt.strftime("%Y-%m-%dT%H:%M:%S")
        jpg_name = f"alert_{ts}.jpg"
        json_name = f"alert_{ts}.json"

        # Save snapshot
        cv2.imwrite(os.path.join(ALERTS_FOLDER, jpg_name), frame)

        # Save JSON sidecar
        alert_data = {
            "timestamp": iso,
            "motion": True,
            "class": alert_class,
            "confidence": alert_conf,
            "snapshot": f"alerts/{jpg_name}",
        }
        with open(os.path.join(ALERTS_FOLDER, json_name), "w") as f:
            json.dump(alert_data, f)

        # Keep in-memory list for fast API responses
        self.alerts.append(alert_data)
        if len(self.alerts) > 50:
            self.alerts = self.alerts[-50:]

    def get_frame_bytes(self):
        with self.lock:
            if self.frame is None:
                return None
            _, buffer = cv2.imencode(".jpg", self.frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            return buffer.tobytes()


camera_stream = CameraStream()


def generate_mjpeg():
    while camera_stream.is_running:
        frame_bytes = camera_stream.get_frame_bytes()
        if frame_bytes:
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n"
            )
        time.sleep(0.033)


# ═══════════════════════════════════════════════════════════════
#  VIDEO UPLOAD PROCESSING
# ═══════════════════════════════════════════════════════════════

def process_video(input_path, output_path):
    """Process uploaded video: motion → YOLO → annotated output."""
    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        return False, 0, {}

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(output_path, fourcc, int(fps), (width, height))

    # Fresh motion detector for this video
    vid_motion_det = MotionDetector(min_area=1000)
    vid_yolo_det = YOLODetector(model_name="yolov8n.pt", conf_threshold=app_settings["conf_threshold"])

    any_motion = False
    motion_frame_count = 0
    class_counts = {}

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        processed = frame.copy()
        motion_boxes = vid_motion_det.detect(frame)
        has_motion = len(motion_boxes) > 0

        # Draw green rectangles around motion
        for (mx1, my1, mx2, my2) in motion_boxes:
            cv2.rectangle(processed, (mx1, my1), (mx2, my2), (0, 255, 0), 2)

        detections = []
        if has_motion:
            detections = vid_yolo_det.detect(frame)
            any_motion = True
            motion_frame_count += 1

            # Count classes
            for det in detections:
                class_counts[det.class_name] = class_counts.get(det.class_name, 0) + 1

        # Draw YOLO boxes
        for det in detections:
            x1, y1, x2, y2 = det.bbox
            color = get_color(det.class_name)
            cv2.rectangle(processed, (x1, y1), (x2, y2), color, 2)
            label = f"{det.class_name} {int(det.confidence * 100)}%"
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            cv2.rectangle(processed, (x1, y1 - th - 5), (x1 + tw, y1), color, -1)
            cv2.putText(processed, label, (x1, y1 - 3),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)

        # Status text
        if detections:
            status = "Tracking Active"
            sc = (0, 200, 255)
        elif has_motion:
            status = "Motion Detected"
            sc = (0, 255, 255)
        else:
            status = "Normal"
            sc = (0, 255, 0)

        cv2.putText(processed, status, (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, sc, 2)
        cv2.putText(processed, datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    (10, processed.shape[0] - 15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

        out.write(processed)

    cap.release()
    out.release()
    return any_motion, motion_frame_count, class_counts


# ═══════════════════════════════════════════════════════════════
#  ROUTES
# ═══════════════════════════════════════════════════════════════

@app.route("/")
def serve_index():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/api/test", methods=["GET"])
def test():
    return jsonify({"message": "Backend working"})


@app.route("/api/settings", methods=["GET"])
def get_settings():
    return jsonify(app_settings)


@app.route("/api/settings", methods=["POST"])
def update_settings():
    data = request.json
    if "conf_threshold" in data:
        app_settings["conf_threshold"] = float(data["conf_threshold"])
    return jsonify({"status": "success", "settings": app_settings})


# ─── Live Camera ─────────────────────────────────────────────

@app.route("/api/live", methods=["GET"])
def live_stream():
    if not camera_stream.is_running:
        return jsonify({"error": "Camera is not running"}), 400
    return Response(
        generate_mjpeg(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


@app.route("/api/live/start", methods=["POST"])
def start_camera():
    result = camera_stream.start()
    if "error" in result:
        return jsonify(result), 500
    return jsonify(result)


@app.route("/api/live/stop", methods=["POST"])
def stop_camera():
    return jsonify(camera_stream.stop())


@app.route("/api/live/status", methods=["GET"])
def camera_status_endpoint():
    return jsonify({
        "is_running": camera_stream.is_running,
        "motion_detected": camera_stream.motion_detected,
    })


# ─── Upload ──────────────────────────────────────────────────

@app.route("/api/upload", methods=["POST"])
def upload_video():
    if "video" not in request.files:
        return jsonify({"error": "No video file provided. Use field name 'video'."}), 400

    file = request.files["video"]
    if file.filename == "":
        return jsonify({"error": "No file selected."}), 400

    if not allowed_file(file.filename):
        return jsonify({"error": f"File type not allowed. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"}), 400

    filename = secure_filename(file.filename)
    save_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file.save(save_path)

    out_filename = f"processed_{filename}"
    out_path = os.path.join(OUTPUT_FOLDER, out_filename)

    try:
        motion_found, motion_frame_count, class_counts = process_video(save_path, out_path)
    except Exception as e:
        return jsonify({
            "message": "Video uploaded but processing failed",
            "error": str(e),
            "saved_as": filename,
        }), 200

    return jsonify({
        "message": f"Video processed — {'motion detected!' if motion_found else 'no motion found.'}",
        "saved_as": filename,
        "motion_detected": motion_found,
        "motion_frame_count": motion_frame_count,
        "detection_summary": class_counts,
        "output_video_url": f"/api/output/{out_filename}",
    }), 200


@app.route("/api/output/<filename>", methods=["GET"])
def serve_output_video(filename):
    return send_from_directory(OUTPUT_FOLDER, filename)


# ─── Alerts ──────────────────────────────────────────────────

@app.route("/api/alerts", methods=["GET"])
def get_alerts():
    return jsonify(camera_stream.alerts)


@app.route("/alerts/<filename>", methods=["GET"])
def serve_alert_frame(filename):
    return send_from_directory(ALERTS_FOLDER, filename)


# ═══════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print(f"[OK] Upload folder  : {UPLOAD_FOLDER}")
    print(f"[OK] Alerts folder  : {ALERTS_FOLDER}")
    print(f"[OK] Frontend folder: {FRONTEND_DIR}")
    print("[START] Flask server running on http://127.0.0.1:5000")
    app.run(debug=True, host="127.0.0.1", port=5000, threaded=True)
