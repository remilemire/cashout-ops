"""`TextDetector` over the PP-OCRv4 detection model (DBNet), run with onnxruntime.

Only the detection stage of PP-OCR runs here: the model outputs a per-pixel
text probability map, and the post-processing turns its connected regions
into boxes. The pre- and post-processing follow RapidOCR's configuration of
this model (its `DetPreProcess` and `DBPostProcess`), except that each
region's shape is its minimum-area rectangle from OpenCV rather than a
polygon from the polygon libraries, which stay out of the dependency list.
"""

from __future__ import annotations

import asyncio
import hashlib
import threading
from importlib.resources import files
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import onnxruntime as ort
from numpy.typing import NDArray

from .client import ImageArray, TextBox
from .errors import TextDetectionError

MODEL_FILENAME = "ch_PP-OCRv4_det_infer.onnx"
# Recorded when the model was vendored (see models/NOTICE); the constructor
# refuses a file that no longer matches, so a corrupted or swapped model fails
# boot instead of silently detecting nothing.
MODEL_SHA256 = "d2a7720d45a54257208b1e13e36a8479894cb74155a5efe29462512d42f49da9"

# The network takes sides that are multiples of 32; larger inputs cost time
# without finding more text at document scale. Callers hand in an image
# already downscaled for detection, so this is a ceiling, not the target.
_NETWORK_STRIDE = 32
_MAX_NETWORK_SIDE = 2000
# Normalization the model was trained with: x / 255, then (x - mean) / std.
_MEAN = 0.5
_STD = 0.5

# DB post-processing, as RapidOCR configures PP-OCRv4 det.
_PROBABILITY_THRESHOLD = 0.3
_BOX_SCORE_THRESHOLD = 0.5
_UNCLIP_RATIO = 1.6
_MIN_BOX_SIDE = 3
_DILATION_KERNEL = np.ones((2, 2), dtype=np.uint8)


def model_path() -> Path:
    """The vendored model file inside the installed package."""
    return Path(str(files(__package__) / "models" / MODEL_FILENAME))


class PPOCRTextDetector:
    """`TextDetector` backed by the vendored PP-OCRv4 detection model.

    The ONNX session is built once and shared; inference runs off the event
    loop and behind a lock, so concurrent uploads queue for the one model
    rather than multiplying its memory.
    """

    def __init__(
        self, path: Path | None = None, *, intra_op_num_threads: int = 2
    ) -> None:
        path = model_path() if path is None else path
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if digest != MODEL_SHA256:
            raise RuntimeError(
                f"Text-detection model {path} does not match its recorded SHA-256"
                f" (got {digest})."
            )
        options = ort.SessionOptions()
        options.intra_op_num_threads = intra_op_num_threads
        self._session = ort.InferenceSession(
            data, options, providers=["CPUExecutionProvider"]
        )
        self._input_name: str = self._session.get_inputs()[0].name
        self._lock = threading.Lock()

    async def detect(self, image: ImageArray) -> list[TextBox]:
        return await asyncio.to_thread(self._detect, image)

    def _detect(self, image: ImageArray) -> list[TextBox]:
        if image.ndim != 3 or image.shape[2] != 3 or image.dtype != np.uint8:
            raise TextDetectionError(
                "Text detection expects an 8-bit RGB image (height × width × 3)."
            )
        height, width = image.shape[:2]
        network_input = _resize_for_network(image)
        if network_input is None:
            # Too small to hold a network stride: no text worth finding.
            return []
        tensor = _to_tensor(network_input)
        with self._lock:
            try:
                outputs = self._session.run(None, {self._input_name: tensor})
            except Exception as exc:
                raise TextDetectionError(str(exc)) from exc
        prediction: NDArray[np.float32] = np.asarray(outputs[0], dtype=np.float32)
        # (1, 1, h, w): one probability map for the one image.
        probability_map = prediction[0, 0]
        return _boxes_from_probability_map(
            probability_map, image_width=width, image_height=height
        )


