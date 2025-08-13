import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import subprocess
import threading
import json
import os
import re
import multiprocessing

CONFIG_FILE = "timelapse_config.json"

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_config(config):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

def validate_regex(pattern):
    try:
        re.compile(pattern)
        return True
    except re.error:
        return False

class TimelapseGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Make Timelapse GUI")
        self.process = None
        self.config = load_config()
        self.vars = {}
        self.create_widgets()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def create_widgets(self):
        main_frame = ttk.Frame(self.root, padding=10)
        main_frame.grid(row=0, column=0, sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        def add_labeled_entry(label, varname, browse=False, is_dir=False):
            ttk.Label(main_frame, text=label).grid(sticky="w")
            entry = ttk.Entry(main_frame)
            entry.grid(sticky="ew")
            if browse:
                def browse_func():
                    path = filedialog.askdirectory() if is_dir else filedialog.askopenfilename()
                    if path:
                        entry.delete(0, tk.END)
                        entry.insert(0, path)
                btn = ttk.Button(main_frame, text="Browse", command=browse_func)
                btn.grid(sticky="e")
            self.vars[varname] = entry

        def add_spinbox(label, varname, from_, to, increment=1):
            ttk.Label(main_frame, text=label).grid(sticky="w")
            spin = ttk.Spinbox(main_frame, from_=from_, to=to, increment=increment)
            spin.grid(sticky="ew")
            self.vars[varname] = spin

        def add_checkbox(label, varname):
            var = tk.BooleanVar()
            chk = ttk.Checkbutton(main_frame, text=label, variable=var)
            chk.grid(sticky="w")
            self.vars[varname] = var

        add_labeled_entry("Ref file (--ref)", "ref", browse=True)
        add_labeled_entry("Input directory (--input_dir)", "input_dir", browse=True, is_dir=True)
        add_labeled_entry("Aligned directory (--aligned_dir)", "aligned_dir", browse=True, is_dir=True)
        add_labeled_entry("Movie file (--movie)", "movie", browse=True)
        add_spinbox("Iterations (--iterations)", "iterations", 0, 9999, 1)
        add_labeled_entry("Stddev (--stddev)", "stddev")
        add_spinbox("Workers (--workers)", "workers", 1, multiprocessing.cpu_count(), 1)
        add_checkbox("Use fast (--fast)", "fast")
        add_checkbox("Use multiscale (--multiscale)", "multiscale")
        add_spinbox("CRF (--crf)", "crf", 1, 50, 1)
        add_spinbox("FPS (--fps)", "fps", 1, 120, 1)
        add_checkbox("Show caption (--caption)", "caption")
        add_labeled_entry("Caption RE Pattern (--caption_re)", "caption_re_pattern")
        add_labeled_entry("Caption RE Replacement (--caption_re)", "caption_re_replacement")

        for key, widget in self.vars.items():
            if key in self.config:
                if isinstance(widget, ttk.Entry) or isinstance(widget, ttk.Spinbox):
                    widget.delete(0, tk.END)
                    widget.insert(0, self.config[key])
                elif isinstance(widget, tk.BooleanVar):
                    widget.set(self.config[key])

        button_frame = ttk.Frame(self.root)
        button_frame.grid(row=2, column=0, sticky="ew", pady=5)
        button_frame.columnconfigure(0, weight=1)
        button_frame.columnconfigure(1, weight=1)
        button_frame.columnconfigure(2, weight=1)

        run_btn = ttk.Button(button_frame, text="Run", command=self.run_script)
        run_btn.grid(row=0, column=0, sticky="ew", padx=5)

        stop_btn = ttk.Button(button_frame, text="Stop", command=self.stop_script)
        stop_btn.grid(row=0, column=1, sticky="ew", padx=5)

        close_btn = ttk.Button(button_frame, text="Close", command=self.on_close)
        close_btn.grid(row=0, column=2, sticky="ew", padx=5)

        self.output_text = tk.Text(self.root, wrap="word")
        self.output_text.grid(row=1, column=0, sticky="nsew")
        self.root.rowconfigure(1, weight=1)
        self.root.columnconfigure(0, weight=1)

    def build_command(self):
        cmd = ["python", "make_timelapse.py"]
        config_to_save = {}

        def add_option(key, option_name, is_flag=False):
            widget = self.vars[key]
            if isinstance(widget, ttk.Entry) or isinstance(widget, ttk.Spinbox):
                value = widget.get().strip()
                if value:
                    cmd.extend([option_name, value])
                    config_to_save[key] = value
            elif isinstance(widget, tk.BooleanVar):
                if widget.get():
                    cmd.append(option_name)
                    config_to_save[key] = True
                else:
                    config_to_save[key] = False

        add_option("ref", "--ref")
        add_option("input_dir", "--input_dir")
        add_option("aligned_dir", "--aligned_dir")
        if self.vars["movie"].get().strip():
            add_option("movie", "--movie")
        add_option("iterations", "--iterations")
        add_option("stddev", "--stddev")
        if self.vars["workers"].get().strip():
            add_option("workers", "--workers")
        add_option("fast", "--fast")
        add_option("multiscale", "--multiscale")
        add_option("crf", "--crf")
        add_option("fps", "--fps")
        add_option("caption", "--caption")

        pattern = self.vars["caption_re_pattern"].get().strip()
        replacement = self.vars["caption_re_replacement"].get().strip()
        if pattern and replacement:
            if validate_regex(pattern):
                cmd.extend(["--caption_re", pattern, replacement])
                config_to_save["caption_re_pattern"] = pattern
                config_to_save["caption_re_replacement"] = replacement
            else:
                messagebox.showerror("Regex Error", "Invalid regular expression pattern.")
                return None, None

        return cmd, config_to_save

    def run_script(self):
        cmd, config_to_save = self.build_command()
        if cmd is None:
            return
        save_config(config_to_save)
        self.output_text.delete("1.0", tk.END)

        def run():
            try:
                self.process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                for line in self.process.stdout:
                    self.output_text.insert(tk.END, line)
                    self.output_text.see(tk.END)
                self.process.wait()
            except Exception as e:
                self.output_text.insert(tk.END, f"Error: {e}\n")

        threading.Thread(target=run).start()

    def stop_script(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            self.output_text.insert(tk.END, "Process terminated.\n")
            self.process = None

    def on_close(self):
        config_to_save = {}
        for key, widget in self.vars.items():
            if isinstance(widget, ttk.Entry) or isinstance(widget, ttk.Spinbox):
                config_to_save[key] = widget.get().strip()
            elif isinstance(widget, tk.BooleanVar):
                config_to_save[key] = widget.get()
        save_config(config_to_save)
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = TimelapseGUI(root)
    root.mainloop()
