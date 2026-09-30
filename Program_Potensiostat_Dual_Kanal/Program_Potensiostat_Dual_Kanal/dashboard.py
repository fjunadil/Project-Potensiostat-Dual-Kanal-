from __future__ import annotations

import os
import queue
import csv
import json
import multiprocessing as mp
import socket
import subprocess
import threading
import time
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

from config import DEFAULT_CV_PARAMETERS, DEFAULT_METHOD_PARAMETERS, METHOD_LABELS, RAW_DATA_DIR, RODEOSTAT_PORT
from touchscreen_fix import apply_touchscreen_axis_swap


BG = "#f3f6f8"
PANEL = "#ffffff"
SURFACE = "#f7faf9"
BORDER = "#d7dee8"
TEXT = "#111827"
MUTED = "#5f6f7f"
PRIMARY = "#0b6b5f"
PRIMARY_DARK = "#07564d"
ACCENT = "#2f6fed"
SUCCESS = "#16803c"
WARNING = "#b7791f"
DANGER = "#b42318"
DANGER_DARK = "#8f1d14"
HEADER = "#0b1220"
HEADER_ACCENT = "#8ddbd0"
SOFT_TEAL = "#e7f6f3"
SOFT_BLUE = "#eaf2ff"
SOFT_RED = "#fff0ee"
LOG_BG = "#101827"
FONT = "Arial"
COMPACT_SCREEN_WIDTH = 640

PARAMETER_LABELS = {
    "currentRange": "current range uA",
    "sampleRate": "sample rate (Hz)",
    "quietTime": "quiet time (s)",
    "quietValue": "quiet value (V)",
    "startValue": "min value (V)",
    "vertex1Value": "max value (V)",
    "vertex2Value": "return value (V)",
    "stepValue": "step value (V)",
    "scanRate": "scan rate (V/s)",
    "numCycles": "cycles (#)",
    "amplitude": "amplitude (V)",
    "offset": "offset (V)",
    "period": "period (ms)",
    "shift": "shift",
    "finalValue": "final value (V)",
    "value": "value (V)",
    "duration": "duration (ms)",
    "window": "window",
    "step": "step ms:V",
}

CYCLE_OPTIONS = ("1", "3", "5", "10", "20", "35", "50")
CURRENT_RANGE_OPTIONS = ("1 uA", "10 uA", "100 uA", "1000 uA")


class QueueWriter:
    def __init__(self, log_queue: queue.Queue[str]) -> None:
        self.log_queue = log_queue

    def write(self, text: str) -> None:
        if text:
            self.log_queue.put(text)

    def flush(self) -> None:
        pass


class ProcessQueueWriter:
    def __init__(self, output_queue: mp.Queue) -> None:
        self.output_queue = output_queue

    def write(self, text: str) -> None:
        if text:
            self.output_queue.put(("log", text))

    def flush(self) -> None:
        pass


def measurement_process_entry(
    output_queue: mp.Queue,
    port: str,
    channels: tuple[int, ...],
    method: str,
    parameter_overrides: dict[str, object],
    measurement_info: dict[str, str],
) -> None:
    try:
        from multi_channel_cv import run_multi_channel_cv

        with redirect_stdout(ProcessQueueWriter(output_queue)):
            data_files, plot_file, analysis_file, info_file = run_multi_channel_cv(
                port=port,
                channels=channels,
                method=method,
                parameter_overrides=parameter_overrides,
                measurement_info=measurement_info,
                show_plot=False,
            )
        output_queue.put(
            (
                "done",
                {
                    "data_files": [str(path) for path in data_files],
                    "plot_file": str(plot_file),
                    "analysis_file": str(analysis_file),
                    "info_file": str(info_file),
                },
            )
        )
    except Exception as exc:
        output_queue.put(("error", str(exc)))


