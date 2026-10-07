import io
import sys
import threading
import tkinter as tk
from tkinter import scrolledtext, ttk, filedialog

from PIL import Image, ImageOps, ImageTk

import bootstrap
import manager as music_manager
import sheets


class StdoutRedirector:
    """
    Redirige los print() hacia un widget de texto de Tkinter,
    aplicando un color/estilo distinto según el tipo de línea
    (búsqueda, match, descarga, error...).
    """
    def __init__(self, text_widget):
        self.text_widget = text_widget
        self._configure_tags()

    def _configure_tags(self):
        # Definimos cada "tag" una sola vez: nombre + estilo (color, negrita...)
        self.text_widget.tag_configure("search", foreground="#1a73e8")           # azul
        self.text_widget.tag_configure("match", foreground="#188038", font=("TkDefaultFont", 10, "bold"))  # verde negrita
        self.text_widget.tag_configure("downloading", foreground="#9c27b0")      # morado
        self.text_widget.tag_configure("done", foreground="#188038", font=("TkDefaultFont", 10, "bold"))   # verde negrita
        self.text_widget.tag_configure("error", foreground="#d93025")            # rojo
        self.text_widget.tag_configure("failed", foreground="#d93025", font=("TkDefaultFont", 10, "bold")) # rojo negrita

    def write(self, message):
        self.text_widget.after(0, self._append, message)

    def _append(self, message):
        # Cada print() puede traer varias líneas pegadas (por los \n);
        # las separamos para poder dar a cada una su propio color.
        self.text_widget.config(state="normal")
        lines = message.split("\n")
        for idx, line in enumerate(lines):
            if line:
                tag = self._classify(line)
                if tag:
                    self.text_widget.insert(tk.END, line, tag)
                else:
                    self.text_widget.insert(tk.END, line)
            if idx < len(lines) - 1:
                self.text_widget.insert(tk.END, "\n")
        self.text_widget.see(tk.END)
        self.text_widget.config(state="disabled")

    def _classify(self, line):
        # Decide qué tag aplicar según el contenido de la línea.
        # Importante: el orden importa (de más específico a más genérico).
        lower = line.lower()
        if "> search" in lower:
            return "search"
        if "> match:" in lower:
            return "match"
        if "downloading:" in lower or "downloading..." in lower:
            return "downloading"
        if "> done." in lower or ("downloaded" in lower and "failed" not in lower):
            return "done"
        if "failed" in lower:
            return "failed"
        if "error" in lower:
            return "error"
        return None

    def flush(self):
        pass


class MusicManagerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Music Manager")
        self.root.geometry("1200x520")
        self.playlist_name = None

        self._build_setup()
        self._build_picker()
        self._build_runner()

        sys.stdout = StdoutRedirector(self.log_box)
        if bootstrap.is_configured():
            self.show_picker()
        else:
            self.show_setup()

    # pantalla de configuracion del primer arranque
    def _build_setup(self):
        self.setup = tk.Frame(self.root, padx=40, pady=30)
        tk.Label(self.setup, text="Set up Music Manager",
                 font=("TkDefaultFont", 13, "bold")).pack(anchor="w", pady=(0, 4))
        tk.Label(self.setup, anchor="w", justify="left", wraplength=800,
                 text="slskd (the Soulseek client) will be downloaded and configured automatically. "
                      "If the Soulseek username does not exist yet, it will be created with this password.").pack(anchor="w", pady=(0, 16))

        form = tk.Frame(self.setup)
        form.pack(anchor="w", fill=tk.X)
        form.columnconfigure(1, weight=1)

        self.setup_user = self._form_row(form, 0, "Soulseek username:")
        self.setup_pass = self._form_row(form, 1, "Soulseek password:", show="*")
        self.setup_music = self._form_row(form, 2, "Music folder:",
                                          browse=lambda: self._pick_dir(self.setup_music, "Music folder"))
        self.setup_music.insert(0, str(bootstrap.DEFAULT_MUSIC_DIR))
        self.setup_share = self._form_row(form, 3, "Folder to share (optional):",
                                          browse=lambda: self._pick_dir(self.setup_share, "Folder to share on Soulseek"))
        self.setup_creds = self._form_row(form, 4, "Google credentials.json:",
                                          browse=lambda: self._pick_file(self.setup_creds))
        if bootstrap.CREDENTIALS_FILE.exists():
            self.setup_creds.insert(0, str(bootstrap.CREDENTIALS_FILE))

        self.setup_button = tk.Button(self.setup, text="Set up", cursor="hand2", command=self.start_setup)
        self.setup_button.pack(anchor="w", pady=(18, 10))
        self.setup_progress = ttk.Progressbar(self.setup, mode="indeterminate", length=400)
        self.setup_status = tk.Label(self.setup, text="", anchor="w", justify="left", wraplength=800)
        self.setup_status.pack(anchor="w")

    def _form_row(self, parent, row, label, show=None, browse=None):
        tk.Label(parent, text=label, anchor="w").grid(row=row, column=0, sticky="w", pady=4)
        entry = tk.Entry(parent, show=show) if show else tk.Entry(parent)
        entry.grid(row=row, column=1, sticky="ew", padx=8, pady=4)
        if browse:
            tk.Button(parent, text="...", cursor="hand2", command=browse).grid(row=row, column=2, pady=4)
        return entry

    def _pick_dir(self, entry, title):
        path = filedialog.askdirectory(title=title)
        if path:
            entry.delete(0, tk.END)
            entry.insert(0, path)

    def _pick_file(self, entry):
        path = filedialog.askopenfilename(title="credentials.json", filetypes=[("JSON", "*.json")])
        if path:
            entry.delete(0, tk.END)
            entry.insert(0, path)

    def start_setup(self):
        user = self.setup_user.get().strip()
        pwd = self.setup_pass.get()
        music = self.setup_music.get().strip()
        share = self.setup_share.get().strip() or None
        creds = self.setup_creds.get().strip() or None
        if not user or not pwd:
            self.setup_status.config(text="Soulseek username and password are required.")
            return
        if not music:
            self.setup_status.config(text="Choose a music folder.")
            return
        if not creds:
            self.setup_status.config(text="Select your Google credentials.json.")
            return
        self.setup_button.config(state="disabled")
        self.setup_progress.pack(anchor="w", pady=(0, 8), before=self.setup_status)
        self.setup_progress.start(12)
        threading.Thread(target=self._setup_thread, args=(user, pwd, music, share, creds), daemon=True).start()

    def _setup_thread(self, user, pwd, music, share, creds):
        progress = lambda msg: self.root.after(0, self.setup_status.config, {"text": msg})
        try:
            bootstrap.run_setup(user, pwd, music, share, creds, progress=progress)
            error = None
        except Exception as e:
            error = e
        self.root.after(0, self._on_setup_done, error)

    def _on_setup_done(self, error):
        self.setup_progress.stop()
        self.setup_progress.pack_forget()
        self.setup_button.config(state="normal")
        if error:
            self.setup_status.config(text=f"Error: {error}")
            return
        self.show_picker()

    def show_setup(self):
        self.picker.pack_forget()
        self.runner.pack_forget()
        self.setup.pack(fill=tk.BOTH, expand=True)

    # pantalla de selección de playlist
    THUMB = 160
    COLS = 6

    def _build_picker(self):
        self.picker = tk.Frame(self.root, padx=10, pady=10)

        tk.Label(self.picker, text="Choose a playlist from your Drive:",
                 font=("TkDefaultFont", 11, "bold")).pack(anchor="w")

        # Canvas con scroll que contiene el frame de tarjetas
        grid_frame = tk.Frame(self.picker)
        grid_frame.pack(fill=tk.BOTH, expand=True, pady=8)
        self.canvas = tk.Canvas(grid_frame, highlightthickness=0)
        scrollbar = tk.Scrollbar(grid_frame, orient="vertical", command=self.canvas.yview)
        self.cards = tk.Frame(self.canvas)
        self.cards.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.cards, anchor="nw")
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.bind_all("<MouseWheel>", lambda e: self.canvas.yview_scroll(-e.delta // 120, "units"))

        buttons = tk.Frame(self.picker)
        buttons.pack(fill=tk.X)
        self.picker_status = tk.Label(buttons, text="", anchor="w")
        self.picker_status.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.refresh_button = tk.Button(buttons, text="Refresh", cursor="hand2", command=self.load_playlists)
        self.refresh_button.pack(side=tk.LEFT)

        self.thumbs = []   # referencias a las PhotoImage: si se pierden, Tk las borra

    def load_playlists(self):
        self.refresh_button.config(state="disabled")
        self.picker_status.config(text="Loading playlists from Drive...")
        threading.Thread(target=self._load_playlists_thread, daemon=True).start()

    def _load_playlists_thread(self):
        try:
            playlists = sheets.list_playlists()
            error = None
        except Exception as e:
            playlists, error = [], e
        self.root.after(0, self._on_playlists_loaded, playlists, error)

    def _on_playlists_loaded(self, playlists, error):
        self.refresh_button.config(state="normal")
        if error:
            self.picker_status.config(text=f"Could not load playlists: {error}")
            return
        for w in self.cards.winfo_children():
            w.destroy()
        self.thumbs.clear()

        for i, p in enumerate(playlists):
            photo = self._make_thumb(p['image'])
            self.thumbs.append(photo)
            card = tk.Frame(self.cards, padx=8, pady=8, cursor="hand2")
            card.grid(row=i // self.COLS, column=i % self.COLS, padx=6, pady=6)
            img_label = tk.Label(card, image=photo, bd=1, relief="solid")
            img_label.pack()
            txt_label = tk.Label(card, text=p['title'], wraplength=self.THUMB, justify="center")
            txt_label.pack(pady=(6, 0))
            for w in (card, img_label, txt_label):
                w.bind("<Button-1>", lambda e, name=p['title']: self.open_playlist(name))

        self.picker_status.config(text=f"{len(playlists)} playlists available.")

    def _make_thumb(self, image_bytes):
        if image_bytes:
            img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            img = ImageOps.fit(img, (self.THUMB, self.THUMB))
        else:
            img = Image.new("RGB", (self.THUMB, self.THUMB), "#dddddd")
        return ImageTk.PhotoImage(img)

    def open_playlist(self, name):
        self.playlist_name = name
        self.show_runner()

    # pantalla de descarga
    def _build_runner(self):
        self.runner = tk.Frame(self.root)

        top_frame = tk.Frame(self.runner, pady=10)
        top_frame.pack(fill=tk.X, padx=10)
        self.back_button = tk.Button(top_frame, text="< Playlists", cursor="hand2", command=self.show_picker)
        self.back_button.pack(side=tk.LEFT, padx=(0, 12))
        self.title_label = tk.Label(top_frame, text="", font=("TkDefaultFont", 11, "bold"), anchor="w")
        self.title_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.run_button = tk.Button(top_frame, text="Run", cursor="hand2", command=self.start_run)
        self.run_button.pack(side=tk.LEFT)

        self.log_box = scrolledtext.ScrolledText(self.runner, cursor="arrow", wrap=tk.WORD, state="disabled")
        self.log_box.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        bottom_frame = tk.Frame(self.runner)
        bottom_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        self.status_label = tk.Label(bottom_frame, text="Ready.", anchor="w")
        self.status_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.stop_button = tk.Button(bottom_frame, text="Stop", cursor="hand2", command=self._on_stop)
        self.stop_button.pack(side=tk.LEFT)

    def show_picker(self):
        self.setup.pack_forget()
        self.runner.pack_forget()
        self.picker.pack(fill=tk.BOTH, expand=True)
        self.load_playlists()

    def show_runner(self):
        self.picker.pack_forget()
        self.title_label.config(text=self.playlist_name)
        self.status_label.config(text="Ready.")
        self.runner.pack(fill=tk.BOTH, expand=True)
        self.start_run()

    def start_run(self):
        self.run_button.config(state="disabled")
        self.back_button.config(state="disabled")
        self.status_label.config(text=f"Running: {self.playlist_name} ...")
        thread = threading.Thread(target=self._run_in_thread, args=(self.playlist_name,), daemon=True)
        thread.start()

    def _run_in_thread(self, name):
        try:
            music_manager.run_manager(name)
        except Exception as e:
            print(f"Unexpected error: {e}")
        finally:
            # Volvemos a habilitar el botón desde el hilo principal
            self.root.after(0, self._on_finished)

    def _on_finished(self):
        self.run_button.config(state="normal")
        self.back_button.config(state="normal")
        self.status_label.config(text="Ready.")

    def _on_stop(self):
        self.status_label.config(text="Stopping...")
        music_manager.stop_manager()

if __name__ == "__main__":
    root = tk.Tk()
    app = MusicManagerGUI(root)
    root.mainloop()