import json
import os
import subprocess
import threading
import signal
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
        # flag to stop output printing when Stop is requested
        self._stop_requested = False
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
            widget_type = item["type"]
            name = item["name"]

            # render left-side label for normal fields (not heading labels, buttons, or checkboxes)
            # checkboxes will render their own label to the right of the checkbox inside the same column
            if widget_type not in ("label", "button", "check"):
                left_lbl = ttk.Label(main_frame, text=item.get("label", ""))
                left_lbl.grid(row=item["row"], column=0, sticky="w", pady=2)

            if widget_type == "label":
                # If label text is empty, create a fixed-height spacer.
                label_text = item.get("label", "")
                if not label_text:
                    spacer_height = item.get("height", 10)
                    spacer = ttk.Frame(main_frame, height=spacer_height)
                    spacer.grid(row=item["row"], column=0, columnspan=3, sticky="we", pady=2)
                    # prevent the frame from shrinking to 0 height
                    try:
                        spacer.grid_propagate(False)
                    except Exception:
                        pass
                    continue

                # Render visible labels as bold headings
                try:
                    if hasattr(tk, "font") and hasattr(tk.font, "Font"):
                        bold_font = tk.font.Font(weight="bold")
                        lbl = ttk.Label(main_frame, text=label_text, font=bold_font)
                    else:
                        lbl = ttk.Label(main_frame, text=label_text, font=("TkDefaultFont", 10, "bold"))
                except Exception:
                    lbl = ttk.Label(main_frame, text=label_text)
                lbl.grid(row=item["row"], column=0, columnspan=3, sticky="w", pady=2)
                # don't store as interactive widget
                continue

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
                # place checkbox in column 0 and set label via Checkbutton's text argument
                check = ttk.Checkbutton(main_frame, variable=var, text=item.get("label", ""))
                check.grid(row=item["row"], column=0, sticky="w", pady=2)
                self.widgets[name] = ("check", var)
            elif widget_type == "file":
                entry = ttk.Entry(main_frame, width=40)
                entry.grid(row=item["row"], column=1, sticky="ew", pady=2)
                self.widgets[name] = ("file", entry)
            elif widget_type == "folder":
                entry = ttk.Entry(main_frame, width=40)
                entry.grid(row=item["row"], column=1, sticky="ew", pady=2)
                self.widgets[name] = ("folder", entry)
            elif widget_type == "button":
                # place button at specified column (default 1)
                col = item.get("col", 1)
                action = item.get("action")
                target = item.get("target")
                btn = ttk.Button(main_frame, text=item.get("label", "Button"))
                btn.grid(row=item["row"], column=col, padx=5)
                # wire actions
                if action == "browse_file" and target:
                    # button should open file dialog and set target entry
                    def make_cmd(t=target):
                        def cmd():
                            entry_pair = self.widgets.get(t)
                            if entry_pair:
                                _, e = entry_pair
                                self.browse_file(e)
                        return cmd
                    btn.config(command=make_cmd())
                elif action == "browse_folder" and target:
                    def make_cmd2(t=target):
                        def cmd():
                            entry_pair = self.widgets.get(t)
                            if entry_pair:
                                _, e = entry_pair
                                self.browse_folder(e)
                        return cmd
                    btn.config(command=make_cmd2())
                elif action == "run":
                    btn.config(command=self.run_script)
                elif action == "stop":
                    btn.config(command=self.stop_script)
                elif action == "close":
                    btn.config(command=self.on_close)
                # store button if needed
                self.widgets[name] = ("button", btn)
    # previously the Run/Stop/Close were a fixed block; now they are defined via UI JSON

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
        close_pair = self.widgets.get("close")
        if close_pair:
            try:
                close_pair[1].config(state="disabled")
            except Exception:
                pass
        # disable run button to prevent re-entry
        run_pair = self.widgets.get("run")
        if run_pair:
            try:
                run_pair[1].config(state="disabled")
            except Exception:
                pass
        # clear stop flag for new run
        self._stop_requested = False
        # On Windows, create new process group to make termination more reliable
        popen_kwargs = dict(stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        if os.name == 'nt':
            popen_kwargs['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP
        self.process = subprocess.Popen(cmd, **popen_kwargs)

        def read_output():
            for line in self.process.stdout:
                # if stop was requested, stop printing further lines
                if getattr(self, '_stop_requested', False):
                    break
                self.output_text.insert(tk.END, line)
                self.output_text.see(tk.END)
            self.process = None
            # ensure close button is re-enabled
            close_pair = self.widgets.get("close")
            run_pair = self.widgets.get("run")
            if close_pair:
                try:
                    close_pair[1].config(state="normal")
                except Exception:
                    pass
            if run_pair:
                try:
                    run_pair[1].config(state="normal")
                except Exception:
                    pass

        threading.Thread(target=read_output, daemon=True).start()

    def stop_script(self):
        # indicate we want to stop printing further output
        self._stop_requested = True
        if self.process:
            try:
                self.process.terminate()
                try:
                    self.process.wait(timeout=2)
                except Exception:
                    # still alive -> force kill
                    try:
                        self.process.kill()
                        self.process.wait(timeout=2)
                    except Exception:
                        pass
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass
            finally:
                self.process = None
                self.output_text.insert(tk.END, "\nProcess terminated.\n")
                self.output_text.see(tk.END)
                close_pair = self.widgets.get("close")
                if close_pair:
                    try:
                        close_pair[1].config(state="normal")
                    except Exception:
                        pass
                run_pair = self.widgets.get("run")
                if run_pair:
                    try:
                        run_pair[1].config(state="normal")
                    except Exception:
                        pass

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
