# HW_Model_tkinter_v4.py
"""
Merged and extended MHW Dashboard (v4):
- Additional Data tab split into two subtabs:
  1) Data Load: upload additional/current/forecast CSV, reference period filters (default: most recent 30 years),
     station selection, detection parameters replicated from Data & Run tab, recalculate button, preview panel
     showing detected heatwaves and statistics for daytime, nighttime and compound heatwaves.
  2) Plotting: plotting controls for calendar, category, timeseries per heatwave type, date-range selection,
     save plot buttons, save detected events.
- Calendar plots highlight all detected heatwaves (day, night, compound).
- Batch run, main Data & Run, plotting tabs preserved with robustness and logging.
- Defensive coding to avoid common Tkinter callback AttributeError issues (use functools.partial).
- Threaded batch processing remains for responsiveness.
"""
import os
import sys
import tempfile
import subprocess
import datetime
from datetime import date
import logging
import warnings
import threading
import functools
import time

import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import pandas as pd
import numpy as np
import marineHeatWaves as mhw

# Matplotlib imports
import matplotlib
matplotlib.use('TkAgg')

# Suppress Helvetica font warnings triggered internally by calplot
logging.getLogger('matplotlib.font_manager').setLevel(logging.ERROR)
warnings.filterwarnings("ignore", message=".*findfont: Font family.*Helvetica.*")

# Suppress expected scalar divide warnings from marineHeatWaves
warnings.filterwarnings("ignore", category=RuntimeWarning, message=".*invalid value encountered in scalar divide.*")

import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk

plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.sans-serif'] = ['DejaVu Sans', 'Arial', 'sans-serif']
plt.style.use('dark_background')

# calplot for calendar heatmap
try:
    import calplot
except Exception:
    calplot = None  # Handle gracefully if missing

# Pillow for rotated sidebar labels
from PIL import Image, ImageDraw, ImageFont, ImageColor
import io

# ---------- Logging ----------
LOG_FILE = os.path.join(os.path.abspath(os.path.dirname(__file__)), "mhw_app.log")
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
console = logging.StreamHandler()
console.setLevel(logging.ERROR)
logging.getLogger().addHandler(console)

def log_action(msg):
    try:
        logging.info(msg)
    except Exception:
        pass

# ---------- Utilities ----------
def dates_to_ord(dates):
    return np.array([d.toordinal() for d in pd.to_datetime(dates)])

def open_file_with_default_app(path):
    """Open a file with the system default application."""
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.run(["open", path], check=False)
        else:
            subprocess.run(["xdg-open", path], check=False)
    except Exception:
        pass

# ---------- Preview widget helper ----------
class PreviewText(tk.Frame):
    def __init__(self, master, width=50, height=10, bg="#2b2f33", fg="#e6eef6", **kwargs):
        super().__init__(master)
        master_bg = None
        try:
            if hasattr(master, "cget"):
                val = master.cget("fg_color")
                if isinstance(val, str) and len(val.split()) == 1:
                    master_bg = val
        except Exception:
            master_bg = None

        final_bg = master_bg if master_bg else bg
        try:
            self.configure(bg=final_bg)
        except Exception:
            self.configure(bg=bg)

        self.text = tk.Text(self, wrap="none", height=height, width=width, bg=bg, fg=fg,
                            insertbackground=fg, relief="flat")
        self.vbar = tk.Scrollbar(self, orient="vertical", command=self.text.yview)
        self.hbar = tk.Scrollbar(self, orient="horizontal", command=self.text.xview)
        self.text.configure(yscrollcommand=self.vbar.set, xscrollcommand=self.hbar.set)

        self.vbar.pack(side="right", fill="y")
        self.hbar.pack(side="bottom", fill="x")
        self.text.pack(side="left", fill="both", expand=True)

    def set(self, content: str):
        self.text.delete("1.0", "end")
        self.text.insert("1.0", content)

    def get(self):
        return self.text.get("1.0", "end")

    def clear(self):
        self.text.delete("1.0", "end")

# ---------- Sidebar Rotated Label Helper ----------
def _normalize_color_for_pillow(col, fallback="#1f2326"):
    if col is None:
        col = fallback
    if isinstance(col, (list, tuple)):
        if all(isinstance(x, (int, float)) for x in col):
            try:
                vals = tuple(int(max(0, min(255, round(255 * float(x))))) for x in col[:3])
                return vals
            except Exception:
                pass
        for item in col:
            if isinstance(item, str) and item.strip():
                col = item
                break
    if isinstance(col, str):
        if len(col.split()) > 1:
            col = col.split()[0]
        try:
            return ImageColor.getrgb(col)
        except Exception:
            try:
                return ImageColor.getrgb(col.strip())
            except Exception:
                pass
    try:
        return ImageColor.getrgb(fallback)
    except Exception:
        return (31, 35, 38)

