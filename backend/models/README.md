# models/

Place the following files here after running `train_autoencoder.ipynb` on Google Colab:

| File | Description |
|---|---|
| `anomaly_model.h5` | Trained Convolutional Autoencoder weights |
| `threshold.npy` | Anomaly detection threshold (95th percentile of Normal errors) |
| `model_report.json` | Training report with per-category error stats |

## How to obtain these files

1. Open `ml_model/train_autoencoder.ipynb` in Google Colab
2. Run all cells (takes ~30–60 min depending on GPU)
3. Files are automatically saved to your Google Drive under `surveillance_model/`
4. Download and place here

## Detectable anomaly categories

- Fighting
- Robbery
- Road Accident
- Stealing
- Shooting
- Burglary
