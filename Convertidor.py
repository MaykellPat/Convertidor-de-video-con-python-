import subprocess
import os
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
import threading
from queue import Queue

class VideoConverterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Video Converter")
        self.root.geometry("800x600")

        self.files = []
        self.output_directory = tk.StringVar()
        self.supported_formats = ['mp4', 'avi', 'mov', 'mkv']
        self.file_queue = Queue()
        self.current_thread = None
        self.paused = threading.Event()
        self.paused.set()
        self.cancelled = threading.Event()

        self.label = tk.Label(root, text="Seleccione archivos de video:")
        self.label.pack(pady=10)

        self.file_listbox = tk.Listbox(root, selectmode=tk.MULTIPLE, width=60)
        self.file_listbox.pack(pady=10)

        self.add_button = tk.Button(root, text="Agregar Archivos", command=self.add_files)
        self.add_button.pack(pady=5)

        self.remove_button = tk.Button(root, text="Eliminar Seleccionados", command=self.remove_files)
        self.remove_button.pack(pady=5)

        self.output_dir_label = tk.Label(root, text="Seleccione el directorio de salida:")
        self.output_dir_label.pack(pady=10)

        self.output_dir_entry = tk.Entry(root, textvariable=self.output_directory, width=50)
        self.output_dir_entry.pack(pady=5)

        self.browse_button = tk.Button(root, text="Buscar", command=self.browse_output_directory)
        self.browse_button.pack(pady=5)

        self.format_label = tk.Label(root, text="Seleccione el formato de salida:")
        self.format_label.pack(pady=10)

        self.format_var = tk.StringVar(value="mp4")
        self.format_entry = tk.Entry(root, textvariable=self.format_var)
        self.format_entry.pack(pady=5)

        self.convert_button = tk.Button(root, text="Convertir Archivos", command=self.convert_files)
        self.convert_button.pack(pady=20)

        self.pause_button = tk.Button(root, text="Pausar", command=self.pause_conversion, state=tk.DISABLED)
        self.pause_button.pack(pady=5)

        self.cancel_button = tk.Button(root, text="Cancelar", command=self.cancel_conversion, state=tk.DISABLED)
        self.cancel_button.pack(pady=5)

        self.log_window = tk.Toplevel(root)
        self.log_window.title("Registro de Conversión")
        self.log_text = scrolledtext.ScrolledText(self.log_window, width=80, height=20)
        self.log_text.pack(pady=10, fill=tk.BOTH, expand=True)

        self.message_box = None  # Variable para almacenar la ventana emergente del mensaje

    def add_files(self):
        files = filedialog.askopenfilenames(filetypes=[("Video files", "*.mp4;*.avi;*.mov;*.mkv")])
        if files:
            for file in files:
                if file not in self.files:
                    self.files.append(file)
                    self.file_listbox.insert(tk.END, file)

    def remove_files(self):
        selected_files = self.file_listbox.curselection()
        for index in reversed(selected_files):
            file = self.file_listbox.get(index)
            self.file_listbox.delete(index)
            self.files.remove(file)

    def browse_output_directory(self):
        directory = filedialog.askdirectory()
        if directory:
            self.output_directory.set(directory)

    def convert_chunk(self, input_file, output_format, start, end, progress_callback):
        output_file = f"{os.path.splitext(input_file)[0]}_{start}_{end}.{output_format}"
        try:
            subprocess.run(['ffmpeg', '-i', input_file, '-ss', str(start), '-to', str(end), '-c', 'copy', output_file], check=True)
            progress_callback(True, f"Convertido: {output_file}\n")
        except subprocess.CalledProcessError as e:
            progress_callback(False, f"Error al convertir: {e}\n")

    def merge_chunks(self, input_files, output_file):
        try:
            with open(output_file, 'wb') as f:
                for input_file in input_files:
                    with open(input_file, 'rb') as chunk_file:
                        f.write(chunk_file.read())
        except Exception as e:
            messagebox.showerror("Error", f"Error al unir archivos: {e}")

    def delete_temp_files(self, input_files):
        for file in input_files:
            os.remove(file)

    def convert_file(self, input_file, output_format, progress_callback):
        try:
            # Dividir el archivo en partes de 10 MB
            file_size = os.path.getsize(input_file)
            chunk_size = 10 * 1024 * 1024
            num_chunks = file_size // chunk_size
            if file_size % chunk_size != 0:
                num_chunks += 1

            chunk_threads = []
            chunk_files = []

            for i in range(num_chunks):
                start = i * chunk_size
                end = min((i + 1) * chunk_size, file_size)
                thread = threading.Thread(target=self.convert_chunk, args=(input_file, output_format, start, end, progress_callback))
                chunk_threads.append(thread)
                thread.start()

            for thread in chunk_threads:
                thread.join()

            for i in range(num_chunks):
                chunk_files.append(f"{os.path.splitext(input_file)[0]}_{i * chunk_size}_{min((i + 1) * chunk_size, file_size)}.{output_format}")

            # Unir las partes convertidas
            output_file = f"{os.path.splitext(input_file)[0]}.{output_format}"
            self.merge_chunks(chunk_files, output_file)
            progress_callback(True, f"Archivo de salida: {output_file}\n")

            # Eliminar archivos temporales
            self.delete_temp_files(chunk_files)
        except Exception as e:
            progress_callback(False, f"Error durante la conversión: {e}\n")

    def worker(self):
        while not self.file_queue.empty():
            file, output_format, progress_callback = self.file_queue.get()
            self.convert_file(file, output_format, progress_callback)
            self.file_queue.task_done()

        # Mostrar el mensaje de finalización de la conversión cuando se haya completado la cola de archivos
        self.show_completion_message()

    def show_completion_message(self):
        # Crear una ventana emergente para mostrar el mensaje de finalización
        self.message_box = tk.Toplevel(self.root)
        self.message_box.title("Conversión completada")
        self.message_box.geometry("300x100")

        message_label = tk.Label(self.message_box, text="¡La conversión de todos los archivos ha finalizado!")
        message_label.pack(pady=10)

        # Función para cerrar la aplicación al hacer clic en "Aceptar"
        def close_application():
            self.message_box.destroy()  # Cerrar la ventana emergente
            self.root.quit()  # Cerrar la aplicación

        accept_button = tk.Button(self.message_box, text="Aceptar", command=close_application)
        accept_button.pack(pady=5)

    def convert_files(self):
        output_format = self.format_var.get().lower()
        if output_format not in self.supported_formats:
            messagebox.showwarning("Formato no soportado", f"El formato {output_format} no está soportado.")
            return

        if not output_format:
            messagebox.showwarning("Formato no especificado", "Por favor, especifique el formato de salida.")
            return

        if not self.files:
            messagebox.showwarning("Archivos no seleccionados", "Por favor, seleccione al menos un archivo de video.")
            return

        if not self.output_directory.get():
            messagebox.showwarning("Directorio no especificado", "Por favor, seleccione el directorio de salida.")
            return

        self.paused.set()
        self.cancelled.clear()
        self.pause_button.config(state=tk.NORMAL)
        self.cancel_button.config(state=tk.NORMAL)

        for file in self.files:
            self.file_queue.put((file, output_format, self.update_log_text))

        if not self.current_thread or not self.current_thread.is_alive():
            self.current_thread = threading.Thread(target=self.worker)
            self.current_thread.start()

    def pause_conversion(self):
        if self.paused.is_set():
            self.paused.clear()
            self.pause_button.config(text="Reanudar")
        else:
            self.paused.set()
            self.pause_button.config(text="Pausar")

    def cancel_conversion(self):
        self.cancelled.set()
        if self.current_thread and self.current_thread.is_alive():
            self.current_thread.join()
        self.pause_button.config(state=tk.DISABLED)
        self.cancel_button.config(state=tk.DISABLED)
        self.paused.set()

    def update_log_text(self, success, message):
        if success:
            self.log_text.insert(tk.END, message)
        else:
            self.log_text.insert(tk.END, message)
            self.cancel_conversion()

if __name__ == "__main__":
    root = tk.Tk()
    app = VideoConverterApp(root)
    root.mainloop()

