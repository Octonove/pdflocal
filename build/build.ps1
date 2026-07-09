# Construye el ejecutable de PDFLocal con PyInstaller (onedir).
# No empaqueta FFmpeg (no se usa). PyMuPDF trae su propia MuPDF.
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$py = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = Join-Path $root "..\CapturaPro\.venv\Scripts\python.exe" }
if (-not (Test-Path $py)) { $py = "python" }
Write-Host "Python: $py" -ForegroundColor DarkGray

Write-Host "== Generando icono ==" -ForegroundColor Cyan
& $py (Join-Path $PSScriptRoot "gen_icon.py")

$icon = Join-Path $PSScriptRoot "icon.ico"
if (Test-Path $icon) { $env:APP_ICON = $icon } else { $env:APP_ICON = "" }

Write-Host "== Compilando con PyInstaller ==" -ForegroundColor Cyan
Push-Location $root
& $py -m PyInstaller --noconfirm --clean (Join-Path $PSScriptRoot "PDFLocal.spec")
$code = $LASTEXITCODE
Pop-Location

if ($code -eq 0) {
    Write-Host "`n== LISTO ==" -ForegroundColor Green
    Write-Host "Ejecutable: $(Join-Path $root 'dist\PDFLocal\PDFLocal.exe')"
} else {
    Write-Host "`nLa compilacion fallo (codigo $code)." -ForegroundColor Red
    exit $code
}
