import tkinter as tk
from tkinter import scrolledtext, ttk
import threading
import sys

import music_manager_v2 as music_manager


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

        self._build_picker()
        self._build_runner()

        sys.stdout = StdoutRedirector(self.log_box)
        self.show_picker()

    # pantalla de selección de playlist
    def _build_picker(self):
        self.picker = tk.Frame(self.root, padx=10, pady=10)

        tk.Label(self.picker, text="Elige una playlist de tu Drive:",
                 font=("TkDefaultFont", 11, "bold")).pack(anchor="w")

        list_frame = tk.Frame(self.picker)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=8)
        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.playlist_list = tk.Listbox(list_frame, font=("TkDefaultFont", 11),
                                        yscrollcommand=scrollbar.set, activestyle="none")
        self.playlist_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.playlist_list.yview)
        self.playlist_list.bind("<Double-Button-1>", lambda e: self.open_selected())
        self.playlist_list.bind("<Return>", lambda e: self.open_selected())

        buttons = tk.Frame(self.picker)
        buttons.pack(fill=tk.X)
        self.picker_status = tk.Label(buttons, text="", anchor="w")
        self.picker_status.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.refresh_button = tk.Button(buttons, text="Actualizar", cursor="hand2", command=self.load_playlists)
        self.refresh_button.pack(side=tk.LEFT, padx=(0, 8))
        self.open_button = tk.Button(buttons, text="Abrir", cursor="hand2", command=self.open_selected)
        self.open_button.pack(side=tk.LEFT)

    def load_playlists(self):
        self.refresh_button.config(state="disabled")
        self.picker_status.config(text="Cargando playlists de Drive...")
        threading.Thread(target=self._load_playlists_thread, daemon=True).start()
    
    def _load_playlists_thread(self):
        try:
            names = music_manager.list_spreadsheets()
            error = None
        except Exception as e:
            names, error = [], e
        self.root.after(0, self._on_playlists_loaded, names, error)

    def _on_playlists_loaded(self, names, error):
        self.refresh_button.config(state="normal")
        if error:
            self.picker_status.config(text=f"No se pudieron cargar las playlists: {error}")
            return
        self.playlist_list.delete(0, tk.END)
        for name in names:
            self.playlist_list.insert(tk.END, name)
        if names:
            self.playlist_list.selection_set(0)
            self.playlist_list.focus_set()
        self.picker_status.config(text=f"{len(names)} playlists disponibles.")

    def open_selected(self):
        selection = self.playlist_list.curselection()
        if not selection:
            self.picker_status.config(text="Selecciona una playlist primero.")
            return
        self.playlist_name = self.playlist_list.get(selection[0])
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
        self.run_button = tk.Button(top_frame, text="Ejecutar", cursor="hand2", command=self.start_run)
        self.run_button.pack(side=tk.LEFT)

        self.log_box = scrolledtext.ScrolledText(self.runner, cursor="arrow", wrap=tk.WORD, state="normal")
        self.log_box.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        bottom_frame = tk.Frame(self.runner)
        bottom_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        self.status_label = tk.Label(bottom_frame, text="Listo.", anchor="w")
        self.status_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.stop_button = tk.Button(bottom_frame, text="Detener", cursor="hand2", command=self._on_stop)
        self.stop_button.pack(side=tk.LEFT)

    def show_picker(self):
        self.runner.pack_forget()
        self.picker.pack(fill=tk.BOTH, expand=True)
        self.load_playlists()

    def show_runner(self):
        self.picker.pack_forget()
        self.title_label.config(text=self.playlist_name)
        self.status_label.config(text="Listo.")
        self.runner.pack(fill=tk.BOTH, expand=True)
        self.start_run()

    def start_run(self):
        self.run_button.config(state="disabled")
        self.back_button.config(state="disabled")
        self.status_label.config(text=f"Ejecutando: {self.playlist_name} ...")
        thread = threading.Thread(target=self._run_in_thread, args=(self.playlist_name,), daemon=True)
        thread.start()

    def _run_in_thread(self, name):
        try:
            music_manager.run_manager(name)
        except Exception as e:
            print(f"Error inesperado: {e}")
        finally:
            # Volvemos a habilitar el botón desde el hilo principal
            self.root.after(0, self._on_finished)

    def _on_finished(self):
        self.run_button.config(state="normal")
        self.back_button.config(state="normal")
        self.status_label.config(text="Listo.")

    def _on_stop(self):
        self.status_label.config(text="Deteniendo...")
        music_manager.stop_manager()

if __name__ == "__main__":
    root = tk.Tk()
    app = MusicManagerGUI(root)
    root.mainloop()