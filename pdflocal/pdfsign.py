"""Firma digital de PDF con certificado (.p12/.pfx) y verificacion de firmas.

Usa pyHanko (PAdES/PKCS#7). Todo en local: el certificado y su contrasena nunca
salen del PC. Distinto del "sello de imagen" (que es solo un dibujo): esto es una
firma criptografica que prueba autoria e integridad del documento.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


class SignError(Exception):
    pass


# kwargs "sin consola" unificados en el core (mismo cuerpo que antes). OJO:
# sign_with_store_cert NO los usa A PROPOSITO — la consola debe verse para que
# Windows pueda mostrar el aviso de contrasena de Export-PfxCertificate.
from octonove_core.procutil import subprocess_kwargs as _ps_kwargs  # noqa: E402


def _cn_of(subject: str) -> str:
    m = re.search(r"CN=([^,]+)", subject or "")
    return (m.group(1).strip() if m else subject or "").strip()


# --------------------------------------------------------- deteccion de certs
def find_cert_files() -> list[dict]:
    """Busca .p12/.pfx en carpetas comunes del usuario."""
    out: list[dict] = []
    seen = set()
    home = Path.home()
    dirs = [home / "Desktop", home / "Documents", home / "Downloads", home,
            Path(os.environ.get("USERPROFILE", str(home)))]
    for d in dirs:
        try:
            if not d.is_dir():
                continue
            for ext in ("*.p12", "*.pfx", "*.P12", "*.PFX"):
                for p in d.glob(ext):
                    try:
                        if p.is_symlink() or not p.is_file():
                            continue          # no seguir symlinks (evita fugas de info)
                        rp = str(p.resolve())
                    except OSError:
                        continue
                    if rp.lower() in seen:
                        continue
                    seen.add(rp.lower())
                    out.append({"kind": "file", "path": rp, "label": p.name,
                                "subject": p.name, "expires": ""})
        except OSError:
            continue
    return out


def list_store_certs() -> list[dict]:
    """Certificados personales del almacen de Windows (CurrentUser\\My) con clave
    privada, aptos para firmar. Solo lectura. Filtra los de aplicaciones (Adobe)."""
    if os.name != "nt":
        return []
    ps = (
        "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8;"  # nombres con ñ/acentos correctos
        "$ErrorActionPreference='SilentlyContinue';"
        "Get-ChildItem Cert:\\CurrentUser\\My | Where-Object { $_.HasPrivateKey } | "
        "ForEach-Object { [PSCustomObject]@{ thumbprint=$_.Thumbprint; subject=$_.Subject;"
        " issuer=$_.Issuer; notafter=$_.NotAfter.ToString('yyyy-MM-dd') } } | ConvertTo-Json -Compress"
    )
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                           capture_output=True, timeout=20, **_ps_kwargs())
        raw = r.stdout.decode("utf-8", "replace").strip()
        if not raw:
            return []
        import json
        try:
            data = json.loads(raw)
        except (ValueError, TypeError):
            logger.warning("Salida de PowerShell no parseable al listar certificados.")
            return []
        if isinstance(data, dict):
            data = [data]
        if not isinstance(data, list):
            return []
        out = []
        _GUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                           r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
        for c in data:
            if not isinstance(c, dict):
                continue
            subj = c.get("subject", "") or ""
            issuer = c.get("issuer", "") or ""
            if "Adobe" in subj or "Adobe" in issuer:
                continue
            cn = _cn_of(subj)
            if not cn or _GUID.match(cn):   # GUID interno (no es un cert de persona)
                continue
            out.append({"kind": "store", "thumbprint": c.get("thumbprint", ""),
                        "subject": cn, "label": f"{cn}  (Windows, cad. {c.get('notafter','?')})",
                        "expires": c.get("notafter", "")})
        return out
    except Exception as exc:  # noqa: BLE001
        logger.warning("No se pudieron listar certificados de Windows: %s", exc)
        return []


def list_signing_certs() -> list[dict]:
    """Todos los certificados disponibles para firmar: almacen de Windows + archivos."""
    return list_store_certs() + find_cert_files()


def sign_with_store_cert(path: str, out_path: str, thumbprint: str, *,
                         reason: str = "", location: str = "", field_name: str = "Firma1",
                         visible: bool = False, page_index: int = 0,
                         rel_rect=(0.62, 0.85, 0.95, 0.97)) -> str:
    """Firma usando un certificado del almacen de Windows. Exporta su clave a un PFX
    TEMPORAL (solo si es exportable), firma y borra el temporal de inmediato. La
    clave nunca sale del equipo."""
    if os.name != "nt":
        raise SignError("El almacen de certificados de Windows solo esta en Windows.")
    if not re.fullmatch(r"[0-9A-Fa-f]{20,}", thumbprint or ""):
        raise SignError("Identificador de certificado invalido.")
    import secrets as _secrets
    pw = _secrets.token_urlsafe(18)
    # token largo (128 bits) -> nombre unico aunque haya firmas concurrentes
    tmp_pfx = Path(tempfile.gettempdir()) / f"_pdflocal_{os.getpid()}_{_secrets.token_hex(16)}.pfx"
    # En PowerShell una comilla simple dentro de un literal '...' se escapa doblandola.
    # El TEMP puede contener una comilla si el usuario de Windows la tiene (C:\Users\O'Brien);
    # sin esto la cadena de PowerShell se romperia y la exportacion fallaria.
    pfx_ps = str(tmp_pfx).replace("'", "''")
    pw_ps = pw.replace("'", "''")
    ps = (
        "$ErrorActionPreference='Stop';"
        f"$pw = ConvertTo-SecureString -String '{pw_ps}' -Force -AsPlainText;"
        f"Export-PfxCertificate -Cert Cert:\\CurrentUser\\My\\{thumbprint} "
        f"-FilePath '{pfx_ps}' -Password $pw -ChainOption EndEntityCertOnly | Out-Null"
    )
    # IMPORTANTE: la exportacion de algunas claves (ACCV con proteccion alta, etc.)
    # hace que WINDOWS MUESTRE UN AVISO pidiendo la contrasena de la clave. Por eso:
    #  - NO usamos -NonInteractive ni ocultamos la consola (si no, el aviso queda
    #    escondido y la firma se queda colgada esperando respuesta).
    #  - Redirigimos la salida a un FICHERO (no a un PIPE): al matar por timeout, leer
    #    un PIPE heredado por el proceso del aviso podria bloquearse varios minutos.
    log = Path(tempfile.gettempdir()) / f"_pdflocal_ps_{os.getpid()}_{_secrets.token_hex(4)}.log"
    try:
        try:
            with open(log, "wb") as fh:
                subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                               stdout=fh, stderr=subprocess.STDOUT, timeout=180)
        except subprocess.TimeoutExpired:
            raise SignError(
                "La firma no se completo (3 min de espera). Suele pasar cuando Windows "
                "muestra una ventana pidiendo la contrasena de tu certificado y no se "
                "responde a tiempo.\n\nVuelve a intentarlo y atiende ese aviso de Windows; "
                "o exporta el certificado a un archivo .p12 (certmgr.msc > Todas las tareas "
                "> Exportar, con la clave privada) y usalo como archivo.")
        if not tmp_pfx.is_file():
            try:
                err = log.read_text("utf-8", "replace")[-600:]
            except OSError:
                err = ""
            raise SignError(
                "No se pudo usar ese certificado del almacen de Windows. Puede que su clave "
                "privada no sea exportable (DNIe / proteccion fuerte) o que se cancelara el "
                "aviso de Windows.\n\nAlternativa: exportalo como archivo .p12 desde "
                "'certmgr.msc' (Todas las tareas > Exportar, incluyendo la clave privada) y "
                "usalo como archivo.\n\n" + err)
        return sign_pdf(path, out_path, str(tmp_pfx), pw, reason=reason, location=location,
                        field_name=field_name, visible=visible, page_index=page_index,
                        rel_rect=rel_rect)
    except SignError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise SignError(f"No se pudo firmar con el certificado de Windows: {exc}") from exc
    finally:
        # Borrado del PFX temporal: varias pasadas + fsync antes de unlink. En SSD el
        # borrado seguro es best-effort (wear-leveling), pero minimiza la exposicion.
        try:
            if tmp_pfx.is_file():
                n = tmp_pfx.stat().st_size
                with open(tmp_pfx, "r+b") as f:
                    for pat in (b"\xff", b"\x00"):
                        f.seek(0)
                        f.write(pat * n)
                        f.flush()
                        os.fsync(f.fileno())
                    f.seek(0)
                    f.write(os.urandom(n))
                    f.flush()
                    os.fsync(f.fileno())
                tmp_pfx.unlink()
        except OSError as exc:
            logger.error("SEGURIDAD: no se pudo borrar/sobrescribir el PFX temporal %s: %s",
                         tmp_pfx, exc)
        try:
            log.unlink(missing_ok=True)
        except OSError:
            pass


def _page_size(path: str, index: int) -> tuple[float, float]:
    import fitz
    doc = fitz.open(path)
    try:
        i = max(0, min(index, doc.page_count - 1))
        r = doc[i].rect
        return (r.width, r.height)
    finally:
        doc.close()


def sign_pdf(path: str, out_path: str, p12_path: str, p12_password: str, *,
             reason: str = "", location: str = "", field_name: str = "Firma1",
             visible: bool = False, page_index: int = 0,
             rel_rect: tuple[float, float, float, float] = (0.62, 0.85, 0.95, 0.97)) -> str:
    """Firma el PDF con el certificado .p12. Si visible, dibuja un recuadro con los
    datos del firmante en la pagina indicada.

    rel_rect = (left, top, right, bottom) en fracciones [0..1] del tamano de la
    pagina, con el origen ARRIBA-izquierda (igual que el sello de imagen)."""
    from pyhanko.sign import signers
    from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter

    if not Path(p12_path).is_file():
        raise SignError("No se encontro el archivo del certificado (.p12/.pfx).")
    if visible:
        if len(rel_rect) != 4 or not all(0 <= v <= 1 for v in rel_rect):
            raise SignError("La posicion de la firma no es valida.")
        x0, y0, x1, y1 = rel_rect
        if not (x0 < x1 and y0 < y1):
            raise SignError("La posicion de la firma no es valida (recuadro vacio).")
    # comprobar que se puede escribir la salida ANTES de firmar (operacion costosa)
    out_dir = Path(out_path).parent
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise SignError(f"No se puede crear la carpeta de salida: {exc}") from exc
    if not os.access(str(out_dir), os.W_OK):
        raise SignError("No hay permiso de escritura en la carpeta de salida.")

    passphrase = p12_password if isinstance(p12_password, bytes) else (p12_password or "").encode("utf-8")
    try:
        signer = signers.SimpleSigner.load_pkcs12(pfx_file=p12_path, passphrase=passphrase)
    except Exception as exc:  # noqa: BLE001
        raise SignError("No se pudo abrir el certificado. Revisa la contrasena o el "
                        f"archivo .p12.\n\n({exc})") from exc
    if signer is None:
        raise SignError("Certificado invalido o contrasena incorrecta.")

    meta = signers.PdfSignatureMetadata(field_name=field_name, reason=reason or None,
                                        location=location or None)
    try:
        with open(path, "rb") as inf:
            w = IncrementalPdfFileWriter(inf)
            if visible:
                from pyhanko.sign.fields import SigFieldSpec, append_signature_field
                pw, ph = _page_size(path, page_index)
                x0, y0, x1, y1 = rel_rect
                # PDF: origen abajo-izquierda; rel_rect viene con y desde arriba
                box = (x0 * pw, ph - y1 * ph, x1 * pw, ph - y0 * ph)
                append_signature_field(
                    w, SigFieldSpec(sig_field_name=field_name, on_page=page_index, box=box))
            result = signers.sign_pdf(w, meta, signer=signer)
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "wb") as f:
            f.write(result.getvalue())
    except SignError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise SignError(f"No se pudo firmar el documento: {exc}") from exc
    return out_path


def verify_signatures(path: str) -> list[dict]:
    """Lista las firmas digitales del PDF y su estado. Cada elemento:
    {campo, firmante, fecha, integro, valido, confianza, cobertura, resumen}."""
    from pyhanko.pdf_utils.reader import PdfFileReader
    from pyhanko.sign.validation import validate_pdf_signature
    from pyhanko_certvalidator import ValidationContext

    out: list[dict] = []
    try:
        f = open(path, "rb")
    except OSError as exc:
        raise SignError(f"No se pudo abrir el PDF: {exc}") from exc
    try:
        r = PdfFileReader(f)
        sigs = list(r.embedded_signatures)
        if not sigs:
            return []
        for s in sigs:
            campo = getattr(s, "field_name", "?")
            firmante = "?"
            fecha = ""
            integro = valido = confianza = None
            try:
                fecha = str(getattr(s, "self_reported_timestamp", "") or "")
            except Exception:  # noqa: BLE001
                fecha = ""
            # certificado del firmante (best-effort)
            try:
                cert = getattr(s, "signer_cert", None)
                if cert is not None:
                    firmante = cert.subject.human_friendly
            except Exception:  # noqa: BLE001
                pass
            # validacion criptografica (offline: sin descargar CRL/OCSP).
            # OJO: s.coverage solo se rellena DESPUES de validar, asi que se lee aqui.
            try:
                st = validate_pdf_signature(s, ValidationContext(allow_fetching=False))
                integro = bool(getattr(st, "intact", False))
                valido = bool(getattr(st, "valid", False))
                confianza = bool(getattr(st, "trusted", False))
                sc = getattr(st, "signing_cert", None)
                if sc is not None:
                    firmante = sc.subject.human_friendly
            except Exception as exc:  # noqa: BLE001
                logger.warning("Validacion de firma fallo: %s", exc)
            cobertura = ""
            try:
                cov = getattr(s, "coverage", None)
                if cov is not None:
                    name = getattr(cov, "name", str(cov))
                    cobertura = ("cubre todo el documento" if "ENTIRE" in str(name).upper()
                                 else "cubre solo parte del documento")
            except Exception:  # noqa: BLE001
                cobertura = ""
            if integro and valido:
                resumen = ("Firma valida e integra (documento no alterado tras la firma). "
                           + ("Cadena de confianza verificada." if confianza else
                              "Confianza de la CA no verificada en local."))
            elif integro is False:
                resumen = "El documento fue MODIFICADO despues de firmarse."
            else:
                resumen = "No se pudo validar criptograficamente la firma."
            out.append({"campo": campo, "firmante": firmante, "fecha": fecha,
                        "integro": integro, "valido": valido, "confianza": confianza,
                        "cobertura": cobertura, "resumen": resumen})
    except SignError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise SignError(f"No se pudieron leer las firmas: {exc}") from exc
    finally:
        try:
            f.close()
        except OSError:
            pass
    return out
