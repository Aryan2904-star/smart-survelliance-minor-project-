import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename

app = Flask(__name__)
CORS(app)

# ─── Configuration ───────────────────────────────────────────────
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
ALLOWED_EXTENSIONS = {"mp4", "mov", "avi", "mkv"}

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# Create uploads folder if it doesn't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def allowed_file(filename):
    """Check if the file extension is allowed."""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# ─── Routes ──────────────────────────────────────────────────────

@app.route("/api/test", methods=["GET"])
def test():
    return jsonify({"message": "Backend working"})


@app.route("/api/upload", methods=["POST"])
def upload_video():
    # Check if the 'video' field is present in the request
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
        "saved_path": f"uploads/{filename}"
    }), 200


# ─── Run Server ──────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"✅ Upload folder: {UPLOAD_FOLDER}")
    print("🚀 Flask server running on http://127.0.0.1:5000")
    app.run(debug=True, host="127.0.0.1", port=5000)
