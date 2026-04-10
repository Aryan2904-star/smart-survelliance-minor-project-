"""
detector.py
Motion detection (OpenCV MOG2) returns bounding boxes of motion regions.
YOLOv8 detection returns detected objects with class, confidence, and bbox.
"""
from dataclasses import dataclass
from typing import List, Tuple
import cv2
import numpy as np

# ─── Lazy-load YOLO to avoid slow startup ────────────────────
_yolo_models = {}

def get_yolo(model_name="yolov8n.pt"):
    if model_name not in _yolo_models:
        from ultralytics import YOLO
        _yolo_models[model_name] = YOLO(model_name)
    return _yolo_models[model_name]


# ─── Detection dataclass ────────────────────────────────────
@dataclass
class Detection:
    class_name: str
    confidence: float
    bbox: Tuple[int, int, int, int]  # x1, y1, x2, y2


# ═══════════════════════════════════════════════════════════════
#  MOTION DETECTOR  (OpenCV MOG2)
#  Returns list of bounding-box tuples for motion regions
# ═══════════════════════════════════════════════════════════════

class MotionDetector:
    def __init__(self, min_area: int = 1000):
        self.min_area = min_area
        self.bg_subtractor = cv2.createBackgroundSubtractorMOG2(
            history=500, varThreshold=25, detectShadows=True
        )

    def detect(self, frame: np.ndarray) -> List[Tuple[int, int, int, int]]:
        """
        Returns list of (x1, y1, x2, y2) bounding boxes where motion is detected.
        Empty list = no motion.
        """
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (11, 11), 0)

        fg_mask = self.bg_subtractor.apply(gray)
        _, thresh = cv2.threshold(fg_mask, 200, 255, cv2.THRESH_BINARY)
        thresh = cv2.dilate(thresh, None, iterations=2)

        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        boxes = []
        for contour in contours:
            if cv2.contourArea(contour) > self.min_area:
                x, y, w, h = cv2.boundingRect(contour)
                boxes.append((x, y, x + w, y + h))

        return boxes


# ═══════════════════════════════════════════════════════════════
#  YOLO DETECTOR  (YOLOv8)
# ═══════════════════════════════════════════════════════════════

class YOLODetector:
    def __init__(self, model_name: str = "yolov8n.pt", conf_threshold: float = 0.5):
        self.model_name = model_name
        self.conf_threshold = conf_threshold

    def detect(self, frame: np.ndarray) -> List[Detection]:
        """Run YOLOv8 on frame. Returns list of Detection objects."""
        model = get_yolo(self.model_name)

        # Classes: 0=person, 67=cell phone
        results = model.predict(
            frame,
            conf=self.conf_threshold,
            iou=0.45,
            classes=[0, 67],
            imgsz=640,
            verbose=False,
        )

        detections = []
        for result in results:
            boxes = result.boxes
            if boxes is None:
                continue
            for box in boxes:
                cls_id = int(box.cls[0])
                cls_name = model.names[cls_id] if hasattr(model, "names") else str(cls_id)
                conf = float(box.conf[0])
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().astype(int)

                detections.append(Detection(
                    class_name=cls_name.lower(),
                    confidence=round(conf, 3),
                    bbox=(int(x1), int(y1), int(x2), int(y2)),
                ))

        return detections
