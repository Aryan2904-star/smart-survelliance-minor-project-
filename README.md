# 🛡️ Smart Surveillance System

An AI-powered video surveillance system with **real-time object detection** (YOLOv8) and **anomaly detection** (Convolutional Autoencoder).

## ✨ Features

- **YOLOv8 Object Detection** — Detects people, vehicles, animals in real-time with bounding boxes and confidence scores
- **Autoencoder Anomaly Detection** — Learns "normal" patterns and flags unusual activity via reconstruction error
- **Live Camera Feed** — Real-time webcam surveillance with ML detection overlay
- **Video Upload & Analysis** — Upload video files for offline ML processing
- **Settings Panel** — Configure detection confidence, target classes, anomaly sensitivity
- **Alert System** — Automatic alert capture with annotated frames
- **Responsive Dashboard** — Dark-themed UI with section navigation, stats, and activity timeline

## 🏗️ Tech Stack

| Component | Technology |
|-----------|------------|
| Backend | Python, Flask, Flask-CORS |
| Object Detection | YOLOv8 (Ultralytics) |
| Anomaly Detection | Convolutional Autoencoder (PyTorch) |
| Computer Vision | OpenCV |
| Frontend | HTML5, CSS3, Vanilla JS |
| Video Processing | FFmpeg (via imageio-ffmpeg) |

## 📁 Project Structure

```
smart surveillance(minor project)/
├── backend/
│   ├── app.py                  # Flask server (main entry point)
│   ├── requirements.txt        # Python dependencies
│   ├── models/
│   │   ├── __init__.py
│   │   ├── yolo_detector.py    # YOLOv8 wrapper
│   │   ├── autoencoder.py      # Conv Autoencoder model
│   │   └── train_autoencoder.py # Training script
│   ├── uploads/                # Uploaded videos
│   ├── outputs/                # Processed videos
│   └── alerts/                 # Alert frames
├── smart survillance (minor project)/
│   ├── index.html              # Dashboard UI
│   ├── style.css               # Styles (dark theme)
│   └── script.js               # Frontend logic
└── README.md
```

## 🚀 Setup & Run

### 1. Install Dependencies

```bash
cd backend
pip install -r requirements.txt
```

### 2. Train the Autoencoder (Optional but Recommended)

Downloads the UCSD Ped2 dataset and trains the anomaly detection model:

```bash
python models/train_autoencoder.py --download --epochs 50
```

Or train on your own video files:

```bash
python models/train_autoencoder.py --data ./path/to/normal/videos --epochs 50
```

### 3. Start the Server

```bash
python app.py
```

Open **http://127.0.0.1:5000** in your browser.

## 🧠 ML Architecture

### YOLOv8 (Object Detection)
- **Model**: `yolov8n.pt` (nano, fastest, auto-downloaded)
- **Classes**: Person, Car, Motorcycle, Bus, Truck, Bicycle, Dog, Cat
- **Configurable**: Confidence threshold and target classes via Settings

### Convolutional Autoencoder (Anomaly Detection)
- **Architecture**: Encoder (Conv2d 3→32→64→128) → Decoder (ConvTranspose2d 128→64→32→3)
- **Input**: 128×128 RGB frames
- **Anomaly Score**: Mean Squared Error between input and reconstruction
- **Threshold**: Automatically computed as mean + 2σ of training errors

## 📡 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Dashboard UI |
| GET | `/api/test` | Health check |
| POST | `/api/live/start` | Start live camera |
| POST | `/api/live/stop` | Stop live camera |
| GET | `/api/live` | MJPEG video stream |
| GET | `/api/live/status` | Camera + detection status |
| POST | `/api/upload` | Upload & analyze video |
| GET | `/api/output/<file>` | Serve processed video |
| GET | `/api/alerts` | Get alert history |
| GET/POST | `/api/settings` | Get/update detection config |
| GET | `/api/models/status` | Check ML model status |
| POST | `/api/train` | Trigger autoencoder training |
