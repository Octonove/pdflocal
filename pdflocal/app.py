"""Ventana principal de PDFLocal."""

from __future__ import annotations

import logging
import os
import threading
import webbrowser
from pathlib import Path

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog

from . import APP_NAME, APP_VERSION, theme
from . import pdfops, pdfchat, pdfsign, llm
from .config import AppConfig, load_config, save_config, get_data_dir

logger = logging.getLogger(__name__)


def _preview_dir() -> Path:
    d = get_data_dir() / "preview"
    d.mkdir(parents=True, exist_ok=True)
    return d


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"{APP_NAME} {APP_VERSION}")
        self.geometry("1080x740")
        self.minsize(960, 660)
        theme.apply(self)
        try:
            ico = Path(__file__).resolve().parent.parent / "build" / "icon.ico"
            if ico.is_file():
                self.iconbitmap(str(ico))
        except tk.TclError:
            pass

        self.cfg: AppConfig = load_config()
        self.current_pdf: str | None = None
        self.n_pages = 0
        self.page = 0
        self._busy = False
        self._closing = False
        self._photo = None
        self.chat: pdfchat.PdfChat | None = None

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(300, self._first_run_check)

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        theme.header(self, APP_NAME, "Tu navaja suiza de PDF · 100% en tu PC, sin subir nada")
        self.status = theme.status_bar(self, "Abre un PDF para empezar.")

        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=0)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        # --- Documento + preview ---
        left = ttk.LabelFrame(body, text="📄  Documento", padding=10)
        left.grid(row=0, column=0, sticky="ns", padx=(0, 12))
        ttk.Button(left, text="Abrir PDF…", style="Primary.TButton",
                   command=self._open_pdf).pack(fill="x")
        self.lbl_doc = ttk.Label(left, text="(ninguno)", style="CardMuted.TLabel",
                                 wraplength=240, justify="left")
        self.lbl_doc.pack(anchor="w", pady=(6, 6))

        self.canvas = tk.Canvas(left, width=270, height=360, bg="#33445A",
                                highlightthickness=1, highlightbackground=theme.BORDER)
        self.canvas.pack()
        nav = ttk.Frame(left); nav.pack(fill="x", pady=(6, 0))
        self.btn_prev = ttk.Button(nav, text="◀", width=3, command=self._prev_page, state="disabled")
        self.btn_prev.pack(side="left")
        self.lbl_page = ttk.Label(nav, text="–", style="CardMuted.TLabel")
        self.lbl_page.pack(side="left", expand=True)
        self.btn_next = ttk.Button(nav, text="▶", width=3, command=self._next_page, state="disabled")
        self.btn_next.pack(side="right")

        self.pb = ttk.Progressbar(left, mode="indeterminate", length=260)
        self.pb.pack(fill="x", pady=(10, 0))

        # --- Notebook de funciones ---
        right = ttk.Frame(body)
        right.grid(row=0, column=1, sticky="nsew")
        self.nb = ttk.Notebook(right)
        self.nb.pack(fill="both", expand=True)
        self._build_tools_tab()
        self._build_text_tab()
        self._build_chat_tab()

    def _build_tools_tab(self) -> None:
        tab = ttk.Frame(self.nb, padding=12)
        self.nb.add(tab, text="🧰 Herramientas")
        tools = [
            ("🔗  Unir PDFs", self._t_merge, False),
            ("✂  Dividir (1 archivo por pagina)", self._t_split, True),
            ("📑  Extraer paginas…", self._t_extract, True),
            ("🗑  Borrar paginas…", self._t_delete, True),
            ("🔄  Rotar paginas…", self._t_rotate, True),
            ("🗜  Comprimir", self._t_compress, True),
            ("🔒  Proteger con contrasena…", self._t_encrypt, True),
            ("🔓  Quitar contrasena…", self._t_decrypt, True),
            ("🖼  Imagenes → PDF…", self._t_img2pdf, False),
            ("📤  PDF → Imagenes…", self._t_pdf2img, True),
            ("💧  Marca de agua…", self._t_watermark, True),
            ("🖋  Sello de imagen (visual)…", self._t_sign, True),
            ("🔏  Firmar con certificado digital…", self._t_sign_cert, True),
            ("✔  Comprobar firmas digitales", self._t_verify_sign, True),
            ("🏷  Editar metadatos…", self._t_metadata, True),
            ("🔎  OCR (PDF escaneado)", self._t_ocr, True),
        ]
        cols = 2
        for i, (label, cmd, needs_doc) in enumerate(tools):
            b = ttk.Button(tab, text=label, style="Tool.TButton",
                           command=lambda c=cmd, n=needs_doc: self._tool(c, n))
            b.grid(row=i // cols, column=i % cols, sticky="ew", padx=4, pady=4)
        for c in range(cols):
            tab.columnconfigure(c, weight=1)
        ttk.Label(tab, text="Las funciones marcadas usan el PDF abierto. Los resultados se guardan en "
                  "tu carpeta de salida.", style="CardMuted.TLabel", wraplength=560,
                  justify="left").grid(row=99, column=0, columnspan=cols, sticky="w", pady=(12, 0))
        ttk.Button(tab, text="Cambiar carpeta de salida…", command=self._choose_outdir).grid(
            row=100, column=0, sticky="w", pady=(6, 0))
        self.lbl_out = ttk.Label(tab, text="", style="CardMuted.TLabel", wraplength=560,
                                 justify="left")
        self.lbl_out.grid(row=101, column=0, columnspan=cols, sticky="w")
        self._refresh_outlabel()

    def _build_text_tab(self) -> None:
        tab = ttk.Frame(self.nb, padding=10)
        self.nb.add(tab, text="📝 Texto")
        bar = ttk.Frame(tab); bar.pack(fill="x")
        ttk.Button(bar, text="Extraer texto del PDF", command=lambda: self._tool(self._do_extract_text, True)).pack(side="left")
        ttk.Button(bar, text="Guardar .txt", command=self._save_text).pack(side="left", padx=6)
        ttk.Button(bar, text="Copiar", command=self._copy_text).pack(side="left")
        self.txt = tk.Text(tab, wrap="word", font=(theme.FONT, 10), bg=theme.WHITE,
                           fg=theme.TEXT, relief="flat", padx=10, pady=8)
        sb = ttk.Scrollbar(tab, command=self.txt.yview)
        self.txt.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y", pady=(8, 0))
        self.txt.pack(fill="both", expand=True, pady=(8, 0))

    def _build_chat_tab(self) -> None:
        tab = ttk.Frame(self.nb, padding=10)
        self.nb.add(tab, text="💬 Chat con el PDF")
        top = ttk.Frame(tab); top.pack(fill="x")
        ttk.Label(top, text="Pregunta sobre el documento:", style="H.TLabel").pack(side="left")
        self.lbl_chat_ia = ttk.Label(top, text="", style="CardMuted.TLabel")
        self.lbl_chat_ia.pack(side="right")
        q = ttk.Frame(tab); q.pack(fill="x", pady=(6, 6))
        self.var_q = tk.StringVar()
        ent = ttk.Entry(q, textvariable=self.var_q)
        ent.pack(side="left", fill="x", expand=True)
        ent.bind("<Return>", lambda e: self._ask())
        ttk.Button(q, text="Preguntar", style="Primary.TButton", command=self._ask).pack(side="left", padx=(6, 0))
        ttk.Button(q, text="Configurar IA…", command=self._ollama_dialog).pack(side="left", padx=(6, 0))
        self.chat_out = tk.Text(tab, wrap="word", font=(theme.FONT, 10), bg=theme.WHITE,
                                fg=theme.TEXT, relief="flat", padx=10, pady=8)
        sb = ttk.Scrollbar(tab, command=self.chat_out.yview)
        self.chat_out.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.chat_out.pack(fill="both", expand=True)
        self._set_text(self.chat_out,
                       "Abre un PDF y pregunta lo que quieras: 'resume el documento', "
                       "'¿cuales son las conclusiones?', '¿que dice sobre X?'.\n\n"
                       "Con Ollama instalado, responde redactando y citando paginas. "
                       "Sin Ollama, te muestra los fragmentos mas relevantes. Todo en local.")
        self._refresh_chat_ia()

    # -------------------------------------------------------------- abrir
    def _open_pdf(self) -> None:
        p = filedialog.askopenfilename(title="Abrir PDF", initialdir=self.cfg.last_dir or None,
                                       filetypes=[("PDF", "*.pdf")])
        if not p:
            return
        self._load_pdf(p)

    def _load_pdf(self, path: str) -> None:
        # No se cambia de documento con una operacion en curso: los workers leen
        # self.current_pdf y cambiarlo a media operacion daria un resultado del PDF
        # equivocado.
        if self._busy:
            messagebox.showinfo(APP_NAME, "Espera a que termine la operacion en curso "
                                "antes de abrir otro PDF.")
            return
        try:
            self.n_pages = pdfops.page_count(path)
        except pdfops.PdfError as exc:
            messagebox.showerror(APP_NAME, str(exc))
            return
        self.current_pdf = path
        self.cfg.last_dir = str(Path(path).parent)
        save_config(self.cfg)
        self.page = 0
        self.chat = None
        enc = pdfops.is_encrypted(path)
        self.lbl_doc.config(text=f"{Path(path).name}\n{self.n_pages} pagina(s)"
                            + ("  · 🔒 protegido" if enc else ""))
        self.btn_prev.config(state="normal")
        self.btn_next.config(state="normal")
        self._render_preview()
        self._set_status(f"Abierto: {Path(path).name}")
        self._set_text(self.txt, "")

    def _render_preview(self) -> None:
        if not self.current_pdf:
            return
        try:
            import io
            from PIL import Image, ImageTk
            w, h = pdfops.page_size(self.current_pdf, self.page)
            target_w = 260
            zoom = max(0.2, min(2.5, target_w / max(1.0, w)))
            raw = pdfops.render_page_bytes(self.current_pdf, self.page, zoom=zoom)
            img = ImageTk.PhotoImage(Image.open(io.BytesIO(raw)))   # PIL: compatible siempre
            self._photo = img            # referencia viva para que no se recolecte
            self.canvas.delete("all")
            cw, ch = int(w * zoom), int(h * zoom)
            canvas_w, canvas_h = min(270, cw + 6), min(380, ch + 6)
            self.canvas.config(width=canvas_w, height=canvas_h)
            self.canvas.update_idletasks()
            self.canvas.create_image(canvas_w // 2, canvas_h // 2, image=img, anchor="center")
            self.lbl_page.config(text=f"Pagina {self.page + 1} / {self.n_pages}")
        except Exception as exc:  # noqa: BLE001
            logger.warning("preview fallo: %s", exc)
            self.canvas.delete("all")
            self.canvas.create_text(135, 180, text="(sin vista previa)", fill="white")

    def _prev_page(self) -> None:
        if self.current_pdf and self.page > 0:
            self.page -= 1
            self._render_preview()

    def _next_page(self) -> None:
        if self.current_pdf and self.page < self.n_pages - 1:
            self.page += 1
            self._render_preview()

    # -------------------------------------------------------------- helpers
    def _set_status(self, text: str) -> None:
        try:
            self.status.config(text=text)
        except tk.TclError:
            pass

    def _set_text(self, widget: tk.Text, content: str) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", content)

    def _refresh_outlabel(self) -> None:
        self.lbl_out.config(text=f"Carpeta de salida: {self.cfg.output_dir}")

    def _choose_outdir(self) -> None:
        d = filedialog.askdirectory(title="Carpeta donde guardar los resultados",
                                    initialdir=self.cfg.output_dir)
        if d:
            self.cfg.output_dir = d
            save_config(self.cfg)
            self._refresh_outlabel()

    def _out(self, name: str) -> str:
        Path(self.cfg.output_dir).mkdir(parents=True, exist_ok=True)
        return str(Path(self.cfg.output_dir) / name)

    def _stem(self) -> str:
        return Path(self.current_pdf).stem if self.current_pdf else "documento"

    def _open_folder(self) -> None:
        try:
            os.startfile(self.cfg.output_dir)
        except OSError:
            pass

    def _tool(self, fn, needs_doc: bool) -> None:
        if self._busy:
            return
        if needs_doc and not self.current_pdf:
            messagebox.showinfo(APP_NAME, "Primero abre un PDF.")
            return
        fn()

    def _run_async(self, work, on_done, busy_msg: str) -> None:
        if self._busy:      # el guard de _tool no cubre los dialogos previos:
            return          # el teclado puede reinvocar una herramienta abierta
        self._busy = True
        self._set_status(busy_msg)
        self.pb.start(12)

        def runner():
            try:
                res = work()
                self._post(lambda: self._async_ok(res, on_done))
            except Exception as exc:  # noqa: BLE001
                logger.exception("operacion fallo")
                self._post(lambda: self._async_err(exc))
        threading.Thread(target=runner, daemon=True).start()

    def _post(self, fn) -> None:
        if self._closing:
            return
        try:
            self.after(0, fn)
        except (RuntimeError, tk.TclError):
            pass

    def _modal(self, win) -> None:
        """grab_set seguro: libera el grab al destruir la ventana (evita que la
        ventana principal quede bloqueada si el dialogo se cierra inesperadamente)."""
        def _release(_e=None, w=win):
            try:
                if w.grab_current():
                    w.grab_release()
            except tk.TclError:
                pass
        win.bind("<Destroy>", _release)
        try:
            win.grab_set()
        except tk.TclError:
            pass

    def _async_ok(self, res, on_done) -> None:
        if self._closing:
            return
        self.pb.stop()
        self._busy = False
        on_done(res)

    def _async_err(self, exc) -> None:
        if self._closing:
            return
        self.pb.stop()
        self._busy = False
        self._set_status("Operacion cancelada por un error.")
        messagebox.showerror(APP_NAME, str(exc))

    def _done_toast(self, path_or_list) -> None:
        if isinstance(path_or_list, list):
            n = len(path_or_list)
            self._set_status(f"Listo: {n} archivo(s) en {self.cfg.output_dir}")
            msg = f"Generados {n} archivos en:\n{self.cfg.output_dir}\n\nAbrir la carpeta?"
        else:
            self._set_status(f"Listo: {path_or_list}")
            msg = f"Guardado:\n{path_or_list}\n\nAbrir la carpeta?"
        if messagebox.askyesno(APP_NAME, msg):
            self._open_folder()

    # -------------------------------------------------------------- TOOLS
    def _t_merge(self) -> None:
        paths = filedialog.askopenfilenames(title="Elige 2 o mas PDF (en orden)",
                                            initialdir=self.cfg.last_dir or None,
                                            filetypes=[("PDF", "*.pdf")])
        paths = list(paths)
        if len(paths) < 2:
            if paths:
                messagebox.showinfo(APP_NAME, "Selecciona al menos dos PDF.")
            return
        out = self._out("unido.pdf")
        self._run_async(lambda: pdfops.merge(paths, out), self._done_toast, "Uniendo PDFs…")

    def _t_split(self) -> None:
        outdir = self._out(f"{self._stem()}_paginas")
        self._run_async(lambda: pdfops.split_each_page(self.current_pdf, outdir),
                        self._done_toast, "Dividiendo…")

    def _t_extract(self) -> None:
        rng = simpledialog.askstring(APP_NAME, f"Paginas a extraer (1-{self.n_pages}). "
                                     "Ej: 1-3,5,8", parent=self)
        if not rng:
            return
        out = self._out(f"{self._stem()}_extraido.pdf")
        self._run_async(lambda: pdfops.extract_pages(self.current_pdf, out, rng),
                        self._done_toast, "Extrayendo paginas…")

    def _t_delete(self) -> None:
        rng = simpledialog.askstring(APP_NAME, f"Paginas a BORRAR (1-{self.n_pages}). "
                                     "Ej: 2,4-6", parent=self)
        if not rng:
            return
        out = self._out(f"{self._stem()}_sin_paginas.pdf")
        self._run_async(lambda: pdfops.delete_pages(self.current_pdf, out, rng),
                        self._done_toast, "Borrando paginas…")

    def _t_rotate(self) -> None:
        deg = simpledialog.askinteger(APP_NAME, "Grados (90, 180 o 270):",
                                      parent=self, initialvalue=90)
        if deg is None:
            return
        rng = simpledialog.askstring(APP_NAME, "Paginas a rotar (vacio = todas). "
                                     "Ej: 1-3", parent=self)
        out = self._out(f"{self._stem()}_rotado.pdf")
        self._run_async(lambda: pdfops.rotate(self.current_pdf, out, deg, rng or None),
                        self._done_toast, "Rotando…")

    def _ask_nivel_compresion(self) -> str | None:
        """Dialogo modal con los 3 niveles de compresion. None si cancela."""
        dlg = tk.Toplevel(self)
        dlg.title("Comprimir PDF")
        dlg.transient(self)
        dlg.resizable(False, False)
        var = tk.StringVar(value="media")
        ttk.Label(dlg, text="Nivel de compresion:",
                  font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=16, pady=(14, 6))
        opciones = (
            ("ligera", "Ligera", "maxima calidad, para imprimir (ahorro menor)"),
            ("media", "Media", "equilibrio calidad/tamano (recomendada)"),
            ("fuerte", "Fuerte", "maximo ahorro, para email o web"),
        )
        primero = None
        for key, titulo, desc in opciones:
            rb = ttk.Radiobutton(dlg, text=f"{titulo} — {desc}", value=key,
                                 variable=var)
            rb.pack(anchor="w", padx=24, pady=2)
            primero = primero or rb
        res: dict = {"v": None}
        fila = ttk.Frame(dlg)
        fila.pack(pady=(12, 14))

        def ok():
            res["v"] = var.get()
            dlg.destroy()
        ttk.Button(fila, text="Comprimir", command=ok).pack(side="left", padx=6)
        ttk.Button(fila, text="Cancelar", command=dlg.destroy).pack(side="left", padx=6)
        self._modal(dlg)
        # el grab de Tk solo bloquea el PUNTERO: sin mover el foco al dialogo,
        # Espacio sigue llegando al boton de la ventana principal y REABRE la
        # herramienta (dos dialogos, dos hilos sobre el mismo archivo)
        if primero is not None:
            primero.focus_set()
        dlg.wait_window()
        return res["v"]

    def _t_compress(self) -> None:
        nivel = self._ask_nivel_compresion()
        if not nivel or self._busy:   # re-check: pudo abrirse otra instancia
            return                    # mientras este dialogo esperaba
        out = self._out(f"{self._stem()}_comprimido.pdf")

        def fmt(b):
            return f"{b / 1e6:.1f} MB" if b >= 1e6 else f"{b / 1e3:.0f} KB"

        def done(res):
            self._set_status(f"Comprimido ({res.get('nivel', nivel)}): "
                             f"ahorro {res.get('ahorro_pct', 0)}%")
            extra = ("" if res.get("ahorro_pct", 0) > 0 else
                     "\n\nEste PDF ya estaba optimizado: se conservo el original "
                     "(nunca se genera un archivo mas grande).")
            messagebox.showinfo(APP_NAME, f"Comprimido (nivel {res.get('nivel', nivel)}).\n"
                                f"Antes: {fmt(res['antes'])}\n"
                                f"Despues: {fmt(res['despues'])}\n"
                                f"Ahorro: {res['ahorro_pct']}%{extra}\n\n{out}")
            if messagebox.askyesno(APP_NAME, "Abrir la carpeta?"):
                self._open_folder()
        self._run_async(lambda: pdfops.compress(self.current_pdf, out, nivel),
                        done, "Comprimiendo…")

    def _t_encrypt(self) -> None:
        pw = simpledialog.askstring(APP_NAME, "Contrasena para abrir el PDF:",
                                    parent=self, show="•")
        if not pw:
            return
        out = self._out(f"{self._stem()}_protegido.pdf")
        self._run_async(lambda: pdfops.encrypt(self.current_pdf, out, pw),
                        self._done_toast, "Cifrando…")

    def _t_decrypt(self) -> None:
        pw = simpledialog.askstring(APP_NAME, "Contrasena actual del PDF:",
                                    parent=self, show="•")
        if pw is None:
            return
        out = self._out(f"{self._stem()}_sin_proteccion.pdf")
        self._run_async(lambda: pdfops.decrypt(self.current_pdf, out, pw),
                        self._done_toast, "Quitando proteccion…")

    def _t_img2pdf(self) -> None:
        imgs = filedialog.askopenfilenames(
            title="Elige imagenes (en orden)", initialdir=self.cfg.last_dir or None,
            filetypes=[("Imagenes", "*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp")])
        imgs = list(imgs)
        if not imgs:
            return
        out = self._out("imagenes.pdf")
        self._run_async(lambda: pdfops.images_to_pdf(imgs, out), self._done_toast,
                        "Creando PDF desde imagenes…")

    def _t_pdf2img(self) -> None:
        dpi = simpledialog.askinteger(APP_NAME, "Resolucion (DPI): 72-300",
                                      parent=self, initialvalue=150, minvalue=36, maxvalue=400)
        if not dpi:
            return
        outdir = self._out(f"{self._stem()}_imagenes")
        self._run_async(lambda: pdfops.pdf_to_images(self.current_pdf, outdir, dpi=dpi),
                        self._done_toast, "Exportando imagenes…")

    def _t_watermark(self) -> None:
        txt = simpledialog.askstring(APP_NAME, "Texto de la marca de agua:", parent=self,
                                     initialvalue="CONFIDENCIAL")
        if not txt:
            return
        out = self._out(f"{self._stem()}_marca.pdf")
        self._run_async(lambda: pdfops.watermark(self.current_pdf, out, txt),
                        self._done_toast, "Aplicando marca de agua…")

    def _t_sign(self) -> None:
        img = filedialog.askopenfilename(title="Imagen de la firma/sello (PNG con transparencia ideal)",
                                         filetypes=[("Imagenes", "*.png *.jpg *.jpeg")])
        if not img:
            return
        page = simpledialog.askinteger(APP_NAME, f"Pagina donde firmar (1-{self.n_pages}):",
                                       parent=self, initialvalue=self.n_pages,
                                       minvalue=1, maxvalue=self.n_pages)
        if not page:
            return
        corner = self._ask_corner()
        if not corner:
            return
        rects = {
            "Abajo derecha": (0.62, 0.85, 0.95, 0.97),
            "Abajo izquierda": (0.05, 0.85, 0.38, 0.97),
            "Arriba derecha": (0.62, 0.03, 0.95, 0.15),
            "Arriba izquierda": (0.05, 0.03, 0.38, 0.15),
        }
        rel = rects[corner]
        out = self._out(f"{self._stem()}_sello.pdf")
        self._run_async(lambda: pdfops.stamp_image(self.current_pdf, out, img, page - 1, rel),
                        self._done_toast, "Aplicando sello…")

    _CORNERS = {
        "Abajo derecha": (0.62, 0.85, 0.95, 0.97),
        "Abajo izquierda": (0.05, 0.85, 0.38, 0.97),
        "Arriba derecha": (0.62, 0.03, 0.95, 0.15),
        "Arriba izquierda": (0.05, 0.03, 0.38, 0.15),
    }

    def _t_sign_cert(self) -> None:
        if self.n_pages < 1:
            messagebox.showinfo(APP_NAME, "El PDF no tiene paginas validas para firmar.")
            return
        self._set_status("Buscando certificados en tu equipo…")
        self.update_idletasks()
        certs = pdfsign.list_signing_certs()
        self._set_status("")

        win = tk.Toplevel(self)
        theme.center_window(win)
        win.title("Firmar con certificado digital")
        win.configure(bg=theme.BG)
        win.transient(self); win.resizable(False, False)
        frm = ttk.Frame(win, padding=18); frm.pack(fill="both", expand=True)
        ttk.Label(frm, text="Firmar con certificado digital", style="H.TLabel").pack(anchor="w")
        ttk.Label(frm, text="Firma criptografica (PAdES). El certificado y su clave no salen de tu PC.",
                  style="Muted.TLabel").pack(anchor="w", pady=(2, 10))

        ttk.Label(frm, text="Certificado:", style="H.TLabel").pack(anchor="w")
        options = [c["label"] for c in certs] + ["📁  Elegir un archivo .p12/.pfx…"]
        var_cert = tk.StringVar(value=options[0])
        cmb = ttk.Combobox(frm, textvariable=var_cert, values=options, state="readonly", width=52)
        cmb.current(0)
        cmb.pack(anchor="w", pady=(0, 2))
        if certs:
            ttk.Label(frm, text=f"Detectados {len(certs)}: almacen de Windows y/o archivos.",
                      style="Muted.TLabel").pack(anchor="w")
        else:
            ttk.Label(frm, text="No se detectaron certificados; elige un archivo .p12/.pfx.",
                      style="Muted.TLabel").pack(anchor="w")

        ttk.Label(frm, text="Contrasena (solo para archivos .p12/.pfx):",
                  style="CardMuted.TLabel").pack(anchor="w", pady=(8, 0))
        var_pw = tk.StringVar()
        ttk.Entry(frm, textvariable=var_pw, show="•", width=34).pack(anchor="w")

        ttk.Label(frm, text="Motivo (opcional):", style="CardMuted.TLabel").pack(anchor="w", pady=(8, 0))
        var_reason = tk.StringVar(value="Conforme")
        ttk.Entry(frm, textvariable=var_reason, width=34).pack(anchor="w")

        vis = ttk.Frame(frm); vis.pack(fill="x", pady=(10, 0))
        var_vis = tk.BooleanVar(value=False)
        ttk.Checkbutton(vis, text="Firma visible en", variable=var_vis).pack(side="left")
        var_page = tk.IntVar(value=self.n_pages or 1)
        ttk.Spinbox(vis, from_=1, to=max(1, self.n_pages), textvariable=var_page, width=5).pack(side="left", padx=4)
        ttk.Label(vis, text="pag.,", style="CardMuted.TLabel").pack(side="left")
        var_corner = tk.StringVar(value="Abajo derecha")
        ttk.Combobox(vis, textvariable=var_corner, values=list(self._CORNERS.keys()),
                     state="readonly", width=16).pack(side="left", padx=4)

        def do_sign():
            idx = cmb.current()
            chosen = certs[idx] if idx < len(certs) else None
            file_path = None
            if chosen is None:
                file_path = filedialog.askopenfilename(
                    title="Certificado (.p12 / .pfx)", filetypes=[("Certificado", "*.p12 *.pfx")])
                if not file_path:
                    return
            visible = bool(var_vis.get())
            page_index = max(0, min(self.n_pages - 1, var_page.get() - 1)) if visible else 0
            rel = self._CORNERS.get(var_corner.get(), self._CORNERS["Abajo derecha"])
            reason = var_reason.get()
            out = self._out(f"{self._stem()}_firmado.pdf")
            is_store = chosen is not None and chosen["kind"] == "store"
            win.destroy()
            if is_store:
                messagebox.showinfo(
                    APP_NAME, "Es posible que Windows te muestre una ventana pidiendo la "
                    "contrasena de tu certificado.\n\nSi aparece, atiendela (mira la barra "
                    "de tareas o pulsa Alt+Tab). La firma terminara en cuanto la respondas.")
                work = lambda: pdfsign.sign_with_store_cert(
                    self.current_pdf, out, chosen["thumbprint"], reason=reason,
                    visible=visible, page_index=page_index, rel_rect=rel)
            else:
                p12 = chosen["path"] if chosen is not None else file_path
                pw = var_pw.get()
                work = lambda: pdfsign.sign_pdf(self.current_pdf, out, p12, pw, reason=reason,
                                                visible=visible, page_index=page_index, rel_rect=rel)
            self._run_async(work, self._done_toast, "Firmando digitalmente…")

        ttk.Button(frm, text="Firmar", style="Primary.TButton", command=do_sign).pack(
            anchor="e", pady=(14, 0))
        self._modal(win)

    def _t_verify_sign(self) -> None:
        def done(sigs):
            if not sigs:
                messagebox.showinfo(APP_NAME, "Este PDF no tiene firmas digitales.")
                self._set_status("Sin firmas digitales.")
                return
            self._show_signatures(sigs)
            self._set_status(f"{len(sigs)} firma(s) digital(es) encontrada(s).")
        self._run_async(lambda: pdfsign.verify_signatures(self.current_pdf), done,
                        "Comprobando firmas digitales…")

    def _show_signatures(self, sigs: list[dict]) -> None:
        win = tk.Toplevel(self)
        theme.center_window(win)
        win.title("Firmas digitales")
        win.configure(bg=theme.BG)
        win.transient(self)
        frm = ttk.Frame(win, padding=16); frm.pack(fill="both", expand=True)
        ttk.Label(frm, text=f"{len(sigs)} firma(s) en el documento", style="H.TLabel").pack(anchor="w")
        for i, s in enumerate(sigs, 1):
            card = ttk.LabelFrame(frm, text=f"Firma {i}: {s['campo']}", padding=10)
            card.pack(fill="x", pady=(8, 0))
            estado = "✓ VALIDA" if (s["integro"] and s["valido"]) else "✗ PROBLEMA"
            ttk.Label(card, text=estado, style="H.TLabel").pack(anchor="w")
            ttk.Label(card, text=f"Firmante: {s['firmante']}", style="CardMuted.TLabel",
                      wraplength=460, justify="left").pack(anchor="w")
            if s["fecha"]:
                ttk.Label(card, text=f"Fecha declarada: {s['fecha']}",
                          style="CardMuted.TLabel").pack(anchor="w")
            if s["cobertura"]:
                ttk.Label(card, text=f"Alcance: {s['cobertura']}",
                          style="CardMuted.TLabel").pack(anchor="w")
            ttk.Label(card, text=s["resumen"], style="CardMuted.TLabel",
                      wraplength=460, justify="left").pack(anchor="w", pady=(4, 0))
        ttk.Button(frm, text="Cerrar", command=win.destroy).pack(anchor="e", pady=(12, 0))
        self._modal(win)

    def _ask_corner(self) -> str | None:
        win = tk.Toplevel(self)
        theme.center_window(win)
        win.title("Posicion de la firma")
        win.configure(bg=theme.BG)
        win.transient(self); win.resizable(False, False)
        frm = ttk.Frame(win, padding=16); frm.pack()
        ttk.Label(frm, text="Donde colocar la firma:", style="H.TLabel").pack(anchor="w", pady=(0, 8))
        var = tk.StringVar(value="Abajo derecha")
        for c in ("Abajo derecha", "Abajo izquierda", "Arriba derecha", "Arriba izquierda"):
            ttk.Radiobutton(frm, text=c, value=c, variable=var).pack(anchor="w")
        res = {"v": None}
        ttk.Button(frm, text="Aceptar", style="Primary.TButton",
                   command=lambda: (res.update(v=var.get()), win.destroy())).pack(anchor="e", pady=(10, 0))
        self._modal(win)
        self.wait_window(win)
        return res["v"]

    def _t_metadata(self) -> None:
        try:
            md = pdfops.get_metadata(self.current_pdf)
        except pdfops.PdfError as exc:
            messagebox.showerror(APP_NAME, str(exc)); return
        win = tk.Toplevel(self)
        theme.center_window(win)
        win.title("Metadatos del PDF")
        win.configure(bg=theme.BG)
        win.transient(self); win.resizable(False, False)
        frm = ttk.Frame(win, padding=16); frm.pack(fill="both", expand=True)
        ttk.Label(frm, text=f"Paginas: {md.get('paginas', '?')}",
                  style="CardMuted.TLabel").pack(anchor="w", pady=(0, 8))
        fields = {}
        for key, label in (("Title", "Titulo"), ("Author", "Autor"),
                           ("Subject", "Asunto"), ("Keywords", "Palabras clave")):
            ttk.Label(frm, text=label, style="H.TLabel").pack(anchor="w")
            var = tk.StringVar(value=md.get(key, ""))
            ttk.Entry(frm, textvariable=var, width=46).pack(fill="x", pady=(0, 6))
            fields[key] = var

        def save():
            out = self._out(f"{self._stem()}_metadatos.pdf")
            data = {k: v.get() for k, v in fields.items() if v.get().strip()}
            try:
                pdfops.set_metadata(self.current_pdf, out, data)
            except pdfops.PdfError as exc:
                messagebox.showerror(APP_NAME, str(exc)); return
            win.destroy()
            self._done_toast(out)
        ttk.Button(frm, text="Guardar copia con metadatos", style="Primary.TButton",
                   command=save).pack(anchor="e", pady=(8, 0))
        self._modal(win)

    def _t_ocr(self) -> None:
        if not pdfops.tesseract_available():
            messagebox.showinfo(APP_NAME, "El OCR necesita Tesseract instalado (gratis):\n\n"
                                "winget install UB-Mannheim.TesseractOCR\n\n"
                                "Despues reinicia PDFLocal.")
            return

        def done(text):
            self.nb.select(1)
            self._set_text(self.txt, text or "(sin texto reconocido)")
            self._set_status("OCR completado. Texto en la pestana 'Texto'.")
        self._run_async(lambda: pdfops.ocr_text(self.current_pdf), done,
                        "Reconociendo texto (OCR)… puede tardar.")

    # -------------------------------------------------------------- TEXTO
    def _do_extract_text(self) -> None:
        def done(text):
            self.nb.select(1)
            self._set_text(self.txt, text or "(este PDF no tiene texto; prueba el OCR)")
            self._set_status("Texto extraido.")
        self._run_async(lambda: pdfops.extract_text(self.current_pdf), done,
                        "Extrayendo texto…")

    def _save_text(self) -> None:
        content = self.txt.get("1.0", "end").strip()
        if not content:
            messagebox.showinfo(APP_NAME, "No hay texto. Pulsa 'Extraer texto' primero.")
            return
        out = self._out(f"{self._stem()}.txt")
        try:
            Path(out).write_text(content, encoding="utf-8")
        except OSError as exc:
            messagebox.showerror(APP_NAME, str(exc)); return
        self._done_toast(out)

    def _copy_text(self) -> None:
        content = self.txt.get("1.0", "end").strip()
        if content:
            self.clipboard_clear()
            self.clipboard_append(content)
            self._set_status("Texto copiado al portapapeles.")

    # -------------------------------------------------------------- CHAT
    def _ask(self) -> None:
        if self._busy:
            return
        q = self.var_q.get().strip()
        if not q:
            return
        if not self.current_pdf:
            messagebox.showinfo(APP_NAME, "Primero abre un PDF.")
            return
        # Capturas locales: la extraccion de chunks y el build del indice (que puede
        # pedir embeddings a Ollama) se hacen en el HILO, no en la UI, para no congelarla.
        # Todo lo que lee estado de la app se fija aqui para evitar carreras si el
        # usuario abre otro PDF mientras se responde.
        pdf_path = self.current_pdf
        existing = self.chat
        embed_model = self.cfg.ollama_embed_model or None
        model = self.cfg.ollama_model or None
        self._set_text(self.chat_out, "Pensando…")

        def work():
            chat_obj = existing
            built_now = False
            if chat_obj is None:
                chunks = pdfops.page_text_chunks(pdf_path)
                if not chunks:
                    raise pdfops.PdfError(
                        "Este PDF no tiene texto seleccionable. Usa OCR primero si es "
                        "un documento escaneado.")
                chat_obj = pdfchat.PdfChat(chunks, embed_model)
                chat_obj.build()
                built_now = True
            res = pdfchat.answer(q, chat_obj, model=model)
            return {"chat": chat_obj, "res": res, "built_now": built_now}

        def done(payload):
            # Cachea el indice recien construido solo si seguimos en el MISMO PDF
            # (si el usuario abrio otro, no pisamos su chat/current_pdf).
            if payload["built_now"] and self.current_pdf == pdf_path:
                self.chat = payload["chat"]
            res = payload["res"]
            lines = [f"P: {q}", "", res["respuesta"]]
            if res.get("fuentes"):
                pags = ", ".join(str(f["page"]) for f in res["fuentes"])
                lines += ["", f"— Fuentes: paginas {pags}  ·  modo: {res.get('modo','')}"]
            self._set_text(self.chat_out, "\n".join(lines))
            self._set_status("Respuesta lista.")
        self._run_async(work, done, "Buscando en el documento…")

    # -------------------------------------------------------------- Ollama
    def _refresh_chat_ia(self) -> None:
        from octonove_core.ai_dialog import status_text
        self.lbl_chat_ia.config(text=status_text())

    def _ollama_dialog(self) -> None:
        # Dialogo de IA UNIFICADO de la suite: Ollama local (gratis) o una API
        # potente (OpenAI/Gemini/Anthropic). Se configura una vez para las 5 apps.
        # (Los embeddings para la busqueda semantica siguen autodetectandose de
        # Ollama si esta presente, aunque el chat use un proveedor de nube.)
        from octonove_core.ai_dialog import show_ai_dialog

        def _saved():
            self.chat = None
            self._refresh_chat_ia()
            self._set_status("IA configurada.")
        show_ai_dialog(self, on_saved=_saved)

    # -------------------------------------------------------------- varios
    def _first_run_check(self) -> None:
        if self.cfg.seen_welcome:
            return
        self.cfg.seen_welcome = True
        save_config(self.cfg)
        messagebox.showinfo(
            APP_NAME,
            "Bienvenido a PDFLocal.\n\n"
            "Une, divide, rota, comprime, protege, convierte, firma y extrae texto de "
            "tus PDF — y ademas puedes 'chatear' con el documento.\n\n"
            "TODO ocurre en tu PC: ningun archivo se sube a internet. La alternativa "
            "privada a Adobe y a las webs de PDF.")

    def _on_close(self) -> None:
        if self._busy:
            if not messagebox.askyesno(APP_NAME, "Hay una operacion en curso. Salir igualmente?"):
                return
        self._closing = True
        try:
            save_config(self.cfg)
        except Exception:  # noqa: BLE001
            pass
        self.destroy()


def main() -> None:
    from .config import setup_logging
    setup_logging()
    App().mainloop()
