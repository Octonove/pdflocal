"""Tests de PDFLocal: parser de rangos, operaciones reales y chat."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pdflocal import pdfops, pdfchat, pdfsign  # noqa: E402


@pytest.fixture()
def p12_cert(tmp_path):
    import datetime
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives.serialization import pkcs12
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subj = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Octonove Test")])
    now = datetime.datetime(2025, 1, 1, tzinfo=datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(subj).issuer_name(subj)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=3650))
            .sign(key, hashes.SHA256()))
    p12 = tmp_path / "cert.p12"
    p12.write_bytes(pkcs12.serialize_key_and_certificates(
        b"test", key, cert, None, serialization.BestAvailableEncryption(b"1234")))
    return str(p12)


@pytest.fixture()
def sample_pdf(tmp_path):
    import fitz
    doc = fitz.open()
    for i, word in enumerate(["uno", "dos", "tres"]):
        page = doc.new_page()
        page.insert_text((72, 72), f"Pagina {word}. Contenido de prueba numero {i + 1}.",
                         fontsize=14)
    p = tmp_path / "muestra.pdf"
    doc.save(str(p))
    doc.close()
    return str(p)


# ----------------------------------------------------- parse_ranges
def test_parse_ranges_basic():
    assert pdfops.parse_ranges("1-3,5", 10) == [0, 1, 2, 4]
    assert pdfops.parse_ranges("2", 10) == [1]
    assert pdfops.parse_ranges("8-", 10) == [7, 8, 9]
    assert pdfops.parse_ranges("-3", 10) == [0, 1, 2]


def test_parse_ranges_dedup_and_order():
    assert pdfops.parse_ranges("3,1,2,2", 5) == [0, 1, 2]


def test_parse_ranges_clamps_out_of_range():
    assert pdfops.parse_ranges("4-99", 5) == [3, 4]


def test_parse_ranges_errors():
    with pytest.raises(pdfops.PdfError):
        pdfops.parse_ranges("", 5)
    with pytest.raises(pdfops.PdfError):
        pdfops.parse_ranges("50-60", 5)
    with pytest.raises(pdfops.PdfError):
        pdfops.parse_ranges("1", 0)


def test_parse_ranges_inverted_rejected():
    with pytest.raises(pdfops.PdfError):
        pdfops.parse_ranges("8-3", 10)


def test_parse_ranges_non_numeric_rejected():
    with pytest.raises(pdfops.PdfError):
        pdfops.parse_ranges("abc", 10)


# ----------------------------------------------------- operaciones
def test_page_count(sample_pdf):
    assert pdfops.page_count(sample_pdf) == 3


def test_merge(sample_pdf, tmp_path):
    out = str(tmp_path / "merged.pdf")
    pdfops.merge([sample_pdf, sample_pdf], out)
    assert pdfops.page_count(out) == 6


def test_extract_pages(sample_pdf, tmp_path):
    out = str(tmp_path / "ext.pdf")
    pdfops.extract_pages(sample_pdf, out, "1-2")
    assert pdfops.page_count(out) == 2


def test_delete_pages(sample_pdf, tmp_path):
    out = str(tmp_path / "del.pdf")
    pdfops.delete_pages(sample_pdf, out, "2")
    assert pdfops.page_count(out) == 2


def test_delete_all_fails(sample_pdf, tmp_path):
    with pytest.raises(pdfops.PdfError):
        pdfops.delete_pages(sample_pdf, str(tmp_path / "x.pdf"), "1-3")


def test_split_each_page(sample_pdf, tmp_path):
    outs = pdfops.split_each_page(sample_pdf, str(tmp_path / "split"))
    assert len(outs) == 3
    assert all(Path(o).is_file() for o in outs)


def test_rotate(sample_pdf, tmp_path):
    out = str(tmp_path / "rot.pdf")
    pdfops.rotate(sample_pdf, out, 90)
    assert pdfops.page_count(out) == 3
    with pytest.raises(pdfops.PdfError):
        pdfops.rotate(sample_pdf, out, 45)


def test_reorder(sample_pdf, tmp_path):
    out = str(tmp_path / "ord.pdf")
    pdfops.reorder(sample_pdf, out, [2, 1, 0])
    assert pdfops.page_count(out) == 3
    with pytest.raises(pdfops.PdfError):
        pdfops.reorder(sample_pdf, out, [0, 1])


def test_encrypt_decrypt(sample_pdf, tmp_path):
    enc = str(tmp_path / "enc.pdf")
    pdfops.encrypt(sample_pdf, enc, "secreto")
    assert pdfops.is_encrypted(enc)
    dec = str(tmp_path / "dec.pdf")
    pdfops.decrypt(enc, dec, "secreto")
    assert not pdfops.is_encrypted(dec)
    with pytest.raises(pdfops.PdfError):
        pdfops.decrypt(enc, str(tmp_path / "bad.pdf"), "malo")


def test_extract_text(sample_pdf):
    txt = pdfops.extract_text(sample_pdf)
    assert "uno" in txt and "Pagina" in txt
    assert "--- Pagina 1 ---" in txt


def test_metadata_roundtrip(sample_pdf, tmp_path):
    out = str(tmp_path / "meta.pdf")
    pdfops.set_metadata(sample_pdf, out, {"Title": "Mi Doc", "Author": "Octonove"})
    md = pdfops.get_metadata(out)
    assert md.get("Title") == "Mi Doc"
    assert md.get("Author") == "Octonove"


def test_compress(sample_pdf, tmp_path):
    out = str(tmp_path / "small.pdf")
    res = pdfops.compress(sample_pdf, out)
    assert Path(out).is_file()
    assert "ahorro_pct" in res


def test_images_to_pdf(tmp_path):
    from PIL import Image
    img = tmp_path / "a.png"
    Image.new("RGB", (200, 120), (200, 110, 97)).save(img)
    out = str(tmp_path / "fromimg.pdf")
    pdfops.images_to_pdf([str(img)], out)
    assert pdfops.page_count(out) == 1


def test_pdf_to_images(sample_pdf, tmp_path):
    outs = pdfops.pdf_to_images(sample_pdf, str(tmp_path / "imgs"), dpi=72)
    assert len(outs) == 3 and all(Path(o).is_file() for o in outs)


def test_render_and_page_size(sample_pdf, tmp_path):
    w, h = pdfops.page_size(sample_pdf, 0)
    assert w > 0 and h > 0
    out = str(tmp_path / "prev.png")
    pdfops.render_page_png(sample_pdf, 0, out, zoom=0.5)
    assert Path(out).is_file()


def test_render_page_bytes(sample_pdf):
    raw = pdfops.render_page_bytes(sample_pdf, 0, zoom=0.5)
    assert isinstance(raw, bytes) and raw[:8] == b"\x89PNG\r\n\x1a\n"  # firma PNG
    with pytest.raises(pdfops.PdfError):
        pdfops.render_page_bytes(sample_pdf, 0, zoom=0)


# ----------------------------------------------------- chat
def test_make_passages():
    chunks = [{"page": 1, "text": "Hola mundo. " * 200}]
    passages = pdfchat.make_passages(chunks, max_chars=300)
    assert len(passages) > 1
    assert all(p["page"] == 1 for p in passages)


def test_chat_keyword_retrieve():
    chunks = [{"page": 1, "text": "El presupuesto de marketing aumenta este ano."},
              {"page": 2, "text": "La receta del bizcocho lleva harina y huevos."}]
    chat = pdfchat.PdfChat(chunks)
    chat.build()  # sin Ollama -> keyword
    hits = chat.retrieve("cuanto es el presupuesto de marketing", k=1)
    assert hits and hits[0]["page"] == 1


def test_cosine():
    assert pdfchat._cosine([1, 0], [1, 0]) == pytest.approx(1.0)
    assert pdfchat._cosine([1, 0], [0, 1]) == pytest.approx(0.0)
    assert pdfchat._cosine([], [1]) == 0.0


def test_sign_invisible_and_verify(sample_pdf, p12_cert, tmp_path):
    out = str(tmp_path / "signed.pdf")
    pdfsign.sign_pdf(sample_pdf, out, p12_cert, "1234", reason="Conforme")
    sigs = pdfsign.verify_signatures(out)
    assert len(sigs) == 1
    s = sigs[0]
    assert s["integro"] is True and s["valido"] is True
    assert "Octonove Test" in s["firmante"]


def test_sign_visible_and_verify(sample_pdf, p12_cert, tmp_path):
    out = str(tmp_path / "signed_vis.pdf")
    pdfsign.sign_pdf(sample_pdf, out, p12_cert, "1234", visible=True, page_index=0)
    sigs = pdfsign.verify_signatures(out)
    assert len(sigs) == 1 and sigs[0]["integro"] is True


def test_sign_wrong_password(sample_pdf, p12_cert, tmp_path):
    with pytest.raises(pdfsign.SignError):
        pdfsign.sign_pdf(sample_pdf, str(tmp_path / "x.pdf"), p12_cert, "malo")


def test_verify_unsigned_returns_empty(sample_pdf):
    assert pdfsign.verify_signatures(sample_pdf) == []


def test_resolve_ollama_url(monkeypatch):
    from pdflocal import llm
    cases = {
        None: "http://127.0.0.1:11434",
        "localhost:11434": "http://127.0.0.1:11434",
        "http://localhost": "http://127.0.0.1:11434",          # critico: sin puerto
        "http://localhost:11434": "http://127.0.0.1:11434",
        "myhost": "http://myhost:11434",
        "http://10.0.0.5:1234": "http://10.0.0.5:1234",
    }
    for env, expected in cases.items():
        monkeypatch.delenv("OLLAMA_HOST", raising=False)
        if env is not None:
            monkeypatch.setenv("OLLAMA_HOST", env)
        assert llm._resolve_ollama_url() == expected, env


def test_cn_of():
    assert pdfsign._cn_of("C=ES, O=ACCV, OU=CIUDADANOS, CN=ANTONIO JOSE") == "ANTONIO JOSE"
    assert pdfsign._cn_of("CN=Solo") == "Solo"
    assert pdfsign._cn_of("") == ""


def test_cert_detection_no_crash():
    # Deben devolver listas sin lanzar (dependen del equipo).
    assert isinstance(pdfsign.find_cert_files(), list)
    assert isinstance(pdfsign.list_store_certs(), list)
    assert isinstance(pdfsign.list_signing_certs(), list)


def test_sign_with_store_cert_bad_thumbprint(sample_pdf, tmp_path):
    with pytest.raises(pdfsign.SignError):
        pdfsign.sign_with_store_cert(sample_pdf, str(tmp_path / "x.pdf"), "no-es-valido")


def test_verify_detects_tampering(sample_pdf, p12_cert, tmp_path):
    out = str(tmp_path / "signed2.pdf")
    pdfsign.sign_pdf(sample_pdf, out, p12_cert, "1234")
    # alterar el fichero firmado
    data = bytearray(Path(out).read_bytes())
    # corromper un tramo cerca del inicio del contenido (tras el header)
    for i in range(200, 260):
        data[i] = data[i] ^ 0xFF
    tampered = Path(tmp_path / "tampered.pdf")
    tampered.write_bytes(bytes(data))
    try:
        sigs = pdfsign.verify_signatures(str(tampered))
    except pdfsign.SignError:
        return  # si el PDF queda ilegible, tambien es un resultado aceptable
    if sigs:
        assert sigs[0]["integro"] is not True


def test_answer_without_ollama():
    chunks = [{"page": 1, "text": "El informe concluye que las ventas suben un diez por ciento."}]
    chat = pdfchat.PdfChat(chunks)
    chat.build()
    res = pdfchat.answer("que dice el informe sobre las ventas", chat)
    assert res["fuentes"]
    assert "ventas" in res["respuesta"].lower() or "pag" in res["respuesta"].lower()
