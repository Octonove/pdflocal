# PDFLocal

Caja de herramientas **PDF** para **Windows**, **100% local**: tus documentos nunca salen de tu PC.

## Funciones

- **Páginas**: unir PDFs, dividir, extraer/eliminar páginas, rotar, reordenar.
- **Convertir**: PDF → imágenes, imágenes → PDF, comprimir.
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
