"""'Chatea con tu PDF', 100% local.

Trocea el texto del PDF en pasajes, recupera los mas relevantes a la pregunta
(con embeddings de Ollama si los hay, o por solapamiento de palabras si no) y
redacta una respuesta con citas de pagina (con el LLM de Ollama, o devolviendo
los pasajes mas relevantes si no hay LLM).
"""

from __future__ import annotations

import logging
import math
import re

from . import llm

logger = logging.getLogger(__name__)

_STOP = set("""
a al algo ante con como de del desde donde el ella en es esta este la las lo los me mi
no o para pero por porque que se si sin sobre su sus tu un una uno y ya the a an of to
in is it for on and or as at be this that with from your you
""".split())


def make_passages(chunks: list[dict], max_chars: int = 900) -> list[dict]:
    """chunks: [{page, text}] -> pasajes [{page, text}] de ~max_chars."""
    passages: list[dict] = []
    for ch in chunks:
        page = ch["page"]
        text = re.sub(r"[ \t]+", " ", ch["text"]).strip()
        if not text:
            continue
        # cortar por parrafos y agrupar hasta max_chars
        paras = [p.strip() for p in re.split(r"\n{2,}|\.\s+(?=[A-ZÁÉÍÓÚÑ0-9])", text) if p.strip()]
        buf = ""
        for p in paras:
            if len(buf) + len(p) + 1 > max_chars and buf:
                passages.append({"page": page, "text": buf.strip()})
                buf = ""
            buf += " " + p
        if buf.strip():
            passages.append({"page": page, "text": buf.strip()})
    return passages


def _tokens(s: str) -> list[str]:
    return [w for w in re.findall(r"[a-záéíóúñü0-9]+", s.lower())
            if len(w) > 2 and w not in _STOP]


def _keyword_scores(question: str, passages: list[dict]) -> list[float]:
    q = set(_tokens(question))
    if not q:
        return [0.0] * len(passages)
    scores = []
    for p in passages:
        toks = _tokens(p["text"])
        if not toks:
            scores.append(0.0)
            continue
        tset = set(toks)
        overlap = sum(1 for w in q if w in tset)
        # bonus por frecuencia total de los terminos de la pregunta
        freq = sum(toks.count(w) for w in q)
        scores.append(overlap * 2.0 + freq / (len(toks) ** 0.5))
    return scores


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


class PdfChat:
    """Indice de un PDF para preguntas/respuestas."""

    def __init__(self, chunks: list[dict], embed_model: str | None = None):
        self.passages = make_passages(chunks)
        self.embed_model = embed_model
        self._embs: list[list[float]] | None = None
        self.mode = "keyword"   # keyword | embeddings

    def build(self) -> str:
        """Pre-calcula embeddings si Ollama los ofrece. Devuelve el modo elegido."""
        if not self.passages:
            return self.mode
        if llm.available() and (self.embed_model or llm.default_embed_model()):
            vecs = llm.embed([p["text"] for p in self.passages], self.embed_model)
            # Solo usamos embeddings si TODOS salieron y con dimension consistente;
            # si no, degradamos a busqueda por palabras (sin fallos silenciosos).
            if (vecs and len(vecs) == len(self.passages) and all(vecs)):
                dim = len(vecs[0])
                if all(len(v) == dim for v in vecs):
                    self._embs = vecs
                    self.mode = "embeddings"
                else:
                    logger.warning("Embeddings con dimensiones inconsistentes; uso keyword.")
        return self.mode

    def retrieve(self, question: str, k: int = 4) -> list[dict]:
        if not self.passages:
            return []
        if self.mode == "embeddings" and self._embs:
            qv = llm.embed([question], self.embed_model)
            # comprueba dimension: si el modelo cambio, evita un cosine roto (todo 0)
            if qv and qv[0] and len(qv[0]) == len(self._embs[0]):
                scores = [_cosine(qv[0], e) for e in self._embs]
            else:
                logger.warning("Embedding de la pregunta no disponible/compatible; uso keyword.")
                scores = _keyword_scores(question, self.passages)
        else:
            scores = _keyword_scores(question, self.passages)
        ranked = sorted(zip(scores, range(len(self.passages))), key=lambda t: -t[0])
        out = []
        for sc, i in ranked[:k]:
            if sc <= 0:
                continue
            out.append({**self.passages[i], "score": round(float(sc), 3)})
        return out


_SYS = ("Eres un asistente que responde preguntas SOBRE un documento PDF usando solo "
        "el contexto dado. Responde en espanol, de forma concisa, y cita las paginas "
        "entre parentesis, p.ej. (pag. 3). Si la respuesta no esta en el contexto, dilo.")


def answer(question: str, chat: "PdfChat", model: str | None = None) -> dict:
    """Devuelve {respuesta, fuentes:[{page,text}], modo}."""
    hits = chat.retrieve(question, k=4)
    if not hits:
        return {"respuesta": "No encontre nada relacionado en el documento.",
                "fuentes": [], "modo": chat.mode}
    if llm.available() and llm.default_model():
        ctx = "\n\n".join(f"[pag. {h['page']}] {h['text']}" for h in hits)
        prompt = (f"CONTEXTO DEL DOCUMENTO:\n{ctx}\n\n"
                  f"PREGUNTA: {question}\n\nRespuesta:")
        resp = llm.generate(prompt, system=_SYS, model=model)
        if resp:
            return {"respuesta": resp, "fuentes": hits, "modo": chat.mode + "+llm"}
    # sin LLM: devolver los pasajes mas relevantes
    txt = "No tengo IA generativa activa (Ollama), pero esto es lo mas relevante:\n\n"
    txt += "\n\n".join(f"• (pag. {h['page']}) {h['text'][:400]}" for h in hits)
    return {"respuesta": txt, "fuentes": hits, "modo": chat.mode}
