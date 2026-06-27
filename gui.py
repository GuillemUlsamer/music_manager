import tkinter as tk
from tkinter import scrolledtext
import threading
import sys

import music_manager


class StdoutRedirector:
    # Redirige los print() hacia un widget de texto de Tkinter
    def __init__(self, text_widget):
        self.text_widget = text_widget

    def write(self, message):
        self.text_widget.after(0, self._append, message)

    def _append(self, message):
        self.text_widget.insert(tk.END, message)
        self.text_widget.see(tk.END)

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

        self.name_entry = tk.Entry(top_frame)
        self.name_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8)
        self.name_entry.bind("<Return>", lambda event: self.start_run())

        self.run_button = tk.Button(top_frame, text="Ejecutar", command=self.start_run)
        self.run_button.pack(side=tk.LEFT)

        # Log
        self.log_box = scrolledtext.ScrolledText(root, wrap=tk.WORD, state="normal")
        self.log_box.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        # Fila inferior: Status label + botón Detener
        bottom_frame = tk.Frame(root)
        bottom_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        self.status_label = tk.Label(bottom_frame, text="Listo.", anchor="w")
        self.status_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Stop button
        self.stop_button = tk.Button(bottom_frame, text="Detener", command=self._on_stop)
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