import io

from fastapi.testclient import TestClient
from PIL import Image

from app.main import app


def png_bytes(width=80, height=40):
    image = Image.new("RGB", (width, height), "white")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def jpeg_bytes():
    image = Image.new("RGB", (80, 40), "white")
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


def test_homepage():
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert "Process" in response.text
    assert "Copy text" in response.text
    assert "Download text" in response.text


def test_recognize_png(monkeypatch, tmp_path):
    monkeypatch.setenv("RESULT_DIR", str(tmp_path))
    monkeypatch.setattr(
        "app.recognition.ocr.pytesseract.image_to_string",
        lambda image, lang="eng", config="": "Hello",
    )
    client = TestClient(app)
    response = client.post(
        "/api/recognize",
        files={"file": ("note.png", png_bytes(), "image/png")},
    )
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["text"], str)
    assert isinstance(body["processing_ms"], (int, float))
    assert body["filename"] == "note.png"


def test_recognize_jpeg(monkeypatch, tmp_path):
    monkeypatch.setenv("RESULT_DIR", str(tmp_path))
    monkeypatch.setattr(
        "app.recognition.ocr.pytesseract.image_to_string",
        lambda image, lang="eng", config="": "Hello",
    )
    client = TestClient(app)
    response = client.post(
        "/api/recognize",
        files={"file": ("scan.jpg", jpeg_bytes(), "image/jpeg")},
    )
    assert response.status_code == 200
    assert isinstance(response.json()["text"], str)


def test_download_returns_recognized_text(monkeypatch, tmp_path):
    monkeypatch.setenv("RESULT_DIR", str(tmp_path))
    monkeypatch.setattr(
        "app.recognition.ocr.pytesseract.image_to_string",
        lambda image, lang="eng", config="": "Hello\nWorld",
    )
    client = TestClient(app)
    created = client.post(
        "/api/recognize",
        files={"file": ("note.png", png_bytes(), "image/png")},
    )
    assert created.json()["text"] == "Hello\nWorld"
    first = client.get(f"/api/results/{created.json()['id']}/download")
    second = client.get(f"/api/results/{created.json()['id']}/download")
    assert first.status_code == 200
    assert first.text == "Hello\nWorld"
    assert second.text == "Hello\nWorld"


def test_download_unknown_result(monkeypatch, tmp_path):
    monkeypatch.setenv("RESULT_DIR", str(tmp_path))
    client = TestClient(app)
    response = client.get(f"/api/results/{'0' * 32}/download")
    assert response.status_code == 404


def test_ocr_receives_binarized_image(monkeypatch, tmp_path):
    monkeypatch.setenv("RESULT_DIR", str(tmp_path))
    seen = {}

    def fake_ocr(image, lang="eng", config=""):
        seen["image"] = image
        seen["config"] = config
        return "Hello"

    monkeypatch.setattr("app.recognition.ocr.pytesseract.image_to_string", fake_ocr)
    client = TestClient(app)
    client.post("/api/recognize", files={"file": ("note.png", png_bytes(1000, 400), "image/png")})
    image = seen["image"]
    assert image.ndim == 2
    assert image.shape == (320, 800)
    assert "--psm 7" not in seen["config"]


def test_resize_keeps_small_images_and_aspect_ratio():
    import numpy as np

    from app.preprocessing.image_ops import resize_image

    small = np.zeros((40, 80, 3), dtype=np.uint8)
    assert resize_image(small).shape == (40, 80, 3)
    tall = np.zeros((1200, 480, 3), dtype=np.uint8)
    assert resize_image(tall).shape[:2] == (600, 240)


def test_missing_tesseract_returns_json_error(monkeypatch, tmp_path):
    import pytesseract

    monkeypatch.setenv("RESULT_DIR", str(tmp_path))

    def missing(image, lang="eng", config=""):
        raise pytesseract.TesseractNotFoundError()

    monkeypatch.setattr("app.recognition.ocr.pytesseract.image_to_string", missing)
    client = TestClient(app)
    response = client.post("/api/recognize", files={"file": ("note.png", png_bytes(), "image/png")})
    assert response.status_code == 500
    assert response.json()["error"]


def test_missing_file():
    client = TestClient(app)
    response = client.post("/api/recognize")
    assert response.status_code == 422


def test_rejects_pdf():
    client = TestClient(app)
    response = client.post(
        "/api/recognize",
        files={"file": ("notes.pdf", b"%PDF-1.4", "application/pdf")},
    )
    assert response.status_code == 400


def test_rejects_png_with_wrong_content():
    client = TestClient(app)
    response = client.post(
        "/api/recognize",
        files={"file": ("note.png", b"not-an-image", "image/png")},
    )
    assert response.status_code == 400


def test_rejects_oversized_image():
    client = TestClient(app)
    payload = png_bytes() + b"0" * (5 * 1024 * 1024)
    response = client.post(
        "/api/recognize",
        files={"file": ("large.png", payload, "image/png")},
    )
    assert response.status_code == 400


def test_rejects_path_filename(monkeypatch, tmp_path):
    monkeypatch.setenv("RESULT_DIR", str(tmp_path))
    client = TestClient(app)
    response = client.post(
        "/api/recognize",
        files={"file": ("../../secret.png", png_bytes(), "image/png")},
    )
    assert response.status_code == 400
