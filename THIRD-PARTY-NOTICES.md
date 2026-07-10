# Avisos de terceros (Third-Party Notices)

PDFLocal empaqueta y/o utiliza los siguientes componentes de terceros:

## PyMuPDF (fitz) — GNU AGPL v3
PDFLocal incluye **PyMuPDF** (https://github.com/pymupdf/PyMuPDF), que incorpora
la librería MuPDF de Artifex, para el renderizado, compresión y manipulación de
PDF. PyMuPDF se distribuye bajo la **GNU Affero General Public License v3**
(con opción de licencia comercial ofrecida por Artifex Software).

- Proyecto: https://github.com/pymupdf/PyMuPDF
- Artifex (licencia comercial): https://artifex.com/licensing/
- Texto de la licencia AGPL: https://www.gnu.org/licenses/agpl-3.0.html

**Nota sobre la AGPL:** dado que PDFLocal empaqueta PyMuPDF (AGPL-3.0), el
código fuente completo de la aplicación está disponible públicamente en este
mismo repositorio, lo que satisface las obligaciones de la AGPL para esta
distribución.

## pypdf — BSD-3-Clause
PDFLocal utiliza **pypdf** para unir, dividir, rotar, extraer y cifrar/descifrar
documentos PDF. Se distribuye bajo licencia **BSD de 3 cláusulas**.

- Proyecto: https://github.com/py-pdf/pypdf

## pyHanko — MIT
PDFLocal utiliza **pyHanko** para la firma digital y la validación de firmas en
documentos PDF. Se distribuye bajo licencia **MIT**.

- Proyecto: https://github.com/MatthiasValvekens/pyHanko

## pyhanko-certvalidator — MIT
Validación de certificados y cadenas de confianza usada por pyHanko. Se
distribuye bajo licencia **MIT**.

- Proyecto: https://github.com/MatthiasValvekens/certvalidator

## cryptography — Apache-2.0 / BSD-3-Clause
Primitivas criptográficas usadas por la firma digital y el cifrado de PDF. Se
distribuye bajo doble licencia **Apache License 2.0 o BSD de 3 cláusulas**.

- Proyecto: https://github.com/pyca/cryptography

## Pillow — MIT-CMU (HPND)
PDFLocal utiliza **Pillow** (PIL) para las vistas previas de página e imágenes
de firma. Se distribuye bajo licencia **MIT-CMU** (históricamente HPND).

- Proyecto: https://python-pillow.org

## Otras dependencias empaquetadas
Dependencias transitivas recogidas en el ejecutable junto con pyHanko:

- **asn1crypto** — licencia MIT — https://github.com/wbond/asn1crypto
- **oscrypto** — licencia MIT — https://github.com/wbond/oscrypto
- **tzlocal** — licencia MIT — https://github.com/regebro/tzlocal
- **lxml** — licencia BSD-3-Clause — https://lxml.de

PDFLocal también invoca **PowerShell** del sistema operativo para listar los
certificados del almacén de Windows; PowerShell forma parte de Windows y no se
empaqueta con la aplicación.

El resto del código de PDFLocal se distribuye bajo licencia MIT (ver `LICENSE`).
