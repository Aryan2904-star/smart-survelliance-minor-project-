"""
detector.py
Motion detection (OpenCV MOG2) + YOLOv8 object detection.

Design decisions:
  - MOG2 only (no frame-diff): frame-diff creates false positives on noisy webcams
  - varThreshold=60: robust against webcam sensor noise
  - min_area=1500: ignores small noise blobs
  - YOLO conf=0.35: good recall for person + cell phone
  - Motion cooldown: YOLO keeps running for MOTION_PERSIST_SECS after
    MOG2 last detected motion (handles MOG2 adapting to stationary objects)
"""

from dataclasses import dataclass
from typing import List, Tuple, Optional
import cv2
import numpy as np

# ─── Lazy-load YOLO to avoid slow startup ────────────────────
_yolo_models: dict = {}

def get_yolo(model_name: str = "yolov8n.pt"):
    if model_name not in _yolo_models:
        from ultralytics import YOLO
        _yolo_models[model_name] = YOLO(model_name)
    return _yolo_models[model_name]


# ─── Detection dataclass ────────────────────────────────────
@dataclass
class Detection:
    class_name: str
    confidence: float
    bbox: Tuple[int, int, int, int]   # x1, y1, x2, y2


# ═══════════════════════════════════════════════════════════════
#  MOTION DETECTOR  (OpenCV MOG2)
#  Returns list of (x1,y1,x2,y2) bounding boxes for motion regions.
#  Returns empty list when there is NO movement.
# ═══════════════════════════════════════════════════════════════

class MotionDetector:
    """
    Pure MOG2 motion detector.

    Parameters
    ----------
    min_area      : ignore contours smaller than this (px²).
    var_threshold : MOG2 Mahalanobis distance threshold.
                    Higher = less sensitive = fewer false positives on noisy cameras.
    history       : number of frames MOG2 uses to build the background model.
    warmup_frames : frames to skip before reporting motion (lets MOG2 stabilise).
    """

    def __init__(
        self,
        min_area: int = 1500,
        var_threshold: float = 60,
        history: int = 300,
        warmup_frames: int = 30,
    ):
        self.min_area = min_area
        self.warmup_frames = warmup_frames
        self._frame_count = 0

        # detectShadows=False → fg mask is clean 0/255 only
        self.bg_subtractor = cv2.createBackgroundSubtractorMOG2(
            history=history,
            varThreshold=var_threshold,
            detectShadows=False,
        )

        # Morphological kernel for closing gaps in the mask
        self._kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))

    def detect(self, frame: np.ndarray) -> List[Tuple[int, int, int, int]]:
        """
        Feed one BGR frame. Returns bounding-box list.
        Returns [] during warmup and when nothing moves.
        """
        # Convert to gray + blur to suppress sensor noise
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (21, 21), 0)

        # Apply MOG2
        fg_mask = self.bg_subtractor.apply(blurred)

        self._frame_count += 1
        # Skip reporting during warmup (background model is not stable yet)
        if self._frame_count <= self.warmup_frames:
            return []

        # Clean the mask
        # 1. Binary threshold (mask is already 0/255 since detectShadows=False)
        _, thresh = cv2.threshold(fg_mask, 200, 255, cv2.THRESH_BINARY)
        # 2. Erode to kill isolated noise pixels
        thresh = cv2.erode(thresh, self._kernel, iterations=1)
        # 3. Dilate + close to merge nearby blobs
        thresh = cv2.dilate(thresh, self._kernel, iterations=3)
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, self._kernel)

        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        boxes = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area > self.min_area:
                x, y, w, h = cv2.boundingRect(cnt)
                boxes.append((x, y, x + w, y + h))

        return boxes


# ═══════════════════════════════════════════════════════════════
#  YOLO DETECTOR  (YOLOv8)
# ═══════════════════════════════════════════════════════════════

class YOLODetector:
    """
    YOLOv8 wrapper. Detects person (class 0) and cell phone (class 67).
    Confidence threshold is deliberately kept at 0.35 for better recall;
    raise it in app_settings if you get too many false positives.
    """

    def __init__(self, model_name: str = "yolov8n.pt", conf_threshold: float = 0.35):
        self.model_name = model_name
        self.conf_threshold = conf_threshold

    def detect(self, frame: np.ndarray) -> List[Detection]:
        """
        Run YOLOv8 on a BGR uint8 frame.
        Returns a list of Detection objects sorted by confidence (highest first).
        """
        model = get_yolo(self.model_name)

        # Guard: YOLO needs BGR uint8
        if frame is None or frame.size == 0:
            return []
        if frame.dtype != np.uint8:
            frame = np.clip(frame, 0, 255).astype(np.uint8)

        results = model.predict(
            frame,
            conf=self.conf_threshold,
            iou=0.5,
            classes=[0, 67],       # 0=person, 67=cell phone
            imgsz=640,
            verbose=False,
            agnostic_nms=True,
            half=False,            # full precision → more accurate on CPU
        )

        detections: List[Detection] = []
        for result in results:
            if result.boxes is None:
                continue
            for box in result.boxes:
                cls_id  = int(box.cls[0])
                conf    = float(box.conf[0])
                cls_name = (model.names.get(cls_id) or str(cls_id)).lower()

                xyxy = box.xyxy[0]
                if hasattr(xyxy, "cpu"):
                    xyxy = xyxy.cpu().numpy()
                x1, y1, x2, y2 = xyxy.astype(int).tolist()

                detections.append(Detection(
                    class_name=cls_name,
                    confidence=round(conf, 3),
                    bbox=(x1, y1, x2, y2),
                ))

        # Sort highest confidence first
        detections.sort(key=lambda d: d.confidence, reverse=True)
        return detections
