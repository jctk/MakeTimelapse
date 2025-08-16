import json
import os
import subprocess
import threading
import signal
import re
import sys

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import tkinter.font as tkfont

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

        # helper to produce grid option dict from UI item with sensible defaults
        def grid_options(item, defaults=None):
            if defaults is None:
                defaults = {}
            opts = {}
            # required: row
            opts['row'] = item.get('row', defaults.get('row', 0))
            # column default may be supplied per-call
            if 'col' in item:
                opts['column'] = item['col']
            elif 'column' in item:
                opts['column'] = item['column']
            elif 'column' in defaults:
                opts['column'] = defaults['column']
            # columnspan/rowspan
            if 'columnspan' in item:
                opts['columnspan'] = item['columnspan']
            elif 'colspan' in item:
                opts['columnspan'] = item['colspan']
            elif 'columnspan' in defaults:
                opts['columnspan'] = defaults['columnspan']
            if 'rowspan' in item:
                opts['rowspan'] = item['rowspan']
            elif 'rowspan' in defaults:
                opts['rowspan'] = defaults['rowspan']
            # sticky/padx/pady
            if 'sticky' in item:
                opts['sticky'] = item['sticky']
            elif 'sticky' in defaults:
                opts['sticky'] = defaults['sticky']
            if 'padx' in item:
                opts['padx'] = item['padx']
            elif 'padx' in defaults:
                opts['padx'] = defaults['padx']
            if 'pady' in item:
                opts['pady'] = item['pady']
            elif 'pady' in defaults:
                opts['pady'] = defaults['pady']
            return opts

        for item in ui_layout.get("fields", []):
            widget_type = item["type"]
            name = item["name"]

            # render left-side label for normal fields (not heading labels, buttons, checkboxes, or frames)
            # checkboxes will render their own label to the right of the checkbox inside the same column
            if widget_type not in ("label", "button", "check", "frame"):
                left_lbl = ttk.Label(main_frame, text=item.get("label", ""))
                left_opts = grid_options(item, defaults={'column': 0, 'sticky': 'w', 'pady': 2})
                left_lbl.grid(**left_opts)

            if widget_type == "label":
                # If label text is empty, create a fixed-height spacer.
                label_text = item.get("label", "")
                if not label_text:
                    spacer_height = item.get("height", 10)
                    spacer = ttk.Frame(main_frame, height=spacer_height)
                    spacer_opts = grid_options(item, defaults={'column': 0, 'columnspan': 3, 'sticky': 'we', 'pady': 2})
                    spacer.grid(**spacer_opts)
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
                lbl_opts = grid_options(item, defaults={'column': 0, 'columnspan': 3, 'sticky': 'w', 'pady': 2})
                lbl.grid(**lbl_opts)
                # don't store as interactive widget
                continue

            if widget_type == "entry":
                entry = ttk.Entry(main_frame, width=item.get("width", 40))
                entry_opts = grid_options(item, defaults={'column': 1, 'sticky': 'w', 'pady': 2})
                entry.grid(**entry_opts)
                # store as (type, widget) so we can handle tkxui/tk compatibility
                self.widgets[name] = ("entry", entry)
            elif widget_type == "spinbox":
                spin = ttk.Spinbox(main_frame, from_=item["min"], to=item["max"], width=10)
                spin_opts = grid_options(item, defaults={'column': 1, 'sticky': 'w', 'pady': 2})
                spin.grid(**spin_opts)
                self.widgets[name] = ("spinbox", spin)
            elif widget_type == "check":
                var = tk.BooleanVar()
                # place checkbox in column 0 and set label via Checkbutton's text argument
                check = ttk.Checkbutton(main_frame, variable=var, text=item.get("label", ""))
                check_opts = grid_options(item, defaults={'column': 0, 'sticky': 'w', 'pady': 2})
                check.grid(**check_opts)
                self.widgets[name] = ("check", var)
            elif widget_type == "file":
                entry = ttk.Entry(main_frame, width=40)
                entry_opts = grid_options(item, defaults={'column': 1, 'sticky': 'ew', 'pady': 2})
                entry.grid(**entry_opts)
                self.widgets[name] = ("file", entry)
            elif widget_type == "folder":
                entry = ttk.Entry(main_frame, width=40)
                entry_opts = grid_options(item, defaults={'column': 1, 'sticky': 'ew', 'pady': 2})
                entry.grid(**entry_opts)
                self.widgets[name] = ("folder", entry)
            elif widget_type == "button":
                # place button either into a named parent frame (via pack) or at specified column (via grid)
                action = item.get("action")
                target = item.get("target")
                parent_name = item.get("parent")
                if parent_name:
                    parent_pair = self.widgets.get(parent_name)
                    if parent_pair and parent_pair[0] == "frame":
                        parent_widget = parent_pair[1]
                        btn = ttk.Button(parent_widget, text=item.get("label", "Button"))
                        # pack options: side and anchor are accepted from JSON
                        pack_side = item.get("pack_side", "left")
                        pack_anchor = item.get("pack_anchor", None)
                        pack_kwargs = {'side': pack_side}
                        if pack_anchor:
                            pack_kwargs['anchor'] = pack_anchor
                        if 'padx' in item:
                            pack_kwargs['padx'] = item.get('padx')
                        if 'pady' in item:
                            pack_kwargs['pady'] = item.get('pady')
                        btn.pack(**pack_kwargs)
                    else:
                        # fallback to grid on main_frame if parent not found
                        col = item.get("col", 1)
                        btn = ttk.Button(main_frame, text=item.get("label", "Button"))
                        btn_opts = grid_options(item, defaults={'column': col, 'pady': 0, 'padx': 5})
                        btn.grid(**btn_opts)
                else:
                    # place button at specified column (default 1)
                    col = item.get("col", 1)
                    btn = ttk.Button(main_frame, text=item.get("label", "Button"))
                    btn_opts = grid_options(item, defaults={'column': col, 'pady': 0, 'padx': 5})
                    btn.grid(**btn_opts)
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
            elif widget_type == "frame":
                # create a container frame that can be referenced by other widgets
                parent_name = item.get('parent')
                if parent_name:
                    parent_pair = self.widgets.get(parent_name)
                    if parent_pair and parent_pair[0] == 'frame':
                        parent_widget = parent_pair[1]
                        # apply fixed width/height only when provided
                        fw = item.get('fixed_width')
                        fh = item.get('fixed_height')
                        frame_kwargs = {}
                        if fw is not None:
                            frame_kwargs['width'] = fw
                        if fh is not None:
                            frame_kwargs['height'] = fh
                        frame = ttk.Frame(parent_widget, **frame_kwargs)
                        # pack into parent frame
                        pack_side = item.get('pack_side', None)
                        pack_anchor = item.get('pack_anchor', None)
                        pack_kwargs = {}
                        if 'padx' in item:
                            pack_kwargs['padx'] = item.get('padx')
                        if 'pady' in item:
                            pack_kwargs['pady'] = item.get('pady')

                        # Special-case: center the button_group by adding expanding spacers
                        if name == 'button_group':
                            # left spacer expands
                            left_spacer = ttk.Frame(parent_widget)
                            left_spacer.pack(side='left', expand=True)
                            # pack the group itself centered via anchor; use fixed width if provided
                            frame.pack(side='left', anchor='center', **pack_kwargs)
                            # if both width and height were provided, disable geometry propagation so frame keeps fixed size
                            if fw is not None and fh is not None:
                                try:
                                    frame.pack_propagate(False)
                                except Exception:
                                    pass
                            # right spacer expands
                            right_spacer = ttk.Frame(parent_widget)
                            right_spacer.pack(side='left', expand=True)
                        else:
                            if pack_side:
                                pack_kwargs['side'] = pack_side
                            if pack_anchor:
                                pack_kwargs['anchor'] = pack_anchor
                            frame.pack(**pack_kwargs)
                        self.widgets[name] = ('frame', frame)
                        continue
                # default: grid into main_frame
                frame = ttk.Frame(main_frame)
                frame_opts = grid_options(item, defaults={'column': 0, 'columnspan': 1, 'sticky': 'w', 'pady': 0})
                frame.grid(**frame_opts)
                self.widgets[name] = ("frame", frame)
        # previously the Run/Stop/Close were a fixed block; now they are defined via UI JSON

        # Output Text with vertical scrollbar
        text_frame = ttk.Frame(main_frame)
        # allow overriding the output text grid via a top-level key in UI JSON
        output_def = ui_layout.get('output') or {}
        text_opts = grid_options(output_def, defaults={'row': 101, 'column': 0, 'columnspan': 3, 'sticky': 'nsew', 'pady': 5})
        text_frame.grid(**text_opts)
        main_frame.rowconfigure(101, weight=1)
        # allow the three primary columns to expand so wide widgets/frames can center contents
        try:
            main_frame.columnconfigure(0, weight=1)
            main_frame.columnconfigure(1, weight=1)
            main_frame.columnconfigure(2, weight=1)
        except Exception:
            pass

        self.output_text = tk.Text(text_frame, height=15)
        self.output_text.pack(side="left", fill="both", expand=True)

        # Make output read-only to prevent user edits; all writes should go
        # through append_output so only command output is shown.
        try:
            self.output_text.config(state='disabled')
        except Exception:
            pass

        scrollbar = ttk.Scrollbar(text_frame, orient="vertical", command=self.output_text.yview)
        scrollbar.pack(side="right", fill="y")
        self.output_text.config(yscrollcommand=scrollbar.set)

        # Calculate and set minimum window size so that all widgets remain visible
        # while allowing the output text area to shrink to two lines.
        try:
            # Ensure layout sizes are up-to-date
            self.update_idletasks()

            # Requested size of the whole window
            req_w = self.winfo_reqwidth()
            req_h = self.winfo_reqheight()

            # Determine height of one text line (in pixels)
            try:
                text_font = tkfont.nametofont(self.output_text.cget("font"))
            except Exception:
                text_font = tkfont.Font()
            line_h = text_font.metrics("linespace") or 16

            # Current output widget height in lines (default set above)
            try:
                cur_lines = int(self.output_text.cget("height"))
            except Exception:
                cur_lines = 15

            # Compute minimal height when output shrinks to 2 lines
            shrink_pixels = max(0, (cur_lines - 2) * line_h)
            min_h = max(100, req_h - shrink_pixels)

            # Ensure a reasonable minimal width (at least the requested width)
            min_w = max(200, req_w)

            # Apply as window minimum size
            try:
                self.minsize(min_w, min_h)
            except Exception:
                # Some Tk platforms may not support minsize robustly; ignore if fails
                pass
        except Exception:
            pass

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

    def append_output(self, text):
        """Safely append text to the output widget from any thread.

        This schedules the actual insert on the Tk main thread and keeps the
        widget in disabled state so the user cannot type into it.
        """
        try:
            # enable, insert, then disable again
            self.output_text.config(state='normal')
            self.output_text.insert(tk.END, text)
            self.output_text.see(tk.END)
            self.output_text.config(state='disabled')
        except Exception:
            pass

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

        # clear output in a safe way
        try:
            self.output_text.config(state='normal')
            self.output_text.delete("1.0", tk.END)
            self.output_text.config(state='disabled')
        except Exception:
            pass
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
                # schedule append on main thread
                try:
                    self.output_text.after(0, lambda l=line: self.append_output(l))
                except Exception:
                    # fallback: try direct append
                    try:
                        self.append_output(line)
                    except Exception:
                        pass

            def _finalize_after_read():
                # mark process as finished and re-enable buttons
                self.process = None
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

            try:
                # schedule finalization on main thread
                self.output_text.after(0, _finalize_after_read)
            except Exception:
                _finalize_after_read()

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
                try:
                    # use append_output to keep widget disabled for user
                    try:
                        self.output_text.after(0, lambda: self.append_output("\nProcess terminated.\n"))
                    except Exception:
                        self.append_output("\nProcess terminated.\n")
                except Exception:
                    pass
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
