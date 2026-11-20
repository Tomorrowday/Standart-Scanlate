from fastapi import HTTPException
from services.cleaner import release_vram
from ml.models import ml
from logger import logger


def release_vram_endpoint():
    try:
        release_vram()
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def unload_all_models_endpoint():
    """Полностью выгружает все нейросети (YOLO, OCR, LaMa, GiNZA/SudachiPy) из VRAM и RAM."""
    try:
        stats = ml.unload_all()
        logger.info(
            "Ручная выгрузка моделей: освобождено {freed} МБ VRAM ({before} → {after} МБ).".format(
                freed=stats.get("freed_mb", 0.0),
                before=stats.get("vram_before_mb", 0.0),
                after=stats.get("vram_after_mb", 0.0),
            )
        )
        return {"success": True, **stats}
    except Exception as e:
        logger.error(f"Ошибка выгрузки моделей: {e}")
        raise HTTPException(status_code=500, detail=str(e))
