import json
import os
import subprocess
import threading
import re
import sys

# Prefer tkxui if available, otherwise fall back to tkinter.
try:
    import tkxui as tk
    from tkxui import ttk, filedialog, messagebox
    USING_TKXUI = True
except Exception:
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
    USING_TKXUI = False

CONFIG_FILE = "make_timelapse_gui_config.json"
UI_FILE = "make_timelapse_gui_ui.json"

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

class TimelapseGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Make Timelapse")
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.process = None
        self.config_data = load_config()
        self.widgets = {}
        self.build_ui()
        self.load_previous_values()

    def build_ui(self):
        if not os.path.exists(UI_FILE):
            messagebox.showerror("Error", f"UI definition file '{UI_FILE}' not found.")
            self.destroy()
            return

        with open(UI_FILE, "r", encoding="utf-8") as f:
            ui_layout = json.load(f)

        main_frame = ttk.Frame(self)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        for item in ui_layout.get("fields", []):
            label = ttk.Label(main_frame, text=item["label"])
            label.grid(row=item["row"], column=0, sticky="w", pady=2)

            widget_type = item["type"]
            name = item["name"]

            if widget_type == "entry":
                entry = ttk.Entry(main_frame, width=item.get("width", 40))
                entry.grid(row=item["row"], column=1, sticky="w", pady=2)
                # store as (type, widget) so we can handle tkxui/tk compatibility
                self.widgets[name] = ("entry", entry)
            elif widget_type == "spinbox":
                spin = ttk.Spinbox(main_frame, from_=item["min"], to=item["max"], width=10)
                spin.grid(row=item["row"], column=1, sticky="w", pady=2)
                self.widgets[name] = ("spinbox", spin)
            elif widget_type == "check":
                var = tk.BooleanVar()
                check = ttk.Checkbutton(main_frame, variable=var)
                check.grid(row=item["row"], column=1, sticky="w", pady=2)
                self.widgets[name] = ("check", var)
            elif widget_type == "file":
                entry = ttk.Entry(main_frame, width=40)
                entry.grid(row=item["row"], column=1, sticky="ew", pady=2)
                btn = ttk.Button(main_frame, text="Browse", command=lambda e=entry: self.browse_file(e))
                btn.grid(row=item["row"], column=2, padx=5)
                self.widgets[name] = ("file", entry)
            elif widget_type == "folder":
                entry = ttk.Entry(main_frame, width=40)
                entry.grid(row=item["row"], column=1, sticky="ew", pady=2)
                btn = ttk.Button(main_frame, text="Browse", command=lambda e=entry: self.browse_folder(e))
                btn.grid(row=item["row"], column=2, padx=5)
                self.widgets[name] = ("folder", entry)

        # Buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.grid(row=100, column=0, columnspan=3, pady=10)

        run_btn = ttk.Button(btn_frame, text="Run", command=self.run_script)
        run_btn.pack(side="left", padx=5)

        stop_btn = ttk.Button(btn_frame, text="Stop", command=self.stop_script)
        stop_btn.pack(side="left", padx=5)

        self.close_btn = ttk.Button(btn_frame, text="Close", command=self.on_close)
        self.close_btn.pack(side="left", padx=5)

        # Output Text with vertical scrollbar
        text_frame = ttk.Frame(main_frame)
        text_frame.grid(row=101, column=0, columnspan=3, sticky="nsew", pady=5)
        main_frame.rowconfigure(101, weight=1)
        main_frame.columnconfigure(1, weight=1)

        self.output_text = tk.Text(text_frame, height=15)
        self.output_text.pack(side="left", fill="both", expand=True)

        scrollbar = ttk.Scrollbar(text_frame, orient="vertical", command=self.output_text.yview)
        scrollbar.pack(side="right", fill="y")
        self.output_text.config(yscrollcommand=scrollbar.set)

    def browse_file(self, entry):
        filename = filedialog.askopenfilename()
        if filename:
            entry.delete(0, tk.END)
            entry.insert(0, filename)

    def browse_folder(self, entry):
        foldername = filedialog.askdirectory()
        if foldername:
            entry.delete(0, tk.END)
            entry.insert(0, foldername)

    def load_previous_values(self):
        for key, pair in self.widgets.items():
            wtype, widget = pair
            if key in self.config_data:
                value = self.config_data[key]
                if wtype in ("entry", "spinbox", "file", "folder"):
                    try:
                        widget.delete(0, tk.END)
                        widget.insert(0, value)
                    except Exception:
                        # fallback: ignore if widget API differs
                        pass
                elif wtype == "check":
                    try:
                        widget.set(bool(value))
                    except Exception:
                        pass

        # Restore window size
        width = self.config_data.get("window_width")
        height = self.config_data.get("window_height")
        if width and height:
            self.geometry(f"{width}x{height}")

    def collect_inputs(self):
        inputs = {}
        for key, pair in self.widgets.items():
            wtype, widget = pair
            if wtype in ("entry", "spinbox", "file", "folder"):
                try:
                    inputs[key] = widget.get()
                except Exception:
                    inputs[key] = None
            elif wtype == "check":
                try:
                    inputs[key] = bool(widget.get())
                except Exception:
                    inputs[key] = False
        return inputs

    def run_script(self):
        inputs = self.collect_inputs()
        save_config(inputs)

        cmd = [sys.executable, "make_timelapse.py"]

        def add_arg(flag, value):
            if value:
                cmd.extend([flag, value])

        add_arg("--ref", inputs.get("ref"))
        add_arg("--input_dir", inputs.get("input_dir"))
        add_arg("--aligned_dir", inputs.get("aligned_dir"))
        if inputs.get("movie"):
            add_arg("--movie", inputs.get("movie"))
        add_arg("--iterations", inputs.get("iterations"))
        add_arg("--stddev", inputs.get("stddev"))
        if inputs.get("workers"):
            add_arg("--workers", inputs.get("workers"))
        if inputs.get("fast") == True:
            cmd.append("--fast")
        if inputs.get("multiscale") == True:
            cmd.append("--multiscale")
        add_arg("--crf", inputs.get("crf"))
        fps = inputs.get("fps")
        if fps:
            add_arg("--fps", fps)
        if inputs.get("caption") == True:
            cmd.append("--caption")
        pattern = inputs.get("caption_re_pattern")
        replacement = inputs.get("caption_re_replacement")
        if pattern and replacement and validate_regex(pattern):
            cmd.extend(["--caption_re", pattern, replacement])

        self.output_text.delete("1.0", tk.END)
        self.close_btn.config(state="disabled")
        self.process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

        def read_output():
            for line in self.process.stdout:
                self.output_text.insert(tk.END, line)
                self.output_text.see(tk.END)
            self.process = None
            self.close_btn.config(state="normal")

        threading.Thread(target=read_output, daemon=True).start()

    def stop_script(self):
        if self.process:
            self.process.terminate()
            self.process = None
            self.output_text.insert(tk.END, "\nProcess terminated.\n")
            self.output_text.see(tk.END)
            self.close_btn.config(state="normal")

    def on_close(self):
        inputs = self.collect_inputs()
        width = self.winfo_width()
        height = self.winfo_height()
        inputs["window_width"] = width
        inputs["window_height"] = height
        save_config(inputs)
        self.destroy()

if __name__ == "__main__":
    app = TimelapseGUI()
    app.mainloop()
