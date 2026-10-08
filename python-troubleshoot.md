# Python App (Handwriting Recognition) – Troubleshooting Report

Seven bugs were found and fixed. Regression tests are in `python/tests/test_recognize.py`. Each new test fails on the original code and passes on the fixed code.

---

## 1. "Download text" always returned an empty file

**File:** `app/utils/files.py`

**Problem:** `read_result` opened the result file in `"w+"` mode. `"w+"` **truncates** the file (wipes its content) before reading, so:

- the download was always empty, and the saved result was destroyed;
- an unknown result id returned **200** with an empty file instead of **404**, because `"w+"` *creates* the file if it does not exist.

```python
with path.open("w+", encoding="utf-8") as handle:
    return handle.read()
```

**Fix:** Open in read mode. A missing file now raises `FileNotFoundError`, which the route already turns into a 404.

```python
with path.open("r", encoding="utf-8") as handle:
    return handle.read()
```

---

## 2. OCR was given the raw image instead of the preprocessed one

**File:** `app/services/pipeline.py`

**Problem:** The function signature is `prepare_for_ocr(original, preprocessed)`, and it returns `preprocessed`. The pipeline passed the arguments in reverse order:

```python
ocr_input = prepare_for_ocr(preprocessed, resized)
```

So the function returned `resized`, the raw colour image. All the grayscale, blur and threshold work was thrown away before OCR.

**Fix:**

```python
ocr_input = prepare_for_ocr(resized, preprocessed)
```

---

## 3. Every image was stretched to exactly 800×600

**File:** `app/preprocessing/image_ops.py`

**Problem:** `resize_image` forced every image to 800×600, ignoring the aspect ratio. A tall 480×1200 note was squashed vertically and stretched horizontally, which distorts the letters. Small images were also blown up.

```python
if width == max_width and height == max_height:
    return image
return cv2.resize(image, (max_width, max_height))
```

**Fix:** Scale down to fit inside 800×600 while keeping the aspect ratio. Images that already fit are left unchanged.

```python
scale = min(max_width / width, max_height / height)
if scale >= 1:
    return image
size = (max(1, round(width * scale)), max(1, round(height * scale)))
return cv2.resize(image, size, interpolation=cv2.INTER_AREA)
```

---

## 4. Threshold produced white text on a black background

**File:** `app/preprocessing/image_ops.py`

**Problem:** `THRESH_BINARY_INV` inverts the image, so dark ink became white on a black background. Tesseract is designed for dark text on a light background and reads inverted images poorly.

**Fix:** Use a normal (non-inverted) Otsu threshold.

```python
cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
```

---

## 5. Tesseract was told the image is a single line

**File:** `app/recognition/ocr.py`

**Problem:** `--psm 7` means "treat the image as a single text line". Multi-line notes such as `samples/note_lines.png` and `samples/note_tall.png` could not be read correctly.

**Fix:** `--psm 6` treats the image as a uniform block of text, which handles one or more lines.

```python
return "--oem 3 --psm 6"
```

---

## 6. Line breaks were lost in the recognised text

**File:** `app/utils/text.py`

**Problem:** The recognised lines were joined with a space, so a three-line note came back as one long line, both in the textarea and in the downloaded `.txt` file.

```python
return " ".join(line for line in lines if line)
```

**Fix:** Join with a newline. Empty lines are still removed.

```python
return "\n".join(line for line in lines if line)
```

---

## 7. Missing Tesseract crashed the request and froze the UI

**Files:** `app/recognition/ocr.py`, `frontend/static/js/app.js`

**Problem:**

- **Backend:** if Tesseract is not installed, pytesseract raises `TesseractNotFoundError`. The route doesn't catch that error, so the server returned a plain-text 500 response.
- **Frontend:** the frontend called `response.json()` on that response. Parsing failed and threw an error. Because of that, `processButton.disabled = false` never ran: the **Process button stayed disabled forever**, and no error message was shown.

**Fix:**

- **Backend:** convert the error to `RuntimeError`, which the route already returns as JSON: `500 {"error": "Image could not be processed"}`.

  ```python
  try:
      return pytesseract.image_to_string(image, lang="eng", config=config)
  except pytesseract.TesseractNotFoundError as error:
      raise RuntimeError("Tesseract is not installed") from error
  ```

- **Frontend:** wrap the request in `try / catch / finally`. The button is always re-enabled, and network or parse errors show "Request failed".

---

## Testing

```powershell
cd python
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pytest
```

Result: **13/13 tests pass** (8 original + 5 new regression tests):

- `test_download_returns_recognized_text`: download returns the real text, multi-line and repeatable (bugs 1, 6)
- `test_download_unknown_result`: an unknown id returns 404 (bug 1)
- `test_ocr_receives_binarized_image`: OCR gets the 2-D preprocessed image, the aspect ratio is kept, and the config is not `--psm 7` (bugs 2, 3, 5)
- `test_resize_keeps_small_images_and_aspect_ratio` (bug 3)
- `test_missing_tesseract_returns_json_error` (bug 7)

These tests mock `pytesseract.image_to_string`, so they check the pipeline wiring, not OCR accuracy. The effect of fixes 3–5 on real recognition quality should be checked by running the app with Tesseract installed on the images in `samples/`.
