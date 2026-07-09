# -*- mode: python ; coding: utf-8 -*-
"""Spec de PyInstaller para PDFLocal (onedir, ventana sin consola).

No empaqueta FFmpeg (no se usa). PyMuPDF (fitz) trae su propia libreria MuPDF.
"""

import os
from PyInstaller.utils.hooks import collect_all

block_cipher = None

icon_path = os.environ.get("APP_ICON", "")
icon_arg = icon_path if (icon_path and os.path.isfile(icon_path)) else None

# pyHanko (firma digital) se importa de forma perezosa, asi que hay que recoger
# explicitamente sus submodulos/datos y los de sus dependencias clave.
sign_datas, sign_bins, sign_hidden = [], [], []
for _pkg in ("pyhanko", "pyhanko_certvalidator", "asn1crypto", "cryptography",
             "tzlocal", "lxml", "oscrypto"):
    try:
        _d, _b, _h = collect_all(_pkg)
        sign_datas += _d; sign_bins += _b; sign_hidden += _h
    except Exception:
        pass

a = Analysis(
    ['..\\PDFLocal.py'],
    pathex=[],
    binaries=sign_bins,
    datas=sign_datas,
    hiddenimports=['fitz', 'pypdf', 'PIL', 'PIL._tkinter_finder', 'PIL.ImageTk',
                   'cryptography', 'pypdf._crypt_providers._cryptography'] + sign_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['scipy', 'pandas', 'matplotlib', 'PyQt5', 'PyQt6', 'PySide6',
              'soundcard', 'mss', 'numpy'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='PDFLocal',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_arg,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='PDFLocal',
)
