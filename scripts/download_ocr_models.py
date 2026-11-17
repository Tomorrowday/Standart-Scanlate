# scripts/download_ocr_models.py
# Скачивание OCR-моделей HuggingFace в локальную папку weights/ocr/<имя_модели> без симлинков.

from pathlib import Path

from huggingface_hub import snapshot_download

BASE_DIR = Path(__file__).resolve().parent.parent
OCR_DIR = BASE_DIR / "weights" / "ocr"

MODELS = {
    "hayai-ocr-v2.7-supernova": "JustANormalTinkerer/hayai-ocr-v2.7-supernova",
    "manga-ocr-base-CPT": "muscgab/manga-ocr-base-CPT",
    "PaddleOCR-VL-For-Manga": "jzhang533/PaddleOCR-VL-For-Manga",
}

if __name__ == "__main__":
    OCR_DIR.mkdir(parents=True, exist_ok=True)
    for local_name, repo_id in MODELS.items():
        target_dir = OCR_DIR / local_name
        print(f"\n=== Скачивание {repo_id} -> {target_dir} ===")
        snapshot_download(
            repo_id=repo_id,
            local_dir=str(target_dir),
            local_dir_use_symlinks=False,
        )
        print(f"Готово: {local_name}")