def _resize_for_network(image: ImageArray) -> ImageArray | None:
    """Fit the image under the ceiling with both sides multiples of 32."""
    height, width = image.shape[:2]
    longest = max(height, width)
    ratio = _MAX_NETWORK_SIDE / longest if longest > _MAX_NETWORK_SIDE else 1.0
    target_height = int(round(height * ratio / _NETWORK_STRIDE) * _NETWORK_STRIDE)
    target_width = int(round(width * ratio / _NETWORK_STRIDE) * _NETWORK_STRIDE)
    if target_height <= 0 or target_width <= 0:
        return None
    resized = cv2.resize(image, (target_width, target_height))
    return np.asarray(resized, dtype=np.uint8)


def _to_tensor(image: ImageArray) -> NDArray[np.float32]:
    # The model was trained on cv2-decoded (BGR) images; callers pass RGB.
    bgr = image[:, :, ::-1].astype(np.float32)
    normalized = (bgr / 255.0 - _MEAN) / _STD
    # HWC → NCHW.
    return np.ascontiguousarray(normalized.transpose(2, 0, 1)[np.newaxis, ...])


def _boxes_from_probability_map(
    probability_map: NDArray[np.float32], *, image_width: int, image_height: int
) -> list[TextBox]:
    """DB post-processing over one probability map, yielding boxes in the
    coordinates of the image the map was computed for: each region's
    axis-aligned envelope, and its minimum-area rectangle as the outline."""
    map_height, map_width = probability_map.shape
    scale_x = image_width / map_width
    scale_y = image_height / map_height

    binary = (probability_map > _PROBABILITY_THRESHOLD).astype(np.uint8)
    dilated = cv2.dilate(binary, _DILATION_KERNEL)
    contours, _ = cv2.findContours(dilated, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

    boxes: list[TextBox] = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if min(w, h) < _MIN_BOX_SIDE:
            continue
        if _contour_score(probability_map, contour, x, y, w, h) < _BOX_SCORE_THRESHOLD:
            continue
        # DB's unclip: the network shrinks text regions during training, so
        # each region grows back by area * ratio / perimeter on every side —
        # of its own rectangle, not of its axis-aligned envelope, which for
        # a tilted line is several times the region and would grow it as much.
        centre, (rect_width, rect_height), angle = cv2.minAreaRect(contour)
        perimeter = 2 * (rect_width + rect_height)
        if perimeter <= 0:
            continue
        offset = (rect_width * rect_height) * _UNCLIP_RATIO / perimeter
        if min(rect_width, rect_height) + 2 * offset < _MIN_BOX_SIDE + 2:
            continue
        outline = tuple(
            (
                float(np.clip(px * scale_x, 0, image_width)),
                float(np.clip(py * scale_y, 0, image_height)),
            )
            for px, py in np.asarray(
                cv2.boxPoints(
                    (centre, (rect_width + 2 * offset, rect_height + 2 * offset), angle)
                ),
                dtype=np.float64,
            )
        )
        # The axis-aligned box is the grown region's envelope.
        xs = [px for px, _ in outline]
        ys = [py for _, py in outline]
        box = TextBox(
            left=int(np.floor(min(xs))),
            top=int(np.floor(min(ys))),
            right=int(np.ceil(max(xs))),
            bottom=int(np.ceil(max(ys))),
            outline=outline,
        )
        if box.width > 0 and box.height > 0:
            boxes.append(box)
    return boxes


def _contour_score(
    probability_map: NDArray[np.float32],
    contour: Any,
    x: int,
    y: int,
    w: int,
    h: int,
) -> float:
    """Mean probability inside the contour: how text-like the region is."""
    mask = np.zeros((h, w), dtype=np.uint8)
    shifted = np.asarray(contour, dtype=np.int32).reshape(-1, 1, 2) - np.array(
        [x, y], dtype=np.int32
    )
    cv2.fillPoly(mask, [shifted], 1)
    region = probability_map[y : y + h, x : x + w]
    return float(cv2.mean(region, mask)[0])


__all__ = ["MODEL_FILENAME", "MODEL_SHA256", "PPOCRTextDetector", "model_path"]
