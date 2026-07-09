"""Operaciones sobre PDF, 100% locales.

pypdf para operaciones estructurales (unir, extraer, borrar, rotar, cifrar,
metadatos) y PyMuPDF (fitz) para render, compresion, imagenes<->PDF, texto,
marca de agua, firma y OCR. Funciones deterministas y testeables.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)


class PdfError(Exception):
    pass


# --------------------------------------------------------------- utilidades
def parse_ranges(spec: str, n_pages: int) -> list[int]:
    """'1-3,5,8-' -> indices 0-based, ordenados y unicos. Valida contra n_pages.

    Acepta: 'N', 'A-B', 'A-' (hasta el final), '-B' (desde el principio)."""
    if n_pages <= 0:
        raise PdfError("El documento no tiene paginas.")
    spec = (spec or "").strip()
    if not spec:
        raise PdfError("Indica al menos una pagina (p.ej. 1-3,5).")
    pages: set[int] = set()
    skipped: list[int] = []
    try:
        for part in spec.split(","):
            part = part.strip()
            if not part:
                continue
            if "-" in part:
                a, _, b = part.partition("-")
                a, b = a.strip(), b.strip()
                start = int(a) if a else 1
                end = int(b) if b else n_pages
                if start > end:
                    raise PdfError(f"Rango invertido: '{part}'. Escribe antes la pagina menor.")
                # Acotamos ANTES de iterar: un spec como '1-999999999' haria que
                # range() recorriera millones de numeros (cuelgue + RAM) aunque
                # luego se descartasen. min/max deja el bucle dentro del documento.
                lo, hi = max(1, start), min(end, n_pages)
                if hi < lo:
                    skipped.append(part)   # el rango entero cae fuera del documento
                    continue
                if lo > start or hi < end:
                    skipped.append(part)   # se recorto parcialmente
                for p in range(lo, hi + 1):
                    pages.add(p - 1)
            else:
                p = int(part)
                if 1 <= p <= n_pages:
                    pages.add(p - 1)
                else:
                    skipped.append(p)
    except ValueError:
        raise PdfError(f"'{spec}' no es valido. Usa numeros y guiones, p.ej. 1-3,5")
    if skipped:
        logger.warning("Paginas fuera de rango (1-%d) ignoradas: %s", n_pages, skipped)
    if not pages:
        raise PdfError(f"Las paginas indicadas estan fuera de rango (1-{n_pages}).")
    return sorted(pages)


def _read_bytes(path: str):
    """Lee el PDF a memoria y cierra el descriptor del fichero de inmediato.
    Asi ninguna operacion deja el archivo abierto (en Windows eso bloquea
    borrarlo/renombrarlo hasta el GC)."""
    import io
    with open(path, "rb") as f:
        return io.BytesIO(f.read())


def page_count(path: str) -> int:
    import pypdf
    try:
        return len(pypdf.PdfReader(_read_bytes(path)).pages)
    except Exception as exc:  # noqa: BLE001
        raise PdfError(f"No se pudo leer el PDF: {exc}") from exc


def is_encrypted(path: str) -> bool:
    import pypdf
    try:
        return bool(pypdf.PdfReader(_read_bytes(path)).is_encrypted)
    except Exception:  # noqa: BLE001
        return False


def _reader(path: str, password: str | None = None):
    import pypdf
    r = pypdf.PdfReader(_read_bytes(path))
    if r.is_encrypted:
        if not r.decrypt(password or ""):
            raise PdfError("El PDF esta protegido con contrasena. Quita la proteccion primero.")
    return r


# ----------------------------------------------------------- estructurales
def merge(paths: list[str], out_path: str) -> str:
    import pypdf
    if len(paths) < 2:
        raise PdfError("Selecciona al menos dos PDF para unir.")
    w = pypdf.PdfWriter()
    for p in paths:
        for page in _reader(p).pages:
            w.add_page(page)
    _write(w, out_path)
    return out_path


def extract_pages(path: str, out_path: str, ranges: str) -> str:
    import pypdf
    r = _reader(path)
    idx = parse_ranges(ranges, len(r.pages))
    w = pypdf.PdfWriter()
    for i in idx:
        w.add_page(r.pages[i])
    _write(w, out_path)
    return out_path


def delete_pages(path: str, out_path: str, ranges: str) -> str:
    import pypdf
    r = _reader(path)
    n = len(r.pages)
    drop = set(parse_ranges(ranges, n))
    keep = [i for i in range(n) if i not in drop]
    if not keep:
        raise PdfError("No puedes borrar todas las paginas.")
    w = pypdf.PdfWriter()
    for i in keep:
        w.add_page(r.pages[i])
    _write(w, out_path)
    return out_path


def split_each_page(path: str, out_dir: str) -> list[str]:
    import pypdf
    r = _reader(path)
    stem = Path(path).stem
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    outs = []
    width = len(str(len(r.pages)))
    for i, page in enumerate(r.pages):
        w = pypdf.PdfWriter()
        w.add_page(page)
        op = str(Path(out_dir) / f"{stem}_p{str(i + 1).zfill(width)}.pdf")
        _write(w, op)
        outs.append(op)
    return outs


def rotate(path: str, out_path: str, degrees: int, ranges: str | None = None) -> str:
    import pypdf
    if degrees % 90 != 0:
        raise PdfError("La rotacion debe ser multiplo de 90.")
    r = _reader(path)
    n = len(r.pages)
    idx = set(parse_ranges(ranges, n)) if ranges else set(range(n))
    w = pypdf.PdfWriter()
    for i, page in enumerate(r.pages):
        if i in idx:
            page.rotate(degrees)
        w.add_page(page)
    _write(w, out_path)
    return out_path


def reorder(path: str, out_path: str, order: list[int]) -> str:
    """order: lista 0-based con el nuevo orden (debe cubrir todas las paginas)."""
    import pypdf
    r = _reader(path)
    n = len(r.pages)
    if sorted(order) != list(range(n)):
        raise PdfError("El nuevo orden debe incluir todas las paginas exactamente una vez.")
    w = pypdf.PdfWriter()
    for i in order:
        w.add_page(r.pages[i])
    _write(w, out_path)
    return out_path


# ----------------------------------------------------------- proteccion
def encrypt(path: str, out_path: str, user_pw: str, owner_pw: str | None = None) -> str:
    import pypdf
    if not user_pw:
        raise PdfError("Escribe una contrasena.")
    r = _reader(path)
    w = pypdf.PdfWriter()
    for page in r.pages:
        w.add_page(page)
    import inspect
    # Deteccion por firma (no try/except TypeError, que enmascararia un fallo real
    # del proveedor de cifrado, p.ej. cryptography ausente).
    params = inspect.signature(w.encrypt).parameters
    if "user_password" in params:
        w.encrypt(user_password=user_pw, owner_password=owner_pw or user_pw,
                  algorithm="AES-256")
    else:
        w.encrypt(user_pwd=user_pw, owner_pwd=owner_pw or user_pw)
    _write(w, out_path)
    return out_path


def decrypt(path: str, out_path: str, password: str) -> str:
    import pypdf
    r = pypdf.PdfReader(_read_bytes(path))
    if r.is_encrypted and not r.decrypt(password or ""):
        raise PdfError("Contrasena incorrecta.")
    w = pypdf.PdfWriter()
    for page in r.pages:
        w.add_page(page)
    _write(w, out_path)
    return out_path


# ----------------------------------------------------------- metadatos
def get_metadata(path: str) -> dict:
    r = _reader(path)
    md = r.metadata or {}
    out = {}
    for k, v in md.items():
        try:
            sval = v.decode("utf-8", "replace") if isinstance(v, bytes) else str(v)
        except Exception:  # noqa: BLE001
            sval = "[ilegible]"
        out[str(k).lstrip("/")] = sval
    out["paginas"] = str(len(r.pages))
    return out


def set_metadata(path: str, out_path: str, fields: dict) -> str:
    import pypdf
    r = _reader(path)
    w = pypdf.PdfWriter()
    for page in r.pages:
        w.add_page(page)
    meta = {}
    for k, v in fields.items():
        key = k if k.startswith("/") else "/" + k
        meta[key] = v
    w.add_metadata(meta)
    _write(w, out_path)
    return out_path


def _write(writer, out_path: str) -> None:
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(out_path, "wb") as f:
            writer.write(f)
    except OSError as exc:
        raise PdfError(f"No se pudo guardar: {exc}") from exc


# ----------------------------------------------------------- fitz (PyMuPDF)
def compress(path: str, out_path: str) -> dict:
    import fitz
    try:
        doc = fitz.open(path)
    except Exception as exc:  # noqa: BLE001
        raise PdfError(f"No se pudo abrir el PDF: {exc}") from exc
    try:
        if doc.needs_pass:
            raise PdfError("El PDF esta protegido; quita la contrasena primero.")
        before = Path(path).stat().st_size
        doc.save(out_path, garbage=4, deflate=True, deflate_images=True,
                 deflate_fonts=True, clean=True)
        after = Path(out_path).stat().st_size
        return {"antes": before, "despues": after,
                "ahorro_pct": (0 if before == 0 else round(100 * (before - after) / before, 1))}
    except PdfError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise PdfError(f"No se pudo comprimir: {exc}") from exc
    finally:
        doc.close()


def images_to_pdf(image_paths: list[str], out_path: str) -> str:
    import fitz
    if not image_paths:
        raise PdfError("Selecciona al menos una imagen.")
    doc = fitz.open()
    try:
        for img in image_paths:
            imgdoc = fitz.open(img)
            try:
                pdfbytes = imgdoc.convert_to_pdf()
            finally:
                imgdoc.close()
            src = fitz.open("pdf", pdfbytes)
            try:
                doc.insert_pdf(src)
            finally:
                src.close()
        if doc.page_count == 0:
            raise PdfError("No se pudieron convertir las imagenes.")
        doc.save(out_path)
    except PdfError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise PdfError(f"No se pudo crear el PDF: {exc}") from exc
    finally:
        doc.close()
    return out_path


def pdf_to_images(path: str, out_dir: str, dpi: int = 150, fmt: str = "png") -> list[str]:
    import fitz
    doc = fitz.open(path)
    try:
        if doc.needs_pass:
            raise PdfError("El PDF esta protegido; quita la contrasena primero.")
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        stem = Path(path).stem
        outs = []
        width = len(str(doc.page_count))
        fmt = "png" if fmt.lower() not in ("png", "jpg", "jpeg") else fmt.lower()
        for i, page in enumerate(doc):
            pix = page.get_pixmap(dpi=dpi)
            op = str(Path(out_dir) / f"{stem}_p{str(i + 1).zfill(width)}.{('jpg' if fmt in ('jpg', 'jpeg') else 'png')}")
            pix.save(op)
            outs.append(op)
        return outs
    finally:
        doc.close()


def extract_text(path: str) -> str:
    import fitz
    doc = fitz.open(path)
    try:
        if doc.needs_pass:
            raise PdfError("El PDF esta protegido; quita la contrasena primero.")
        parts = []
        for i, page in enumerate(doc):
            parts.append(f"--- Pagina {i + 1} ---\n{page.get_text().strip()}")
        return "\n\n".join(parts).strip()
    finally:
        doc.close()


def page_text_chunks(path: str) -> list[dict]:
    """Texto por pagina, para el chat: [{page, text}]."""
    import fitz
    doc = fitz.open(path)
    try:
        if doc.needs_pass:
            raise PdfError("El PDF esta protegido; quita la contrasena primero.")
        chunks = []
        for i, page in enumerate(doc):
            t = page.get_text().strip()
            if t:
                chunks.append({"page": i + 1, "text": t})
        return chunks
    finally:
        doc.close()


def watermark(path: str, out_path: str, text: str, *, opacity: float = 0.18,
              fontsize: int = 48) -> str:
    import fitz
    if not text.strip():
        raise PdfError("Escribe el texto de la marca de agua.")
    doc = fitz.open(path)
    if doc.needs_pass:
        raise PdfError("El PDF esta protegido; quita la contrasena primero.")
    try:
        for page in doc:
            rect = page.rect
            page.insert_textbox(
                fitz.Rect(0, rect.height / 2 - 60, rect.width, rect.height / 2 + 60),
                text, fontsize=fontsize, color=(0.5, 0.5, 0.5), align=1,
                rotate=0, fill_opacity=opacity, overlay=True)
        doc.save(out_path, garbage=3, deflate=True)
    finally:
        doc.close()
    return out_path


def stamp_image(path: str, out_path: str, image_path: str, page_index: int,
                rel_rect: tuple[float, float, float, float]) -> str:
    """Coloca una imagen (firma) en la pagina. rel_rect en fraccion 0..1
    (x0,y0,x1,y1) respecto al tamano de la pagina."""
    import fitz
    doc = fitz.open(path)
    if doc.needs_pass:
        raise PdfError("El PDF esta protegido; quita la contrasena primero.")
    try:
        if not (0 <= page_index < doc.page_count):
            raise PdfError("Pagina fuera de rango.")
        page = doc[page_index]
        w, h = page.rect.width, page.rect.height
        x0, y0, x1, y1 = rel_rect
        rect = fitz.Rect(x0 * w, y0 * h, x1 * w, y1 * h)
        page.insert_image(rect, filename=image_path, overlay=True)
        doc.save(out_path, garbage=3, deflate=True)
    finally:
        doc.close()
    return out_path


def page_size(path: str, page_index: int = 0) -> tuple[float, float]:
    import fitz
    doc = fitz.open(path)
    try:
        i = max(0, min(page_index, doc.page_count - 1))
        r = doc[i].rect
        return (r.width, r.height)
    finally:
        doc.close()


def render_page_bytes(path: str, page_index: int, zoom: float = 1.0) -> bytes:
    """Renderiza una pagina a PNG EN MEMORIA (sin tocar disco). Para la vista
    previa: evita que un antivirus bloquee momentaneamente el fichero recien escrito."""
    import fitz
    if not (0 < zoom <= 10):
        raise PdfError("Zoom invalido (debe estar entre 0.1 y 10).")
    doc = fitz.open(path)
    try:
        page_index = max(0, min(page_index, doc.page_count - 1))
        pix = doc[page_index].get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        return pix.tobytes("png")
    finally:
        doc.close()


def render_page_png(path: str, page_index: int, out_png: str, zoom: float = 1.0) -> str:
    import fitz
    if not (0 < zoom <= 10):
        raise PdfError("Zoom invalido (debe estar entre 0.1 y 10).")
    doc = fitz.open(path)
    try:
        page_index = max(0, min(page_index, doc.page_count - 1))
        page = doc[page_index]
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        pix.save(out_png)
    finally:
        doc.close()
    return out_png


# ----------------------------------------------------------- OCR (opcional)
def tesseract_available() -> bool:
    return shutil.which("tesseract") is not None


def ocr_text(path: str) -> str:
    """Extrae texto de un PDF escaneado via OCR (necesita Tesseract instalado)."""
    import fitz
    if not tesseract_available():
        raise PdfError("Para OCR necesitas Tesseract instalado.\n"
                       "Instalalo con: winget install UB-Mannheim.TesseractOCR")
    doc = fitz.open(path)
    try:
        if doc.needs_pass:
            raise PdfError("El PDF esta protegido; quita la contrasena primero.")
        parts = []
        for i, page in enumerate(doc):
            try:
                tp = page.get_textpage_ocr(flags=0, full=True)
                txt = page.get_text(textpage=tp).strip()
            except Exception as exc:  # noqa: BLE001
                raise PdfError(f"OCR fallo en la pagina {i + 1}: {exc}") from exc
            parts.append(f"--- Pagina {i + 1} ---\n{txt}")
        return "\n\n".join(parts).strip()
    finally:
        doc.close()
