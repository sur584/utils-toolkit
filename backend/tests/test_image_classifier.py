"""
ImageClassifier unit tests.

Covers:
- disabled state returns "general" without downloading
- download failure -> "general", failure counter increments
- threshold failures auto-disable
- retry interval (5-minute window)
- second URL fallback
- preprocess output shape / dtype / normalization
- batch classify on disabled state
"""

from __future__ import annotations

import io
import urllib.error
from pathlib import Path
import numpy as np
import pytest
from PIL import Image

from backend.services.image_classifier import ImageClassifier


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_image(size: tuple = (300, 200), color: tuple = (123, 222, 64)) -> Image.Image:
    """Create an RGB PIL image with a fixed color."""
    return Image.new("RGB", size, color)


def _http_error(url: str = "http://example.com/m.onnx") -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        url=url,
        code=500,
        msg="Internal Server Error",
        hdrs=None,
        fp=io.BytesIO(b""),
    )


# ---------------------------------------------------------------------------
# 1. disabled state must return "general" and not download the model
# ---------------------------------------------------------------------------

def test_classify_disabled_returns_general(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ic = ImageClassifier(models_dir=str(tmp_path))
    ic._disabled = True

    called = {"n": 0}

    def _fake_urlretrieve(*_args, **_kwargs):
        called["n"] += 1
        raise AssertionError("urlretrieve must not be called when classifier is disabled")

    monkeypatch.setattr("urllib.request.urlretrieve", _fake_urlretrieve)

    result = ic.classify(_make_image())

    assert result == "general"
    assert called["n"] == 0, "urlretrieve was invoked despite _disabled=True"


# ---------------------------------------------------------------------------
# 2. download failure -> "general" and failure count +1
# ---------------------------------------------------------------------------

def test_classify_download_failure_returns_general(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ic = ImageClassifier(models_dir=str(tmp_path))

    # Initialize counter if the implementation has not defined it yet,
    # so the delta assertion is isolated and meaningful.
    if not hasattr(ic, "_failure_count"):
        ic._failure_count = 0
    before = ic._failure_count

    def _fake_urlretrieve(*_args, **_kwargs):
        raise _http_error()

    monkeypatch.setattr("urllib.request.urlretrieve", _fake_urlretrieve)

    result = ic.classify(_make_image())

    assert result == "general", "classify must fall back to 'general' on download failure"
    assert hasattr(ic, "_failure_count"), "implementation is missing _failure_count"
    assert ic._failure_count == before + 1, (
        f"_failure_count should increase by 1 after a download failure, "
        f"before={before}, after={ic._failure_count}"
    )


# ---------------------------------------------------------------------------
# 3. threshold failures (3) auto-disable; after disable, no more downloads
# ---------------------------------------------------------------------------

def test_classify_disable_after_threshold_failures(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ic = ImageClassifier(models_dir=str(tmp_path))

    # Honor a class-level threshold constant if present; otherwise use
    # the spec value 3.
    threshold = getattr(ic, "FAILURE_THRESHOLD", 3)

    call_count = {"n": 0}

    def _fake_urlretrieve(*_args, **_kwargs):
        call_count["n"] += 1
        raise _http_error()

    monkeypatch.setattr("urllib.request.urlretrieve", _fake_urlretrieve)

    results = [ic.classify(_make_image()) for _ in range(threshold)]
    assert all(r == "general" for r in results), "classify must keep returning general while failing"

    assert getattr(ic, "_disabled", False) is True, (
        f"classifier must set _disabled=True after {threshold} consecutive failures"
    )

    # Once disabled, another classify() must not trigger urlretrieve again.
    before = call_count["n"]
    result_after = ic.classify(_make_image())
    assert result_after == "general"
    assert call_count["n"] == before, "urlretrieve was called after the classifier was disabled"


# ---------------------------------------------------------------------------
# 4. retry interval: within 5-minute window, do not re-download
# ---------------------------------------------------------------------------

def test_classify_retry_interval(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ic = ImageClassifier(models_dir=str(tmp_path))

    call_count = {"n": 0}

    def _fake_urlretrieve(*_args, **_kwargs):
        call_count["n"] += 1
        raise _http_error()

    monkeypatch.setattr("urllib.request.urlretrieve", _fake_urlretrieve)

    # First call: fails after trying every URL in the fallback list
    # (ImageClassifier.MODEL_URLS has 2 entries), then records last-failure time.
    assert ic.classify(_make_image()) == "general"
    assert call_count["n"] == len(ic.MODEL_URLS), (
        f"first classify should try all fallback URLs, got {call_count['n']} calls"
    )
    calls_after_first = call_count["n"]

    # Second immediate call: inside retry window, urlretrieve must NOT fire.
    assert ic.classify(_make_image()) == "general"
    assert call_count["n"] == calls_after_first, (
        f"urlretrieve must not be called again within the retry window, "
        f"but it was called {call_count['n']} times"
    )

    # Rewind last-failure time to epoch (0) so the window has elapsed.
    assert hasattr(ic, "_last_failure_time"), "implementation is missing _last_failure_time"
    ic._last_failure_time = 0
    assert ic.classify(_make_image()) == "general"
    assert call_count["n"] == calls_after_first + len(ic.MODEL_URLS), (
        "urlretrieve should be called again (once per fallback URL) after the retry window elapses"
    )


# ---------------------------------------------------------------------------
# 5. first URL fails, fallback to second URL succeeds
# ---------------------------------------------------------------------------

def test_ensure_model_falls_back_to_second_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ic = ImageClassifier(models_dir=str(tmp_path))

    # The implementation is expected to expose a list of URLs (MODEL_URLS)
    # to support fallback.
    assert hasattr(ImageClassifier, "MODEL_URLS"), (
        "ImageClassifier must define MODEL_URLS (list) to support multi-URL fallback"
    )

    urls = list(getattr(ImageClassifier, "MODEL_URLS"))
    assert len(urls) >= 2, "MODEL_URLS must contain at least 2 URLs to test fallback"

    call_log: list = []

    def _fake_urlretrieve(url, dst=None, *_args, **_kwargs):
        call_log.append(url)
        if url == urls[0]:
            raise _http_error(url)
        # Second URL: write fake bytes into the temp destination so
        # os.replace can promote it to the final path.
        target = Path(dst) if dst else ic._model_path.with_suffix(".tmp")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"FAKE_ONNX_MODEL_BYTES")
        return str(target), None

    monkeypatch.setattr("urllib.request.urlretrieve", _fake_urlretrieve)
    monkeypatch.setattr(
        "os.replace",
        lambda src, dst: Path(dst).write_bytes(Path(src).read_bytes()),
    )

    # Only validate _ensure_model behavior; do not actually invoke
    # onnxruntime here.
    ic._ensure_model()

    assert ic._model_path.exists(), "model file must exist after fallback download"
    assert urls[0] in call_log and urls[1] in call_log, (
        f"both URLs must have been attempted, actual calls: {call_log}"
    )


# ---------------------------------------------------------------------------
# 6. preprocess output shape / dtype / normalization
# ---------------------------------------------------------------------------

def test_preprocess_output_shape_and_normalization(tmp_path: Path):
    ic = ImageClassifier(models_dir=str(tmp_path))
    img = _make_image(size=(300, 200))

    arr = ic._preprocess(img)

    assert isinstance(arr, np.ndarray)
    assert arr.shape == (1, 3, 224, 224), f"unexpected shape: {arr.shape}"
    assert arr.dtype == np.float32, f"unexpected dtype: {arr.dtype}"

    # After ImageNet normalization on a flat-color image, the global mean
    # should sit comfortably inside [-0.5, 0.5].
    mean_val = float(arr.mean())
    assert -0.5 <= mean_val <= 0.5, (
        f"normalized mean {mean_val:.4f} outside [-0.5, 0.5]; normalization may be wrong"
    )


# ---------------------------------------------------------------------------
# 7. classify_batch on disabled state returns all "general" and no download
# ---------------------------------------------------------------------------

def test_classify_batch_returns_general_on_disabled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ic = ImageClassifier(models_dir=str(tmp_path))
    ic._disabled = True

    called = {"n": 0}

    def _fake_urlretrieve(*_args, **_kwargs):
        called["n"] += 1
        raise AssertionError("urlretrieve must not be called for batch classify when disabled")

    monkeypatch.setattr("urllib.request.urlretrieve", _fake_urlretrieve)

    images = [_make_image(size=(100, 100), color=(i * 20, 100, 200)) for i in range(3)]
    results = ic.classify_batch(images)

    assert results == ["general", "general", "general"], f"unexpected batch result: {results}"
    assert called["n"] == 0, "urlretrieve was invoked during disabled batch classify"