class PotentiostatDashboard:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Potentiostat")
        self.root.geometry("800x480")
        self.root.configure(bg=BG)
        self.root.option_add("*Font", f"{FONT} 10")
        self.root.attributes("-fullscreen", True)
        self.root.attributes("-topmost", True)
        self.root.bind("<Escape>", lambda _event: self.root.attributes("-fullscreen", False))
        self.root.bind("<Control-q>", lambda _event: self.root.destroy())
        self._configure_ttk_style()

        self.log_queue: queue.Queue[str] = queue.Queue()
        self.is_running = False
        self.cancel_requested = False
        self.measurement_process: mp.Process | None = None
        self.measurement_queue: mp.Queue | None = None

        self.port_var = tk.StringVar(value=RODEOSTAT_PORT)
        self.method_var = tk.StringVar(value="cv")
        self.method_display_var = tk.StringVar(value=METHOD_LABELS["cv"])
        self.channel1_var = tk.BooleanVar(value=True)
        self.channel2_var = tk.BooleanVar(value=True)
        self.preset_var = tk.StringVar(value="CV standar")
        self.status_var = tk.StringVar(value="Siap")
        self.result_var = tk.StringVar(value="-")
        self.ip_var = tk.StringVar(value="-")
        self.ip_badge_var = tk.StringVar(value="IP: -")
        self.wifi_var = tk.StringVar(value="-")
        self.potentiostat_var = tk.StringVar(value="Belum dicek")
        self.potentiostat_badge_var = tk.StringVar(value="POTENTIOSTAT: BELUM DICEK")
        self.pi_badge_var = tk.StringVar(value="PI: SIAP")
        self.data_badge_var = tk.StringVar(value="DATA: -")
        self.clock_var = tk.StringVar()
        self.summary_var = tk.StringVar(value="Belum ada hasil pengukuran.")
        self.advanced_var = tk.BooleanVar(value=False)
        self.wifi_ssid_var = tk.StringVar()
        self.wifi_password_var = tk.StringVar()
        self.param_vars: dict[str, tk.StringVar] = {}
        self.ip_badge_label: tk.Label | None = None
        self.potentiostat_badge_label: tk.Label | None = None
        self.potentiostat_value_label: tk.Label | None = None
        self.pi_badge_label: tk.Label | None = None
        self.data_badge_label: tk.Label | None = None
        self.stop_button: tk.Button | None = None
        self.start_button: tk.Canvas | None = None
        self.start_button_fill_id: int | None = None
        self.start_button_text_id: int | None = None
        self.progress_started_at: float | None = None
        self.progress_estimated_seconds: float = 1.0
        self.port_holder: tk.Frame | None = None
        self.param_holder: tk.Frame | None = None
        self.param_frame: tk.LabelFrame | None = None
        self.data_tree: ttk.Treeview | None = None
        self.data_scroll_canvas: tk.Canvas | None = None
        self.data_tree_scrollbar: tk.Scrollbar | None = None
        self.data_text_frame: tk.Frame | None = None
        self.data_preview: tk.Text | None = None
        self.data_image_label: tk.Label | None = None
        self.data_image_canvas: tk.Canvas | None = None
        self.data_preview_image: object | None = None
        self.fullscreen_image_window: tk.Toplevel | None = None
        self.fullscreen_image_ref: object | None = None
        self.data_files: list[Path] = []
        self.data_tree_paths: dict[str, Path] = {}

        self._build_layout()
        self._show_startup_splash()
        self._load_parameter_fields("cv")
        self.root.after(100, self._drain_log_queue)
        self.root.after(250, lambda: self.log_queue.put("GUI siap. Pilih channel lalu tekan Mulai.\n"))
        self.root.after(400, self.refresh_home_status)
        self.root.after(5000, self._auto_refresh_home_status)
        self._update_clock()

    def _configure_ttk_style(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TNotebook", background=BG, borderwidth=0, tabmargins=(4, 0, 4, 0))
        style.configure(
            "TNotebook.Tab",
            background="#e8eef5",
            foreground=TEXT,
            padding=(20, 9),
            font=(FONT, 10, "bold"),
            borderwidth=0,
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", PANEL), ("active", SOFT_BLUE)],
            foreground=[("selected", PRIMARY), ("active", TEXT)],
        )
        style.configure(
            "Treeview",
            background=PANEL,
            fieldbackground=PANEL,
            foreground=TEXT,
            rowheight=30,
            borderwidth=0,
            font=(FONT, 9),
        )
        style.configure(
            "Treeview.Heading",
            background="#edf2f7",
            foreground=TEXT,
            font=(FONT, 9, "bold"),
            relief="flat",
        )
        style.map("Treeview", background=[("selected", "#d8f3ee")], foreground=[("selected", TEXT)])

    def _build_layout(self) -> None:
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=8, pady=8)

        home = tk.Frame(self.notebook, bg=BG)
        measurement = tk.Frame(self.notebook, bg=BG)
        data = tk.Frame(self.notebook, bg=BG)
        status = tk.Frame(self.notebook, bg=BG)
        self.notebook.add(home, text="Home")
        self.notebook.add(measurement, text="Pengukuran")
        self.notebook.add(data, text="Data")
        self.notebook.add(status, text="Status")

        self._build_home(home)
        self._build_measurement(measurement)
        self._build_data_tab(data)
        self._build_status_tab(status)

    def _show_startup_splash(self) -> None:
        splash = tk.Toplevel(self.root)
        splash.configure(bg=HEADER)
        splash.attributes("-fullscreen", True)
        splash.attributes("-topmost", True)
        splash.overrideredirect(True)

        frame = tk.Frame(splash, bg=HEADER)
        frame.pack(fill="both", expand=True)
        tk.Label(
            frame,
            text="Potentiostat",
            bg=HEADER,
            fg="white",
            font=(FONT, 34, "bold"),
        ).place(relx=0.5, rely=0.48, anchor="center")
        tk.Frame(frame, bg=PRIMARY, height=4, width=170).place(relx=0.5, rely=0.58, anchor="center")
        splash.after(2200, splash.destroy)

    def _build_home(self, parent: tk.Frame) -> None:
        content = tk.Frame(parent, bg=BG)
        content.pack(fill="both", expand=True)

        left = tk.Frame(content, bg=PANEL, highlightthickness=1, highlightbackground=BORDER)
        left.pack(side="left", fill="both", expand=True, padx=(0, 8), pady=1)

        hero = tk.Frame(left, bg=PANEL)
        hero.pack(fill="x", padx=18, pady=(18, 10))
        title_block = tk.Frame(hero, bg=PANEL)
        title_block.pack(side="left", fill="x", expand=True)
        tk.Label(
            title_block,
            text="Potentiostat",
            bg=PANEL,
            fg=TEXT,
            font=(FONT, 22, "bold"),
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            title_block,
            textvariable=self.ip_var,
            bg=PANEL,
            fg=MUTED,
            font=(FONT, 9, "bold"),
            anchor="w",
        ).pack(fill="x", pady=(2, 0))
        tk.Label(
            hero,
            textvariable=self.clock_var,
            bg=PANEL,
            fg=PRIMARY_DARK,
            font=(FONT, 12, "bold"),
            anchor="e",
        ).pack(side="right", padx=(8, 0))

        divider = tk.Frame(left, bg=SOFT_TEAL, height=3)
        divider.pack(fill="x", padx=18, pady=(0, 14))

        menu = tk.Frame(left, bg=PANEL)
        menu.pack(fill="x", padx=18, pady=(0, 12))
        tk.Button(menu, text="Mulai Test", command=lambda: self.notebook.select(1), height=3, bg=PRIMARY, fg="white", activebackground=PRIMARY_DARK, activeforeground="white", relief="flat", font=(FONT, 13, "bold"), bd=0).pack(side="left", fill="x", expand=True, padx=(0, 8))
        tk.Button(menu, text="Data", command=self.show_data_tab, height=3, bg=SOFT_BLUE, fg="#1d4f91", activebackground="#d7e8ff", relief="flat", font=(FONT, 13, "bold"), bd=0).pack(side="left", fill="x", expand=True, padx=(0, 8))
        tk.Button(menu, text="Shutdown", command=self.shutdown_system, height=3, bg=SOFT_RED, fg=DANGER, activebackground="#ffe0dc", relief="flat", font=(FONT, 13, "bold"), bd=0).pack(side="left", fill="x", expand=True)

        tk.Frame(left, bg=PANEL).pack(fill="both", expand=True)

    def _build_status_tab(self, parent: tk.Frame) -> None:
        panel = tk.Frame(parent, bg=PANEL, highlightthickness=1, highlightbackground=BORDER)
        panel.pack(fill="both", expand=True, pady=1)

        tk.Label(panel, text="Status Sistem", bg=PANEL, fg=TEXT, font=(FONT, 16, "bold"), anchor="w").pack(fill="x", padx=18, pady=(16, 10))

        status_box = tk.LabelFrame(panel, text="Koneksi", bg=PANEL, fg=TEXT, padx=12, pady=10, font=(FONT, 10, "bold"), highlightbackground=BORDER)
        status_box.pack(fill="x", padx=18, pady=(0, 12))
        self._status_row(status_box, "IP Raspberry Pi", self.ip_var)
        self._status_row(status_box, "WiFi", self.wifi_var)
        self.potentiostat_value_label = self._status_row(status_box, "Koneksi Potentiostat", self.potentiostat_var)
        self._status_row(status_box, "Status Pengukuran", self.status_var)
        tk.Button(status_box, text="Refresh Status", command=self.refresh_home_status, height=2, bg=SOFT_TEAL, fg=PRIMARY_DARK, activebackground="#d7eee9", relief="flat", bd=0, font=(FONT, 10, "bold")).pack(fill="x", pady=(10, 0))

        info_box = tk.LabelFrame(panel, text="Ringkasan", bg=PANEL, fg=TEXT, padx=12, pady=10, font=(FONT, 10, "bold"), highlightbackground=BORDER)
        info_box.pack(fill="x", padx=18, pady=(0, 12))
        self._status_row(info_box, "Data", self.data_badge_var)
        self._status_row(info_box, "Pi", self.pi_badge_var)

        wifi_box = tk.LabelFrame(panel, text="WiFi", bg=PANEL, fg=TEXT, padx=12, pady=10, font=(FONT, 10, "bold"), highlightbackground=BORDER)
        wifi_box.pack(fill="x", padx=18, pady=(0, 12))
        self._entry(wifi_box, "Nama WiFi / SSID", self.wifi_ssid_var, in_frame=True)
        self._entry(wifi_box, "Password", self.wifi_password_var, in_frame=True, show="*")
        tk.Button(wifi_box, text="Hubungkan WiFi", command=self.connect_wifi, height=2, bg=PRIMARY, fg="white", activebackground=PRIMARY_DARK, activeforeground="white", relief="flat", bd=0, font=(FONT, 10, "bold")).pack(fill="x", pady=(6, 0))

    def _badge(self, parent: tk.Frame, variable: tk.StringVar, color: str, padx: tuple[int, int] = (0, 0)) -> tk.Label:
        label = tk.Label(
            parent,
            textvariable=variable,
            bg=color,
            fg="white",
            font=(FONT, 11, "bold"),
            padx=10,
            pady=10,
            anchor="center",
        )
        label.pack(side="left", fill="x", expand=True, padx=padx)
        return label

    def _status_row(self, parent: tk.Frame, label: str, variable: tk.StringVar) -> tk.Label:
        row = tk.Frame(parent, bg=PANEL)
        row.pack(fill="x", pady=4)
        tk.Label(row, text=label, bg=PANEL, fg=MUTED, width=19, anchor="w", font=(FONT, 9, "bold")).pack(side="left")
        value = tk.Label(row, textvariable=variable, bg=PANEL, fg=TEXT, anchor="w", wraplength=360, justify="left", font=(FONT, 9))
        value.pack(side="left", fill="x", expand=True)
        return value

    def _build_measurement(self, body: tk.Frame) -> None:
        if self.root.winfo_screenwidth() <= COMPACT_SCREEN_WIDTH:
            scroll_canvas = tk.Canvas(body, bg=BG, highlightthickness=0)
            scroll_canvas.pack(side="left", fill="both", expand=True)
            tab_scrollbar = tk.Scrollbar(body, orient="vertical", command=scroll_canvas.yview)
            tab_scrollbar.pack(side="right", fill="y")
            scroll_canvas.configure(yscrollcommand=tab_scrollbar.set)

            content = tk.Frame(scroll_canvas, bg=BG)
            content_id = scroll_canvas.create_window((0, 0), window=content, anchor="nw")
            content.bind("<Configure>", lambda _event: scroll_canvas.configure(scrollregion=scroll_canvas.bbox("all")))
            scroll_canvas.bind("<Configure>", lambda event: scroll_canvas.itemconfigure(content_id, width=event.width))

            controls = tk.Frame(content, bg=PANEL, highlightthickness=1, highlightbackground=BORDER)
            controls.pack(fill="x", pady=(1, 6))
            self._build_controls(controls)

            log_panel = tk.Frame(content, bg=PANEL, highlightthickness=1, highlightbackground=BORDER)
            log_panel.pack(fill="x", pady=(0, 1))
            self._build_log_panel(log_panel, compact=True)
            return

        left = tk.Frame(body, bg=PANEL, highlightthickness=1, highlightbackground=BORDER)
        left.configure(width=332)
        left.pack_propagate(False)
        left.pack(side="left", fill="y", padx=(0, 8), pady=1)

        right = tk.Frame(body, bg=PANEL, highlightthickness=1, highlightbackground=BORDER)
        right.pack(side="left", fill="both", expand=True, pady=1)

        canvas = tk.Canvas(left, bg=PANEL, width=308, highlightthickness=0)
        scrollbar = tk.Scrollbar(left, orient="vertical", command=canvas.yview)
        self.control_frame = tk.Frame(canvas, bg=PANEL)
        self.control_frame.bind(
            "<Configure>",
            lambda _event: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        control_id = canvas.create_window((0, 0), window=self.control_frame, anchor="nw")
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(control_id, width=event.width))
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="y", expand=True)
        scrollbar.pack(side="right", fill="y")

        self._build_controls(self.control_frame)
        self._build_log_panel(right)

    def _build_controls(self, parent: tk.Frame) -> None:
        tk.Label(parent, text="Pengukuran", bg=PANEL, fg=TEXT, font=(FONT, 16, "bold")).pack(anchor="w", padx=12, pady=(13, 8))

        self._step_label(parent, "1. Metode")
        method_box = tk.Frame(parent, bg=PANEL)
        method_box.pack(fill="x", padx=10, pady=(0, 6))
        method_menu = tk.OptionMenu(method_box, self.method_display_var, *METHOD_LABELS.values(), command=self._on_method_display_change)
        method_menu.configure(bg=SURFACE, fg=TEXT, activebackground="#e2e8f0", relief="flat", bd=0, highlightthickness=1, highlightbackground=BORDER)
        method_menu.pack(fill="x")

        preset_box = tk.LabelFrame(parent, text="Preset", bg=PANEL, fg=TEXT, padx=8, pady=7, font=(FONT, 10, "bold"))
        preset_box.pack(fill="x", padx=10, pady=(0, 8))
        for index, (text, preset) in enumerate((
            ("CV Standar", "cv_standard"),
            ("Aktivasi SPCE", "spce_activation"),
        )):
            row = index // 2
            column = index % 2
            tk.Button(
                preset_box,
                text=text,
                command=lambda name=preset: self.apply_preset(name),
                height=1,
                bg=SURFACE,
                fg=TEXT,
                activebackground=SOFT_BLUE,
                relief="flat",
                bd=0,
                font=(FONT, 9, "bold"),
            ).grid(row=row, column=column, sticky="ew", padx=(0 if column == 0 else 4, 4 if column == 0 else 0), pady=(0, 4))
        preset_box.grid_columnconfigure(0, weight=1)
        preset_box.grid_columnconfigure(1, weight=1)

        self._step_label(parent, "2. Channel")
        channel_box = tk.Frame(parent, bg=PANEL)
        channel_box.pack(fill="x", padx=10, pady=(0, 8))
        tk.Checkbutton(channel_box, text="Channel 1", variable=self.channel1_var, bg=PANEL, fg=TEXT, selectcolor=PANEL, activebackground=PANEL, anchor="w", font=(FONT, 10, "bold")).pack(side="left")
        tk.Checkbutton(channel_box, text="Channel 2", variable=self.channel2_var, bg=PANEL, fg=TEXT, selectcolor=PANEL, activebackground=PANEL, anchor="w", font=(FONT, 10, "bold")).pack(side="left", padx=(10, 0))

        tk.Checkbutton(parent, text="Advanced", variable=self.advanced_var, command=self._toggle_advanced, bg=PANEL, fg=TEXT, selectcolor=PANEL, activebackground=PANEL, anchor="w").pack(fill="x", padx=10, pady=(0, 4))
        self.port_holder = tk.Frame(parent, bg=PANEL)
        self._entry(self.port_holder, "Port", self.port_var, in_frame=True)
        self.param_holder = tk.Frame(parent, bg=PANEL)
        self.param_holder.pack(fill="x")
        self.param_frame = tk.LabelFrame(self.param_holder, text="Parameter", bg=PANEL, fg=TEXT, padx=8, pady=6, font=(FONT, 10, "bold"))

        self._step_label(parent, "4. Mulai")
        button_box = tk.Frame(parent, bg=PANEL)
        button_box.pack(fill="x", padx=10, pady=(4, 12))
        self.start_button = tk.Canvas(
            button_box,
            height=48,
            bg=PRIMARY,
            highlightthickness=0,
            bd=0,
        )
        self.start_button.pack(fill="x", pady=(0, 6))
        self.start_button.bind("<Button-1>", lambda _event: self.start_measurement())
        self.start_button.bind("<Configure>", lambda _event: self._draw_start_button_idle())
        self._draw_start_button_idle()
        self.stop_button = tk.Button(
            button_box,
            text="Stop",
            command=self.stop_measurement,
            bg="#6b7280",
            fg="white",
            activebackground="#4b5563",
            activeforeground="white",
            font=(FONT, 12, "bold"),
            relief="flat",
            bd=0,
            height=2,
            state="disabled",
        )
        self.stop_button.pack(fill="x", pady=(0, 6))
        tk.Button(button_box, text="Buka Data", command=self.show_data_tab, height=2, bg=SOFT_BLUE, fg="#1d4f91", activebackground="#d7e8ff", relief="flat", bd=0, font=(FONT, 10, "bold")).pack(fill="x")

    def _build_log_panel(self, parent: tk.Frame, compact: bool = False) -> None:
        top = tk.Frame(parent, bg=PANEL)
        top.pack(fill="x", padx=12, pady=(12, 6))
        tk.Label(top, text="Status", bg=PANEL, fg=MUTED, font=(FONT, 10, "bold")).pack(side="left")
        status_label = tk.Label(top, textvariable=self.status_var, bg=SOFT_TEAL, fg=PRIMARY_DARK, font=(FONT, 10, "bold"), padx=10, pady=4, justify="left")
        status_label.pack(side="left", fill="x", expand=True, padx=(8, 0))
        status_label.bind("<Configure>", lambda event: status_label.configure(wraplength=max(80, event.width - 20)))

        log_wrap = tk.Frame(parent, bg=PANEL)
        log_wrap.pack(fill="both", expand=True, padx=12, pady=4)
        self.log_text = tk.Text(log_wrap, wrap="word", bg=LOG_BG, fg="#e8edf3", insertbackground="white", relief="flat", bd=0, padx=11, pady=9, font=("Consolas", 9), height=7 if compact else 12)
        self.log_text.pack(side="left", fill="both", expand=True)
        scrollbar = tk.Scrollbar(log_wrap, command=self.log_text.yview)
        scrollbar.pack(side="right", fill="y")
        self.log_text.configure(yscrollcommand=scrollbar.set)

        tk.Label(parent, text="Hasil terakhir", bg=PANEL, fg=MUTED, font=(FONT, 10, "bold")).pack(anchor="w", padx=12, pady=(6, 0))
        result_label = tk.Label(parent, textvariable=self.result_var, bg=SURFACE, fg=TEXT, justify="left", anchor="w", padx=8, pady=6)
        result_label.pack(fill="x", padx=12, pady=(2, 8))
        result_label.bind("<Configure>", lambda event: result_label.configure(wraplength=max(80, event.width - 20)))
        tk.Label(parent, text="Ringkasan", bg=PANEL, fg=MUTED, font=(FONT, 10, "bold")).pack(anchor="w", padx=12, pady=(0, 0))
        summary_label = tk.Label(parent, textvariable=self.summary_var, bg=SOFT_TEAL, fg=TEXT, justify="left", anchor="w", padx=8, pady=6)
        summary_label.pack(fill="x", padx=12, pady=(2, 10))
        summary_label.bind("<Configure>", lambda event: summary_label.configure(wraplength=max(80, event.width - 20)))

    def _build_data_tab(self, parent: tk.Frame) -> None:
        scroll_canvas = tk.Canvas(parent, bg=BG, highlightthickness=0)
        scroll_canvas.pack(side="left", fill="both", expand=True)
        tab_scrollbar = tk.Scrollbar(parent, orient="vertical", command=scroll_canvas.yview)
        tab_scrollbar.pack(side="right", fill="y")
        scroll_canvas.configure(yscrollcommand=tab_scrollbar.set)
        self.data_scroll_canvas = scroll_canvas

        body = tk.Frame(scroll_canvas, bg=BG)
        body_id = scroll_canvas.create_window((0, 0), window=body, anchor="nw")
        body.bind("<Configure>", lambda _event: scroll_canvas.configure(scrollregion=scroll_canvas.bbox("all")))
        scroll_canvas.bind("<Configure>", lambda event: scroll_canvas.itemconfigure(body_id, width=event.width))

        list_panel = tk.Frame(body, bg=PANEL, highlightthickness=1, highlightbackground=BORDER)
        list_panel.pack(fill="x", padx=0, pady=(1, 6))

        preview_panel = tk.Frame(body, bg=PANEL, highlightthickness=1, highlightbackground=BORDER)
        preview_panel.pack(fill="both", expand=True, pady=(0, 1))

        top = tk.Frame(list_panel, bg=PANEL)
        top.pack(fill="x", padx=10, pady=(8, 5))
        tk.Label(top, text="Data Pengukuran", bg=PANEL, fg=TEXT, font=(FONT, 13, "bold")).pack(side="left")
        tk.Button(top, text="Refresh", command=lambda: self.refresh_data_files(select_latest_png=True), height=1, bg=SURFACE, fg=TEXT, activebackground="#e2e8f0", relief="flat", bd=0).pack(side="right")

        nav = tk.Frame(list_panel, bg=PANEL)
        nav.pack(fill="x", padx=8, pady=(0, 5))
        tk.Button(nav, text="File Atas", command=lambda: self._scroll_data_files(-3), height=2, bg=SURFACE, fg=TEXT, activebackground="#e2e8f0", relief="flat", bd=0, font=(FONT, 9, "bold")).pack(side="left", fill="x", expand=True, padx=(0, 4))
        tk.Button(nav, text="File Bawah", command=lambda: self._scroll_data_files(3), height=2, bg=SURFACE, fg=TEXT, activebackground="#e2e8f0", relief="flat", bd=0, font=(FONT, 9, "bold")).pack(side="left", fill="x", expand=True, padx=(0, 4))
        tk.Button(nav, text="Preview", command=self._scroll_data_to_preview, height=2, bg=SOFT_BLUE, fg="#1d4f91", activebackground="#d7e8ff", relief="flat", bd=0, font=(FONT, 9, "bold")).pack(side="left", fill="x", expand=True, padx=(0, 4))
        tk.Button(nav, text="Atas", command=self._scroll_data_to_top, height=2, bg=SOFT_TEAL, fg=PRIMARY_DARK, activebackground="#d7eee9", relief="flat", bd=0, font=(FONT, 9, "bold")).pack(side="left", fill="x", expand=True)

        columns = ("name", "type", "size", "time")
        table_wrap = tk.Frame(list_panel, bg=PANEL)
        table_wrap.pack(fill="x", padx=8, pady=(0, 6))
        self.data_tree = ttk.Treeview(table_wrap, columns=columns, show="headings", height=3)
        self.data_tree.heading("name", text="Nama File")
        self.data_tree.heading("type", text="Jenis")
        self.data_tree.heading("size", text="Ukuran")
        self.data_tree.heading("time", text="Waktu")
        self.data_tree.column("name", width=380, anchor="w")
        self.data_tree.column("type", width=60, anchor="center")
        self.data_tree.column("size", width=80, anchor="e")
        self.data_tree.column("time", width=105, anchor="center")
        self.data_tree.pack(side="left", fill="x", expand=True)
        self.data_tree.bind("<<TreeviewSelect>>", lambda _event: self._refresh_data_preview())
        self.data_tree.bind("<Double-1>", lambda _event: self.open_selected_data_file())

        self.data_tree_scrollbar = tk.Scrollbar(table_wrap, orient="vertical", command=self.data_tree.yview)
        self.data_tree_scrollbar.pack(side="right", fill="y")
        self.data_tree.configure(yscrollcommand=self.data_tree_scrollbar.set)

        preview_top = tk.Frame(preview_panel, bg=PANEL)
        preview_top.pack(fill="x", padx=8, pady=(6, 4))
        tk.Label(preview_top, text="Preview", bg=PANEL, fg=TEXT, font=(FONT, 13, "bold"), anchor="w").pack(side="left")
        tk.Button(preview_top, text="Buka File", command=self.open_selected_data_file, height=1, bg=PRIMARY, fg="white", activebackground=PRIMARY_DARK, activeforeground="white", relief="flat", bd=0).pack(side="right", padx=(6, 0))
        tk.Button(preview_top, text="Buka Folder", command=self.open_data_folder_external, height=1, bg=SURFACE, fg=TEXT, activebackground="#e2e8f0", relief="flat", bd=0).pack(side="right")
        tk.Button(preview_top, text="Lihat Besar", command=self.open_selected_png_fullscreen, height=1, bg=SUCCESS, fg="white", activebackground="#166534", activeforeground="white", relief="flat", bd=0).pack(side="right", padx=(6, 0))

        preview_body = tk.Frame(preview_panel, bg=PANEL)
        preview_body.pack(fill="both", expand=True, padx=8, pady=(0, 6))
        self.data_image_canvas = tk.Canvas(preview_body, bg="#ffffff", height=210, highlightthickness=1, highlightbackground=BORDER)
        self.data_image_canvas.pack(fill="both", expand=True)
        self.data_text_frame = tk.Frame(preview_body, bg=PANEL)
        self.data_preview = tk.Text(self.data_text_frame, wrap="word", height=6, bg=SURFACE, fg=TEXT, relief="flat", bd=0, padx=8, pady=6)
        text_scrollbar = tk.Scrollbar(self.data_text_frame, orient="vertical", command=self.data_preview.yview)
        self.data_preview.configure(yscrollcommand=text_scrollbar.set)
        self.data_preview.pack(side="left", fill="both", expand=True)
        text_scrollbar.pack(side="right", fill="y")
        self.data_text_frame.pack(fill="both", expand=True)

        self.refresh_data_files()

    def _label(self, parent: tk.Frame, text: str) -> None:
        tk.Label(parent, text=text, bg=PANEL, fg=MUTED, anchor="w", font=(FONT, 9, "bold")).pack(fill="x", padx=10, pady=(6, 2))

    def _step_label(self, parent: tk.Frame, text: str) -> None:
        tk.Label(parent, text=text, bg=PANEL, fg=PRIMARY_DARK, anchor="w", font=(FONT, 10, "bold")).pack(fill="x", padx=10, pady=(8, 4))

    def _entry(self, parent: tk.Frame, label: str, variable: tk.StringVar, in_frame: bool = False, show: str | None = None) -> None:
        pad_x = 0 if in_frame else 10
        self._label(parent, label) if not in_frame else tk.Label(parent, text=label, bg=PANEL, fg=MUTED, anchor="w", font=(FONT, 9, "bold")).pack(fill="x")
        tk.Entry(parent, textvariable=variable, bg=SURFACE, fg=TEXT, relief="flat", bd=0, highlightthickness=1, highlightbackground=BORDER, highlightcolor=PRIMARY, show=show, insertbackground=TEXT).pack(fill="x", padx=pad_x, pady=(0, 5), ipady=3)

    def _on_method_display_change(self, display_name: str) -> None:
        method = next((key for key, label in METHOD_LABELS.items() if label == display_name), "cv")
        self.method_var.set(method)
        self._load_parameter_fields(method)

    def _set_method(self, method: str) -> None:
        self.method_var.set(method)
        self.method_display_var.set(METHOD_LABELS.get(method, method))
        self._load_parameter_fields(method)

    def _load_parameter_fields(self, method: str) -> None:
        if self.param_frame is None:
            return
        for child in self.param_frame.winfo_children():
            child.destroy()

        defaults = DEFAULT_METHOD_PARAMETERS.get(method, DEFAULT_CV_PARAMETERS)
        self.param_vars = {}
        for key, value in defaults.items():
            variable = tk.StringVar(value=str(value))
            self.param_vars[key] = variable
            tk.Label(self.param_frame, text=PARAMETER_LABELS.get(key, key), bg=PANEL, fg=MUTED, anchor="w").pack(fill="x")
            if key in {"currentRange", "numCycles"}:
                options = CURRENT_RANGE_OPTIONS if key == "currentRange" else CYCLE_OPTIONS
                option_menu = tk.OptionMenu(self.param_frame, variable, *options)
                option_menu.configure(bg=SURFACE, fg=TEXT, activebackground="#e2e8f0", relief="flat", bd=0, highlightthickness=1, highlightbackground=BORDER)
                option_menu.pack(fill="x", pady=(0, 5))
            else:
                tk.Entry(self.param_frame, textvariable=variable, bg=SURFACE, fg=TEXT, relief="flat", bd=0, highlightthickness=1, highlightbackground=BORDER, highlightcolor=PRIMARY, insertbackground=TEXT).pack(fill="x", pady=(0, 5), ipady=3)
        self._toggle_advanced()

    def _toggle_advanced(self) -> None:
        if self.param_frame is None:
            return
        if self.advanced_var.get():
            if self.port_holder is not None:
                self.port_holder.pack(fill="x", padx=10, pady=(0, 6))
            self.param_frame.pack(fill="x", padx=10, pady=(4, 8))
        else:
            if self.port_holder is not None:
                self.port_holder.pack_forget()
            self.param_frame.pack_forget()

    def apply_preset(self, preset: str) -> None:
        self._set_method("cv")

        values_by_preset = {
            "spce_activation": {"quietTime": 10, "quietValue": 0.0, "startValue": 0.0, "vertex1Value": 1.0, "vertex2Value": 0.0, "stepValue": 0.01, "scanRate": 0.1, "numCycles": 10},
        }
        for key, value in values_by_preset.get(preset, {}).items():
            if key in self.param_vars:
                self.param_vars[key].set(str(value))

        self.preset_var.set({
            "cv_standard": "CV standar",
            "spce_activation": "Aktivasi SPCE",
        }.get(preset, ""))
        self.log_queue.put(f"Preset dipilih: {preset}\n")

    def selected_channels(self) -> tuple[int, ...]:
        channels = []
        if self.channel1_var.get():
            channels.append(1)
        if self.channel2_var.get():
            channels.append(2)
        return tuple(channels)

    def parameter_overrides(self) -> dict[str, object]:
        overrides: dict[str, object] = {}
        defaults = DEFAULT_METHOD_PARAMETERS.get(self.method_var.get(), DEFAULT_CV_PARAMETERS)
        for key, variable in self.param_vars.items():
            raw = variable.get().strip()
            default_value = defaults.get(key)
            try:
                if isinstance(default_value, int) and not isinstance(default_value, bool):
                    overrides[key] = int(float(raw))
                elif isinstance(default_value, float):
                    overrides[key] = float(raw)
                else:
                    overrides[key] = raw
            except ValueError:
                overrides[key] = raw
        return overrides

    def start_measurement(self) -> None:
        if self.is_running:
            return

        errors = self.validate_measurement_inputs()
        if errors:
            messagebox.showwarning("Parameter belum valid", "\n".join(errors))
            return

        channels = self.selected_channels()
        if not channels:
            messagebox.showwarning("Channel belum dipilih", "Pilih minimal satu channel.")
            return

        parameter_overrides = self.parameter_overrides()
        if not self._confirm_measurement_start(channels, parameter_overrides):
            return

        self.is_running = True
        self.cancel_requested = False
        self.progress_started_at = time.monotonic()
        self.progress_estimated_seconds = self._estimate_measurement_seconds(channels, parameter_overrides)
        self._draw_start_button_progress(0)
        if self.stop_button is not None:
            self.stop_button.configure(state="normal", bg=DANGER)
        self.status_var.set("Pengukuran berjalan...")
        self.result_var.set("-")
        self.summary_var.set("Pengukuran berjalan...")
        self.log_text.delete("1.0", "end")

        self.measurement_queue = mp.Queue()
        self.measurement_process = mp.Process(
            target=measurement_process_entry,
            args=(
                self.measurement_queue,
                self.port_var.get().strip() or RODEOSTAT_PORT,
                channels,
                self.method_var.get(),
                parameter_overrides,
                {"preset": self.preset_var.get()},
            ),
            daemon=True,
        )
        self.measurement_process.start()
        self.root.after(300, self._update_start_progress)
        self.root.after(100, self._poll_measurement_process)

    def _draw_start_button_idle(self) -> None:
        if self.start_button is None or self.is_running:
            return
        width = max(self.start_button.winfo_width(), 1)
        height = max(self.start_button.winfo_height(), 48)
        self.start_button.delete("all")
        self.start_button.configure(bg=PRIMARY, cursor="hand2")
        self.start_button.create_rectangle(0, 0, width, height, fill=PRIMARY, outline=PRIMARY)
        self.start_button.create_text(width / 2, height / 2, text="Mulai", fill="white", font=(FONT, 12, "bold"))

    def _draw_start_button_progress(self, percent: float) -> None:
        if self.start_button is None:
            return
        width = max(self.start_button.winfo_width(), 1)
        height = max(self.start_button.winfo_height(), 48)
        bounded = max(0, min(100, percent))
        fill_width = int(width * bounded / 100)
        self.start_button.delete("all")
        self.start_button.configure(bg="#d1fae5", cursor="")
        self.start_button.create_rectangle(0, 0, width, height, fill="#d1fae5", outline="#d1fae5")
        self.start_button.create_rectangle(0, 0, fill_width, height, fill=SUCCESS, outline=SUCCESS)
        self.start_button.create_text(
            width / 2,
            height / 2,
            text=f"{int(round(bounded))}%",
            fill="white" if bounded >= 45 else PRIMARY_DARK,
            font=(FONT, 12, "bold"),
        )

    def _update_start_progress(self) -> None:
        if not self.is_running or self.progress_started_at is None:
            return
        elapsed = time.monotonic() - self.progress_started_at
        percent = min(99, (elapsed / max(self.progress_estimated_seconds, 1.0)) * 100)
        self._draw_start_button_progress(percent)
        self.root.after(500, self._update_start_progress)

    def _estimate_measurement_seconds(self, channels: tuple[int, ...], parameters: dict[str, object]) -> float:
        method = self.method_var.get()
        if method != "cv":
            duration = parameters.get("duration")
            if duration is not None:
                try:
                    return max(1.0, (float(duration) / 1000) * len(channels))
                except (TypeError, ValueError):
                    pass
            return max(10.0, 15.0 * len(channels))
        try:
            start_value = float(parameters.get("startValue", DEFAULT_CV_PARAMETERS["startValue"]))
            vertex_value = float(parameters.get("vertex1Value", DEFAULT_CV_PARAMETERS["vertex1Value"]))
            scan_rate = float(parameters.get("scanRate", DEFAULT_CV_PARAMETERS["scanRate"]))
            cycles = int(float(parameters.get("numCycles", DEFAULT_CV_PARAMETERS["numCycles"])))
            quiet_time = float(parameters.get("quietTime", DEFAULT_CV_PARAMETERS["quietTime"]))
        except (TypeError, ValueError):
            return max(10.0, 15.0 * len(channels))
        amplitude = abs(vertex_value - start_value) / 2
        if amplitude <= 0 or scan_rate <= 0:
            return max(10.0, 15.0 * len(channels))
        seconds_per_cycle = 4 * amplitude / scan_rate
        seconds_per_channel = quiet_time + (seconds_per_cycle * cycles)
        return max(1.0, seconds_per_channel * len(channels))

    def _confirm_measurement_start(self, channels: tuple[int, ...], parameters: dict[str, object]) -> bool:
        return messagebox.askyesno("Mulai pengukuran?", "Mulai pengukuran sekarang?")

    def stop_measurement(self) -> None:
        if not self.is_running:
            return
        self.cancel_requested = True
        self.status_var.set("Dibatalkan")
        self.log_queue.put("Stop ditekan. Proses pengukuran dihentikan.\n")
        if self.measurement_process is not None and self.measurement_process.is_alive():
            self.measurement_process.terminate()
            self.measurement_process.join(timeout=2)
            if self.measurement_process.is_alive():
                self.measurement_process.kill()
                self.measurement_process.join(timeout=2)
        self._finish_measurement(
            "Dibatalkan",
            "Pengukuran dibatalkan oleh operator.",
            "Tidak ada ringkasan baru karena pengukuran dihentikan.",
            failed=True,
        )
        if self.stop_button is not None:
            self.stop_button.configure(state="disabled", bg="#6b7280")

    def validate_measurement_inputs(self) -> list[str]:
        errors: list[str] = []
        if not (self.port_var.get().strip() or RODEOSTAT_PORT):
            errors.append("Port Rodeostat tidak boleh kosong.")
        if not self.selected_channels():
            errors.append("Pilih minimal satu channel.")

        defaults = DEFAULT_METHOD_PARAMETERS.get(self.method_var.get(), DEFAULT_CV_PARAMETERS)
        for key, default_value in defaults.items():
            raw = self.param_vars.get(key, tk.StringVar(value="")).get().strip()
            if isinstance(default_value, (int, float)):
                try:
                    value = float(raw)
                except ValueError:
                    errors.append(f"Parameter {key} harus angka.")
                    continue
                if key in {"sampleRate", "stepValue", "scanRate", "duration", "period"} and value <= 0:
                    errors.append(f"Parameter {key} harus lebih besar dari 0.")
                if key == "numCycles" and int(value) <= 0:
                    errors.append("Parameter cycles (#) harus lebih besar dari 0.")
                if key == "quietTime" and value < 0:
                    errors.append("Parameter quietTime tidak boleh negatif.")
            elif key == "step" and not raw:
                errors.append("Parameter step tidak boleh kosong.")
        return errors

    def _poll_measurement_process(self) -> None:
        if self.measurement_queue is None or self.measurement_process is None:
            return

        finished = False
        while True:
            try:
                kind, payload = self.measurement_queue.get_nowait()
            except queue.Empty:
                break
            if kind == "log":
                self.log_queue.put(str(payload))
            elif kind == "done":
                result = (
                    "Data: "
                    + ", ".join(payload["data_files"])
                    + f"\nPlot: {payload['plot_file']}\nAnalisis: {payload['analysis_file']}"
                )
                summary = self._build_measurement_summary(Path(payload["analysis_file"]))
                self.log_queue.put(f"\nSelesai.\n{result}\n")
                self._finish_measurement(
                    "Selesai",
                    result,
                    summary,
                    failed=False,
                    preferred_data_path=Path(payload["plot_file"]),
                    analysis_path=Path(payload["analysis_file"]),
                )
                finished = True
            elif kind == "error":
                self.log_queue.put(f"\nERROR: {payload}\n")
                self._finish_measurement("Gagal", str(payload), "Pengukuran gagal. Cek log proses.", failed=True)
                finished = True

        if finished:
            return

        if not self.measurement_process.is_alive():
            exit_code = self.measurement_process.exitcode
            if exit_code not in (0, None):
                self._finish_measurement(
                    "Gagal" if not self.cancel_requested else "Dibatalkan",
                    f"Proses pengukuran berhenti dengan kode {exit_code}.",
                    "Tidak ada ringkasan baru.",
                    failed=True,
                )
            return

        self.root.after(100, self._poll_measurement_process)

    def _finish_measurement(
        self,
        status: str,
        result: str,
        summary: str,
        failed: bool,
        preferred_data_path: Path | None = None,
        analysis_path: Path | None = None,
    ) -> None:
        self.is_running = False
        self.measurement_process = None
        self.measurement_queue = None
        self.status_var.set(status)
        self.result_var.set(result)
        self.summary_var.set(summary)
        self._draw_start_button_progress(100)
        self.root.after(700, self._draw_start_button_idle)
        if self.stop_button is not None:
            self.stop_button.configure(state="disabled", bg="#6b7280")
        self.refresh_home_status()
        self.refresh_data_files(preferred_data_path=preferred_data_path)
        if not failed and preferred_data_path is not None:
            self._show_measurement_done_dialog(preferred_data_path, analysis_path)

    def _build_measurement_summary(self, analysis_file: Path) -> str:
        try:
            with analysis_file.open("r", newline="", encoding="utf-8") as csv_file:
                rows = list(csv.DictReader(csv_file))
        except Exception as exc:
            return f"Analisis tersimpan, tetapi ringkasan gagal dibaca: {exc}"
        if not rows:
            return "Analisis tersimpan, tetapi tidak ada baris ringkasan."
        lines = []
        for row in rows:
            channel = row.get("channel", "?")
            oxidation_current = row.get("max_current", "-")
            oxidation_potential = row.get("max_current_potential", "-")
            reduction_current = row.get("min_current", "-")
            reduction_potential = row.get("min_current_potential", "-")
            points = row.get("points", "-")
            lines.append(
                f"Ch {channel}: Oksidasi {oxidation_current} µA @ {oxidation_potential} V\n"
                f"Ch {channel}: Reduksi {reduction_current} µA @ {reduction_potential} V ({points} titik)"
            )
        return "\n".join(lines)

    def _show_measurement_done_dialog(self, plot_path: Path, analysis_path: Path | None) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title("Selesai")
        dialog.configure(bg=PANEL)
        dialog.transient(self.root)
        dialog.attributes("-topmost", True)
        dialog.resizable(False, False)
        self._center_window(dialog, 320, 168)

        tk.Label(dialog, text="Pengukuran selesai", bg=PANEL, fg=TEXT, font=(FONT, 14, "bold")).pack(fill="x", padx=14, pady=(12, 8))

        def view_plot() -> None:
            dialog.destroy()
            self.refresh_data_files(preferred_data_path=plot_path)
            self.notebook.select(2)
            self._open_png_fullscreen(plot_path)

        def view_analysis() -> None:
            dialog.destroy()
            self.refresh_data_files(preferred_data_path=analysis_path)
            self.notebook.select(2)

        def test_again() -> None:
            dialog.destroy()
            self.notebook.select(1)

        tk.Button(dialog, text="Lihat Grafik", command=view_plot, bg=PRIMARY, fg="white", activebackground=PRIMARY_DARK, activeforeground="white", relief="flat", bd=0, height=1, font=(FONT, 10, "bold")).pack(fill="x", padx=14, pady=(0, 6))
        tk.Button(dialog, text="Lihat Analisis", command=view_analysis, bg=SOFT_BLUE, fg="#1d4f91", activebackground="#d7e8ff", relief="flat", bd=0, height=1, font=(FONT, 10, "bold")).pack(fill="x", padx=14, pady=(0, 6))
        tk.Button(dialog, text="Test Lagi", command=test_again, bg=SURFACE, fg=TEXT, activebackground="#e2e8f0", relief="flat", bd=0, height=1).pack(fill="x", padx=14)

    def _center_window(self, window: tk.Toplevel, width: int, height: int) -> None:
        self.root.update_idletasks()
        root_x = self.root.winfo_rootx()
        root_y = self.root.winfo_rooty()
        root_width = max(self.root.winfo_width(), self.root.winfo_screenwidth())
        root_height = max(self.root.winfo_height(), self.root.winfo_screenheight())
        x = root_x + max(0, (root_width - width) // 2)
        y = root_y + max(0, (root_height - height) // 2)
        window.geometry(f"{width}x{height}+{x}+{y}")

    def _drain_log_queue(self) -> None:
        while True:
            try:
                text = self.log_queue.get_nowait()
            except queue.Empty:
                break
            self.log_text.insert("end", text)
            self.log_text.see("end")
        self.root.after(100, self._drain_log_queue)

    def show_data_tab(self) -> None:
        self.refresh_data_files(select_latest_png=True)
        self.notebook.select(2)
        self._scroll_data_to_top()

    def _scroll_data_files(self, amount: int) -> None:
        if self.data_tree is not None:
            self.data_tree.yview_scroll(amount, "units")

    def _scroll_data_to_preview(self) -> None:
        if self.data_scroll_canvas is not None:
            self.data_scroll_canvas.yview_moveto(0.45)

    def _scroll_data_to_top(self) -> None:
        if self.data_scroll_canvas is not None:
            self.data_scroll_canvas.yview_moveto(0.0)

    def open_data_folder_external(self) -> None:
        folder = RAW_DATA_DIR.resolve()
        folder.mkdir(parents=True, exist_ok=True)
        self._open_path(folder)

    def open_selected_data_file(self) -> None:
        path = self._selected_data_path()
        if path is None:
            messagebox.showinfo("Data", "Pilih file data terlebih dahulu.")
            return
        if path.suffix.lower() == ".png":
            self._open_png_fullscreen(path)
            return
        self._open_path(path)

    def open_selected_png_fullscreen(self) -> None:
        path = self._selected_data_path()
        if path is None:
            messagebox.showinfo("Plot", "Pilih file PNG terlebih dahulu.")
            return
        if path.suffix.lower() != ".png":
            messagebox.showinfo("Plot", "Lihat besar hanya untuk file PNG.")
            return
        self._open_png_fullscreen(path)

    def _open_path(self, path: Path) -> None:
        try:
            if os.name == "nt":
                os.startfile(path)
            else:
                opener = shutil_which("xdg-open") or shutil_which("gio") or shutil_which("pcmanfm")
                if opener is None:
                    raise RuntimeError("Aplikasi pembuka file tidak tersedia")
                if Path(opener).name == "gio":
                    subprocess.Popen([opener, "open", str(path)])
                else:
                    subprocess.Popen([opener, str(path)])
            self.log_queue.put(f"Membuka: {path}\n")
        except Exception as exc:
            self.log_queue.put(f"Gagal membuka {path}: {exc}\n")
            messagebox.showerror("Buka data gagal", f"Tidak bisa membuka:\n{path}\n\n{exc}")

    def refresh_data_files(self, preferred_data_path: Path | None = None, select_latest_png: bool = False) -> None:
        RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.data_files = self._list_data_files()
        self.data_badge_var.set(f"DATA: {len(self.data_files)} FILE")

        if self.data_tree is None:
            return
        selected_path = preferred_data_path or self._selected_data_path()
        if selected_path is None and select_latest_png:
            selected_path = next((path for path in self.data_files if path.suffix.lower() == ".png"), None)
        self.data_tree.delete(*self.data_tree.get_children())
        self.data_tree_paths = {}

        index = 0
        for title, paths in self._group_data_files(self.data_files):
            first = paths[0]
            parent_id = f"group-{index}"
            self.data_tree.insert(
                "",
                "end",
                iid=parent_id,
                values=(title, "SET", f"{len(paths)} file", self._format_mtime(first.stat().st_mtime)),
            )
            index += 1
            for path in paths:
                item_id = f"file-{index}"
                self.data_tree_paths[item_id] = path
                stat = path.stat()
                self.data_tree.insert(
                    "",
                    "end",
                    iid=item_id,
                    values=(
                        f"  {path.name}",
                        path.suffix.upper().lstrip(".") or "FILE",
                        self._format_file_size(stat.st_size),
                        self._format_mtime(stat.st_mtime),
                    ),
                )
                index += 1

        if selected_path is not None:
            selected_item = next((item_id for item_id, path in self.data_tree_paths.items() if path == selected_path), None)
            if selected_item is not None:
                self.data_tree.selection_set(selected_item)
                self.data_tree.focus(selected_item)
                self.data_tree.see(selected_item)
        self._refresh_data_preview()

    def _group_data_files(self, files: list[Path]) -> list[tuple[str, list[Path]]]:
        used: set[Path] = set()
        groups: list[tuple[str, list[Path]]] = []
        for info_file in [path for path in files if path.name.endswith("_info.json")]:
            related = [info_file]
            title = info_file.stem.replace("_info", "")
            try:
                measurement_info = json.loads(info_file.read_text(encoding="utf-8"))
                title = f"{measurement_info.get('method', '').upper()} {measurement_info.get('timestamp', title)}".strip()
                for key in ("plot_file", "analysis_file"):
                    value = measurement_info.get(key)
                    if value:
                        related.append(Path(value))
                for value in measurement_info.get("data_files", []):
                    related.append(Path(value))
            except Exception:
                pass

            existing: list[Path] = []
            for path in related:
                resolved = path if path.is_absolute() else RAW_DATA_DIR / path.name
                if resolved.exists() and resolved not in existing:
                    existing.append(resolved)
                    used.add(resolved)
            if existing:
                groups.append((title, sorted(existing, key=lambda item: item.stat().st_mtime, reverse=True)))

        for path in files:
            if path not in used:
                groups.append((path.stem, [path]))
        return groups

    def _list_data_files(self) -> list[Path]:
        patterns = ("*.txt", "*.csv", "*.json", "*.png")
        files: list[Path] = []
        for pattern in patterns:
            files.extend(RAW_DATA_DIR.glob(pattern))
        files = [path for path in files if not path.name.startswith(".plot_")]
        return sorted(files, key=lambda item: item.stat().st_mtime, reverse=True)

    def _update_data_badge(self) -> None:
        RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.data_badge_var.set(f"DATA: {len(self._list_data_files())} FILE")

    def _selected_data_path(self) -> Path | None:
        if self.data_tree is None:
            return None
        selection = self.data_tree.selection()
        if not selection:
            return None
        return self.data_tree_paths.get(selection[0])

    def _refresh_data_preview(self) -> None:
        if self.data_preview is None:
            return
        self.data_preview.configure(state="normal")
        self.data_preview.delete("1.0", "end")

        path = self._selected_data_path()
        if path is None:
            self._show_text_preview()
            self.data_preview.insert("end", "Belum ada file data.")
            self._clear_png_preview()
        elif path.suffix.lower() == ".png":
            self._show_image_preview()
            self._show_png_preview(path)
            self.data_preview.insert("end", f"Plot PNG:\n{path.name}\n\nTekan Lihat Besar untuk fullscreen.")
            if self.data_scroll_canvas is not None:
                self.root.after(100, self._scroll_data_to_preview)
        else:
            self._show_text_preview()
            self._clear_png_preview()
            try:
                with path.open("r", encoding="utf-8", errors="replace") as data_file:
                    lines = []
                    for line_number, line in enumerate(data_file, start=1):
                        if line_number > 80:
                            lines.append("\n... preview dipotong ...\n")
                            break
                        lines.append(line)
                self.data_preview.insert("end", "".join(lines) or "File kosong.")
            except Exception as exc:
                self.data_preview.insert("end", f"Gagal membaca preview:\n{exc}")
        self.data_preview.configure(state="disabled")

    def _show_image_preview(self) -> None:
        if self.data_text_frame is not None:
            self.data_text_frame.pack_forget()
        if self.data_image_canvas is not None:
            self.data_image_canvas.pack(fill="both", expand=True)

    def _show_text_preview(self) -> None:
        if self.data_image_canvas is not None:
            self.data_image_canvas.pack_forget()
        if self.data_text_frame is not None:
            self.data_text_frame.pack(fill="both", expand=True)

    def _clear_png_preview(self) -> None:
        self.data_preview_image = None
        if self.data_image_canvas is not None:
            self.data_image_canvas.delete("all")
            self.data_image_canvas.update_idletasks()
            width = max(self.data_image_canvas.winfo_width(), 560)
            height = max(self.data_image_canvas.winfo_height(), 185)
            self.data_image_canvas.create_text(
                width // 2,
                height // 2,
                text="Preview plot akan tampil di sini",
                fill=MUTED,
                font=("Arial", 10),
            )

    def _show_png_preview(self, path: Path) -> None:
        if self.data_image_canvas is None:
            return
        self.data_image_canvas.delete("all")
        self.data_image_canvas.update_idletasks()
        canvas_width = max(self.data_image_canvas.winfo_width(), 560)
        canvas_height = max(self.data_image_canvas.winfo_height(), 185)
        max_width = max(canvas_width - 20, 120)
        max_height = max(canvas_height - 20, 80)
        try:
            image_path = self._resized_png_cache(path, int(max_width), int(max_height), ".plot_preview.png")
            image = tk.PhotoImage(file=str(image_path), master=self.root)
            self.data_preview_image = image
            self.data_image_canvas.create_image(canvas_width // 2, canvas_height // 2, image=image, anchor="center")
        except Exception as exc:
            self.data_preview_image = None
            self.data_image_canvas.create_text(
                canvas_width // 2,
                canvas_height // 2,
                text=f"Preview gambar gagal:\n{exc}",
                fill=DANGER,
                font=("Arial", 9),
                width=max_width,
            )
            if self.data_preview is not None:
                self.data_preview.insert("end", f"\nPreview gambar gagal: {exc}")

    def _open_png_fullscreen(self, path: Path) -> None:
        if self.fullscreen_image_window is not None and self.fullscreen_image_window.winfo_exists():
            self.fullscreen_image_window.destroy()

        window = tk.Toplevel(self.root)
        self.fullscreen_image_window = window
        window.title(path.name)
        window.configure(bg="#000000")
        window.attributes("-fullscreen", True)
        window.attributes("-topmost", True)
        window.bind("<Escape>", lambda _event: self.close_fullscreen_image())
        window.bind("<Button-3>", lambda _event: self.close_fullscreen_image())

        close_button = tk.Button(
            window,
            text="Close",
            command=self.close_fullscreen_image,
            bg=DANGER,
            fg="white",
            activebackground="#991b1b",
            activeforeground="white",
            relief="flat",
            font=("Arial", 16, "bold"),
            height=1,
        )
        close_button.pack(fill="x")

        canvas = tk.Canvas(window, bg="#000000", highlightthickness=0)
        canvas.pack(fill="both", expand=True)
        window.update_idletasks()

        try:
            width = max(canvas.winfo_width(), self.root.winfo_screenwidth())
            height = max(canvas.winfo_height(), self.root.winfo_screenheight() - close_button.winfo_height())
            image_path = self._resized_png_cache(path, int(width), int(height), ".plot_fullscreen.png")
            photo = tk.PhotoImage(file=str(image_path), master=window)
            self.fullscreen_image_ref = photo
            canvas.create_image(width // 2, height // 2, image=photo, anchor="center")
        except Exception as exc:
            self.fullscreen_image_ref = None
            canvas.create_text(
                self.root.winfo_screenwidth() // 2,
                self.root.winfo_screenheight() // 2,
                text=f"Gagal membuka plot:\n{exc}",
                fill="white",
                font=("Arial", 14, "bold"),
                width=max(self.root.winfo_screenwidth() - 40, 200),
            )

    def close_fullscreen_image(self) -> None:
        if self.fullscreen_image_window is not None and self.fullscreen_image_window.winfo_exists():
            self.fullscreen_image_window.destroy()
        self.fullscreen_image_window = None
        self.fullscreen_image_ref = None

    def _resized_png_cache(self, path: Path, max_width: int, max_height: int, filename: str) -> Path:
        try:
            from PIL import Image
        except Exception:
            return path

        cache_path = RAW_DATA_DIR / filename
        image = Image.open(path).convert("RGBA")
        image.thumbnail((max_width, max_height))
        image.save(cache_path, format="PNG")
        return cache_path

    def _format_file_size(self, size: int) -> str:
        if size < 1024:
            return f"{size} B"
        if size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        return f"{size / (1024 * 1024):.1f} MB"

    def _format_mtime(self, timestamp: float) -> str:
        return datetime.fromtimestamp(timestamp).strftime("%d/%m %H:%M")

    def _update_clock(self) -> None:
        self.clock_var.set(datetime.now().strftime("%d/%m/%Y %H:%M:%S"))
        self.root.after(1000, self._update_clock)

    def refresh_home_status(self) -> None:
        ip_status = self._get_ip_address()
        self.ip_var.set(ip_status)
        self.ip_badge_var.set(f"IP: {ip_status}")
        self.wifi_var.set(self._get_wifi_status())
        potentiostat_status = self._get_potentiostat_status()
        self.potentiostat_var.set(potentiostat_status)
        self._update_potentiostat_indicator(potentiostat_status)
        self.pi_badge_var.set("PI: SIAP")
        if self.pi_badge_label is not None:
            self.pi_badge_label.configure(bg="#15803d")
        self._update_data_badge()

    def _auto_refresh_home_status(self) -> None:
        self.refresh_home_status()
        self.root.after(5000, self._auto_refresh_home_status)

    def _update_potentiostat_indicator(self, status: str) -> None:
        connected = status.startswith("Terhubung")
        self.potentiostat_badge_var.set(
            f"POTENTIOSTAT: {'TERHUBUNG' if connected else 'TIDAK TERHUBUNG'}"
        )
        color = "#15803d" if connected else DANGER
        if self.potentiostat_badge_label is not None:
            self.potentiostat_badge_label.configure(bg=color)
        if self.potentiostat_value_label is not None:
            self.potentiostat_value_label.configure(fg=color)

    def _get_ip_address(self) -> str:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.connect(("8.8.8.8", 80))
                return sock.getsockname()[0]
        except Exception:
            return "Belum terhubung jaringan"

    def _get_wifi_status(self) -> str:
        if os.name == "nt":
            return "Status WiFi hanya dicek otomatis di Raspberry Pi"
        if not shutil_which("nmcli"):
            return "nmcli tidak tersedia"
        try:
            result = subprocess.run(
                ["nmcli", "-t", "-f", "ACTIVE,SSID", "dev", "wifi"],
                text=True,
                capture_output=True,
                check=False,
                timeout=5,
            )
        except Exception as exc:
            return f"Gagal cek WiFi: {exc}"
        for line in result.stdout.splitlines():
            active, _, ssid = line.partition(":")
            if active == "yes":
                return f"Terhubung ke {ssid or '(SSID tersembunyi)'}"
        return "Belum terhubung WiFi"

    def _get_potentiostat_status(self) -> str:
        port = self.port_var.get().strip() or RODEOSTAT_PORT
        if os.name != "nt" and not Path(port).exists():
            return f"Tidak terdeteksi di {port}"
        if self.is_running:
            return f"Sedang digunakan untuk pengukuran di {port}"
        return f"Terhubung ke potentiostat di {port}"

    def connect_wifi(self) -> None:
        ssid = self.wifi_ssid_var.get().strip()
        password = self.wifi_password_var.get()
        if not ssid:
            messagebox.showwarning("SSID kosong", "Masukkan nama WiFi/SSID.")
            return
        if not shutil_which("nmcli"):
            messagebox.showerror("nmcli tidak tersedia", "NetworkManager/nmcli belum tersedia pada sistem ini.")
            return

        self.wifi_var.set("Menghubungkan WiFi...")
        threading.Thread(target=self._connect_wifi_worker, args=(ssid, password), daemon=True).start()

    def _connect_wifi_worker(self, ssid: str, password: str) -> None:
        command = ["nmcli", "dev", "wifi", "connect", ssid]
        if password:
            command.extend(["password", password])
        result = subprocess.run(command, text=True, capture_output=True, check=False, timeout=30)
        if result.returncode == 0:
            self.log_queue.put(f"WiFi terhubung: {ssid}\n")
        else:
            message = result.stderr.strip() or result.stdout.strip() or "Gagal menghubungkan WiFi"
            self.log_queue.put(f"WiFi gagal: {message}\n")
        self.root.after(0, self.refresh_home_status)

    def shutdown_system(self) -> None:
        if not messagebox.askyesno("Shutdown", "Matikan Raspberry Pi sekarang?"):
            return
        if os.name == "nt":
            messagebox.showinfo("Shutdown", "Tombol shutdown ini ditujukan untuk Raspberry Pi.")
            return

        self.log_queue.put("Mematikan Raspberry Pi...\n")
        commands = (["systemctl", "poweroff"], ["shutdown", "-h", "now"])
        for command in commands:
            try:
                subprocess.Popen(command)
                return
            except FileNotFoundError:
                continue
            except Exception as exc:
                self.log_queue.put(f"Gagal menjalankan {' '.join(command)}: {exc}\n")
        messagebox.showerror("Shutdown gagal", "Perintah shutdown tidak tersedia pada sistem ini.")


def shutil_which(command: str) -> str | None:
    from shutil import which

    return which(command)


def main() -> None:
    mp.freeze_support()
    apply_touchscreen_axis_swap()
    root = tk.Tk()
    PotentiostatDashboard(root)
    root.update_idletasks()
    root.mainloop()


if __name__ == "__main__":
    main()