def make_rotated_label_image(text, font_size=20, padding=2, angle=90, fg="#e6eef6", bg="#1f2326"):
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", font_size)
    except Exception:
        font = ImageFont.load_default()

    fg_rgb = _normalize_color_for_pillow(fg, fallback="#e6eef6")
    bg_rgb = _normalize_color_for_pillow(bg, fallback="#1f2326")

    dummy_img = Image.new("RGBA", (1, 1))
    draw = ImageDraw.Draw(dummy_img)
    try:
        w, h = draw.textsize(text, font=font)
    except Exception:
        try:
            bbox = draw.textbbox((0, 0), text, font=font)
            w = bbox[2] - bbox[0]
            h = bbox[3] - bbox[1]
        except Exception:
            try:
                w, h = font.getsize(text)
            except Exception:
                w = len(text) * (font_size // 2)
                h = font_size

    img = Image.new("RGBA", (w + padding * 2, h + padding * 2), color=bg_rgb + (255,))
    draw = ImageDraw.Draw(img)
    draw.text((padding, padding), text, font=font, fill=fg_rgb + (255,))
    img_rot = img.rotate(angle, expand=True, resample=Image.BICUBIC)

    try:
        photo = ctk.CTkImage(img_rot, size=img_rot.size)
    except Exception:
        with io.BytesIO() as buf:
            img_rot.save(buf, format="PNG")
            buf.seek(0)
            photo = ctk.CTkImage(Image.open(buf), size=img_rot.size)
    return photo

# ---------- Main App ----------
class MHWApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Heatwave Detection Dashboard")
        self.geometry("1400x820")

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        # Data holders
        self.df = None
        self._last_run_df = None
        self.t_ord = None
        self.dates = None

        self.mhws_day = None
        self.clim_day = None
        self.mhws_day_df = pd.DataFrame()

        self.mhws_night = None
        self.clim_night = None
        self.mhws_night_df = pd.DataFrame()

        self.compound_df = pd.DataFrame()
        self.block_df_day = pd.DataFrame()
        self.block_df_night = pd.DataFrame()

        self._last_plot_data = {'day': None, 'night': None, 'compound': None}
        self._last_figs = {'day': None, 'night': None, 'compound': None}

        self.max_points = 3000
        self._nav_images = {}

        # Batch run control
        self._batch_thread = None
        self._batch_cancelled = threading.Event()
        self._batch_lock = threading.Lock()

        # Temporary storage for additional-data detection results
        self.additional_df = None
        self._temp_mhws_day = None
        self._temp_clim_day = None
        self._temp_mhws_night = None
        self._temp_clim_night = None
        self._temp_compound_df = pd.DataFrame()
        self._temp_additional_df = None
        self._temp_t_ord = None

        self._build_ui()

    def switch_tab(self, name):
        for k, frame in self._content_frames.items():
            if k == name:
                frame.pack(fill="both", expand=True, padx=4, pady=4)
            else:
                frame.pack_forget()
        self.status_var.set(f"Active tab: {name}")
        log_action(f"Switched to tab: {name}")

    def _build_ui(self):
        root_frame = ctk.CTkFrame(self)
        root_frame.pack(fill="both", expand=True)

        sidebar = ctk.CTkFrame(root_frame, width=60)
        sidebar.pack(side="left", fill="y", padx=2, pady=2)

        content_area = ctk.CTkFrame(root_frame)
        content_area.pack(side="right", fill="both", expand=True, padx=8, pady=8)

        nav_buttons = [
            ("Data & Run", "data"),
            ("Daytime", "day"),
            ("Nighttime", "night"),
            ("Compound HW", "compound"),
            ("More", "more"),
            ("About", "about"),
        ]

        self._content_frames = {}
        data_frame = ctk.CTkFrame(content_area)
        self._content_frames["data"] = data_frame

        # Compressed Paddings for Data Tab
        top_frame = ctk.CTkFrame(data_frame)
        top_frame.pack(fill="x", padx=4, pady=2)

        ctk.CTkButton(top_frame, text="Open CSV", command=self.open_file, width=90, height=28).grid(row=0, column=0, padx=4, pady=4)
        ctk.CTkLabel(top_frame, text="Date:").grid(row=0, column=1, padx=2, pady=4)
        self.date_col_var = ctk.StringVar(value="Date")
        ctk.CTkEntry(top_frame, textvariable=self.date_col_var, width=90, height=24).grid(row=0, column=2, padx=2, pady=4)

        ctk.CTkLabel(top_frame, text="Day:").grid(row=0, column=3, padx=2, pady=4)
        self.day_col_var = ctk.StringVar(value="tx")
        ctk.CTkEntry(top_frame, textvariable=self.day_col_var, width=70, height=24).grid(row=0, column=4, padx=2, pady=4)

        ctk.CTkLabel(top_frame, text="Night:").grid(row=0, column=5, padx=2, pady=4)
        self.night_col_var = ctk.StringVar(value="tn")
        ctk.CTkEntry(top_frame, textvariable=self.night_col_var, width=70, height=24).grid(row=0, column=6, padx=2, pady=4)

        ctk.CTkLabel(top_frame, text="Station:").grid(row=0, column=7, padx=2, pady=4)
        self.station_col_var = ctk.StringVar(value="station")
        ctk.CTkEntry(top_frame, textvariable=self.station_col_var, width=90, height=24).grid(row=0, column=8, padx=2, pady=4)

        params_frame = ctk.CTkFrame(data_frame)
        params_frame.pack(fill="x", padx=4, pady=2)

        ctk.CTkLabel(params_frame, text="Clim start:").grid(row=0, column=0, padx=2, pady=4)
        self.clim_start = ctk.IntVar(value=1981)
        ctk.CTkEntry(params_frame, textvariable=self.clim_start, width=70, height=24).grid(row=0, column=1, padx=2, pady=4)

        ctk.CTkLabel(params_frame, text="Clim end:").grid(row=0, column=2, padx=2, pady=4)
        self.clim_end = ctk.IntVar(value=2010)
        ctk.CTkEntry(params_frame, textvariable=self.clim_end, width=70, height=24).grid(row=0, column=3, padx=2, pady=4)

        ctk.CTkLabel(params_frame, text="Pctile:").grid(row=0, column=4, padx=2, pady=4)
        self.pctile = ctk.IntVar(value=90)
        ctk.CTkEntry(params_frame, textvariable=self.pctile, width=60, height=24).grid(row=0, column=5, padx=2, pady=4)

        ctk.CTkLabel(params_frame, text="Min dur:").grid(row=0, column=6, padx=2, pady=4)
        self.min_duration = ctk.IntVar(value=3)
        ctk.CTkEntry(params_frame, textvariable=self.min_duration, width=60, height=24).grid(row=0, column=7, padx=2, pady=4)

        self.join_gaps = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(params_frame, text="Join gaps", variable=self.join_gaps, checkbox_height=18, checkbox_width=18).grid(row=0, column=8, padx=4, pady=4)
        ctk.CTkLabel(params_frame, text="Max gap:").grid(row=0, column=9, padx=2, pady=4)
        self.max_gap = ctk.IntVar(value=1)
        ctk.CTkEntry(params_frame, textvariable=self.max_gap, width=60, height=24).grid(row=0, column=10, padx=2, pady=4)

        control_frame = ctk.CTkFrame(data_frame)
        control_frame.pack(fill="x", padx=4, pady=2)
        ctk.CTkLabel(control_frame, text="Select station:").grid(row=0, column=0, padx=4, pady=4)
        self.station_combo = ctk.CTkOptionMenu(control_frame, values=["All"], command=self.on_station_change, height=24)
        self.station_combo.set("All")
        self.station_combo.grid(row=0, column=1, padx=4, pady=4)

        ctk.CTkButton(control_frame, text="Run detection", command=self.run_detection, height=28).grid(row=0, column=2, padx=6, pady=4)
        ctk.CTkButton(control_frame, text="Save block averages", command=lambda: self.save_df(self.block_df_day), height=28).grid(row=0, column=3, padx=6, pady=4)
        ctk.CTkButton(control_frame, text="Printout previews", command=self.printout_previews, height=28).grid(row=0, column=4, padx=6, pady=4)

        # Preview and describe
        preview_frame = ctk.CTkFrame(data_frame)
        preview_frame.pack(fill="both", padx=4, pady=2, expand=False)
        ctk.CTkLabel(preview_frame, text="Data preview (first 10 rows)").pack(anchor="w", padx=6, pady=0)
        self.preview_widget = PreviewText(preview_frame, width=160, height=4)
        self.preview_widget.pack(fill="both", expand=True, padx=6, pady=2)

        describe_frame = ctk.CTkFrame(data_frame)
        describe_frame.pack(fill="both", padx=4, pady=2, expand=False)
        ctk.CTkLabel(describe_frame, text="Selected station Stats").pack(anchor="w", padx=6, pady=0)
        self.describe_widget = PreviewText(describe_frame, width=160, height=4)
        self.describe_widget.pack(fill="both", expand=True, padx=6, pady=2)

        # ---------- Calendar Plot Frame w/ Filters & Export (main) ----------
        cal_frame = ctk.CTkFrame(data_frame)
        cal_frame.pack(fill="both", padx=4, pady=2, expand=False)
        cal_frame.configure(height=240)
        cal_frame.pack_propagate(False)

        cal_top = ctk.CTkFrame(cal_frame, fg_color="transparent")
        cal_top.pack(fill="x", padx=6, pady=2)
        ctk.CTkLabel(cal_top, text="Calendar heatmap plot").pack(side="left")

        # Save Calendar Button
        ctk.CTkButton(cal_top, text="Save Calendar", command=self.save_calendar_plot, width=110, height=26).pack(side="right", padx=6)

        # Interactive Year Selector
        self.cal_year_var = ctk.StringVar(value="")
        self.cal_year_combo = ctk.CTkOptionMenu(cal_top, variable=self.cal_year_var, command=self.update_calendar_plot, width=90, height=24)
        self.cal_year_combo.pack(side="right", padx=2)
        ctk.CTkLabel(cal_top, text="Year:").pack(side="right", padx=2)

        # Day / Night Selection
        self.cal_temp_var = ctk.StringVar(value="Day (tx)")
        self.cal_temp_combo = ctk.CTkOptionMenu(cal_top, values=["Day (tx)", "Night (tn)"], variable=self.cal_temp_var, command=self.update_calendar_plot, width=110, height=24)
        self.cal_temp_combo.pack(side="right", padx=2)
        ctk.CTkLabel(cal_top, text="Plot:").pack(side="right", padx=2)

        # Persistent Plot Container (Prevents Tkinter 'after' errors)
        self.cal_plot_container = ctk.CTkFrame(cal_frame, fg_color="transparent")
        self.cal_plot_container.pack(fill="both", expand=True, padx=2, pady=2)

        self.cal_fig = Figure(figsize=(10, 1.9), dpi=100, facecolor='#1f2326')
        self.cal_canvas = FigureCanvasTkAgg(self.cal_fig, master=self.cal_plot_container)
        self.cal_canvas.get_tk_widget().pack(fill="both", expand=True, padx=4, pady=4)

        # ---------- Plot Sub-Tabs ----------
        for kind in ("day", "night", "compound"):
            frame = ctk.CTkFrame(content_area)
            self._content_frames[kind] = frame
            self._build_plot_tab(frame, kind)

        # ---------- More tab (Additional data with two subtabs + Batch run) ----------
        more_frame = ctk.CTkFrame(content_area)
        self._content_frames["more"] = more_frame
        self._build_more_tab(more_frame)

        # About content frame
        about_frame = ctk.CTkFrame(content_area)
        self._content_frames["about"] = about_frame

        about_title = ctk.CTkLabel(about_frame, text="About this App", font=ctk.CTkFont(size=20, weight="bold"))
        about_title.pack(pady=(6, 12))

        creator_text = (
            "==========================================================================\n"
            "Creator: Cosmos Wemegah, PhD \n"
            "App: Atmospheric Heatwave Detection Dashboard\n"
            "UI: CustomTkinter (dark theme)\n"
            "Version: 4.0\n"
            "==========================================================================\n"
        )
        creator_label = ctk.CTkLabel(about_frame, text=creator_text, anchor="w", justify="left")
        creator_label.pack(fill="x", padx=6, pady=(0, 12))

        readme = (
            "Quick start / How to use\n\n"
            "1. Open CSV: Click 'Open CSV' and select a file.\n"
            "2. Configure detection parameters.\n"
            "3. Select station: Use the station selector to analyze a single station or 'All'.\n"
            "   This automatically updates the Calendar view on the Data tab.\n"
            "4. Run detection: Computes events and generates summaries.\n"
            "5. View results: Switch to Day/Night/Compound tabs.\n"
            "6. More -> Additional data: two subtabs (Data Load, Plotting). Load additional data, set reference period,\n"
            "   recalculate detection, preview events and stats, then use Plotting subtab to inspect and save plots/events.\n"
            "7. More -> Batch run: upload multi-station file and run batch detection; cancel if needed.\n"
        )

        readme_widget = PreviewText(about_frame, width=120, height=18)
        readme_widget.set(readme)
        readme_widget.pack(fill="both", expand=True, padx=6, pady=6)

        for i, (label, key) in enumerate(nav_buttons):
            try:
                sidebar_bg = sidebar.cget("fg_color") if hasattr(sidebar, "cget") else "#1f2326"
            except Exception:
                sidebar_bg = "#1f2326"
            img = make_rotated_label_image(label, font_size=14, padding=8, angle=90,
                                          fg="#e6eef6", bg=sidebar_bg)
            self._nav_images[key] = img

            btn = ctk.CTkButton(sidebar, text="", image=img, width=60, height=110, fg_color=None,
                               hover_color=None, command=functools.partial(self.switch_tab, key))
            btn.pack(pady=6, padx=4)

        # Status / Loading widget area
        status_frame = ctk.CTkFrame(self)
        status_frame.pack(side="bottom", fill="x")
        self.status_var = ctk.StringVar(value="Ready")
        self.status_label = ctk.CTkLabel(status_frame, textvariable=self.status_var, anchor="w")
        self.status_label.pack(side="left", fill="x", expand=True, padx=6, pady=4)

        # Use ttk.Progressbar as a loading indicator (indeterminate)
        self.progress = ttk.Progressbar(status_frame, mode='indeterminate', length=220)
        self.progress.pack(side="right", padx=6, pady=4)
        self.progress_stop_after_id = None

        self.switch_tab("data")

    def _build_plot_tab(self, parent, kind):
        left = ctk.CTkFrame(parent)
        left.pack(side="left", fill="both", expand=True, padx=6, pady=6)

        right = ctk.CTkFrame(parent)
        right.pack(side="right", fill="y", padx=6, pady=6)

        summary_frame = ctk.CTkFrame(left)
        summary_frame.pack(fill="both", padx=4, pady=4)
        ctk.CTkLabel(summary_frame, text=f"{kind.capitalize()} summary").pack(anchor="w", padx=6, pady=4)
        summary_widget = PreviewText(summary_frame, width=80, height=10)
        summary_widget.pack(fill="both", expand=True, padx=6, pady=4)
        setattr(self, f"{kind}_summary_widget", summary_widget)

        table_frame = ctk.CTkFrame(left)
        table_frame.pack(fill="both", padx=4, pady=4, expand=True)
        ctk.CTkLabel(table_frame, text=f"{kind.capitalize()} Events (preview)").pack(anchor="w", padx=6, pady=4)
        table_widget = PreviewText(table_frame, width=80, height=10)
        table_widget.pack(fill="both", expand=True, padx=6, pady=4)
        setattr(self, f"{kind}_table_widget", table_widget)

        ctk.CTkLabel(right, text=f"{kind.capitalize()} controls").pack(pady=6)
        ctk.CTkButton(right, text=f"Save {kind} events", command=functools.partial(self.save_events_for, kind)).pack(fill="x", pady=4, padx=6)
        ctk.CTkButton(right, text=f"Save {kind} block averages", command=functools.partial(self.save_block_for, kind)).pack(fill="x", pady=4, padx=6)

        plot_type_frame = ctk.CTkFrame(right)
        plot_type_frame.pack(fill="x", padx=4, pady=6)
        ctk.CTkLabel(plot_type_frame, text="Plot type:").grid(row=0, column=0, padx=4, pady=6)
        plot_choice = ctk.StringVar(value="Block")
        setattr(self, f"{kind}_plot_choice", plot_choice)
        ctk.CTkOptionMenu(plot_type_frame, values=["Block", "Category", "Heatmap plot", "Timeseries"], variable=plot_choice).grid(row=0, column=1, padx=4, pady=6)

        ctk.CTkLabel(plot_type_frame, text="Year start:").grid(row=1, column=0, padx=4, pady=6)
        ys = ctk.IntVar(value=1981)
        setattr(self, f"{kind}_year_start", ys)
        ctk.CTkEntry(plot_type_frame, textvariable=ys, width=80).grid(row=1, column=1, padx=4, pady=6)
        ctk.CTkLabel(plot_type_frame, text="Year end:").grid(row=1, column=2, padx=4, pady=6)
        ye = ctk.IntVar(value=2018)
        setattr(self, f"{kind}_year_end", ye)
        ctk.CTkEntry(plot_type_frame, textvariable=ye, width=80).grid(row=1, column=3, padx=4, pady=6)

        # Use functools.partial to avoid late-binding issues in lambdas
        ctk.CTkButton(plot_type_frame, text="Update plot", command=functools.partial(self.update_tab_plot, kind)).grid(row=2, column=0, columnspan=4, pady=6, padx=4)

        mpl_frame = ctk.CTkFrame(right)
        mpl_frame.pack(fill="both", expand=True, padx=4, pady=6)
        fig = Figure(figsize=(6, 3), dpi=100, facecolor='#1f2326')
        ax = fig.add_subplot(111, facecolor='#111213')
        ax.text(0.5, 0.5, "Plot will appear here after running detection", ha='center', va='center', color='white')
        canvas = FigureCanvasTkAgg(fig, master=mpl_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)

        toolbar = NavigationToolbar2Tk(canvas, mpl_frame)
        toolbar.update()
        toolbar.pack(side="bottom", fill="x")

        small_toolbar = ctk.CTkFrame(right)
        small_toolbar.pack(fill="x", padx=4, pady=6)
        ctk.CTkButton(small_toolbar, text="Pan", command=lambda tb=toolbar: self._toggle_pan(tb)).pack(side="left", padx=4)
        ctk.CTkButton(small_toolbar, text="Zoom", command=lambda tb=toolbar: self._toggle_zoom(tb)).pack(side="left", padx=4)
        ctk.CTkButton(small_toolbar, text="Reset view", command=lambda f=fig: self._reset_view(f)).pack(side="left", padx=4)

        setattr(self, f"{kind}_mpl_fig", fig)
        setattr(self, f"{kind}_mpl_canvas", canvas)
        setattr(self, f"{kind}_mpl_toolbar", toolbar)

    def _build_more_tab(self, parent):
        # Top-level More controls
        top = ctk.CTkFrame(parent)
        top.pack(fill="x", padx=6, pady=6)

        btn_frame = ctk.CTkFrame(top)
        btn_frame.pack(side="left", padx=6)

        ctk.CTkButton(btn_frame, text="Additional data", command=functools.partial(self._show_more_subtab, "additional")).pack(side="left", padx=4)
        ctk.CTkButton(btn_frame, text="Batch run", command=functools.partial(self._show_more_subtab, "batch")).pack(side="left", padx=4)

        self._more_subframes = {}
        # Additional data main frame (contains two subtabs)
        add_main = ctk.CTkFrame(parent)
        self._more_subframes["additional"] = add_main

        # Subtab buttons for Additional data
        add_tab_buttons = ctk.CTkFrame(add_main)
        add_tab_buttons.pack(fill="x", padx=6, pady=6)
        ctk.CTkButton(add_tab_buttons, text="Data Load", command=functools.partial(self._show_additional_subtab, "data_load")).pack(side="left", padx=4)
        ctk.CTkButton(add_tab_buttons, text="Plotting", command=functools.partial(self._show_additional_subtab, "plotting")).pack(side="left", padx=4)

        self._additional_subframes = {}

        # ---------------- Data Load subtab ----------------
        data_load = ctk.CTkFrame(add_main)
        self._additional_subframes["data_load"] = data_load

        # Upload additional CSV for a selected station
        up_frame = ctk.CTkFrame(data_load)
        up_frame.pack(fill="x", padx=6, pady=6)
        ctk.CTkLabel(up_frame, text="Upload additional/current/forecast CSV for selected station").pack(anchor="w", padx=6, pady=4)
        ctk.CTkButton(up_frame, text="Open additional CSV", command=self.open_additional_file).pack(anchor="w", padx=6, pady=4)

        # Reference period filters and replicated entries from Data & Run
        ref_frame = ctk.CTkFrame(data_load)
        ref_frame.pack(fill="x", padx=6, pady=6)

        # Determine default most recent 30-year period
        current_year = datetime.datetime.now().year
        default_end = current_year - 1
        default_start = default_end - 29

        ctk.CTkLabel(ref_frame, text="Reference start year:").grid(row=0, column=0, padx=4, pady=4)
        self.add_ref_start = ctk.IntVar(value=default_start)
        ctk.CTkEntry(ref_frame, textvariable=self.add_ref_start, width=90).grid(row=0, column=1, padx=4, pady=4)

        ctk.CTkLabel(ref_frame, text="Reference end year:").grid(row=0, column=2, padx=4, pady=4)
        self.add_ref_end = ctk.IntVar(value=default_end)
        ctk.CTkEntry(ref_frame, textvariable=self.add_ref_end, width=90).grid(row=0, column=3, padx=4, pady=4)

        # Replicate other entries from Data & Run
        ctk.CTkLabel(ref_frame, text="Date col:").grid(row=1, column=0, padx=4, pady=4)
        self.add_date_col = ctk.StringVar(value=self.date_col_var.get())
        ctk.CTkEntry(ref_frame, textvariable=self.add_date_col, width=120).grid(row=1, column=1, padx=4, pady=4)

        ctk.CTkLabel(ref_frame, text="Day col:").grid(row=1, column=2, padx=4, pady=4)
        self.add_day_col = ctk.StringVar(value=self.day_col_var.get())
        ctk.CTkEntry(ref_frame, textvariable=self.add_day_col, width=120).grid(row=1, column=3, padx=4, pady=4)

        ctk.CTkLabel(ref_frame, text="Night col:").grid(row=2, column=0, padx=4, pady=4)
        self.add_night_col = ctk.StringVar(value=self.night_col_var.get())
        ctk.CTkEntry(ref_frame, textvariable=self.add_night_col, width=120).grid(row=2, column=1, padx=4, pady=4)

        ctk.CTkLabel(ref_frame, text="Station col:").grid(row=2, column=2, padx=4, pady=4)
        self.add_station_col = ctk.StringVar(value=self.station_col_var.get())
        ctk.CTkEntry(ref_frame, textvariable=self.add_station_col, width=120).grid(row=2, column=3, padx=4, pady=4)

        ctk.CTkLabel(ref_frame, text="Pctile:").grid(row=3, column=0, padx=4, pady=4)
        self.add_pctile = ctk.IntVar(value=self.pctile.get())
        ctk.CTkEntry(ref_frame, textvariable=self.add_pctile, width=80).grid(row=3, column=1, padx=4, pady=4)

        ctk.CTkLabel(ref_frame, text="Min dur:").grid(row=3, column=2, padx=4, pady=4)
        self.add_min_duration = ctk.IntVar(value=self.min_duration.get())
        ctk.CTkEntry(ref_frame, textvariable=self.add_min_duration, width=80).grid(row=3, column=3, padx=4, pady=4)

        self.add_join_gaps = ctk.BooleanVar(value=self.join_gaps.get())
        ctk.CTkCheckBox(ref_frame, text="Join gaps", variable=self.add_join_gaps, checkbox_height=18, checkbox_width=18).grid(row=4, column=0, padx=4, pady=4)
        ctk.CTkLabel(ref_frame, text="Max gap:").grid(row=4, column=1, padx=4, pady=4)
        self.add_max_gap = ctk.IntVar(value=self.max_gap.get())
        ctk.CTkEntry(ref_frame, textvariable=self.add_max_gap, width=80).grid(row=4, column=2, padx=4, pady=4)

        # Station selection for additional data recalculation
        recalc_frame = ctk.CTkFrame(data_load)
        recalc_frame.pack(fill="x", padx=6, pady=6)
        ctk.CTkLabel(recalc_frame, text="Select station to apply additional data:").grid(row=0, column=0, padx=4, pady=4)
        self.add_station_combo = ctk.CTkOptionMenu(recalc_frame, values=["All"], height=24)
        self.add_station_combo.set("All")
        self.add_station_combo.grid(row=0, column=1, padx=4, pady=4)
        ctk.CTkButton(recalc_frame, text="Recalculate detection with additional data", command=self.recalculate_with_additional).grid(row=0, column=2, padx=6, pady=4)

        # Preview panel showing detected heatwaves and statistics for day/night/compound
        preview_panel = ctk.CTkFrame(data_load)
        preview_panel.pack(fill="both", expand=True, padx=6, pady=6)
        left_preview = ctk.CTkFrame(preview_panel)
        left_preview.pack(side="left", fill="both", expand=True, padx=6, pady=6)
        right_preview = ctk.CTkFrame(preview_panel)
        right_preview.pack(side="right", fill="both", expand=True, padx=6, pady=6)

        ctk.CTkLabel(left_preview, text="Detected events (additional data)").pack(anchor="w", padx=6, pady=4)
        self.add_events_widget = PreviewText(left_preview, width=120, height=12)
        self.add_events_widget.pack(fill="both", expand=True, padx=6, pady=4)

        ctk.CTkLabel(right_preview, text="Statistics (Day / Night / Compound)").pack(anchor="w", padx=6, pady=4)
        self.add_stats_widget = PreviewText(right_preview, width=80, height=12)
        self.add_stats_widget.pack(fill="both", expand=True, padx=6, pady=4)

        # ---------------- Plotting subtab ----------------
        plotting = ctk.CTkFrame(add_main)
        self._additional_subframes["plotting"] = plotting

        # Plot controls (calendar, category, timeseries)
        plot_controls = ctk.CTkFrame(plotting)
        plot_controls.pack(fill="x", padx=6, pady=6)

        ctk.CTkLabel(plot_controls, text="Calendar Year:").grid(row=0, column=0, padx=4, pady=4)
        self.plot_cal_year_var = ctk.StringVar(value="")
        self.plot_cal_year_combo = ctk.CTkOptionMenu(plot_controls, variable=self.plot_cal_year_var, values=[], width=90, command=self.update_additional_calendar_plot)
        self.plot_cal_year_combo.grid(row=0, column=1, padx=4, pady=4)

        ctk.CTkLabel(plot_controls, text="Calendar Plot:").grid(row=0, column=2, padx=4, pady=4)
        self.plot_cal_temp_var = ctk.StringVar(value="Day (tx)")
        self.plot_cal_temp_combo = ctk.CTkOptionMenu(plot_controls, values=["Day (tx)", "Night (tn)", "All (highlight all)"], variable=self.plot_cal_temp_var, width=160, command=self.update_additional_calendar_plot)
        self.plot_cal_temp_combo.grid(row=0, column=3, padx=4, pady=4)

        ctk.CTkLabel(plot_controls, text="Category Plot:").grid(row=1, column=0, padx=4, pady=4)
        self.plot_category_toggle = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(plot_controls, text="Show category plot", variable=self.plot_category_toggle, command=self.update_additional_category_plot).grid(row=1, column=1, padx=4, pady=4)

        ctk.CTkLabel(plot_controls, text="Timeseries start:").grid(row=2, column=0, padx=4, pady=4)
        self.plot_ts_start = ctk.StringVar(value="")
        ctk.CTkEntry(plot_controls, textvariable=self.plot_ts_start, width=120).grid(row=2, column=1, padx=4, pady=4)
        ctk.CTkLabel(plot_controls, text="end:").grid(row=2, column=2, padx=4, pady=4)
        self.plot_ts_end = ctk.StringVar(value="")
        ctk.CTkEntry(plot_controls, textvariable=self.plot_ts_end, width=120).grid(row=2, column=3, padx=4, pady=4)
        ctk.CTkButton(plot_controls, text="Update timeseries", command=self.update_additional_timeseries).grid(row=2, column=4, padx=6, pady=4)

        # Plot canvases
        add_plot_frame = ctk.CTkFrame(plotting)
        add_plot_frame.pack(fill="both", expand=True, padx=6, pady=6)

        # Calendar plot container
        cal_container = ctk.CTkFrame(add_plot_frame)
        cal_container.pack(fill="x", padx=4, pady=4, expand=False)
        self.add_cal_fig = Figure(figsize=(10, 1.4), dpi=100, facecolor='#1f2326')
        self.add_cal_canvas = FigureCanvasTkAgg(self.add_cal_fig, master=cal_container)
        self.add_cal_canvas.get_tk_widget().pack(fill="both", expand=True)

        # Category plot container
        cat_container = ctk.CTkFrame(add_plot_frame)
        cat_container.pack(fill="x", padx=4, pady=4, expand=False)
        self.add_cat_fig = Figure(figsize=(10, 2.0), dpi=100, facecolor='#1f2326')
        self.add_cat_canvas = FigureCanvasTkAgg(self.add_cat_fig, master=cat_container)
        self.add_cat_canvas.get_tk_widget().pack(fill="both", expand=True)

        # Timeseries container
        ts_container = ctk.CTkFrame(add_plot_frame)
        ts_container.pack(fill="both", padx=4, pady=4, expand=True)
        self.add_ts_fig = Figure(figsize=(10, 3.0), dpi=100, facecolor='#1f2326')
        self.add_ts_canvas = FigureCanvasTkAgg(self.add_ts_fig, master=ts_container)
        self.add_ts_canvas.get_tk_widget().pack(fill="both", expand=True)

        # Save buttons for plotting subtab
        add_buttons = ctk.CTkFrame(plotting)
        add_buttons.pack(fill="x", padx=6, pady=6)
        ctk.CTkButton(add_buttons, text="Save calendar plot", command=functools.partial(self.save_additional_plot, 'calendar')).pack(side="left", padx=6)
        ctk.CTkButton(add_buttons, text="Save category plot", command=functools.partial(self.save_additional_plot, 'category')).pack(side="left", padx=6)
        ctk.CTkButton(add_buttons, text="Save timeseries plot", command=functools.partial(self.save_additional_plot, 'timeseries')).pack(side="left", padx=6)
        ctk.CTkButton(add_buttons, text="Save detected events (additional)", command=self.save_additional_events).pack(side="left", padx=6)

        # ---------------- Batch run frame ----------------
        batch_frame = ctk.CTkFrame(parent)
        self._more_subframes["batch"] = batch_frame

        batch_top = ctk.CTkFrame(batch_frame)
        batch_top.pack(fill="x", padx=6, pady=6)
        ctk.CTkLabel(batch_top, text="Batch run: upload multi-station CSV and run detection per station").pack(anchor="w", padx=6, pady=4)
        ctk.CTkButton(batch_top, text="Open multi-station CSV", command=self.open_batch_file).pack(anchor="w", padx=6, pady=4)

        batch_controls = ctk.CTkFrame(batch_frame)
        batch_controls.pack(fill="x", padx=6, pady=6)
        ctk.CTkLabel(batch_controls, text="Station column:").grid(row=0, column=0, padx=4, pady=4)
        self.batch_station_col = ctk.StringVar(value=self.station_col_var.get())
        ctk.CTkEntry(batch_controls, textvariable=self.batch_station_col, width=120).grid(row=0, column=1, padx=4, pady=4)
        ctk.CTkButton(batch_controls, text="Start batch run", command=self.start_batch_run).grid(row=0, column=2, padx=6, pady=4)
        ctk.CTkButton(batch_controls, text="Cancel batch run", command=self.cancel_batch_run).grid(row=0, column=3, padx=6, pady=4)

        batch_log_frame = ctk.CTkFrame(batch_frame)
        batch_log_frame.pack(fill="both", expand=True, padx=6, pady=6)
        ctk.CTkLabel(batch_log_frame, text="Batch diagnostics / log").pack(anchor="w", padx=6, pady=4)
        self.batch_log_widget = PreviewText(batch_log_frame, width=120, height=10)
        self.batch_log_widget.pack(fill="both", expand=True, padx=6, pady=4)

        # Initially show Data Load subtab
        self._show_additional_subtab("data_load")
        # Initially show Additional main subtab
        self._show_more_subtab("additional")

    def _show_more_subtab(self, name):
        for k, f in self._more_subframes.items():
            if k == name:
                f.pack(fill="both", expand=True, padx=6, pady=6)
            else:
                f.pack_forget()
        log_action(f"More subtab shown: {name}")

    def _show_additional_subtab(self, name):
        for k, f in self._additional_subframes.items():
            if k == name:
                f.pack(fill="both", expand=True, padx=6, pady=6)
            else:
                f.pack_forget()
        log_action(f"Additional subtab shown: {name}")

    def _toggle_progress(self, start=True):
        try:
            if start:
                self.progress.start(10)
            else:
                self.progress.stop()
        except Exception:
            pass

    # ---------- Flow & File Handlers ----------
    def open_file(self):
        log_action("Open CSV clicked")
        path = filedialog.askopenfilename(filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if not path:
            return
        try:
            df = pd.read_csv(path, parse_dates=[self.date_col_var.get()])
        except Exception:
            df = pd.read_csv(path)
        self.df = df
        self.status_var.set(f"Loaded {os.path.basename(path)}")
        self.preview_widget.set(df.head(10).to_string(index=False))

        st_col = self.station_col_var.get()
        if st_col and st_col in df.columns:
            stations = ["All"] + sorted(df[st_col].dropna().unique().tolist())
            self.station_combo.configure(values=stations)
        else:
            self.station_combo.configure(values=["All"])

        self.station_combo.set("All")
        messagebox.showinfo("File loaded", f"File loaded with {len(df)} rows.")
        self.on_station_change("All")

        # Update additional data station selector as well
        try:
            self.add_station_combo.configure(values=["All"] + sorted(df[self.station_col_var.get()].dropna().unique().tolist()))
        except Exception:
            pass

    def open_additional_file(self):
        log_action("Open additional CSV clicked")
        path = filedialog.askopenfilename(filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if not path:
            return
        try:
            df = pd.read_csv(path, parse_dates=[self.add_date_col.get()])
        except Exception:
            df = pd.read_csv(path)
        self.additional_df = df
        messagebox.showinfo("Additional data loaded", f"Additional data loaded with {len(df)} rows.")
        log_action(f"Additional data loaded: {os.path.basename(path)}")
        # populate add_station_combo if station column exists
        st_col = self.add_station_col.get()
        if st_col and st_col in df.columns:
            try:
                vals = ["All"] + sorted(df[st_col].dropna().unique().tolist())
                self.add_station_combo.configure(values=vals)
                self.add_station_combo.set(vals[0])
            except Exception:
                pass

        # populate calendar year choices for additional data
        try:
            date_col = self.add_date_col.get()
            df[date_col] = pd.to_datetime(df[date_col])
            years = sorted(df[date_col].dt.year.dropna().unique().tolist(), reverse=True)
            years_str = [str(int(y)) for y in years]
            if years_str:
                self.plot_cal_year_combo.configure(values=years_str)
                self.plot_cal_year_var.set(years_str[0])
                self.plot_cal_year_combo.configure(values=years_str)
                self.plot_cal_year_var.set(years_str[0])
                self.plot_cal_year_combo.update()
                self.plot_cal_year_combo.set(years_str[0])
                # also set plotting combobox
                self.plot_cal_year_combo.configure(values=years_str)
                self.plot_cal_year_var.set(years_str[0])
        except Exception:
            pass

    def open_batch_file(self):
        log_action("Open batch CSV clicked")
        path = filedialog.askopenfilename(filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if not path:
            return
        try:
            df = pd.read_csv(path, parse_dates=[self.date_col_var.get()])
        except Exception:
            df = pd.read_csv(path)
        self.batch_df = df
        messagebox.showinfo("Batch file loaded", f"Batch file loaded with {len(df)} rows.")
        log_action(f"Batch file loaded: {os.path.basename(path)}")
        # show stations preview
        st_col = self.batch_station_col.get()
        if st_col and st_col in df.columns:
            stations = sorted(df[st_col].dropna().unique().tolist())
            self.batch_log_widget.set(f"Stations found: {len(stations)}\n" + ", ".join(stations[:50]))

    def on_station_change(self, choice):
        log_action(f"Station changed: {choice}")
        self.update_station_describe()
        self.populate_years()
        self.update_calendar_plot()

    def update_station_describe(self):
        if self.df is None:
            return
        st_col = self.station_col_var.get()
        sel = self.station_combo.get()
        if st_col and st_col in self.df.columns and sel != "All":
            sub = self.df[self.df[st_col] == sel]
        else:
            sub = self.df
        try:
            desc = sub.describe(include='all').transpose()
            text = desc.to_string()
        except Exception:
            text = "Could not compute describe() for this selection."
        self.describe_widget.set(text)

    def populate_years(self):
        if self.df is None or self.df.empty: return

        st_col = self.station_col_var.get()
        sel = self.station_combo.get()
        df = self.df.copy()

        if st_col and st_col in df.columns and sel != "All":
            df = df[df[st_col] == sel]

        date_col = self.date_col_var.get()
        if date_col in df.columns:
            try:
                df[date_col] = pd.to_datetime(df[date_col])
                years = sorted(df[date_col].dt.year.dropna().unique().tolist(), reverse=True)
                years_str = [str(int(y)) for y in years]
                self.cal_year_combo.configure(values=years_str)
                if years_str:
                    self.cal_year_var.set(years_str[0])
            except Exception:
                pass

    # ---------- Calendar plot helpers (main data) ----------
    def update_calendar_plot(self, choice=None):
        """Builds Calendar Heatmap tracking widget state, avoiding canvas recreation to stop 'after' bugs"""
        try:
            self.cal_fig.clf()
            ax = self.cal_fig.add_subplot(111, facecolor='#111213')

            if self.df is None or self.df.empty:
                ax.text(0.5, 0.5, "No data loaded for calendar plot", ha='center', va='center', color='white')
                self.cal_canvas.draw()
                return

            date_col = self.date_col_var.get()
            selected_year_str = self.cal_year_var.get()

            # Day vs Night selection logic
            is_night = (self.cal_temp_var.get() == "Night (tn)")
            temp_col = self.night_col_var.get() if is_night else self.day_col_var.get()

            if date_col not in self.df.columns or temp_col not in self.df.columns or not selected_year_str:
                ax.text(0.5, 0.5, f"Missing columns (Temp col: '{temp_col}') or year unselected.", ha='center', va='center', color='white')
                self.cal_canvas.draw()
                return

            selected_year = int(selected_year_str)
            df = self.df.copy()
            df[date_col] = pd.to_datetime(df[date_col])

            st_col = self.station_col_var.get()
            sel_station = self.station_combo.get()
            if st_col and st_col in df.columns and sel_station != "All":
                df = df[df[st_col] == sel_station]

            df_year = df[df[date_col].dt.year == selected_year].copy()
            if df_year.empty:
                ax.text(0.5, 0.5, f"No data for year {selected_year}", ha='center', va='center', color='white')
                self.cal_canvas.draw()
                return

            daily = df_year.set_index(date_col)[temp_col].resample('D').mean()
            station_text = f" ({sel_station})" if sel_station != "All" else ""

            # Collect all detected heatwave dates from main detection results
            hw_dates = set()
            for mhws in (self.mhws_day, self.mhws_night):
                if mhws and mhws.get('n_events', 0) > 0:
                    for i in range(mhws['n_events']):
                        curr = pd.Timestamp(mhws['date_start'][i])
                        end_ts = pd.Timestamp(mhws['date_end'][i])
                        while curr <= end_ts:
                            if curr.year == selected_year:
                                hw_dates.add(curr)
                            curr += pd.Timedelta(days=1)

            first_day = pd.Timestamp(year=selected_year, month=1, day=1)

            if calplot is not None:
                calplot.yearplot(daily, year=selected_year, ax=ax, cmap='Spectral_r', fillcolor='#2b2f33', linewidth=1, linecolor='#1f2326')

                # Plot Annotations and Heatwave Highlights securely inside calplot boundaries
                for date_val, val in daily.items():
                    if pd.isna(val): continue
                    date_ts = pd.Timestamp(date_val)
                    week = (date_ts - first_day + pd.Timedelta(first_day.dayofweek, unit='d')).days // 7
                    dow = date_ts.dayofweek

                    # Add Day Annotation (Day of Month)
                    ax.text(week + 0.5, dow + 0.5, str(date_ts.day), ha='center', va='center', color='#222222', fontsize=7, fontweight='bold')

                    # Add Heatwave Highlights (all detected)
                    if date_ts in hw_dates:
                        rect = plt.Rectangle((week, dow), 1, 1, fill=False, edgecolor='red', linewidth=3)
                        ax.add_patch(rect)

                if len(ax.collections) > 0:
                    cbar = self.cal_fig.colorbar(ax.collections[0], ax=ax, orientation='vertical', fraction=0.046, pad=0.04)
                    cbar.ax.tick_params(colors='white')
                    cbar.set_label('Temperature', color='white')

                ax.set_title(f"{selected_year} daily {temp_col}{station_text}", color='white')
                ax.tick_params(colors='white')
            else:
                # Fallback implementation
                df_year['doy'] = df_year[date_col].dt.dayofyear
                pivot = df_year.pivot_table(index=df_year[date_col].dt.month, columns='doy', values=temp_col, aggfunc='mean')

                if pivot.empty:
                    ax.text(0.5, 0.5, "Not enough data for calendar heatmap", ha='center', va='center', color='white')
                else:
                    im = ax.imshow(pivot.fillna(np.nan).values, aspect='auto', origin='lower', cmap='Spectral_r')
                    ax.set_yticks(np.arange(len(pivot.index)))
                    ax.set_yticklabels(pivot.index.astype(str), color='white')
                    ax.set_xlabel('Day of year', color='white')
                    ax.set_title(f"{selected_year} daily {temp_col}{station_text}", color='white')
                    self.cal_fig.colorbar(im, ax=ax, orientation='vertical', label='Temperature')

                    for date_val in df_year[date_col]:
                        doy = date_val.dayofyear - 1
                        try:
                            row_idx = list(pivot.index).index(date_val.month)
                            ax.text(doy, row_idx, str(date_val.day), ha='center', va='center', color='#222222', fontsize=6, fontweight='bold')
                            if pd.Timestamp(date_val) in hw_dates:
                                rect = plt.Rectangle((doy-0.5, row_idx-0.5), 1, 1, fill=False, edgecolor='red', linewidth=3)
                                ax.add_patch(rect)
                        except ValueError:
                            pass

            self.cal_canvas.draw()
            self.status_var.set(f"Calendar plot updated for {selected_year}{station_text}.")
        except Exception as e:
            try:
                self.cal_fig.clf()
                ax = self.cal_fig.add_subplot(111, facecolor='#111213')
                ax.text(0.5, 0.5, f"Calendar plot error: {e}", ha='center', va='center', color='white')
                self.cal_canvas.draw()
            except Exception:
                pass
            self.status_var.set("Calendar plot error.")
            log_action(f"Calendar plot error: {e}")

    def save_calendar_plot(self):
        log_action("Save calendar clicked")
        if not hasattr(self, 'cal_fig') or self.cal_fig is None:
            messagebox.showwarning("No plot", "No calendar plot available to save.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".png", filetypes=[("PNG image", "*.png"), ("All files", "*.*")])
        if not path:
            return
        try:
            self.cal_fig.savefig(path, bbox_inches='tight', facecolor=self.cal_fig.get_facecolor())
            messagebox.showinfo("Saved", f"Calendar plot saved to {path}")
            log_action(f"Calendar plot saved to {path}")
        except Exception as e:
            messagebox.showerror("Save error", f"Could not save calendar plot: {e}")
            log_action(f"Calendar save error: {e}")

    # ---------- Detection and metrics ----------
    def run_detection(self):
        log_action("Run detection clicked")
        if self.df is None:
            messagebox.showwarning("No data", "Open a CSV file first.")
            return

        date_col = self.date_col_var.get()
        day_col = self.day_col_var.get()
        night_col = self.night_col_var.get()
        st_col = self.station_col_var.get()

        df = self.df.copy()
        if st_col and st_col in df.columns and self.station_combo.get() != "All":
            df = df[df[st_col] == self.station_combo.get()].copy()

        self._last_run_df = df.copy()

        if date_col not in df.columns or day_col not in df.columns:
            messagebox.showerror("Columns missing", "Make sure the CSV contains the specified date and day temperature columns.")
            return

        night_available = night_col in df.columns

        df[date_col] = pd.to_datetime(df[date_col])
        df = df.sort_values(by=date_col).reset_index(drop=True)

        t_ord = dates_to_ord(df[date_col])
        self.t_ord = t_ord
        self.dates = df[date_col]
        temp_day = df[day_col].to_numpy()
        temp_night = df[night_col].to_numpy() if night_available else None

        kwargs = dict(climatologyPeriod=[int(self.clim_start.get()), int(self.clim_end.get())],
                      pctile=int(self.pctile.get()),
                      minDuration=int(self.min_duration.get()),
                      joinAcrossGaps=bool(self.join_gaps.get()))
        if self.join_gaps.get():
            kwargs['maxGap'] = int(self.max_gap.get())

        # Start loading indicator
        self.status_var.set("Running detection (day)...")
        self._toggle_progress(True)
        self.update_idletasks()
        try:
            mhws_day, clim_day = mhw.detect(t_ord, temp_day, **kwargs)
        except Exception as e:
            messagebox.showerror("Detection error (day)", f"marineHeatWaves.detect failed for day: {e}")
            self.status_var.set("Error")
            self._toggle_progress(False)
            log_action(f"Detection error (day): {e}")
            return
        self.mhws_day = mhws_day
        self.clim_day = clim_day
        self.mhws_day_df = pd.DataFrame.from_dict(mhws_day)

        if night_available:
            self.status_var.set("Running detection (night)...")
            self.update_idletasks()
            try:
                mhws_night, clim_night = mhw.detect(t_ord, temp_night, **kwargs)
            except Exception as e:
                messagebox.showwarning("Detection warning (night)", f"marineHeatWaves.detect failed for night: {e}")
                mhws_night = {'n_events': 0}
                clim_night = {}
                log_action(f"Detection warning (night): {e}")
            self.mhws_night = mhws_night
            self.clim_night = clim_night
            self.mhws_night_df = pd.DataFrame.from_dict(mhws_night)
        else:
            self.mhws_night = {'n_events': 0}
            self.clim_night = {}
            self.mhws_night_df = pd.DataFrame()

        mask_day = self.build_event_mask(self.mhws_day, t_ord)
        mask_night = self.build_event_mask(self.mhws_night, t_ord) if night_available else np.zeros_like(mask_day)
        compound_mask = mask_day & mask_night
        compound_df = self.extract_compound_events(compound_mask, t_ord)

        if not compound_df.empty and night_available:
            thresh_day = np.array(self.clim_day.get('thresh', np.full_like(temp_day, np.nan)))
            thresh_night = np.array(self.clim_night.get('thresh', np.full_like(temp_day, np.nan)))
            intensity_day = temp_day - thresh_day
            intensity_night = temp_night - thresh_night
            for idx, row in compound_df.iterrows():
                start_ord = row['date_start'].toordinal()
                end_ord = row['date_end'].toordinal()
                mask = (t_ord >= start_ord) & (t_ord <= end_ord)
                if mask.sum() == 0:
                    mean_dn = np.nan
                    cum_dn = np.nan
                else:
                    mean_dn = np.nanmean(np.vstack([intensity_day[mask], intensity_night[mask]]), axis=0).mean()
                    cum_dn = np.nansum(np.vstack([intensity_day[mask], intensity_night[mask]]))
                compound_df.at[idx, 'mean_day_night_intensity'] = mean_dn
                compound_df.at[idx, 'cumulative_day_night_intensity'] = cum_dn
        else:
            compound_df['mean_day_night_intensity'] = np.nan
            compound_df['cumulative_day_night_intensity'] = np.nan

        self.compound_df = compound_df

        try:
            mhwBlock_day = mhw.blockAverage(t_ord, self.mhws_day, clim=self.clim_day, temp=temp_day)
            self.block_df_day = pd.DataFrame.from_dict(mhwBlock_day)
        except Exception:
            self.block_df_day = pd.DataFrame()

        if night_available:
            try:
                mhwBlock_night = mhw.blockAverage(t_ord, self.mhws_night, clim=self.clim_night, temp=temp_night)
                self.block_df_night = pd.DataFrame.from_dict(mhwBlock_night)
            except Exception:
                self.block_df_night = pd.DataFrame()
        else:
            self.block_df_night = pd.DataFrame()

        self.update_summary_and_table('day')
        self.update_summary_and_table('night')
        self.update_compound_tab()
        # Update plots for each tab safely
        try:
            self.update_tab_plot('day')
        except Exception as e:
            log_action(f"update_tab_plot(day) error: {e}")
        try:
            self.update_tab_plot('night')
        except Exception as e:
            log_action(f"update_tab_plot(night) error: {e}")
        try:
            self.update_tab_plot('compound')
        except Exception as e:
            log_action(f"update_tab_plot(compound) error: {e}")

        # Redraw calendar to inject heatwave box highlights
        self.update_calendar_plot()

        # Stop loading indicator
        self._toggle_progress(False)
        self.status_var.set("Detection complete.")
        log_action("Detection complete")

    def build_event_mask(self, mhws, t_ord):
        mask = np.zeros_like(t_ord, dtype=bool)
        if mhws is None or mhws.get('n_events', 0) == 0:
            return mask
        for i in range(mhws['n_events']):
            try:
                start = mhws['date_start'][i].toordinal()
                end = mhws['date_end'][i].toordinal()
                mask |= (t_ord >= start) & (t_ord <= end)
            except Exception:
                continue
        return mask

    def extract_compound_events(self, compound_mask, dates_ord):
        if compound_mask.sum() == 0:
            return pd.DataFrame()
        idx = np.where(compound_mask)[0]
        splits = np.where(np.diff(idx) > 1)[0]
        groups = []
        start_idx = idx[0]
        for s in splits:
            end_idx = idx[s]
            groups.append((start_idx, end_idx))
            start_idx = idx[s + 1]
        groups.append((start_idx, idx[-1]))
        rows = []
        for (i0, i1) in groups:
            start_date = date.fromordinal(int(dates_ord[i0]))
            end_date = date.fromordinal(int(dates_ord[i1]))
            duration = i1 - i0 + 1
            rows.append({'date_start': start_date, 'date_end': end_date, 'duration': duration})
        return pd.DataFrame(rows)

    # ---------- UI updates ----------
    def update_summary_and_table(self, kind):
        if kind == 'day':
            mhws = self.mhws_day or {'n_events': 0}
            df_events = self.mhws_day_df
            summary_widget = self.day_summary_widget
            table_widget = self.day_table_widget
        elif kind == 'night':
            mhws = self.mhws_night or {'n_events': 0}
            df_events = self.mhws_night_df
            summary_widget = self.night_summary_widget
            table_widget = self.night_table_widget
        else:
            mhws = {'n_events': 0}
            df_events = self.compound_df
            summary_widget = self.compound_summary_widget
            table_widget = self.compound_table_widget

        n_events = int(mhws.get('n_events', 0))
        lines = [f"Number of events: {n_events}"]
        if n_events > 0:
            try:
                mean_int = mhws.get('intensity_mean')
                max_int = mhws.get('intensity_max')
                cum_int = mhws.get('intensity_cumulative')
                durations = mhws.get('duration')
                lines.append(f"Average maximum intensity: {np.nanmean(max_int):.3f}")
                lines.append(f"Average mean intensity: {np.nanmean(mean_int):.3f}")
                lines.append(f"Average cumulative intensity: {np.nanmean(cum_int):.3f}")
                lines.append(f"Average duration: {np.nanmean(durations):.1f} days")
                lines.append(f"First event start: {mhws['date_start'][0].strftime('%Y-%m-%d')}")
            except Exception:
                lines.append("Event metrics available but could not compute summary.")
        else:
            lines.append("No events detected.")

        summary_widget.set("\n".join(lines))

        if not df_events.empty:
            table_widget.set(df_events.head(50).to_string(index=False))
        else:
            table_widget.set("No events to preview.")

    def update_compound_tab(self):
        txt = f"Day events: {int(self.mhws_day.get('n_events', 0))}\n"
        txt += f"Night events: {int(self.mhws_night.get('n_events', 0))}\n"
        txt += f"Compound events (concurrent): {len(self.compound_df)}\n"
        self.compound_summary_widget.set(txt)
        if not self.compound_df.empty:
            self.compound_table_widget.set(self.compound_df.head(50).to_string(index=False))
        else:
            self.compound_table_widget.set("No compound events detected.")

    # ---------- Plotting ----------
    def update_tab_plot(self, kind):
        log_action(f"Update plot clicked for: {kind}")
        if self._last_run_df is None:
            messagebox.showwarning("No detection data", "Run detection first to generate plots based on detected events.")
            return

        date_col = self.date_col_var.get()
        df = self._last_run_df.copy()
        df[date_col] = pd.to_datetime(df[date_col])
        df = df.sort_values(by=date_col).reset_index(drop=True)

        if kind == 'day':
            plot_choice = getattr(self, 'day_plot_choice').get()
            ys = getattr(self, 'day_year_start').get()
            ye = getattr(self, 'day_year_end').get()
            ax_fig = getattr(self, 'day_mpl_fig')
            canvas = getattr(self, 'day_mpl_canvas')
            toolbar = getattr(self, 'day_mpl_toolbar')
            block_df = self.block_df_day
            temp_col = self.day_col_var.get()
            mhws = self.mhws_day or {'n_events': 0}
            mask = self.build_event_mask(self.mhws_day, self.t_ord) if self.mhws_day else np.zeros_like(self.t_ord, dtype=bool)
        elif kind == 'night':
            plot_choice = getattr(self, 'night_plot_choice').get()
            ys = getattr(self, 'night_year_start').get()
            ye = getattr(self, 'night_year_end').get()
            ax_fig = getattr(self, 'night_mpl_fig')
            canvas = getattr(self, 'night_mpl_canvas')
            toolbar = getattr(self, 'night_mpl_toolbar')
            block_df = self.block_df_night
            temp_col = self.night_col_var.get()
            mhws = self.mhws_night or {'n_events': 0}
            mask = self.build_event_mask(self.mhws_night, self.t_ord) if self.mhws_night else np.zeros_like(self.t_ord, dtype=bool)
        else:
            plot_choice = self.compound_plot_choice.get()
            ys = self.compound_year_start.get()
            ye = self.compound_year_end.get()
            ax_fig = getattr(self, 'compound_mpl_fig')
            canvas = getattr(self, 'compound_mpl_canvas')
            toolbar = getattr(self, 'compound_mpl_toolbar')
            block_df = self.block_df_day
            temp_col = self.day_col_var.get()
            mhws = {'n_events': len(self.compound_df)}
            mask_day = self.build_event_mask(self.mhws_day, self.t_ord) if self.mhws_day else np.zeros_like(self.t_ord, dtype=bool)
            mask_night = self.build_event_mask(self.mhws_night, self.t_ord) if self.mhws_night else np.zeros_like(self.t_ord, dtype=bool)
            mask = mask_day & mask_night

        ax = ax_fig.axes[0] if ax_fig.axes else ax_fig.add_subplot(111)
        ax.clear()
        ax.set_facecolor('#111213')
        plot_data = None

        try:
            if plot_choice.lower().startswith('block'):
                if block_df.empty:
                    ax.text(0.5, 0.5, "No block averages available", ha='center', va='center', color='white')
                    plot_data = pd.DataFrame()
                else:
                    mask_year = (block_df['years_centre'] >= ys) & (block_df['years_centre'] <= ye)
                    df_plot = block_df[mask_year]
                    if df_plot.empty:
                        ax.text(0.5, 0.5, "No block averages in selected year range", ha='center', va='center', color='white')
                        plot_data = pd.DataFrame()
                    else:
                        ax.plot(df_plot['years_centre'], df_plot['count'], marker='o', linestyle='-', color='#1f6feb')
                        ax.set_title("Number of HW events by year", color='white')
                        ax.set_xlabel("Year", color='white')
                        ax.set_ylabel("Count", color='white')
                        ax.tick_params(colors='white')
                        plot_data = df_plot.copy()
            elif plot_choice.lower().startswith('category'):
                if block_df.empty:
                    ax.text(0.5, 0.5, "No block averages available", ha='center', va='center', color='white')
                    plot_data = pd.DataFrame()
                else:
                    mask_year = (block_df['years_centre'] >= ys) & (block_df['years_centre'] <= ye)
                    df_plot = block_df[mask_year]
                    if df_plot.empty:
                        ax.text(0.5, 0.5, "No block averages in selected year range", ha='center', va='center', color='white')
                        plot_data = pd.DataFrame()
                    else:
                        years = df_plot['years_centre'].to_numpy()
                        moderate = df_plot.get('moderate_days', np.zeros(len(df_plot))).to_numpy()
                        strong = df_plot.get('strong_days', np.zeros(len(df_plot))).to_numpy()
                        severe = df_plot.get('severe_days', np.zeros(len(df_plot))).to_numpy()
                        extreme = df_plot.get('extreme_days', np.zeros(len(df_plot))).to_numpy()
                        ax.bar(years, moderate, label='Moderate', color='darkorange')
                        ax.bar(years, strong, bottom=moderate, label='Strong', color='orangered')
                        bottom2 = moderate + strong
                        ax.bar(years, severe, bottom=bottom2, label='Severe', color='darkred')
                        bottom3 = bottom2 + severe
                        ax.bar(years, extreme, bottom=bottom3, label='Extreme', color='purple')
                        ax.set_title("HW category days by year", color='white')
                        ax.set_xlabel("Year", color='white')
                        ax.set_ylabel("Days", color='white')
                        ax.legend()
                        ax.tick_params(colors='white')
                        plot_data = df_plot.copy()
            elif 'heat' in plot_choice.lower():
                df2 = df.copy()
                df2['year'] = df2[date_col].dt.year
                df2['doy'] = df2[date_col].dt.dayofyear
                df2 = df2[(df2['year'] >= ys) & (df2['year'] <= ye)]
                if df2.empty:
                    ax.text(0.5, 0.5, "No data in selected year range", ha='center', va='center', color='white')
                    plot_data = pd.DataFrame()
                else:
                    pivot = df2.pivot_table(index='year', columns='doy', values=temp_col, aggfunc='mean')
                    pivot = pivot.sort_index()
                    im = ax.imshow(pivot.values, aspect='auto', origin='lower', cmap='jet')
                    ax.set_yticks(np.arange(len(pivot.index)))
                    ax.set_yticklabels(pivot.index.astype(str))
                    ax.set_xlabel('Day of year', color='white')
                    ax.set_ylabel('Year', color='white')
                    ax.set_title('Heatplot (year vs day-of-year)', color='white')
                    ax.tick_params(colors='white')
                    ax_fig.colorbar(im, ax=ax, orientation='vertical', label='Temperature')
                    plot_data = pivot.reset_index().rename_axis(columns='doy').copy()
            else:  # timeseries
                if len(df) == 0:
                    ax.text(0.5, 0.5, "No data", ha='center', va='center', color='white')
                    plot_data = pd.DataFrame()
                else:
                    dates = df[date_col]
                    temp = df[temp_col]

                    n = len(df)
                    if n > self.max_points:
                        idx = np.linspace(0, n - 1, self.max_points, dtype=int)
                        dates_ds = dates.iloc[idx]
                        temp_ds = temp.iloc[idx]
                    else:
                        dates_ds = dates
                        temp_ds = temp

                    ax.plot(dates_ds, temp_ds, label="Temperature", color='#a6c8ff', lw=0.8)
                    ax.set_ylabel("Temperature", color='white')
                    ax.set_xlabel("Date", color='white')
                    ax.set_title("Daily temperature time series", color='white')
                    ax.grid(True, color='#333333')

                    n_events = int(mhws.get('n_events', 0))
                    if n_events > 0 and isinstance(mhws, dict):
                        for i in range(n_events):
                            try:
                                start = mhws['date_start'][i]
                                end = mhws['date_end'][i]
                                ax.axvspan(start, end, color='red', alpha=0.2)
                            except Exception:
                                continue
                    ax.legend()
                    plot_data = pd.DataFrame({date_col: dates_ds, temp_col: temp_ds}).reset_index(drop=True)
        except Exception as e:
            ax.text(0.5, 0.5, f"Plot error: {e}", ha='center', va='center', color='white')
            plot_data = pd.DataFrame()
            log_action(f"Plot error for {kind}: {e}")

        canvas.draw()
        try:
            toolbar.canvas = canvas
        except Exception:
            pass

        self._last_plot_data[kind] = plot_data
        self._last_figs[kind] = ax_fig
        self.status_var.set(f"{kind.capitalize()} plot updated.")
        log_action(f"{kind.capitalize()} plot updated")

    # ---------- Save helpers ----------
    def save_plot_image(self, kind):
        fig = self._last_figs.get(kind)
        if fig is None:
            messagebox.showwarning("No plot", "No plot available to save. Click Update plot first.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".png", filetypes=[("PNG image", "*.png"), ("All files", "*.*")])
        if not path:
            return
        try:
            fig.savefig(path, bbox_inches='tight')
            messagebox.showinfo("Saved", f"Plot image saved to {path}")
            log_action(f"Plot image saved: {path}")
        except Exception as e:
            messagebox.showerror("Save error", f"Could not save plot image: {e}")
            log_action(f"Plot save error: {e}")

    def save_plot_data(self, kind):
        df = self._last_plot_data.get(kind)
        if df is None or (isinstance(df, pd.DataFrame) and df.empty):
            messagebox.showwarning("No data", "No plot data available to save. Click Update plot first.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv"), ("All files", "*.*")])
        if not path:
            return
        try:
            df.to_csv(path, index=False)
            messagebox.showinfo("Saved", f"Plot data saved to {path}")
            log_action(f"Plot data saved: {path}")
        except Exception as e:
            messagebox.showerror("Save error", f"Could not save plot data: {e}")
            log_action(f"Plot data save error: {e}")

    # ---------- Misc helpers ----------
    def save_events_for(self, kind):
        log_action(f"Save events clicked for: {kind}")
        if kind == 'day':
            df = self.mhws_day_df
        elif kind == 'night':
            df = self.mhws_night_df
        else:
            df = self.compound_df
        self.save_df(df)

    def save_block_for(self, kind):
        log_action(f"Save block clicked for: {kind}")
        if kind == 'day':
            self.save_df(self.block_df_day)
        elif kind == 'night':
            self.save_df(self.block_df_night)
        else:
            self.save_df(self.block_df_day)

    def save_compound_summary(self):
        log_action("Save compound summary clicked")
        if self.compound_df is None or self.compound_df.empty:
            messagebox.showwarning("No data", "No compound events to save.")
            return
        self.save_df(self.compound_df)

    def save_df(self, df):
        log_action("Save df clicked")
        if df is None or (isinstance(df, pd.DataFrame) and df.empty):
            messagebox.showwarning("No data", "No data to save.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if not path:
            return
        try:
            df.to_csv(path, index=False)
            messagebox.showinfo("Saved", f"Saved to {path}")
            log_action(f"Saved dataframe to {path}")
        except Exception as e:
            messagebox.showerror("Save error", f"Could not save data: {e}")
            log_action(f"Save df error: {e}")

    # ---------- Printout previews ----------
    def printout_previews(self):
        log_action("Printout previews clicked")
        parts = []
        parts.append("=== Data preview ===\n")
        parts.append(self.preview_widget.get())
        parts.append("\n=== Selected station Stats ===\n")
        parts.append(self.describe_widget.get())
        parts.append("\n=== Day summary ===\n")
        parts.append(self.day_summary_widget.get())
        parts.append("\n=== Day events preview ===\n")
        parts.append(self.day_table_widget.get())
        parts.append("\n=== Night summary ===\n")
        parts.append(self.night_summary_widget.get())
        parts.append("\n=== Night events preview ===\n")
        parts.append(self.night_table_widget.get())
        parts.append("\n=== Compound summary ===\n")
        parts.append(self.compound_summary_widget.get())
        parts.append("\n=== Compound events preview ===\n")
        parts.append(self.compound_table_widget.get())

        content = "\n".join(parts)

        try:
            fd, tmp_path = tempfile.mkstemp(suffix=".txt", prefix="mhw_previews_")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
            open_file_with_default_app(tmp_path)
            self.status_var.set("Preview printout opened in default text viewer.")
            log_action("Printout previews opened")
        except Exception as e:
            messagebox.showerror("Printout error", f"Could not create printout: {e}")
            log_action(f"Printout error: {e}")

    # ---------- Additional data recalculation ----------
    def recalculate_with_additional(self):
        log_action("Recalculate with additional data clicked")
        if not hasattr(self, 'additional_df') or self.additional_df is None:
            messagebox.showwarning("No additional data", "Load additional data first.")
            return
        if self.df is None:
            messagebox.showwarning("No base data", "Load historical data first in Data & Run tab.")
            return

        sel_station = self.add_station_combo.get() if hasattr(self, 'add_station_combo') else "All"
        st_col = self.add_station_col.get()
        date_col = self.add_date_col.get()
        day_col = self.add_day_col.get()
        night_col = self.add_night_col.get()

        # Merge additional data into a copy of the historical dataset for the selected station
        base = self.df.copy()
        add = self.additional_df.copy()
        try:
            add[date_col] = pd.to_datetime(add[date_col])
            base[date_col] = pd.to_datetime(base[date_col])
        except Exception:
            pass

        if st_col and st_col in base.columns and sel_station != "All":
            base_sel = base[base[st_col] == sel_station].copy()
        else:
            base_sel = base.copy()

        # Prefer additional data values for overlapping dates; append non-overlapping
        try:
            merged = pd.concat([base_sel.set_index(date_col), add.set_index(date_col)], axis=0, sort=False)
            merged = merged[~merged.index.duplicated(keep='last')].reset_index()
        except Exception:
            # fallback: simple append
            merged = pd.concat([base_sel, add], axis=0, sort=False).drop_duplicates()

        # Temporarily set as last run df and run detection on merged
        prev_last = self._last_run_df
        self._last_run_df = merged.copy()
        self._temp_additional_df = merged.copy()
        # Run detection on merged dataset (non-destructive) using reference period from additional data tab
        try:
            self.run_detection_on_additional_df(merged)
            messagebox.showinfo("Recalculation complete", "Detection recalculated using additional data.")
            log_action("Recalculation with additional data complete")
            # Update preview panel and plotting controls automatically
            try:
                # populate years for additional calendar plotting
                years = sorted(pd.to_datetime(merged[date_col]).dt.year.dropna().unique().tolist(), reverse=True)
                years_str = [str(int(y)) for y in years]
                if years_str:
                    self.plot_cal_year_combo.configure(values=years_str)
                    self.plot_cal_year_var.set(years_str[0])
                    self.plot_cal_year_combo.update()
                # update preview widgets
                self._update_additional_preview_widgets()
                # update plots
                self.update_additional_calendar_plot()
                self.update_additional_category_plot()
                self.update_additional_timeseries()
            except Exception:
                pass
        except Exception as e:
            messagebox.showerror("Recalculation error", f"Could not recalculate: {e}")
            log_action(f"Recalculation error: {e}")
        finally:
            # restore last run df to original if needed
            self._last_run_df = prev_last

    def run_detection_on_additional_df(self, df):
        """Run detection on a provided additional dataframe (used for additional data recalculation)."""
        if df is None or df.empty:
            raise ValueError("Empty dataframe provided for detection.")
        # Use parameters from additional data tab
        date_col = self.add_date_col.get()
        day_col = self.add_day_col.get()
        night_col = self.add_night_col.get()

        if date_col not in df.columns or day_col not in df.columns:
            raise ValueError("Required columns missing in provided dataframe.")

        df = df.copy()
        df[date_col] = pd.to_datetime(df[date_col])
        df = df.sort_values(by=date_col).reset_index(drop=True)

        t_ord = dates_to_ord(df[date_col])
        temp_day = df[day_col].to_numpy()
        night_available = night_col in df.columns
        temp_night = df[night_col].to_numpy() if night_available else None

        kwargs = dict(climatologyPeriod=[int(self.add_ref_start.get()), int(self.add_ref_end.get())],
                      pctile=int(self.add_pctile.get()),
                      minDuration=int(self.add_min_duration.get()),
                      joinAcrossGaps=bool(self.add_join_gaps.get()))
        if self.add_join_gaps.get():
            kwargs['maxGap'] = int(self.add_max_gap.get())

        mhws_day, clim_day = mhw.detect(t_ord, temp_day, **kwargs)
        mhws_night = {'n_events': 0}
        clim_night = {}
        if night_available:
            try:
                mhws_night, clim_night = mhw.detect(t_ord, temp_night, **kwargs)
            except Exception:
                mhws_night = {'n_events': 0}
                clim_night = {}

        # compute compound mask and events
        mask_day = self.build_event_mask(mhws_day, t_ord)
        mask_night = self.build_event_mask(mhws_night, t_ord) if night_available else np.zeros_like(mask_day)
        compound_mask = mask_day & mask_night
        compound_df = self.extract_compound_events(compound_mask, t_ord)

        # store results in temporary attributes for plotting and preview
        self._temp_mhws_day = mhws_day
        self._temp_clim_day = clim_day
        self._temp_mhws_night = mhws_night
        self._temp_clim_night = clim_night
        self._temp_compound_df = compound_df
        self._temp_additional_df = df.copy()
        self._temp_t_ord = t_ord

    def _update_additional_preview_widgets(self):
        # Update events preview and stats for additional data
        try:
            parts = []
            if self._temp_mhws_day:
                parts.append("=== Daytime events ===")
                try:
                    df_day = pd.DataFrame.from_dict(self._temp_mhws_day)
                    parts.append(df_day.head(50).to_string(index=False))
                except Exception:
                    parts.append("Could not format day events.")
            else:
                parts.append("No daytime events detected.")

            if self._temp_mhws_night:
                parts.append("\n=== Nighttime events ===")
                try:
                    df_n = pd.DataFrame.from_dict(self._temp_mhws_night)
                    parts.append(df_n.head(50).to_string(index=False))
                except Exception:
                    parts.append("Could not format night events.")
            else:
                parts.append("\nNo nighttime events detected.")

            if self._temp_compound_df is not None and not self._temp_compound_df.empty:
                parts.append("\n=== Compound events ===")
                parts.append(self._temp_compound_df.head(50).to_string(index=False))
            else:
                parts.append("\nNo compound events detected.")

            self.add_events_widget.set("\n".join(parts))
        except Exception as e:
            self.add_events_widget.set(f"Could not prepare events preview: {e}")

        # Stats
        try:
            stats_lines = []
            # Day stats
            if self._temp_mhws_day and self._temp_mhws_day.get('n_events', 0) > 0:
                md = self._temp_mhws_day
                try:
                    stats_lines.append("Daytime stats:")
                    stats_lines.append(f"Number events: {int(md.get('n_events', 0))}")
                    stats_lines.append(f"Avg max intensity: {np.nanmean(md.get('intensity_max', [np.nan])):.3f}")
                except Exception:
                    stats_lines.append("Daytime stats: could not compute metrics.")
            else:
                stats_lines.append("Daytime: No events")

            # Night stats
            if self._temp_mhws_night and self._temp_mhws_night.get('n_events', 0) > 0:
                mn = self._temp_mhws_night
                try:
                    stats_lines.append("\nNighttime stats:")
                    stats_lines.append(f"Number events: {int(mn.get('n_events', 0))}")
                    stats_lines.append(f"Avg max intensity: {np.nanmean(mn.get('intensity_max', [np.nan])):.3f}")
                except Exception:
                    stats_lines.append("Nighttime stats: could not compute metrics.")
            else:
                stats_lines.append("\nNighttime: No events")

            # Compound stats
            if self._temp_compound_df is not None and not self._temp_compound_df.empty:
                stats_lines.append("\nCompound stats:")
                stats_lines.append(f"Number compound events: {len(self._temp_compound_df)}")
            else:
                stats_lines.append("\nCompound: No events")

            self.add_stats_widget.set("\n".join(stats_lines))
        except Exception as e:
            self.add_stats_widget.set(f"Could not prepare stats: {e}")

    # ---------- Additional data plotting helpers ----------
    def update_additional_calendar_plot(self, *args):
        try:
            fig = self.add_cal_fig
            fig.clf()
            ax = fig.add_subplot(111, facecolor='#111213')

            if not hasattr(self, '_temp_additional_df') or self._temp_additional_df is None:
                ax.text(0.5, 0.5, "No additional detection results. Recalculate first.", ha='center', va='center', color='white')
                self.add_cal_canvas.draw()
                return

            df = self._temp_additional_df.copy()
            date_col = self.add_date_col.get()
            temp_col = self.add_day_col.get() if self.plot_cal_temp_var.get().startswith("Day") else self.add_night_col.get()
            if self.plot_cal_temp_var.get().startswith("All"):
                # use day column for values but highlight all events
                temp_col = self.add_day_col.get()

            if temp_col not in df.columns:
                ax.text(0.5, 0.5, f"Temperature column '{temp_col}' not in additional data.", ha='center', va='center', color='white')
                self.add_cal_canvas.draw()
                return

            selected_year = None
            try:
                selected_year = int(self.plot_cal_year_var.get())
            except Exception:
                pass

            if selected_year is None:
                ax.text(0.5, 0.5, "Select a year for the calendar plot.", ha='center', va='center', color='white')
                self.add_cal_canvas.draw()
                return

            df[date_col] = pd.to_datetime(df[date_col])
            df_year = df[df[date_col].dt.year == selected_year].copy()
            if df_year.empty:
                ax.text(0.5, 0.5, f"No additional data for year {selected_year}", ha='center', va='center', color='white')
                self.add_cal_canvas.draw()
                return

            daily = df_year.set_index(date_col)[temp_col].resample('D').mean()

            # Use temporary mhws results to highlight heatwave days
            hw_dates = set()
            # If "All (highlight all)" selected, combine day/night/compound
            if self.plot_cal_temp_var.get().startswith("All"):
                for mhws in (self._temp_mhws_day, self._temp_mhws_night):
                    if mhws and mhws.get('n_events', 0) > 0:
                        for i in range(mhws['n_events']):
                            curr = pd.Timestamp(mhws['date_start'][i])
                            end_ts = pd.Timestamp(mhws['date_end'][i])
                            while curr <= end_ts:
                                if curr.year == selected_year:
                                    hw_dates.add(curr)
                                curr += pd.Timedelta(days=1)
                # also include compound events explicitly
                if self._temp_compound_df is not None and not self._temp_compound_df.empty:
                    for _, row in self._temp_compound_df.iterrows():
                        s = pd.Timestamp(row['date_start'])
                        e = pd.Timestamp(row['date_end'])
                        curr = s
                        while curr <= e:
                            if curr.year == selected_year:
                                hw_dates.add(curr)
                            curr += pd.Timedelta(days=1)
            else:
                mhws = self._temp_mhws_night if self.plot_cal_temp_var.get().startswith("Night") else self._temp_mhws_day
                if mhws and mhws.get('n_events', 0) > 0:
                    for i in range(mhws['n_events']):
                        curr = pd.Timestamp(mhws['date_start'][i])
                        end_ts = pd.Timestamp(mhws['date_end'][i])
                        while curr <= end_ts:
                            if curr.year == selected_year:
                                hw_dates.add(curr)
                            curr += pd.Timedelta(days=1)

            first_day = pd.Timestamp(year=selected_year, month=1, day=1)

            if calplot is not None:
                calplot.yearplot(daily, year=selected_year, ax=ax, cmap='Spectral_r', fillcolor='#2b2f33', linewidth=1, linecolor='#1f2326')
                for date_val, val in daily.items():
                    if pd.isna(val): continue
                    date_ts = pd.Timestamp(date_val)
                    week = (date_ts - first_day + pd.Timedelta(first_day.dayofweek, unit='d')).days // 7
                    dow = date_ts.dayofweek
                    ax.text(week + 0.5, dow + 0.5, str(date_ts.day), ha='center', va='center', color='#222222', fontsize=7, fontweight='bold')
                    if date_ts in hw_dates:
                        rect = plt.Rectangle((week, dow), 1, 1, fill=False, edgecolor='red', linewidth=3)
                        ax.add_patch(rect)
                if len(ax.collections) > 0:
                    cbar = fig.colorbar(ax.collections[0], ax=ax, orientation='vertical', fraction=0.046, pad=0.04)
                    cbar.ax.tick_params(colors='white')
                    cbar.set_label('Temperature', color='white')
                ax.set_title(f"{selected_year} additional data {temp_col}", color='white')
                ax.tick_params(colors='white')
            else:
                df_year['doy'] = df_year[date_col].dt.dayofyear
                pivot = df_year.pivot_table(index=df_year[date_col].dt.month, columns='doy', values=temp_col, aggfunc='mean')
                if pivot.empty:
                    ax.text(0.5, 0.5, "Not enough data for calendar heatmap", ha='center', va='center', color='white')
                else:
                    im = ax.imshow(pivot.fillna(np.nan).values, aspect='auto', origin='lower', cmap='Spectral_r')
                    ax.set_yticks(np.arange(len(pivot.index)))
                    ax.set_yticklabels(pivot.index.astype(str), color='white')
                    ax.set_xlabel('Day of year', color='white')
                    ax.set_title(f"{selected_year} additional {temp_col}", color='white')
                    fig.colorbar(im, ax=ax, orientation='vertical', label='Temperature')
                    for date_val in df_year[date_col]:
                        doy = date_val.dayofyear - 1
                        try:
                            row_idx = list(pivot.index).index(date_val.month)
                            ax.text(doy, row_idx, str(date_val.day), ha='center', va='center', color='#222222', fontsize=6, fontweight='bold')
                            if pd.Timestamp(date_val) in hw_dates:
                                rect = plt.Rectangle((doy-0.5, row_idx-0.5), 1, 1, fill=False, edgecolor='red', linewidth=3)
                                ax.add_patch(rect)
                        except ValueError:
                            pass

            self.add_cal_canvas.draw()
            self.status_var.set("Additional calendar updated.")
        except Exception as e:
            try:
                self.add_cal_fig.clf()
                ax = self.add_cal_fig.add_subplot(111, facecolor='#111213')
                ax.text(0.5, 0.5, f"Calendar error: {e}", ha='center', va='center', color='white')
                self.add_cal_canvas.draw()
            except Exception:
                pass
            log_action(f"Additional calendar error: {e}")

    def update_additional_category_plot(self, *args):
        try:
            fig = self.add_cat_fig
            fig.clf()
            ax = fig.add_subplot(111, facecolor='#111213')

            if not hasattr(self, '_temp_additional_df') or self._temp_additional_df is None:
                ax.text(0.5, 0.5, "No additional detection results. Recalculate first.", ha='center', va='center', color='white')
                self.add_cat_canvas.draw()
                return

            if not self.plot_category_toggle.get():
                ax.text(0.5, 0.5, "Category plot disabled (toggle off).", ha='center', va='center', color='white')
                self.add_cat_canvas.draw()
                return

            # Try to compute blockAverage for additional data
            try:
                df = self._temp_additional_df.copy()
                date_col = self.add_date_col.get()
                df[date_col] = pd.to_datetime(df[date_col])
                t_ord = self._temp_t_ord
                temp_day = df[self.add_day_col.get()].to_numpy()
                mhws_day = self._temp_mhws_day
                clim_day = self._temp_clim_day
                try:
                    block = mhw.blockAverage(t_ord, mhws_day, clim=clim_day, temp=temp_day)
                    block_df = pd.DataFrame.from_dict(block)
                except Exception:
                    block_df = pd.DataFrame()
            except Exception:
                block_df = pd.DataFrame()

            if block_df.empty:
                ax.text(0.5, 0.5, "No block/category data available for additional dataset.", ha='center', va='center', color='white')
                self.add_cat_canvas.draw()
                return

            years = block_df['years_centre'].to_numpy()
            moderate = block_df.get('moderate_days', np.zeros(len(block_df))).to_numpy()
            strong = block_df.get('strong_days', np.zeros(len(block_df))).to_numpy()
            severe = block_df.get('severe_days', np.zeros(len(block_df))).to_numpy()
            extreme = block_df.get('extreme_days', np.zeros(len(block_df))).to_numpy()
            ax.bar(years, moderate, label='Moderate', color='darkorange')
            ax.bar(years, strong, bottom=moderate, label='Strong', color='orangered')
            bottom2 = moderate + strong
            ax.bar(years, severe, bottom=bottom2, label='Severe', color='darkred')
            bottom3 = bottom2 + severe
            ax.bar(years, extreme, bottom=bottom3, label='Extreme', color='purple')
            ax.set_title("Additional data HW category days by year", color='white')
            ax.set_xlabel("Year", color='white')
            ax.set_ylabel("Days", color='white')
            ax.legend()
            ax.tick_params(colors='white')
            self.add_cat_canvas.draw()
            self.status_var.set("Additional category plot updated.")
        except Exception as e:
            try:
                self.add_cat_fig.clf()
                ax = self.add_cat_fig.add_subplot(111, facecolor='#111213')
                ax.text(0.5, 0.5, f"Category plot error: {e}", ha='center', va='center', color='white')
                self.add_cat_canvas.draw()
            except Exception:
                pass
            log_action(f"Additional category error: {e}")

    def update_additional_timeseries(self):
        try:
            fig = self.add_ts_fig
            fig.clf()
            ax = fig.add_subplot(111, facecolor='#111213')

            if not hasattr(self, '_temp_additional_df') or self._temp_additional_df is None:
                ax.text(0.5, 0.5, "No additional detection results. Recalculate first.", ha='center', va='center', color='white')
                self.add_ts_canvas.draw()
                return

            df = self._temp_additional_df.copy()
            date_col = self.add_date_col.get()
            temp_col = self.add_day_col.get()
            df[date_col] = pd.to_datetime(df[date_col])
            start_s = self.plot_ts_start.get().strip()
            end_s = self.plot_ts_end.get().strip()
            try:
                if start_s:
                    start_dt = pd.to_datetime(start_s)
                else:
                    start_dt = df[date_col].min()
                if end_s:
                    end_dt = pd.to_datetime(end_s)
                else:
                    end_dt = df[date_col].max()
            except Exception:
                start_dt = df[date_col].min()
                end_dt = df[date_col].max()

            df_range = df[(df[date_col] >= start_dt) & (df[date_col] <= end_dt)].copy()
            if df_range.empty:
                ax.text(0.5, 0.5, "No data in selected date range.", ha='center', va='center', color='white')
                self.add_ts_canvas.draw()
                return

            ax.plot(df_range[date_col], df_range[temp_col], color='#a6c8ff', lw=0.8)
            ax.set_title("Additional data timeseries", color='white')
            ax.set_xlabel("Date", color='white')
            ax.set_ylabel("Temperature", color='white')
            ax.grid(True, color='#333333')

            # Mark heatwave strips using temporary detection results (day, night, compound)
            # Day
            mhws_day = self._temp_mhws_day
            if mhws_day and mhws_day.get('n_events', 0) > 0:
                for i in range(mhws_day['n_events']):
                    try:
                        start = pd.Timestamp(mhws_day['date_start'][i])
                        end = pd.Timestamp(mhws_day['date_end'][i])
                        if end < start_dt or start > end_dt:
                            continue
                        ax.axvspan(max(start, start_dt), min(end, end_dt), color='red', alpha=0.18)
                    except Exception:
                        continue
            # Night (outline with different color)
            mhws_night = self._temp_mhws_night
            if mhws_night and mhws_night.get('n_events', 0) > 0:
                for i in range(mhws_night['n_events']):
                    try:
                        start = pd.Timestamp(mhws_night['date_start'][i])
                        end = pd.Timestamp(mhws_night['date_end'][i])
                        if end < start_dt or start > end_dt:
                            continue
                        ax.axvspan(max(start, start_dt), min(end, end_dt), color='orange', alpha=0.12)
                    except Exception:
                        continue
            # Compound (stronger highlight)
            if self._temp_compound_df is not None and not self._temp_compound_df.empty:
                for _, row in self._temp_compound_df.iterrows():
                    try:
                        start = pd.Timestamp(row['date_start'])
                        end = pd.Timestamp(row['date_end'])
                        if end < start_dt or start > end_dt:
                            continue
                        ax.axvspan(max(start, start_dt), min(end, end_dt), color='magenta', alpha=0.22)
                    except Exception:
                        continue

            self.add_ts_canvas.draw()
            self.status_var.set("Additional timeseries updated.")
        except Exception as e:
            try:
                self.add_ts_fig.clf()
                ax = self.add_ts_fig.add_subplot(111, facecolor='#111213')
                ax.text(0.5, 0.5, f"Timeseries error: {e}", ha='center', va='center', color='white')
                self.add_ts_canvas.draw()
            except Exception:
                pass
            log_action(f"Additional timeseries error: {e}")

    def save_additional_plot(self, which):
        try:
            if which == 'calendar':
                fig = self.add_cal_fig
            elif which == 'category':
                fig = self.add_cat_fig
            else:
                fig = self.add_ts_fig
            if fig is None:
                messagebox.showwarning("No plot", "No plot available to save.")
                return
            path = filedialog.asksaveasfilename(defaultextension=".png", filetypes=[("PNG image", "*.png"), ("All files", "*.*")])
            if not path:
                return
            fig.savefig(path, bbox_inches='tight', facecolor=fig.get_facecolor())
            messagebox.showinfo("Saved", f"{which.capitalize()} plot saved to {path}")
            log_action(f"Saved additional {which} plot to {path}")
        except Exception as e:
            messagebox.showerror("Save error", f"Could not save {which} plot: {e}")
            log_action(f"Save additional {which} plot error: {e}")

    def save_additional_events(self):
        try:
            if not hasattr(self, '_temp_mhws_day') or self._temp_mhws_day is None:
                messagebox.showwarning("No events", "No detected events from additional data. Recalculate first.")
                return
            df_day = pd.DataFrame.from_dict(self._temp_mhws_day) if self._temp_mhws_day else pd.DataFrame()
            df_night = pd.DataFrame.from_dict(self._temp_mhws_night) if self._temp_mhws_night else pd.DataFrame()
            df_compound = self._temp_compound_df.copy() if self._temp_compound_df is not None else pd.DataFrame()

            # Save into a single Excel with multiple sheets
            path = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel workbook", "*.xlsx")])
            if not path:
                return
            try:
                with pd.ExcelWriter(path, engine='openpyxl') as writer:
                    if not df_day.empty:
                        df_day.to_excel(writer, sheet_name='day_events', index=False)
                    if not df_night.empty:
                        df_night.to_excel(writer, sheet_name='night_events', index=False)
                    if not df_compound.empty:
                        df_compound.to_excel(writer, sheet_name='compound_events', index=False)
                messagebox.showinfo("Saved", f"Additional detected events saved to {path}")
                log_action(f"Saved additional detected events to {path}")
            except Exception as e:
                messagebox.showerror("Save error", f"Could not save additional events: {e}")
                log_action(f"Save additional events error: {e}")
        except Exception as e:
            messagebox.showerror("Save error", f"Could not save additional events: {e}")
            log_action(f"Save additional events error: {e}")

    # ---------- Batch run ----------
    def start_batch_run(self):
        log_action("Start batch run clicked")
        if not hasattr(self, 'batch_df') or self.batch_df is None:
            messagebox.showwarning("No batch file", "Load a multi-station CSV first.")
            return
        if self._batch_thread and self._batch_thread.is_alive():
            messagebox.showwarning("Batch running", "A batch run is already in progress.")
            return

        # Reset cancel flag and start thread
        self._batch_cancelled.clear()
        self._batch_thread = threading.Thread(target=self._batch_run_worker, daemon=True)
        self._batch_thread.start()
        self.batch_log_widget.set("Batch run started...\n")
        self.status_var.set("Batch run started.")
        self._toggle_progress(True)
        log_action("Batch run thread started")

    def cancel_batch_run(self):
        log_action("Cancel batch run clicked")
        if self._batch_thread and self._batch_thread.is_alive():
            self._batch_cancelled.set()
            self.batch_log_widget.set(self.batch_log_widget.get() + "\nCancellation requested...")
            self.status_var.set("Batch cancellation requested.")
            log_action("Batch cancellation requested")
        else:
            messagebox.showinfo("No batch running", "No active batch run to cancel.")

    def _batch_run_worker(self):
        """Worker thread to process batch detection per station and save results into Excel files."""
        try:
            df = self.batch_df.copy()
            st_col = self.batch_station_col.get()
            date_col = self.date_col_var.get()
            day_col = self.day_col_var.get()
            night_col = self.night_col_var.get()

            if st_col not in df.columns:
                self.batch_log_widget.set("Station column not found in batch file.")
                self._toggle_progress(False)
                return

            # Ensure date parsing
            try:
                df[date_col] = pd.to_datetime(df[date_col])
            except Exception:
                pass

            stations = sorted(df[st_col].dropna().unique().tolist())
            total = len(stations)
            self.batch_log_widget.set(f"Found {total} stations. Beginning processing...\n")
            log_action(f"Batch run: {total} stations")

            # Prepare output writers: create new workbook every 50 stations
            writers = []
            writer = None
            file_count = 0
            sheet_count = 0
            out_files = []

            def new_writer():
                nonlocal writer, file_count, sheet_count
                file_count += 1
                sheet_count = 0
                out_path = filedialog.asksaveasfilename(defaultextension=".xlsx", title=f"Save batch results - file {file_count}", filetypes=[("Excel workbook", "*.xlsx")])
                if not out_path:
                    raise RuntimeError("User cancelled save dialog for batch output.")
                # ensure extension
                if not out_path.lower().endswith(".xlsx"):
                    out_path += ".xlsx"
                writer = pd.ExcelWriter(out_path, engine='openpyxl', mode='w')
                out_files.append(out_path)
                log_action(f"Batch output file created: {out_path}")
                return writer

            try:
                writer = new_writer()
            except Exception as e:
                self.batch_log_widget.set(f"Batch aborted: {e}")
                self._toggle_progress(False)
                return

            processed = 0
            for i, station in enumerate(stations):
                if self._batch_cancelled.is_set():
                    self.batch_log_widget.set(self.batch_log_widget.get() + "\nBatch cancelled by user.")
                    log_action("Batch cancelled by user")
                    break

                self.batch_log_widget.set(self.batch_log_widget.get() + f"\nProcessing station {i+1}/{total}: {station}")
                log_action(f"Batch processing station: {station}")

                # subset data
                sub = df[df[st_col] == station].copy()
                if sub.empty:
                    self.batch_log_widget.set(self.batch_log_widget.get() + "\nNo data for station, skipping.")
                    continue

                # run detection safely
                try:
                    sub = sub.sort_values(by=date_col).reset_index(drop=True)
                    t_ord = dates_to_ord(sub[date_col])
                    temp_day = sub[day_col].to_numpy()
                    temp_night = sub[night_col].to_numpy() if night_col in sub.columns else None

                    kwargs = dict(climatologyPeriod=[int(self.clim_start.get()), int(self.clim_end.get())],
                                  pctile=int(self.pctile.get()),
                                  minDuration=int(self.min_duration.get()),
                                  joinAcrossGaps=bool(self.join_gaps.get()))
                    if self.join_gaps.get():
                        kwargs['maxGap'] = int(self.max_gap.get())

                    mhws_day, clim_day = mhw.detect(t_ord, temp_day, **kwargs)
                    mhws_day_df = pd.DataFrame.from_dict(mhws_day)
                    mhwBlock_day = {}
                    try:
                        mhwBlock_day = mhw.blockAverage(t_ord, mhws_day, clim=clim_day, temp=temp_day)
                        block_df_day = pd.DataFrame.from_dict(mhwBlock_day)
                    except Exception:
                        block_df_day = pd.DataFrame()

                    # Save station results into current writer
                    sheet_name = str(station)[:31]  # Excel sheet name limit
                    # If sheet_count >= 50, create a new workbook
                    if sheet_count >= 50:
                        try:
                            writer.close()
                        except Exception:
                            pass
                        try:
                            writer = new_writer()
                        except Exception as e:
                            self.batch_log_widget.set(self.batch_log_widget.get() + f"\nBatch aborted while creating new file: {e}")
                            break

                    # Write event and block data to separate sheets per station
                    try:
                        mhws_day_df.to_excel(writer, sheet_name=f"{sheet_name}_events", index=False)
                        block_df_day.to_excel(writer, sheet_name=f"{sheet_name}_blocks", index=False)
                    except Exception as e:
                        # If writing fails, log and continue
                        self.batch_log_widget.set(self.batch_log_widget.get() + f"\nFailed to write sheets for {station}: {e}")
                        log_action(f"Failed to write sheets for {station}: {e}")

                    sheet_count += 1
                    processed += 1
                    self.batch_log_widget.set(self.batch_log_widget.get() + f"\nCompleted {station} ({processed}/{total})")
                except Exception as e:
                    self.batch_log_widget.set(self.batch_log_widget.get() + f"\nError processing {station}: {e}")
                    log_action(f"Error processing {station}: {e}")
                # small sleep to allow UI updates and cancellation checks
                time.sleep(0.1)

            # finalize writer
            try:
                if writer:
                    writer.close()
            except Exception:
                pass

            self.batch_log_widget.set(self.batch_log_widget.get() + f"\nBatch run finished. Files created:\n" + "\n".join(out_files))
            self.status_var.set("Batch run finished.")
            self._toggle_progress(False)
            log_action("Batch run finished")
        except Exception as e:
            self.batch_log_widget.set(self.batch_log_widget.get() + f"\nBatch run error: {e}")
            self.status_var.set("Batch run error.")
            self._toggle_progress(False)
            log_action(f"Batch run error: {e}")

if __name__ == "__main__":
    try:
        app = MHWApp()
        app.mainloop()
    except Exception as e:
        logging.exception("Unhandled exception in mainloop: %s", e)
        raise