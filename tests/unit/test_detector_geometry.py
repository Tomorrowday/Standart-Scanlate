# tests/unit/test_detector_geometry.py
# Порядок чтения манги, gutter cutter, разрешение перекрытий и расширение рамок.

import cv2
import numpy as np
import pytest
from PIL import Image

from services.detector_ops import yolo_detector
from services.detector_ops.box_expander import expand_box_to_bubble
from services.detector_ops.gutter_cutter import _find_best_gutter_cut
from services.detector_ops.overlap_resolver import resolve_overlapping_bubbles
from services.detector_ops.reading_order import sort_manga_reading_order

pytestmark = pytest.mark.unit


def _two_panel_gray() -> np.ndarray:
    """600x400: две панели с чёрными рамками и белой просекой по центру."""
    img = np.full((400, 600), 255, dtype=np.uint8)
    cv2.rectangle(img, (20, 50), (280, 350), 0, 4)
    cv2.rectangle(img, (320, 50), (580, 350), 0, 4)
    # Узкий текст у внутренних краёв панелей, чтобы самой широкой белой
    # полосой оставалась именно просека между панелями.
    cv2.rectangle(img, (220, 80), (270, 110), 0, -1)
    cv2.rectangle(img, (330, 80), (380, 110), 0, -1)
    return img


def _box(x: float, y: float, w: float, h: float) -> dict:
    return {"x": x, "y": y, "width": w, "height": h, "class_id": 2}


def test_sort_reading_order_right_to_left_then_top_to_bottom():
    top_right = _box(0.60, 0.10, 0.25, 0.10)
    top_left = _box(0.10, 0.10, 0.25, 0.10)
    bottom_left = _box(0.10, 0.60, 0.25, 0.10)

    ordered = sort_manga_reading_order([top_left, bottom_left, top_right])

    assert [b["order_index"] for b in ordered] == [1, 2, 3]
    # Верхний ряд читается справа налево, затем нижний.
    assert ordered[0]["x"] == pytest.approx(0.60)
    assert ordered[1]["x"] == pytest.approx(0.10)
    assert ordered[2]["y"] == pytest.approx(0.60)


def test_gutter_cutter_finds_white_gutter_between_panels():
    gray = _two_panel_gray()
    items = [
        {"x1": 220 / 600, "y1": 80 / 400, "x2": 270 / 600, "y2": 110 / 400,
         "w": 50 / 600, "h": 30 / 400, "cx": 245 / 600, "cy": 95 / 400},
        {"x1": 330 / 600, "y1": 80 / 400, "x2": 380 / 600, "y2": 110 / 400,
         "w": 50 / 600, "h": 30 / 400, "cx": 355 / 600, "cy": 95 / 400},
    ]
    cut = _find_best_gutter_cut(gray, items, 0, 400, 0, 600, axis="v")

    assert cut is not None
    assert 280 <= cut <= 320

    ordered = sort_manga_reading_order(
        [
            _box(220 / 600, 80 / 400, 50 / 600, 30 / 400),
            _box(330 / 600, 80 / 400, 50 / 600, 30 / 400),
        ],
        gray_img=gray,
    )
    assert ordered[0]["x"] > ordered[1]["x"]


def test_resolve_overlapping_bubbles_splits_on_text_gap():
    img = np.full((200, 500), 255, dtype=np.uint8)
    cv2.rectangle(img, (60, 80), (150, 120), 0, -1)
    cv2.rectangle(img, (250, 80), (340, 120), 0, -1)

    result = resolve_overlapping_bubbles(img, [(40, 60, 230, 140, 0), (210, 60, 360, 140, 0)])

    left, right = result
    assert left[2] < right[0], "рамки должны разойтись по белой просеке"
    assert left[4] == right[4] == 0


def test_resolve_overlapping_ignores_non_bubble_classes():
    img = np.full((200, 500), 255, dtype=np.uint8)
    boxes = [(40, 60, 230, 140, 3), (210, 60, 360, 140, 3)]
    assert resolve_overlapping_bubbles(img, boxes) == boxes


def test_expand_box_to_bubble_reaches_border_and_never_shrinks():
    img = np.full((200, 200), 255, dtype=np.uint8)
    cv2.ellipse(img, (100, 100), (60, 50), 0, 0, 360, 0, 3)
    orig = (70, 80, 130, 120)

    expanded = expand_box_to_bubble(img, *orig)

    x1, y1, x2, y2 = expanded
    assert x1 <= orig[0] and y1 <= orig[1]
    assert x2 >= orig[2] and y2 >= orig[3]
    assert (x2 - x1) * (y2 - y1) >= (orig[2] - orig[0]) * (orig[3] - orig[1])
    # Расширение не вылезает за границы изображения.
    assert 0 <= x1 < x2 <= 200 and 0 <= y1 < y2 <= 200


# --- Дедупликация, вложенные рамки и фильтр SFX на фейковом YOLO -----------------


class _Scalar:
    def __init__(self, value):
        self.value = value

    def __len__(self):
        return 1

    def __getitem__(self, idx):
        return self

    def item(self):
        return self.value


class _Vec:
    def __init__(self, values):
        self.values = values

    def __len__(self):
        return 1

    def __getitem__(self, idx):
        return self

    def tolist(self):
        return list(self.values)


class _FakeBox:
    def __init__(self, xyxy, cls_id, conf):
        self.xyxy = _Vec(xyxy)
        self.cls = _Scalar(cls_id)
        self.conf = _Scalar(conf)


class _FakeResult:
    def __init__(self, boxes):
        self.boxes = boxes


class _FakeYolo:
    names = {0: "bubble", 1: "thought", 2: "text", 3: "sfx"}

    def __init__(self, boxes):
        self._boxes = boxes

    def predict(self, image, conf=0.25, verbose=False):
        return [_FakeResult(self._boxes)]


def _run_fake_detect(monkeypatch, boxes, detect_sfx=False):
    monkeypatch.setattr(yolo_detector.ml, "get_yolo", lambda name: _FakeYolo(boxes))
    image = Image.new("RGB", (400, 400), "white")
    return yolo_detector.detect_and_filter_bubbles(
        image, model_name="fake.pt", detect_sfx=detect_sfx
    )


def test_detect_deduplicates_iou_boxes(monkeypatch):
    boxes = [
        _FakeBox([20, 20, 120, 120], 0, 0.90),
        _FakeBox([20, 20, 120, 120], 0, 0.75),
    ]
    result = _run_fake_detect(monkeypatch, boxes)
    assert len(result) == 1


def test_detect_removes_nested_outer_box(monkeypatch):
    boxes = [
        _FakeBox([0, 0, 300, 300], 0, 0.95),   # внешняя рамка
        _FakeBox([80, 80, 200, 200], 0, 0.90),  # вложенный бабл
    ]
    result = _run_fake_detect(monkeypatch, boxes)
    assert len(result) == 1
    # Остался внутренний бокс, а не внешняя рамка на всю страницу.
    assert result[0]["width"] < 0.75


def test_detect_filters_sfx_class_only_on_detection(monkeypatch):
    boxes = [
        _FakeBox([20, 20, 160, 160], 0, 0.90),
        _FakeBox([200, 20, 360, 160], 3, 0.90),
    ]

    without_sfx = _run_fake_detect(monkeypatch, boxes, detect_sfx=False)
    assert {b["class_id"] for b in without_sfx} == {0}

    with_sfx = _run_fake_detect(monkeypatch, boxes, detect_sfx=True)
    assert {b["class_id"] for b in with_sfx} == {0, 3}
