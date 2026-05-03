"""
app.py — Smart Surveillance System (Flask Backend)

Pipeline:
  Motion detected (MOG2) → Save snapshot + MP4 clip
                         → Run YOLOv8 (person / cell phone)
                         → Run Autoencoder Anomaly Detector
                         → Generate alert
"""

import os
import cv2
import json
import glob
import collections
import threading
import time
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory, Response
from flask_cors import CORS
from werkzeug.utils import secure_filename

from detector import MotionDetector, YOLODetector, Detection

# ─── Anomaly Detector (optional — loads gracefully if model exists) ───
try:
    from anomaly_detector import AnomalyDetector, TRAINED_CATEGORIES
    _anomaly_available = True
except ImportError:
    _anomaly_available = False
    TRAINED_CATEGORIES = []

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
    "conf_threshold": 0.25,   # 0.25: best recall for person + cell phone on YOLOv8n
}

# How many seconds YOLO keeps running after the last detected motion
MOTION_PERSIST_SECS = 5.0

# Minimum gap between consecutive anomaly alerts (seconds)
ANOMALY_DEBOUNCE_SECS = 15.0

# ─── Detectors (initialized once) ───────────────────────────
motion_det = MotionDetector(min_area=1500, var_threshold=60, history=300, warmup_frames=30)
yolo_det   = YOLODetector(model_name="yolov8n.pt", conf_threshold=app_settings["conf_threshold"])

# Anomaly detector — loads silently if model files are missing
if _anomaly_available:
    anomaly_det = AnomalyDetector(
        model_path="models/anomaly_model.h5",
        threshold_path="models/threshold.npy",
    )
else:
    anomaly_det = None
    print("[ANOMALY] anomaly_detector module not available.", flush=True)


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
#  CLIP RECORDER
#  Saves a short MP4 clip around each motion event.
#  Pre-buffer:  3 s of frames before motion triggers recording
#  Post-tail:   4 s of frames after motion stops
# ═══════════════════════════════════════════════════════════════

CLIP_PRE_SECS  = 3.0   # seconds of video kept before motion
CLIP_POST_SECS = 4.0   # seconds of video recorded after motion stops
CLIP_FPS       = 20    # output clip frame-rate

