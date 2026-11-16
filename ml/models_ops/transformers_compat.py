# ml/models_ops/transformers_compat.py
# Патчи совместимости transformers 4.x/5.x для сторонних OCR-моделей (TokenizersBackend, RoPE default)

import json
import logging

import torch

logger = logging.getLogger("manga_translator.ml")


def _patch_tokenizer_config_if_needed(model_dir) -> None:
    """
    Чинит несовместимость моделей, сохранённых в transformers 5.0+
    (где PreTrainedTokenizerFast записан как TokenizersBackend), с transformers 4.x.
    """
    from pathlib import Path

    model_dir = Path(model_dir)
    tok_cfg_path = model_dir / "tokenizer_config.json"
    if not tok_cfg_path.exists():
        return

    try:
        import transformers

        # В transformers 4.x класса TokenizersBackend нет (он появился в 5.x),
        # поэтому регистрируем алиас и правим tokenizer_config.json.
        # В transformers 5.x ничего делать не нужно — класс уже существует.
        if hasattr(transformers, "TokenizersBackend"):
            return

        from transformers import PreTrainedTokenizerFast

        try:
            from transformers.models.auto import tokenization_auto

            if not hasattr(tokenization_auto, "TokenizersBackend"):
                tokenization_auto.TokenizersBackend = PreTrainedTokenizerFast
        except Exception:
            pass
        setattr(transformers, "TokenizersBackend", PreTrainedTokenizerFast)

        with open(tok_cfg_path, "r", encoding="utf-8") as f:
            tok_cfg = json.load(f)

        if tok_cfg.get("tokenizer_class") == "TokenizersBackend":
            tok_cfg["tokenizer_class"] = "PreTrainedTokenizerFast"
            with open(tok_cfg_path, "w", encoding="utf-8") as f:
                json.dump(tok_cfg, f, ensure_ascii=False, indent=2)
            logger.info(
                f"Авто-фикс {tok_cfg_path.name}: TokenizersBackend -> PreTrainedTokenizerFast"
            )
    except Exception as e:
        logger.warning(f"Не удалось проверить/обновить {tok_cfg_path}: {e}")


def _patch_transformers_rope_compat() -> None:
    """
    В transformers 5.x из ROPE_INIT_FUNCTIONS убрали тип "default",
    который всё ещё используют некоторые модели с trust_remote_code
    (например, PaddleOCR-VL-For-Manga). Возвращаем стандартный RoPE.
    """
    try:
        from transformers.modeling_rope_utils import ROPE_INIT_FUNCTIONS

        if "default" in ROPE_INIT_FUNCTIONS:
            return

        def _compute_default_rope_parameters(config, device=None, seq_len=None, **kwargs):
            base = float(getattr(config, "rope_theta", 10000.0))
            partial_rotary_factor = float(getattr(config, "partial_rotary_factor", 1.0))
            head_dim = getattr(config, "head_dim", None)
            if not head_dim:
                head_dim = config.hidden_size // config.num_attention_heads
            dim = int(head_dim * partial_rotary_factor)
            inv_freq = 1.0 / (
                base
                ** (
                    torch.arange(0, dim, 2, dtype=torch.int64, device=device).float()
                    / dim
                )
            )
            return inv_freq, 1.0

        ROPE_INIT_FUNCTIONS["default"] = _compute_default_rope_parameters
        logger.info("Авто-фикс RoPE: добавлен тип 'default' в ROPE_INIT_FUNCTIONS")
    except Exception as e:
        logger.warning(f"Не удалось применить фикс RoPE 'default': {e}")


__all__ = ["_patch_tokenizer_config_if_needed", "_patch_transformers_rope_compat"]
