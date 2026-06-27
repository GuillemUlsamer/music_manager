import tkinter as tk
from tkinter import scrolledtext
import threading
import sys

import music_manager


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
        self.root.geometry("650x520")

        # Fila superior: nombre del spreadsheet + botón
        top_frame = tk.Frame(root, pady=10)
        top_frame.pack(fill=tk.X, padx=10)

        tk.Label(top_frame, text="Nombre de la Playlist:").pack(side=tk.LEFT)

        self.name_entry = tk.Entry(top_frame, cursor="xterm")
        self.name_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8)
        self.name_entry.bind("<Return>", lambda event: self.start_run())

        self.run_button = tk.Button(top_frame, text="Ejecutar", cursor="hand2", command=self.start_run)
        self.run_button.pack(side=tk.LEFT)

        # Log
        self.log_box = scrolledtext.ScrolledText(root, cursor="arrow", wrap=tk.WORD, state="normal")
        self.log_box.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        # Fila inferior: Status label + botón Detener
        bottom_frame = tk.Frame(root)
        bottom_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        self.status_label = tk.Label(bottom_frame, text="Listo.", anchor="w")
        self.status_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Stop button
        self.stop_button = tk.Button(bottom_frame, text="Detener", cursor="hand2", command=self._on_stop)
        self.stop_button.pack(side=tk.LEFT)

        # Redirigimos los print() de music_manager.py hacia el log_box
        sys.stdout = StdoutRedirector(self.log_box)

    def start_run(self):
        name = self.name_entry.get().strip()
        if not name:
            self.status_label.config(text="Escribe un nombre de spreadsheet primero.")
            return

        # Evitar lanzar dos ejecuciones a la vez
        self.run_button.config(state="disabled")
        self.status_label.config(text=f"Ejecutando: {name} ...")

        # Lanzamos la descarga en un hilo aparte para que la ventana no se congele
        thread = threading.Thread(target=self._run_in_thread, args=(name,), daemon=True)
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
        self.status_label.config(text="Listo.")

    def _on_stop(self):
        self.status_label.config(text="Deteniendo...")
        music_manager.stop_manager()


if __name__ == "__main__":
    root = tk.Tk()
    app = MusicManagerGUI(root)
    root.mainloop()