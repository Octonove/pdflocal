"""Capa de IA local OPCIONAL via Ollama: shim del nucleo compartido
(octonove_core.llm) con los defaults de generacion de PDFLocal y las
funciones de embeddings (RAG de pdfchat)."""

from __future__ import annotations

from octonove_core.llm import (  # noqa: F401
    OLLAMA_URL,
    _cache,
    _get,
    _resolve_ollama_url,
    available,
    default_embed_model,
    default_model,
    embed,
    has_gpu,
    list_models,
    recommend_model,
    reset_cache,
    set_model,
    system_ram_gb,
)
from octonove_core.llm import generate as _generate


def generate(prompt: str, *, system: str | None = None, model: str | None = None,
             timeout: float = 180.0, temperature: float = 0.2) -> str | None:
    """Defaults propios de esta app: respuestas con citas sobre documentos largos
    (timeout amplio, temperatura baja). pdfchat.py confia en estos defaults."""
    return _generate(prompt, system=system, model=model, timeout=timeout,
                     temperature=temperature)
