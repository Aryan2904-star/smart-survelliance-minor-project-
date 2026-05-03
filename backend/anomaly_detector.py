"""
anomaly_detector.py — Convolutional Autoencoder Anomaly Detector

Loads a Keras model trained on Normal surveillance frames.
Flags frames whose reconstruction error exceeds the calibrated threshold
as anomalies, assigning a severity level (low / medium / high).

Trained to detect:
  Fighting · Robbery · Road Accident · Stealing · Shooting · Burglary
"""

import os
import numpy as np
import cv2
from dataclasses import dataclass

# The 6 anomaly categories this model was calibrated against
TRAINED_CATEGORIES = [
    "Fighting", "Robbery", "Road Accident",
    "Stealing", "Shooting", "Burglary",
]

# ── Sentinel result returned when the model is not loaded ──────────────
@dataclass
class AnomalyResult:
    is_anomaly: bool
    reconstruction_error: float
    threshold: float
    confidence: float       # 0.0 → 1.0  (error / threshold, capped at 1)
    severity: str           # 'none' | 'low' | 'medium' | 'high'


# ── Null result ────────────────────────────────────────────────────────
_NULL_RESULT = AnomalyResult(
    is_anomaly=False,
    reconstruction_error=0.0,
    threshold=0.0,
    confidence=0.0,
    severity="none",
)


class AnomalyDetector:
    """
    Convolutional Autoencoder anomaly detector.

    Parameters
    ----------
    model_path     : path to anomaly_model.h5
    threshold_path : path to threshold.npy

    Usage
    -----
    detector = AnomalyDetector()
    result   = detector.predict(bgr_frame)
    if result.is_anomaly:
        print(result.severity, result.confidence)
    """

    def __init__(
        self,
        model_path: str = "models/anomaly_model.h5",
        threshold_path: str = "models/threshold.npy",
    ):
        self.loaded = False
        self.active = True                  # can be toggled via API
        self.threshold_override: float | None = None
        self._model = None
        self.threshold: float = 0.0

        # Resolve paths relative to this file's directory
        base = os.path.dirname(os.path.abspath(__file__))
        model_abs     = os.path.join(base, model_path)
        threshold_abs = os.path.join(base, threshold_path)

        if not os.path.exists(model_abs):
            print(
                f"[ANOMALY] Model not found at {model_abs}.\n"
                f"          Run ml_model/train_autoencoder.ipynb on Colab first,\n"
                f"          then place anomaly_model.h5 + threshold.npy in backend/models/",
                flush=True,
            )
            return

        if not os.path.exists(threshold_abs):
            print(f"[ANOMALY] threshold.npy not found at {threshold_abs}.", flush=True)
            return

        try:
            import tensorflow as tf
            # Suppress TF info/warning spam
            os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
            self._model   = tf.keras.models.load_model(model_abs, compile=False)
            self.threshold = float(np.load(threshold_abs))
            self.loaded    = True
            print(f"[ANOMALY] Model loaded. Threshold: {self.threshold:.6f}", flush=True)
            print(f"[ANOMALY] Detects: {', '.join(TRAINED_CATEGORIES)}", flush=True)
        except Exception as exc:
            print(f"[ANOMALY] Failed to load model: {exc}", flush=True)

    # ── Public API ────────────────────────────────────────────────────

    @property
    def effective_threshold(self) -> float:
        return self.threshold_override if self.threshold_override else self.threshold

    def predict(self, frame: np.ndarray) -> AnomalyResult:
        """
        Run autoencoder inference on one BGR frame.
        Returns a null result immediately if model is not loaded or inactive.
        """
        if not self.loaded or not self.active or self._model is None:
            return _NULL_RESULT

        try:
            # ── Pre-process ──────────────────────────────────────────
            gray     = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            resized  = cv2.resize(gray, (128, 128))
            norm     = resized.astype("float32") / 255.0
            tensor   = norm.reshape(1, 128, 128, 1)

            # ── Reconstruct ──────────────────────────────────────────
            recon = self._model.predict(tensor, verbose=0)
            error = float(np.mean(np.power(tensor - recon, 2)))

            t          = self.effective_threshold
            raw_conf   = error / t if t > 0 else 0.0
            confidence = min(raw_conf, 1.0)
            is_anomaly = error > t

            # ── Severity banding ─────────────────────────────────────
            if not is_anomaly:
                severity = "none"
            elif raw_conf < 1.3:
                severity = "low"
            elif raw_conf < 1.7:
                severity = "medium"
            else:
                severity = "high"

            return AnomalyResult(
                is_anomaly=is_anomaly,
                reconstruction_error=round(error, 6),
                threshold=round(t, 6),
                confidence=round(confidence, 4),
                severity=severity,
            )

        except Exception as exc:
            print(f"[ANOMALY] predict() error: {exc}", flush=True)
            return _NULL_RESULT