class ClipRecorder:
    """
    Maintains a rolling pre-motion frame buffer.
    When start_clip() is called it begins writing the pre-buffer + new frames.
    When stop_clip() is called it records CLIP_POST_SECS more frames then closes.
    """

    def __init__(self):
        self._buf: collections.deque = collections.deque()
        self._buf_max = int(CLIP_PRE_SECS * CLIP_FPS)
        self._writer: cv2.VideoWriter | None = None
        self._recording = False
        self._stop_after: float = 0.0   # wall-clock time to finish recording
        self._clip_path: str = ""
        self._clip_name: str = ""
        self._lock = threading.Lock()

    # ── Called every frame from the process loop ──────────────
    def feed(self, frame: "np.ndarray") -> "str | None":
        """
        Feed a processed (annotated) frame.
        Returns the finished clip filename when a clip is finalized, else None.
        """
        import numpy as np
        finished_clip = None

        with self._lock:
            # Always push to pre-buffer (ring-buffer)
            self._buf.append(frame.copy())
            if len(self._buf) > self._buf_max:
                self._buf.popleft()

            if self._recording:
                if self._writer is not None:
                    self._writer.write(frame)

                # Check if post-tail has elapsed
                if time.time() >= self._stop_after:
                    self._writer.release()
                    self._writer = None
                    self._recording = False
                    finished_clip = self._clip_name
                    print(f"[CLIP] Saved: {self._clip_name}", flush=True)

        return finished_clip

    def start_clip(self, ts: str) -> str:
        """Begin a new clip. ts is a timestamp string like '20260501_201500'."""
        with self._lock:
            if self._recording:
                # Extend the post-tail instead of starting a new file
                self._stop_after = time.time() + CLIP_POST_SECS
                return self._clip_name

            self._clip_name = f"clip_{ts}.mp4"
            self._clip_path = os.path.join(ALERTS_FOLDER, self._clip_name)

            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            # Use first buffered frame to get size
            if self._buf:
                h, w = list(self._buf)[0].shape[:2]
            else:
                h, w = 480, 640

            self._writer = cv2.VideoWriter(self._clip_path, fourcc, CLIP_FPS, (w, h))

            # Write pre-buffer frames first
            for f in list(self._buf):
                self._writer.write(f)

            self._recording = True
            self._stop_after = time.time() + CLIP_POST_SECS
            print(f"[CLIP] Recording started: {self._clip_name}", flush=True)
            return self._clip_name

    def extend(self):
        """Extend the clip's post-tail (called each frame motion is detected)."""
        with self._lock:
            if self._recording:
                self._stop_after = time.time() + CLIP_POST_SECS

    def stop(self):
        """Hard-stop recording (on camera shutdown)."""
        with self._lock:
            if self._writer:
                self._writer.release()
                self._writer = None
            self._recording = False
            self._buf.clear()


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
        self._last_alert_per_class = {}   # class_name -> timestamp (float)
        self._clip_recorder = ClipRecorder()
        self._active_clip_name: str = ""  # clip currently being recorded
        self._clip_ts: str = ""           # timestamp when current clip started
        self._last_anomaly_time: float = 0.0   # debounce anomaly alerts
        self._last_anomaly_result = None        # most recent AnomalyResult

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
        self._clip_recorder.stop()   # finalize any open clip
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
        last_yolo_boxes = []    # most recent YOLO detections (kept until replaced)
        # Set to -999 so first motion frame dispatches YOLO immediately (no 1s wait)
        last_yolo_time = -999.0
        last_motion_time = 0.0  # timestamp of the last frame that had motion

        def run_yolo(frame_copy):
            return yolo_det.detect(frame_copy)

        while self.is_running:
            # ── Grab latest raw frame ──────────────────────────────
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

            # ── Step 1: Motion Detection ───────────────────────────
            # Returns [] when nothing moves OR during the 30-frame warmup.
            motion_boxes = motion_det.detect(frame_to_process)
            has_motion = len(motion_boxes) > 0

            if has_motion:
                last_motion_time = current_time

            self.motion_detected = has_motion

            # "Active window": true while moving OR for MOTION_PERSIST_SECS after last motion
            in_active_window = (current_time - last_motion_time) < MOTION_PERSIST_SECS

            # ── Step 2: Draw green motion rectangles ───────────────
            # Only draw green outline when MOG2 actually sees motion
            for (mx1, my1, mx2, my2) in motion_boxes:
                cv2.rectangle(processed, (mx1, my1), (mx2, my2), (0, 255, 0), 2)

            # ── Step 3: Async YOLO ─────────────────────────────────
            # Collect finished YOLO result
            save_alert_this_frame = False
            alert_dets_to_save = []

            if yolo_future is not None and yolo_future.done():
                try:
                    result_dets = yolo_future.result()
                    if result_dets:
                        last_yolo_boxes = result_dets[:5]
                        names = [(d.class_name, d.confidence) for d in last_yolo_boxes]
                        print(f"[YOLO] Detected: {names}", flush=True)
                        save_alert_this_frame = True
                        alert_dets_to_save = last_yolo_boxes
                    else:
                        print(f"[YOLO] No detections (conf={app_settings['conf_threshold']})", flush=True)
                        if in_active_window:
                            save_alert_this_frame = True
                            alert_dets_to_save = []
                except Exception as e:
                    print(f"[YOLO ERROR] {e}", flush=True)
                yolo_future = None

            # Dispatch YOLO:
            #   • must be in active window (motion happening or persisting)
            #   • no job currently queued
            #   • at least 1.0s since last dispatch
            if (in_active_window
                    and yolo_future is None
                    and (current_time - last_yolo_time) > 1.0):
                yolo_det.conf_threshold = app_settings["conf_threshold"]
                frame_copy = frame_to_process.copy()
                yolo_future = yolo_executor.submit(run_yolo, frame_copy)
                last_yolo_time = current_time
                print(f"[YOLO] Dispatching... (frame={frame_count}, motion={has_motion})", flush=True)

            # Only clear YOLO boxes well after the active window ends (10s)
            # This prevents labels flickering off between consecutive YOLO runs
            if (current_time - last_motion_time) > (MOTION_PERSIST_SECS + 5.0):
                last_yolo_boxes = []

            # ── Step 4: Draw YOLO bounding boxes ───────────────────
            for det in last_yolo_boxes:
                x1, y1, x2, y2 = det.bbox
                color = get_color(det.class_name)
                cv2.rectangle(processed, (x1, y1), (x2, y2), color, 2)
                label = f"{det.class_name} {int(det.confidence * 100)}%"
                (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
                cv2.rectangle(processed, (x1, y1 - th - 8), (x1 + tw + 4, y1), color, -1)
                cv2.putText(processed, label, (x1 + 2, y1 - 4),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 2)

            # ── Status overlay ─────────────────────────────────────
            if last_yolo_boxes:
                status_text = "Tracking Active"
                status_color = (0, 200, 255)   # orange
            elif has_motion:
                status_text = "Motion Detected"
                status_color = (0, 255, 255)   # yellow
            elif in_active_window:
                status_text = "Analysing..."
                status_color = (200, 200, 0)   # teal
            else:
                status_text = "Normal"
                status_color = (0, 220, 0)     # green

            cv2.putText(processed, status_text, (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, status_color, 2)
            cv2.putText(processed, datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        (10, processed.shape[0] - 15),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

            # ── Step 5: Anomaly Detection (Autoencoder) ────────────
            anomaly_result = None
            if (anomaly_det is not None
                    and anomaly_det.loaded
                    and in_active_window
                    and (current_time - last_motion_time) < 2.0):
                # Run anomaly inference every ~2 s to keep CPU/GPU manageable
                if not hasattr(self, '_last_anomaly_infer'):
                    self._last_anomaly_infer = 0.0
                if (current_time - self._last_anomaly_infer) > 2.0:
                    self._last_anomaly_infer = current_time
                    try:
                        anomaly_result = anomaly_det.predict(frame_to_process)
                        self._last_anomaly_result = anomaly_result
                        if anomaly_result.is_anomaly:
                            sev = anomaly_result.severity.upper()
                            conf = int(anomaly_result.confidence * 100)
                            print(f"[ANOMALY] {sev}  conf={conf}%  "
                                  f"err={anomaly_result.reconstruction_error:.5f}",
                                  flush=True)
                    except Exception as ae:
                        print(f"[ANOMALY] Error: {ae}", flush=True)

            # Draw anomaly overlay if flagged
            ar = self._last_anomaly_result
            if ar and ar.is_anomaly and in_active_window:
                severity_colors = {
                    'low':    (0, 165, 255),   # orange
                    'medium': (0, 80,  255),   # orange-red
                    'high':   (0, 0,   255),   # red
                }
                a_color = severity_colors.get(ar.severity, (0, 0, 255))
                # Full-frame border
                h_f, w_f = processed.shape[:2]
                cv2.rectangle(processed, (0, 0), (w_f - 1, h_f - 1), a_color, 5)
                # Anomaly label at top
                a_label = f"ANOMALY [{ar.severity.upper()}] {int(ar.confidence*100)}%"
                (atw, ath), _ = cv2.getTextSize(a_label, cv2.FONT_HERSHEY_SIMPLEX, 0.75, 2)
                cv2.rectangle(processed, (0, 0), (atw + 10, ath + 14), a_color, -1)
                cv2.putText(processed, a_label, (5, ath + 6),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.75, (255, 255, 255), 2)

                # Save anomaly alert (debounced)
                if (current_time - self._last_anomaly_time) > ANOMALY_DEBOUNCE_SECS:
                    self._last_anomaly_time = current_time
                    self._save_anomaly_alert(processed.copy(), ar)

            if save_alert_this_frame:
                self._save_alert(processed.copy(), alert_dets_to_save)

            with self.lock:
                self.frame = processed

            # ── Step 6: Clip Recording ──────────────────────────────
            # Feed annotated frame to the rolling buffer / writer
            finished = self._clip_recorder.feed(processed)
            if finished:
                # Clip just closed — attach it to the most recent alert
                self._attach_clip_to_alert(finished)

            # Start / extend clip while motion is happening
            if has_motion:
                ts_str = datetime.now().strftime("%Y%m%d_%H%M%S")
                clip_name = self._clip_recorder.start_clip(ts_str)
                if clip_name != self._active_clip_name:
                    # New clip started
                    self._active_clip_name = clip_name
                    self._clip_ts = ts_str
                else:
                    self._clip_recorder.extend()

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

        # Clip: attach the clip currently being recorded
        clip_name = self._active_clip_name if self._active_clip_name else ""

        # Save JSON sidecar
        alert_data = {
            "timestamp": iso,
            "motion": True,
            "class": alert_class,
            "confidence": alert_conf,
            "snapshot": f"alerts/{jpg_name}",
            "clip": f"alerts/clip/{clip_name}" if clip_name else "",
        }
        with open(os.path.join(ALERTS_FOLDER, json_name), "w") as f:
            json.dump(alert_data, f)

        # Keep in-memory list for fast API responses
        self.alerts.append(alert_data)
        if len(self.alerts) > 50:
            self.alerts = self.alerts[-50:]

    def _attach_clip_to_alert(self, clip_name: str):
        """Once a clip finishes writing, patch the matching in-memory alert."""
        clip_url = f"alerts/clip/{clip_name}"
        for alert in reversed(self.alerts):
            if alert.get("clip", "") in ("", clip_url):
                alert["clip"] = clip_url
                break

    # ─── Anomaly Alert Saving ─────────────────────────────────
    def _save_anomaly_alert(self, frame, result):
        """Persist a snapshot + JSON sidecar for an anomaly event."""
        now_dt = datetime.now()
        ts     = now_dt.strftime("%Y%m%d_%H%M%S_%f")
        iso    = now_dt.isoformat()

        jpg_name  = f"anomaly_{ts}.jpg"
        json_name = f"anomaly_{ts}.json"

        cv2.imwrite(os.path.join(ALERTS_FOLDER, jpg_name), frame)

        meta = {
            "timestamp":              iso,
            "type":                   "anomaly",
            "severity":               result.severity,
            "confidence":             result.confidence,
            "reconstruction_error":   result.reconstruction_error,
            "threshold":              result.threshold,
            "snapshot":               f"alerts/{jpg_name}",
            "clip":                   f"alerts/clip/{self._active_clip_name}" if self._active_clip_name else "",
            "detectable_categories":  TRAINED_CATEGORIES,
        }
        with open(os.path.join(ALERTS_FOLDER, json_name), "w") as f:
            json.dump(meta, f, indent=2)

        print(f"[ANOMALY ALERT] {result.severity.upper()}  saved {jpg_name}", flush=True)

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

    # Fresh motion detector per video (own background model)
    vid_motion_det = MotionDetector(min_area=1500, var_threshold=60, history=300, warmup_frames=30)
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
    data = request.json or {}
    if "conf_threshold" in data:
        app_settings["conf_threshold"] = float(data["conf_threshold"])
    if anomaly_det and "anomaly_detector_active" in data:
        anomaly_det.active = bool(data["anomaly_detector_active"])
    if anomaly_det and "anomaly_threshold_override" in data:
        val = data["anomaly_threshold_override"]
        anomaly_det.threshold_override = float(val) if val else None
    return jsonify({"status": "success", "settings": app_settings})


@app.route("/api/anomaly/status", methods=["GET"])
def anomaly_status():
    """Return current anomaly detector state."""
    if anomaly_det is None or not anomaly_det.loaded:
        return jsonify({
            "model_loaded":      False,
            "detector_active":   False,
            "threshold":         None,
            "detects":           TRAINED_CATEGORIES,
            "message":           "Model not loaded. Run ml_model/train_autoencoder.ipynb and place files in backend/models/",
        })
    return jsonify({
        "model_loaded":    True,
        "detector_active": anomaly_det.active,
        "threshold":       anomaly_det.effective_threshold,
        "detects":         TRAINED_CATEGORIES,
    })


@app.route("/api/alerts/anomaly", methods=["GET"])
def get_anomaly_alerts():
    """Return all saved anomaly alert JSON files (newest first)."""
    pattern = os.path.join(ALERTS_FOLDER, "anomaly_*.json")
    files   = sorted(glob.glob(pattern), reverse=True)
    alerts  = []
    for jf in files[:50]:        # cap at 50 most recent
        try:
            with open(jf) as f:
                alerts.append(json.load(f))
        except Exception:
            pass
    return jsonify({"count": len(alerts), "alerts": alerts})


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


@app.route("/alerts/clip/<filename>", methods=["GET"])
def serve_alert_clip(filename):
    """Serve MP4 clip files saved during motion detection events."""
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
