from database import db_session, get_db
from schemas import UpdateTitleSettingsRequest
from config import get_available_detectors, get_available_cleaners, get_available_ocr_models, get_available_brush_models
from logger import logger
from services.page_service_ops.active_settings import invalidate_global_settings_cache


def get_global_settings_endpoint():
    """Получить глобальные настройки приложения."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM global_settings WHERE id = 1")
        row = cursor.fetchone()

    settings = dict(row) if row else {
        "detector_model": "yolo_manga.pt",
        "ocr_model": "manga-ocr-base",
        "clean_model": "anime-manga-big-lama.pt",
        "detect_conf": 0.25,
        "auto_oval_bubble": 1,
        "default_padding": "safe",
        "default_hyphenation": 1,
        "font_bubble": "v_CCFaceFront",
        "font_thought": "v_CCFaceFront",
        "font_sfx": "v_Mighty Zeo 2.0",
        "lama_downscale": 0,
        "show_sfx": 0,
        "dict_nlp_mode": "auto",
        "export_format": "png",
        "brush_model": "opencv",
        "brush_threshold": 0.5,
        "brush_extra_dilate": 0,
        "brush_max_side": 512,
    }

    settings["auto_oval_bubble"] = bool(settings.get("auto_oval_bubble", 1))
    settings["default_hyphenation"] = bool(settings.get("default_hyphenation", 1))
    settings["lama_downscale"] = bool(settings.get("lama_downscale", 0))
    settings["show_sfx"] = bool(row["show_sfx"]) if (row and "show_sfx" in row.keys()) else False
    settings["dict_nlp_mode"] = (row["dict_nlp_mode"] if (row and "dict_nlp_mode" in row.keys() and row["dict_nlp_mode"]) else "auto")
    settings["ocr_model"] = (row["ocr_model"] if (row and "ocr_model" in row.keys() and row["ocr_model"]) else "manga-ocr-base")
    settings["export_format"] = (
        row["export_format"]
        if (row and "export_format" in row.keys() and row["export_format"] in ("png", "webp", "avif"))
        else "png"
    )
    settings["available_detectors"] = get_available_detectors()
    settings["available_ocr_models"] = get_available_ocr_models()
    settings["available_cleaners"] = get_available_cleaners()

    available_brush = get_available_brush_models()
    settings["available_brush_models"] = available_brush
    brush_current = settings.get("brush_model")
    settings["brush_model"] = brush_current if brush_current in available_brush else "opencv"
    try:
        settings["brush_threshold"] = float(settings.get("brush_threshold", 0.5) or 0.5)
    except (TypeError, ValueError):
        settings["brush_threshold"] = 0.5
    try:
        settings["brush_extra_dilate"] = int(settings.get("brush_extra_dilate", 0) or 0)
    except (TypeError, ValueError):
        settings["brush_extra_dilate"] = 0
    try:
        settings["brush_max_side"] = int(settings.get("brush_max_side", 512) or 512)
    except (TypeError, ValueError):
        settings["brush_max_side"] = 512

    return {"success": True, "settings": settings}


def update_global_settings_endpoint(req: UpdateTitleSettingsRequest):
    """Обновить глобальные настройки приложения (частичное обновление: None = оставить текущее)."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM global_settings WHERE id = 1")
        row = cursor.fetchone()

    current = dict(row) if row else {}

    detector_req = req.detector_model.strip() if req.detector_model else None
    ocr_req = req.ocr_model.strip() if req.ocr_model else None
    cleaner_req = req.clean_model.strip() if req.clean_model else None
    if cleaner_req == "simple_lama":
        cleaner_req = "anime-manga-big-lama.pt"

    detector = detector_req if detector_req is not None else (current.get("detector_model") or "yolo_manga.pt")
    ocr_model_val = ocr_req if ocr_req is not None else (current.get("ocr_model") or "manga-ocr-base")
    cleaner = cleaner_req if cleaner_req is not None else (current.get("clean_model") or "anime-manga-big-lama.pt")
    if cleaner == "simple_lama":
        cleaner = "anime-manga-big-lama.pt"

    conf = float(req.detect_conf) if req.detect_conf is not None else float(current.get("detect_conf") or 0.25)

    if req.auto_oval_bubble is not None:
        auto_oval = 1 if req.auto_oval_bubble else 0
    else:
        auto_oval = int(current.get("auto_oval_bubble") or 0)

    if req.default_padding in ["safe", "fit"]:
        padding = req.default_padding
    elif current.get("default_padding") in ["safe", "fit"]:
        padding = current["default_padding"]
    else:
        padding = "safe"

    if req.default_hyphenation is not None:
        hyph = 1 if req.default_hyphenation else 0
    else:
        hyph = int(current.get("default_hyphenation") or 0)

    font_b = req.font_bubble if req.font_bubble is not None else (current.get("font_bubble") or "v_CCFaceFront")
    font_t = req.font_thought if req.font_thought is not None else (current.get("font_thought") or "v_CCFaceFront")
    font_s = req.font_sfx if req.font_sfx is not None else (current.get("font_sfx") or "v_Mighty Zeo 2.0")

    if req.lama_downscale is not None:
        downscale = 1 if req.lama_downscale else 0
    else:
        downscale = int(current.get("lama_downscale") or 0)

    if req.show_sfx is not None:
        show_sfx_val = 1 if req.show_sfx else 0
    else:
        show_sfx_val = int(current.get("show_sfx") or 0)

    valid_nlp_modes = {"auto", "sudachi", "electra", "bert_large"}
    if req.dict_nlp_mode in valid_nlp_modes:
        nlp_mode_val = req.dict_nlp_mode
    elif current.get("dict_nlp_mode") in valid_nlp_modes:
        nlp_mode_val = current["dict_nlp_mode"]
    else:
        nlp_mode_val = "auto"

    valid_export_formats = {"png", "webp", "avif"}
    req_export_format = (req.export_format or "").strip().lower()
    if req_export_format in valid_export_formats:
        export_format_val = req_export_format
    elif current.get("export_format") in valid_export_formats:
        export_format_val = current["export_format"]
    else:
        export_format_val = "png"

    available_brush = get_available_brush_models()
    req_brush_model = (req.brush_model or "").strip()
    if req_brush_model in available_brush:
        brush_model_val = req_brush_model
    elif current.get("brush_model") in available_brush:
        brush_model_val = current["brush_model"]
    else:
        brush_model_val = "opencv"

    if req.brush_threshold is not None:
        brush_threshold_val = min(0.9, max(0.1, float(req.brush_threshold)))
    else:
        brush_threshold_val = min(0.9, max(0.1, float(current.get("brush_threshold") or 0.5)))

    if req.brush_extra_dilate is not None:
        brush_extra_dilate_val = min(16, max(-8, int(req.brush_extra_dilate)))
    else:
        brush_extra_dilate_val = min(16, max(-8, int(current.get("brush_extra_dilate") or 0)))

    if req.brush_max_side is not None:
        raw_max_side = int(req.brush_max_side)
    else:
        raw_max_side = int(current.get("brush_max_side") or 512)
    brush_max_side_val = max(128, min(2048, int(round(raw_max_side / 32.0)) * 32))

    with db_session() as cur:
        cur.execute(
            """
            INSERT INTO global_settings (
                id, detector_model, ocr_model, clean_model, detect_conf,
                auto_oval_bubble, default_padding, default_hyphenation,
                font_bubble, font_thought, font_sfx, lama_downscale, show_sfx, dict_nlp_mode,
                export_format, brush_model, brush_threshold, brush_extra_dilate, brush_max_side
            ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                detector_model = excluded.detector_model,
                ocr_model = excluded.ocr_model,
                clean_model = excluded.clean_model,
                detect_conf = excluded.detect_conf,
                auto_oval_bubble = excluded.auto_oval_bubble,
                default_padding = excluded.default_padding,
                default_hyphenation = excluded.default_hyphenation,
                font_bubble = excluded.font_bubble,
                font_thought = excluded.font_thought,
                font_sfx = excluded.font_sfx,
                lama_downscale = excluded.lama_downscale,
                show_sfx = excluded.show_sfx,
                dict_nlp_mode = excluded.dict_nlp_mode,
                export_format = excluded.export_format,
                brush_model = excluded.brush_model,
                brush_threshold = excluded.brush_threshold,
                brush_extra_dilate = excluded.brush_extra_dilate,
                brush_max_side = excluded.brush_max_side
            """,
            (detector, ocr_model_val, cleaner, conf, auto_oval, padding, hyph, font_b, font_t, font_s, downscale, show_sfx_val, nlp_mode_val, export_format_val, brush_model_val, brush_threshold_val, brush_extra_dilate_val, brush_max_side_val)
        )

        cur.execute("SELECT show_sfx FROM global_settings WHERE id = 1")
        row_sfx = cur.fetchone()
        actual_show_sfx = bool(row_sfx["show_sfx"]) if (row_sfx and "show_sfx" in row_sfx.keys()) else False

    # Настройки изменились — следующий читатель обязан увидеть новые значения.
    invalidate_global_settings_cache()

    logger.info(f"Глобальные настройки обновлены: сжатие={bool(downscale)}, show_sfx={actual_show_sfx}.")
    return {
        "success": True,
        "settings": {
            "detector_model": detector,
            "ocr_model": ocr_model_val,
            "clean_model": cleaner,
            "detect_conf": conf,
            "auto_oval_bubble": bool(auto_oval),
            "default_padding": padding,
            "default_hyphenation": bool(hyph),
            "font_bubble": font_b,
            "font_thought": font_t,
            "font_sfx": font_s,
            "lama_downscale": bool(downscale),
            "show_sfx": actual_show_sfx,
            "dict_nlp_mode": nlp_mode_val,
            "export_format": export_format_val,
            "brush_model": brush_model_val,
            "brush_threshold": brush_threshold_val,
            "brush_extra_dilate": brush_extra_dilate_val,
            "brush_max_side": brush_max_side_val,
        }
    }


def get_available_detectors_endpoint():
    return {"success": True, "detectors": get_available_detectors()}


def get_available_cleaners_endpoint():
    return {"success": True, "cleaners": get_available_cleaners()}


def get_available_ocr_models_endpoint():
    return {"success": True, "ocr_models": get_available_ocr_models()}


def get_available_brush_models_endpoint():
    return {"success": True, "brush_models": get_available_brush_models()}
