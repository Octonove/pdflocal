# PDFLocal

Caja de herramientas **PDF** para **Windows**, **100% local**: tus documentos nunca salen de tu PC.

<!-- invokard-coffee -->
**&#9749; Si esto te ahorra tiempo, inv&iacute;tame a un caf&eacute;.** [![Inv&iacute;tame a un caf&eacute; con PayPal](https://img.shields.io/badge/PayPal-Inv%C3%ADtame%20a%20un%20caf%C3%A9-00457C?logo=paypal&logoColor=white)](https://www.paypal.com/donate/?business=stradoxx%40gmail.com&no_recurring=0&currency_code=EUR&item_name=Support%20pdflocal)

O en USDC. Env&iacute;a **solo USDC** y **solo por la red indicada**; por otra red se pierde y no hay forma de recuperarlo.

| Red | Direcci&oacute;n USDC |
|---|---|
| **Solana** | `5n6Gfosk7SdwbvdtE9xiLWpcGPBBBGDZYRfAkWyCk86g` |
| **Ethereum** (ERC-20) | `0xe176866f9d7fdb498e0d4a983d3e34d84dcd6bfc` |

## ⬇️ Descargar (Windows 10/11)

### ➡️ [**Descargar PDFLocal (instalador .exe)**](https://github.com/Octonove/pdflocal/releases/latest/download/PDFLocal-Setup.exe)

Descarga **directa** del instalador, sin registro. También puedes ver la [última versión y notas](https://github.com/Octonove/pdflocal/releases/latest).

> Si Windows muestra *"Windows protegió tu PC"* (es normal en programas nuevos sin firma): pulsa **Más información → Ejecutar de todas formas**. Se instala sin permisos de administrador.

---

## Funciones

- **Páginas**: unir PDFs, dividir, extraer/eliminar páginas, rotar, reordenar.
- **Convertir**: PDF → imágenes, imágenes → PDF.
- **Comprimir** con 3 niveles (ligera/media/fuerte): remuestrea y recomprime las imágenes — ahorros reales del 80-95% en PDFs escaneados o de diseño; nunca deja el archivo más grande que el original.
- **Proteger**: cifrar/descifrar con contraseña, marca de agua, sello de imagen.
- **Firma digital** (PAdES/PKCS#7 con pyHanko): con archivo `.p12/.pfx` o directamente con un **certificado del almacén de Windows** (la clave nunca sale del equipo); verificación de firmas.
- **Texto**: extraer texto, OCR local.
- **Chatear con el PDF**: preguntas con citas de página. Con [Ollama](https://ollama.com) (opcional) usa embeddings + LLM local; sin él, búsqueda por palabras.
- **Metadatos**: ver y editar.

## Stack

Python 3 + Tkinter (ttk) · pypdf · PyMuPDF · pyHanko · cryptography · Ollama opcional.

Depende del paquete compartido de la suite [`octonove-core`](https://github.com/Octonove/octonove-core) (tema, capa Ollama, config): debe estar en el `sys.path` del entorno (vía `.pth` o copia junto al proyecto).

## Compilar

```powershell
.\build\build.ps1              # ejecutable (PyInstaller onedir)
.\build\build-installer.ps1    # instalador (Inno Setup)
```

## Tests

```powershell
python -m pytest tests/ -q
```

## Licencia

[MIT](LICENSE) — © 2026 Octonove.
