# This dashboard was developed by Aiden Ware Bosanko
import serial
import numpy as np
import tkinter as tk
import tkinter.font as tkfont
from PIL import Image, ImageDraw, ImageFont
import csv
from datetime import datetime
import os
import random
from collections import deque
import time
from matplotlib.figure import Figure
from matplotlib.ticker import MaxNLocator
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# ==========================================
# SPLASH TUNING KNOBS
# ==========================================
W, H = 960, 600
FONT_PX = 6
FRAME_MS = 30
RAIN_COLOR = "#8c8c8c"
HEAD_COLOR = "#ffffff"
EDGE_COLOR = "#ffffff"
MAX_RED = 42

EDGE_X, EDGE_Y = 2, 1
HALO_X, HALO_Y = 4, 2

T_NAME = 110
T_CLEAR_1 = 250
T_TITLE_2 = 310
T_RED_START, T_RED_END = 335, 430
T_EXIT = 475
RED_EASE = 1.5


# ==========================================
# Text -> grid mask
# ==========================================
def load_font(size):
    for path in ("C:/Windows/Fonts/impact.ttf", "C:/Windows/Fonts/arialbd.ttf"):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    return ImageFont.load_default()


def dilate(m, ry, rx, pad=False):
    h, w = m.shape
    p = np.pad(m, ((ry, ry), (rx, rx)), constant_values=pad)
    out = np.zeros_like(m)
    for dy in range(2 * ry + 1):
        for dx in range(2 * rx + 1):
            out |= p[dy:dy + h, dx:dx + w]
    return out


def build_banner(lines, cols, rows, cw, ch):
    text = "\n".join(lines)
    img_w, img_h = cols * cw, rows * ch
    img = Image.new("L", (img_w, img_h), 0)
    draw = ImageDraw.Draw(img)

    size = 300
    while size > 20:
        font = load_font(size)
        box = draw.multiline_textbbox((0, 0), text, font=font, align="center", spacing=10)
        if (box[2] - box[0]) <= img_w * 0.9 and (box[3] - box[1]) <= img_h * 0.8:
            break
        size -= 4
    bw, bh = box[2] - box[0], box[3] - box[1]
    draw.multiline_text(
        ((img_w - bw) / 2 - box[0], (img_h - bh) / 2 - box[1]),
        text, font=font, fill=255, align="center", spacing=10,
    )

    small = img.resize((cols, rows), Image.BOX)
    filled = np.asarray(small) > 90

    edge = filled & dilate(~filled, EDGE_Y, EDGE_X, pad=True)
    blocked = filled | dilate(filled, HALO_Y, HALO_X)
    return edge, blocked


# ==========================================
# Splash screen
# ==========================================
class WaterfallSplash:
    def __init__(self, root, on_complete):
        self.root = root
        self.on_complete = on_complete

        self.font = tkfont.Font(family="Courier New", size=-FONT_PX, weight="bold")
        self.cw = max(1, self.font.measure("#"))
        self.ch = max(1, self.font.metrics("linespace"))
        self.cols = W // self.cw
        self.rows = H // self.ch
        self.width = self.cols * self.cw
        self.height = self.rows * self.ch

        self.canvas = tk.Canvas(root, width=self.width, height=self.height,
                                bg="black", highlightthickness=0)
        self.canvas.pack()

        self.num_strips = 24
        self.strips = []
        sh = self.height / self.num_strips
        for i in range(self.num_strips):
            self.strips.append(self.canvas.create_rectangle(
                0, i * sh, self.width, (i + 1) * sh + 1, fill="#000000", outline=""))

        def make_layer(color):
            return [self.canvas.create_text(0, r * self.ch, anchor="nw", text="",
                                            fill=color, font=self.font)
                    for r in range(self.rows)]
        self.dim_rows = make_layer(RAIN_COLOR)
        self.head_rows = make_layer(HEAD_COLOR)
        self.edge_rows = make_layer(EDGE_COLOR)
        self.cache = {"dim": [None] * self.rows,
                      "head": [None] * self.rows,
                      "edge": [None] * self.rows}

        n = self.cols
        S = self.rows / 40.0
        self.S = S
        self.rr = np.arange(self.rows)[:, None]
        self.delay = np.random.randint(0, 61, n)
        self.speed = np.random.uniform(0.9, 1.5, n) * S
        self.tail = (np.random.randint(24, 41, n) * S).astype(int)
        self.gap = (np.random.randint(4, 13, n) * S).astype(int)
        self.cyc = self.tail + self.gap

        self.banner = None
        self.clear_t0 = None
        self.frame = 0
        self.animate()

    def start_banner(self, lines):
        self.banner = build_banner(lines, self.cols, self.rows, self.cw, self.ch)
        self.t0 = self.frame
        self.rd = np.random.randint(0, 25, self.cols)
        self.rs = np.random.uniform(0.7, 1.1, self.cols) * self.S
        self.clear_t0 = None

    def start_clear(self):
        self.clear_t0 = self.frame
        self.cd = np.random.randint(0, 15, self.cols)
        self.cs = np.random.uniform(1.2, 1.9, self.cols) * self.S

    def push(self, ids, key, mask):
        b = np.where(mask, 35, 32).astype(np.uint8)
        cache = self.cache[key]
        for r in range(self.rows):
            s = b[r].tobytes().decode("ascii")
            if s != cache[r]:
                cache[r] = s
                self.canvas.itemconfig(ids[r], text=s)

    def render(self):
        f, rr = self.frame, self.rr
        d = ((f - self.delay) * self.speed)[None, :] - rr
        dm = np.floor(d).astype(np.int64) % self.cyc[None, :]
        rain = (d >= 0) & (dm < self.tail[None, :])
        bright = rain & (dm < 3)
        edge_on = np.zeros_like(rain)

        if self.banner is not None:
            edge, blocked = self.banner
            rev = (f - self.t0 - self.rd) * self.rs
            dr = rev[None, :] - rr
            front = (dr >= 0) & (dr < 3)
            if self.clear_t0 is not None:
                clr = (f - self.clear_t0 - self.cd) * self.cs
                dc = clr[None, :] - rr
                front |= (dc >= 0) & (dc < 3)
                below_clear = rr > clr[None, :]
            else:
                below_clear = True
            rain |= front
            bright |= front
            active = blocked & (rr <= rev[None, :]) & below_clear
            rain &= ~active
            bright &= ~active
            edge_on = edge & active

        self.push(self.dim_rows, "dim", rain & ~bright)
        self.push(self.head_rows, "head", bright)
        self.push(self.edge_rows, "edge", edge_on)

    def update_red_gradient(self, progress):
        eased = progress ** RED_EASE
        for i, rect in enumerate(self.strips):
            curve = (i / self.num_strips) ** 1.6
            red = int(MAX_RED * curve * eased)
            self.canvas.itemconfig(rect, fill=f"#{red:02x}0000")

    def animate(self):
        self.frame += 1
        f = self.frame

        if f == T_NAME:
            self.start_banner(["MADE BY", "AIDEN WARE", "BOSANKO"])
        elif f == T_CLEAR_1:
            self.start_clear()
        elif f == T_TITLE_2:
            self.start_banner(["PROPELLER", "DYNA PRO"])

        if T_RED_START <= f <= T_RED_END and f % 2 == 0:
            self.update_red_gradient((f - T_RED_START) / (T_RED_END - T_RED_START))

        self.render()

        if f > T_EXIT:
            self.root.destroy()
            self.on_complete()
            return
        self.root.after(FRAME_MS, self.animate)


# ==========================================
# SPACEX MISSION CONTROL DESIGN SYSTEM
# ==========================================
UI_FONT   = "Segoe UI"
MONO_FONT = "Consolas"

C_VOID    = "#000000"   # Pure pitch-black mission control void
C_SURFACE = "#08090B"   # Subtle recessed console surface
C_HAIR    = "#1C2026"   # Razor-thin 1px structural dividers
C_HAIR_HI = "#323842"
C_WHITE   = "#F5F7FA"   # Primary stark white telemetry
C_SILVER  = "#8A93A2"   # Secondary labels
C_MUTED   = "#4C535E"   # Ticks & dim metadata
C_AMBER   = "#E59400"   # Armed state
C_RED     = "#D92626"   # E-Stop / Fault
C_GREEN   = "#24A159"   # Nominal / Connected


class AntiAliasedArcGauge(tk.Label):
    """2x supersampled Pillow radial arc gauge (SpaceX Dragon telemetry style)."""
    def __init__(self, parent, title, unit, max_val, fmt="{:.1f}", size=156, **kwargs):
        super().__init__(parent, bg=C_VOID, bd=0, highlightthickness=0, **kwargs)
        self.title = title.upper()
        self.unit = unit
        self.max_val = float(max_val)
        self.fmt = fmt
        self.size = size
        self.val = 0.0
        self._last_drawn = None
        self._tk_img = None

        self.f_val = load_font(34)
        self.f_lbl = load_font(15)
        self.f_unit = load_font(14)
        self.set_value(0.0, force=True)

    def set_value(self, val, force=False):
        self.val = float(val)
        disp = self.fmt.format(self.val)
        ratio = max(0.0, min(1.0, self.val / self.max_val))
        key = (disp, round(ratio, 3))
        if not force and key == self._last_drawn:
            return
        self._last_drawn = key

        S = self.size * 2  # 2x supersampling for crisp anti-aliased arcs
        img = Image.new("RGB", (S, S), (0, 0, 0))
        d = ImageDraw.Draw(img)

        pad = 22
        box = [pad, pad, S - pad, S - pad]
        start_ang = 140
        sweep_total = 260

        # Background muted arc track
        d.arc(box, start=start_ang, end=start_ang + sweep_total, fill=(32, 36, 44), width=10)

        # Active stark-white arc sweep
        if ratio > 0.002:
            end_ang = start_ang + sweep_total * ratio
            arc_col = (217, 38, 38) if ratio > 0.90 else (245, 247, 250)
            d.arc(box, start=start_ang, end=end_ang, fill=arc_col, width=10)

        # Center numeric readout
        d.text((S // 2, S // 2 - 8), disp, fill=(245, 247, 250), font=self.f_val, anchor="mm")
        # Unit & Title below
        d.text((S // 2, S // 2 + 28), self.unit, fill=(138, 147, 162), font=self.f_unit, anchor="mm")
        d.text((S // 2, S - 24), self.title, fill=(138, 147, 162), font=self.f_lbl, anchor="mm")

        small = img.resize((self.size, self.size), Image.LANCZOS)
        # Convert to Tkinter PhotoImage via PPM bytes (fast, zero external ImageTk dependency)
        ppm = f"P6\n{self.size} {self.size}\n255\n".encode("ascii") + small.tobytes()
        self._tk_img = tk.PhotoImage(data=ppm)
        self.config(image=self._tk_img)


class VernierThrottle(tk.Canvas):
    """Minimalist precision Vernier throttle bar on pitch black."""
    def __init__(self, parent, min_val=1000, max_val=2000, step=10, on_change=None, **kwargs):
        super().__init__(parent, width=1, height=44, bg=C_VOID, highlightthickness=0, cursor="sb_h_double_arrow", **kwargs)
        self.min_val = min_val
        self.max_val = max_val
        self.step = step
        self.val = min_val
        self.on_change = on_change

        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<Button-1>", self._mouse)
        self.bind("<B1-Motion>", self._mouse)

    def get(self):
        return self.val

    def set(self, new_val):
        clamped = max(self.min_val, min(self.max_val, int(round(new_val / self.step) * self.step)))
        if clamped != self.val:
            self.val = clamped
            self._draw()
            if self.on_change:
                self.on_change(self.val)
        else:
            self._draw()

    def _mouse(self, event):
        pad = 4
        w = max(1, self.winfo_width() - 2 * pad)
        ratio = max(0.0, min(1.0, (event.x - pad) / w))
        self.set(self.min_val + ratio * (self.max_val - self.min_val))

    def _draw(self):
        self.delete("all")
        w = self.winfo_width()
        if w < 20:
            return
        pad = 4
        tw = w - 2 * pad
        ratio = (self.val - self.min_val) / (self.max_val - self.min_val)
        fx = pad + ratio * tw

        # Fine Vernier ticks
        for i in range(51):
            tx = pad + (i / 50.0) * tw
            h_tick = 10 if i % 10 == 0 else (6 if i % 5 == 0 else 3)
            col = C_SILVER if i % 10 == 0 else C_MUTED
            self.create_line(tx, 18 - h_tick, tx, 18, fill=col)

        # Baseline & active white fill
        self.create_line(pad, 20, w - pad, 20, fill=C_HAIR_HI, width=1)
        if ratio > 0:
            fill_c = C_RED if ratio > 0.85 else (C_AMBER if ratio > 0 else C_WHITE)
            self.create_line(pad, 20, fx, 20, fill=fill_c, width=3)

        # Needle triangle pointer
        self.create_polygon([fx, 22, fx - 4, 29, fx + 4, 29], fill=C_WHITE, outline="")

        for pwm in (1000, 1500, 2000):
            tx = pad + ((pwm - self.min_val) / (self.max_val - self.min_val)) * tw
            anc = "w" if pwm == 1000 else ("e" if pwm == 2000 else "center")
            self.create_text(tx, 36, text=str(pwm), fill=C_MUTED, font=(MONO_FONT, 8), anchor=anc)


def clean_btn(parent, text, command, fg=C_WHITE, bg=C_SURFACE, hover="#14171D", border=C_HAIR_HI, font_size=9, pady=8):
    b = tk.Button(
        parent, text=text, command=command,
        fg=fg, bg=bg, activebackground=hover, activeforeground=fg,
        font=(UI_FONT, font_size, "bold"), relief="flat", bd=0,
        highlightthickness=1, highlightbackground=border,
        cursor="hand2", takefocus=0, pady=pady
    )
    b.bind("<Enter>", lambda e: b.config(bg=hover) if str(b.cget("bg")) == bg else None)
    b.bind("<Leave>", lambda e: b.config(bg=bg) if str(b.cget("bg")) == hover else None)
    return b


# ==========================================
# DASHBOARD
# ==========================================
def launch_dashboard():
    main_app = tk.Tk()
    main_app.title("PROPELLER DYNA PRO")
    main_app.geometry("1360x840")
    main_app.minsize(1160, 720)
    main_app.configure(bg=C_VOID)

    # ==========================================
    # 1. MINIMALIST MISSION HEADER
    # ==========================================
    header = tk.Frame(main_app, bg=C_VOID, height=50)
    header.pack(fill="x")
    header.pack_propagate(False)

    tk.Label(header, text="PROPELLER DYNA PRO", fg=C_WHITE, bg=C_VOID,
             font=(UI_FONT, 13, "bold")).pack(side="left", padx=24)
    tk.Label(header, text="STATIC THRUST TEST STAND", fg=C_MUTED, bg=C_VOID,
             font=(UI_FONT, 9, "bold")).pack(side="left", pady=(2, 0))

    status_box = tk.Frame(header, bg=C_VOID)
    status_box.pack(side="right", padx=24)

    link_lbl = tk.Label(status_box, text="COM5  //  INIT", fg=C_SILVER, bg=C_VOID, font=(MONO_FONT, 9))
    link_lbl.pack(side="left", padx=(0, 20))

    state_dot = tk.Canvas(status_box, width=8, height=8, bg=C_VOID, highlightthickness=0)
    dot_id = state_dot.create_oval(1, 1, 7, 7, fill=C_MUTED, outline="")
    state_dot.pack(side="left", padx=(0, 8))

    state_label = tk.Label(status_box, text="DISCONNECTED", fg=C_SILVER, bg=C_VOID, font=(MONO_FONT, 10, "bold"))
    state_label.pack(side="left")

    tk.Frame(main_app, bg=C_HAIR, height=1).pack(fill="x")

    # ==========================================
    # 2. MAIN WORKSPACE (BORDERLESS HAIRLINE SPLIT)
    # ==========================================
    workspace = tk.Frame(main_app, bg=C_VOID)
    workspace.pack(fill="both", expand=True)

    # Left Control Column (320px, separated by a single 1px vertical hairline)
    left_col = tk.Frame(workspace, bg=C_VOID, width=320)
    left_col.pack(side="left", fill="y")
    left_col.pack_propagate(False)
    rail = tk.Frame(left_col, bg=C_VOID, padx=20, pady=16)
    rail.pack(fill="both", expand=True)

    tk.Frame(workspace, bg=C_HAIR, width=1).pack(side="left", fill="y")

    # Right Telemetry & Curves Area
    right_col = tk.Frame(workspace, bg=C_VOID, padx=20, pady=12)
    right_col.pack(side="left", fill="both", expand=True)

    # Footer
    tk.Frame(main_app, bg=C_HAIR, height=1).pack(side="bottom", fill="x")
    footer = tk.Frame(main_app, bg=C_VOID, height=24)
    footer.pack(side="bottom", fill="x")
    footer.pack_propagate(False)
    tk.Label(footer, text="AIDEN WARE BOSANKO", fg=C_MUTED, bg=C_VOID, font=(UI_FONT, 8)).pack(side="left", padx=24)
    tk.Label(footer, text="ESC : E-STOP    SPACE : IDLE", fg=C_MUTED, bg=C_VOID, font=(MONO_FONT, 8)).pack(side="right", padx=24)

    # ==========================================
    # 3. STATE & EVENT HELPERS
    # ==========================================
    ser = None
    system_state = {"armed": False, "hw_state": "UNKNOWN", "sim_mode": True}

    def section_lbl(parent, text, top=16):
        tk.Label(parent, text=text, fg=C_MUTED, bg=C_VOID, font=(UI_FONT, 8, "bold"), anchor="w").pack(fill="x", pady=(top, 6))

    def log_event(msg, tag="INFO"):
        ts = datetime.now().strftime("%H:%M:%S")
        event_box.configure(state="normal")
        event_box.insert("end", f"{ts}  {msg}\n", tag)
        if int(event_box.index("end-1c").split(".")[0]) > 75:
            event_box.delete("1.0", "2.0")
        event_box.see("end")
        event_box.configure(state="disabled")

    def set_state_ui(text, color):
        state_label.config(text=text, fg=color)
        state_dot.itemconfig(dot_id, fill=color)

    # ==========================================
    # 4. LEFT CONTROL COLUMN
    # ==========================================
    estop_btn = clean_btn(
        rail, "EMERGENCY STOP  [ESC]", lambda: send_command("E"),
        fg=C_WHITE, bg=C_RED, hover="#B81D1D", border=C_RED, font_size=10, pady=12
    )
    estop_btn.pack(side="bottom", fill="x", pady=(10, 0))

    section_lbl(rail, "PROPULSION AUTHORITY", top=0)
    auth_row = tk.Frame(rail, bg=C_VOID)
    auth_row.pack(fill="x")
    auth_row.grid_columnconfigure(0, weight=1, uniform="a")
    auth_row.grid_columnconfigure(1, weight=1, uniform="a")

    arm_btn = clean_btn(auth_row, "ARM", lambda: send_command("A"), fg=C_AMBER, border=C_HAIR_HI)
    arm_btn.grid(row=0, column=0, sticky="ew", padx=(0, 4))

    idle_btn = clean_btn(auth_row, "IDLE", lambda: send_command("I"), fg=C_WHITE, border=C_HAIR_HI)
    idle_btn.grid(row=0, column=1, sticky="ew", padx=(4, 0))

    section_lbl(rail, "THROTTLE SETPOINT")
    thr_top = tk.Frame(rail, bg=C_VOID)
    thr_top.pack(fill="x")
    thr_val_lbl = tk.Label(thr_top, text="1000 µs", fg=C_WHITE, bg=C_VOID, font=(MONO_FONT, 15, "bold"))
    thr_val_lbl.pack(side="left")
    thr_pct_lbl = tk.Label(thr_top, text="0%", fg=C_SILVER, bg=C_VOID, font=(MONO_FONT, 10))
    thr_pct_lbl.pack(side="right", pady=(4, 0))

    def on_throttle_change(val):
        pct = ((val - 1000) / 1000.0) * 100.0
        thr_val_lbl.config(text=f"{val} µs")
        thr_pct_lbl.config(text=f"{pct:.0f}%")

    throttle_slider = VernierThrottle(rail, min_val=1000, max_val=2000, step=10, on_change=on_throttle_change)
    throttle_slider.pack(fill="x", pady=(2, 4))

    nudge_row = tk.Frame(rail, bg=C_VOID)
    nudge_row.pack(fill="x")
    for idx, (lbl, delta) in enumerate([("-50", -50), ("-10", -10), ("+10", 10), ("+50", 50)]):
        nudge_row.grid_columnconfigure(idx, weight=1, uniform="n")
        nb = clean_btn(nudge_row, lbl, lambda d=delta: throttle_slider.set(throttle_slider.get() + d),
                       fg=C_SILVER, font_size=8, pady=4)
        nb.grid(row=0, column=idx, sticky="ew", padx=(0 if idx == 0 else 4, 0))

    section_lbl(rail, "SEQUENCE & CALIBRATION")
    seq_row = tk.Frame(rail, bg=C_VOID)
    seq_row.pack(fill="x")
    seq_row.grid_columnconfigure(0, weight=2, uniform="s")
    seq_row.grid_columnconfigure(1, weight=1, uniform="s")

    step_btn = clean_btn(seq_row, "STEP SWEEP", lambda: start_step_test(), fg=C_WHITE)
    step_btn.grid(row=0, column=0, sticky="ew", padx=(0, 4))

    tare_btn = clean_btn(seq_row, "TARE", lambda: send_command("Z"), fg=C_SILVER)
    tare_btn.grid(row=0, column=1, sticky="ew", padx=(4, 0))

    section_lbl(rail, "DATA ACQUISITION")
    log_btn = clean_btn(rail, "RECORD CSV", lambda: toggle_logging(), fg=C_WHITE)
    log_btn.pack(fill="x")

    section_lbl(rail, "SERIAL EVENT STREAM")
    term_box = tk.Frame(rail, bg=C_SURFACE, highlightthickness=1, highlightbackground=C_HAIR)
    term_box.pack(fill="both", expand=True)

    event_box = tk.Text(term_box, bg=C_SURFACE, fg=C_SILVER, font=(MONO_FONT, 8),
                        bd=0, padx=8, pady=6, wrap="word", state="disabled", height=6)
    event_box.pack(fill="both", expand=True)
    event_box.tag_config("INFO", foreground=C_SILVER)
    event_box.tag_config("OK", foreground=C_GREEN)
    event_box.tag_config("WARN", foreground=C_AMBER)
    event_box.tag_config("ERR", foreground=C_RED)

    # ==========================================
    # 5. SERIAL CONNECTION & COMMANDS
    # ==========================================
    try:
        ser = serial.Serial('COM5', 115200, timeout=0.01)
        link_lbl.config(text="COM5  //  115200", fg=C_GREEN)
        set_state_ui("CONNECTED", C_WHITE)
        log_event("Serial link active on COM5", "OK")
        ser.write(b"I\n")
    except Exception:
        link_lbl.config(text="OFFLINE  //  SIM", fg=C_AMBER)
        set_state_ui("IDLE (SIM)", C_SILVER)
        log_event("COM5 offline -> Physics simulation active", "WARN")

    def send_command(cmd):
        if cmd == "E":
            system_state["armed"] = False
            throttle_slider.set(1000)
            if ser and ser.is_open:
                ser.write(b"E\nE\n")
                ser.flush()
                log_event("TX > E  [HARD E-STOP]", "ERR")
            else:
                set_state_ui("E-STOPPED", C_RED)
                log_event("SIM > HARD E-STOP", "ERR")
            return

        if cmd == "I":
            system_state["armed"] = False
            throttle_slider.set(1000)
            if ser and ser.is_open:
                ser.write(b"I\n")
                log_event("TX > I  [IDLE]", "INFO")
            else:
                set_state_ui("IDLE (SIM)", C_SILVER)
                log_event("SIM > IDLE", "OK")
            return

        if cmd == "A":
            if ser and ser.is_open:
                if system_state["hw_state"] == "STOP":
                    ser.write(b"I\n")
                    log_event("Clearing STOP -> IDLE", "WARN")
                ser.write(b"A\n")
                log_event("TX > A  [ARM]", "WARN")
            else:
                system_state["armed"] = True
                set_state_ui("ARMED (SIM)", C_AMBER)
                log_event("SIM > ARMED", "WARN")
            return

        if cmd == "Z":
            if ser and ser.is_open:
                ser.write(b"Z\n")
                log_event("TX > Z  [TARE]", "INFO")
            else:
                log_event("SIM > Tared 0.0 g", "INFO")

    # ==========================================
    # 6. SPACEX RADIAL ARC GAUGE DECK + SECONDARY BUS READOUTS
    # ==========================================
    dial_row = tk.Frame(right_col, bg=C_VOID)
    dial_row.pack(fill="x", pady=(0, 8))

    for c in range(4):
        dial_row.grid_columnconfigure(c, weight=1, uniform="dials")

    g_thrust = AntiAliasedArcGauge(dial_row, "THRUST", "g", max_val=1500.0, fmt="{:.1f}", size=154)
    g_thrust.grid(row=0, column=0)

    g_rpm = AntiAliasedArcGauge(dial_row, "ROTOR SPEED", "RPM", max_val=20000.0, fmt="{:.0f}", size=154)
    g_rpm.grid(row=0, column=1)

    g_power = AntiAliasedArcGauge(dial_row, "ELEC POWER", "W", max_val=500.0, fmt="{:.1f}", size=154)
    g_power.grid(row=0, column=2)

    g_eff = AntiAliasedArcGauge(dial_row, "EFFICIENCY", "g/W", max_val=6.0, fmt="{:.2f}", size=154)
    g_eff.grid(row=0, column=3)

    # Clean hairline bus telemetry bar underneath dials (Voltage & Current)
    tk.Frame(right_col, bg=C_HAIR, height=1).pack(fill="x", pady=(4, 8))
    bus_bar = tk.Frame(right_col, bg=C_VOID)
    bus_bar.pack(fill="x", pady=(0, 8))

    tk.Label(bus_bar, text="BUS VOLTAGE", fg=C_MUTED, bg=C_VOID, font=(UI_FONT, 8, "bold")).pack(side="left")
    volt_lbl = tk.Label(bus_bar, text="16.80 V", fg=C_WHITE, bg=C_VOID, font=(MONO_FONT, 11, "bold"))
    volt_lbl.pack(side="left", padx=(8, 32))

    tk.Label(bus_bar, text="CURRENT DRAW", fg=C_MUTED, bg=C_VOID, font=(UI_FONT, 8, "bold")).pack(side="left")
    curr_lbl = tk.Label(bus_bar, text="0.00 A", fg=C_WHITE, bg=C_VOID, font=(MONO_FONT, 11, "bold"))
    curr_lbl.pack(side="left", padx=(8, 0))

    tk.Frame(right_col, bg=C_HAIR, height=1).pack(fill="x", pady=(0, 6))

    # ==========================================
    # 7. BORDERLESS BLITTED TELEMETRY TRACES
    # ==========================================
    N = 1500
    WINDOW_S = 30.0
    t_data      = deque(maxlen=N)
    thrust_data = deque(maxlen=N)
    rpm_data    = deque(maxlen=N)
    pwm_data    = deque(maxlen=N)
    t_start = time.time()

    fig = Figure(figsize=(9, 4.6), dpi=100, facecolor=C_VOID)
    fig.subplots_adjust(left=0.06, right=0.99, top=0.94, bottom=0.10, hspace=0.30)
    ax_thrust, ax_rpm, ax_pwm = fig.subplots(3, 1, sharex=True)

    def style_ax(ax, title):
        ax.set_facecolor(C_VOID)
        ax.set_title(title, loc="left", color=C_SILVER, fontsize=8,
                     fontfamily="sans-serif", fontweight="bold", pad=3)
        ax.tick_params(colors=C_MUTED, labelsize=8, length=3, width=0.6)
        ax.grid(True, color="#121418", linewidth=0.8)
        ax.yaxis.set_major_locator(MaxNLocator(3))
        for spine in ("top", "right"):
            ax.spines[spine].set_visible(False)
        for spine in ("bottom", "left"):
            ax.spines[spine].set_color(C_HAIR)

    style_ax(ax_thrust, "THRUST  (g)")
    style_ax(ax_rpm, "SPEED  (RPM)")
    style_ax(ax_pwm, "COMMAND  (µs)")
    ax_pwm.set_xlabel("TIME (s)", color=C_MUTED, fontsize=8, fontweight="bold")

    (thrust_line,) = ax_thrust.plot([], [], color=C_WHITE, linewidth=1.6, animated=True)
    (rpm_line,)    = ax_rpm.plot([], [], color=C_SILVER, linewidth=1.4, animated=True)
    (pwm_line,)    = ax_pwm.plot([], [], color=C_AMBER, linewidth=1.3, animated=True)

    ax_thrust.set_ylim(-5, 1600)
    ax_rpm.set_ylim(-200, 20000)
    ax_pwm.set_ylim(950, 2050)
    ax_pwm.set_xlim(0, WINDOW_S)

    graph_canvas = FigureCanvasTkAgg(fig, master=right_col)
    graph_canvas.get_tk_widget().configure(bg=C_VOID)
    graph_canvas.get_tk_widget().pack(fill="both", expand=True)

    blit_state = {"bg": None, "last_xlim": (0.0, WINDOW_S), "last_t_max": 1600.0, "last_r_max": 20000.0}

    def cache_background(event=None):
        graph_canvas.draw()
        blit_state["bg"] = graph_canvas.copy_from_bbox(fig.bbox)

    graph_canvas.mpl_connect("draw_event", lambda e: blit_state.update({"bg": graph_canvas.copy_from_bbox(fig.bbox)}))
    graph_canvas.get_tk_widget().bind("<Configure>", lambda e: main_app.after(50, cache_background))

    draw_counter = {"n": 0}

    def update_graphs(thrust, rpm):
        t_now = time.time() - t_start
        t_data.append(t_now)
        thrust_data.append(thrust)
        rpm_data.append(rpm)
        pwm_data.append(throttle_slider.get())

        draw_counter["n"] += 1
        if draw_counter["n"] % 3 != 0:
            return

        x = list(t_data)
        x_min = max(0.0, t_now - WINDOW_S)
        x_max = max(WINDOW_S, t_now)
        cur_t_max = max(max(thrust_data) * 1.15, 100.0)
        cur_r_max = max(max(rpm_data) * 1.15, 2000.0)

        need_full_redraw = (
            blit_state["bg"] is None or
            abs(x_max - blit_state["last_xlim"][1]) > 0.5 or
            abs(cur_t_max - blit_state["last_t_max"]) > 150.0 or
            abs(cur_r_max - blit_state["last_r_max"]) > 2000.0
        )

        thrust_line.set_data(x, list(thrust_data))
        rpm_line.set_data(x, list(rpm_data))
        pwm_line.set_data(x, list(pwm_data))

        if need_full_redraw:
            ax_pwm.set_xlim(x_min, x_max)
            ax_thrust.set_ylim(-5, cur_t_max)
            ax_rpm.set_ylim(-100, cur_r_max)
            blit_state["last_xlim"] = (x_min, x_max)
            blit_state["last_t_max"] = cur_t_max
            blit_state["last_r_max"] = cur_r_max
            graph_canvas.draw()
            blit_state["bg"] = graph_canvas.copy_from_bbox(fig.bbox)

        graph_canvas.restore_region(blit_state["bg"])
        ax_thrust.draw_artist(thrust_line)
        ax_rpm.draw_artist(rpm_line)
        ax_pwm.draw_artist(pwm_line)
        graph_canvas.blit(fig.bbox)

    # ==========================================
    # 8. CSV LOGGER & TELEMETRY DISPATCH
    # ==========================================
    log_state = {"recording": False, "file": None, "writer": None, "filepath": ""}

    def toggle_logging():
        if not log_state["recording"]:
            log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
            os.makedirs(log_dir, exist_ok=True)
            filename = f"dyna_run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            filepath = os.path.join(log_dir, filename)

            f = open(filepath, mode="w", newline="")
            writer = csv.writer(f)
            writer.writerow(["Timestamp", "Source", "State", "Throttle_PWM_us", "Thrust_g", "RPM", "Voltage_V", "Current_A", "Power_W", "g_per_W"])
            f.flush()

            log_state.update({"file": f, "writer": writer, "filepath": filepath, "recording": True})
            log_btn.config(text=f"STOP & OPEN ({filename})", bg="#2B0B0B", fg=C_RED, highlightbackground=C_RED)
            log_event(f"Recording -> {filename}", "WARN")
        else:
            if log_state["file"]:
                log_state["file"].close()
            saved_path = log_state["filepath"]
            log_state.update({"recording": False, "file": None, "writer": None})
            log_btn.config(text="RECORD CSV", bg=C_SURFACE, fg=C_WHITE, highlightbackground=C_HAIR_HI)
            log_event("CSV saved & opened", "OK")
            try:
                os.startfile(saved_path)
            except Exception as e:
                log_event(f"Auto-open failed: {e}", "ERR")

    gauge_tick = {"n": 0}
    recent = deque(maxlen=400)

    def update_telemetry_and_log(thrust_s, rpm_s, volt_s, curr_s):
        try:
            t_f = float(thrust_s)
            r_f = float(rpm_s)
            v_f = float(volt_s)
            c_f = float(curr_s)
        except ValueError:
            return

        pwr_f = v_f * c_f
        gpw_f = (t_f / pwr_f) if (pwr_f > 0.5 and t_f > 0.5) else 0.0

        gauge_tick["n"] += 1
        if gauge_tick["n"] % 3 == 0:
            g_thrust.set_value(t_f)
            g_rpm.set_value(r_f)
            g_power.set_value(pwr_f)
            g_eff.set_value(gpw_f)
            volt_lbl.config(text=f"{v_f:.2f} V")
            curr_lbl.config(text=f"{c_f:.2f} A")

        update_graphs(t_f, r_f)
        recent.append((time.time(), t_f, r_f, v_f, c_f))

        if log_state["recording"] and log_state["writer"]:
            now_time = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            source_str = "REAL" if (ser and ser.is_open) else "SIM"
            mode_str = "ARMED" if system_state["armed"] else "IDLE"
            log_state["writer"].writerow([
                now_time, source_str, mode_str, throttle_slider.get(),
                f"{t_f:.1f}", int(r_f), f"{v_f:.2f}", f"{c_f:.2f}", f"{pwr_f:.1f}", f"{gpw_f:.3f}"
            ])
            log_state["file"].flush()

    # ==========================================
    # 9. AUTOMATED STEP SWEEP
    # ==========================================
    step = {"running": False, "i": 0}
    SETPOINTS = list(range(1100, 2001, 100))
    HOLD_MS = 3000
    AVG_MS = 1000
    step_results = []

    def reset_step_button():
        step_btn.config(text="STEP SWEEP", bg=C_SURFACE, fg=C_WHITE, highlightbackground=C_HAIR_HI)

    def abort_step_test(reason):
        step["running"] = False
        reset_step_button()
        log_event(f"Sweep aborted ({reason})", "ERR")

    def finish_step_test():
        step["running"] = False
        throttle_slider.set(1000)
        send_command("I")
        reset_step_button()

        source = "REAL" if (ser and ser.is_open) else "SIM"
        log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
        os.makedirs(log_dir, exist_ok=True)
        path = os.path.join(log_dir, f"step_test_{source}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["Source", "PWM_us", "Thrust_g", "RPM", "Voltage_V", "Current_A", "Power_W", "g_per_W"])
            for row in step_results:
                w.writerow([source] + row)
        log_event(f"Saved -> {os.path.basename(path)}", "OK")
        try:
            os.startfile(path)
        except Exception:
            pass

    def next_step():
        if not step["running"]:
            return
        if not system_state["armed"]:
            abort_step_test("disarmed")
            return
        if step["i"] >= len(SETPOINTS):
            finish_step_test()
            return
        sp = SETPOINTS[step["i"]]
        throttle_slider.set(sp)
        log_event(f"Step {step['i']+1}/{len(SETPOINTS)} -> {sp} µs", "INFO")
        main_app.after(HOLD_MS, record_step)

    def record_step():
        if not step["running"]:
            return
        if not system_state["armed"]:
            abort_step_test("disarmed")
            return
        now = time.time()
        pts = [p for p in recent if now - p[0] <= AVG_MS / 1000]
        if not pts:
            abort_step_test("no telemetry")
            return
        n = len(pts)
        thrust = sum(p[1] for p in pts) / n
        rpm    = sum(p[2] for p in pts) / n
        volt   = sum(p[3] for p in pts) / n
        curr   = sum(p[4] for p in pts) / n
        power  = volt * curr
        gpw    = thrust / power if power > 0 else 0.0
        step_results.append([SETPOINTS[step["i"]], round(thrust, 1), round(rpm), round(volt, 2),
                             round(curr, 2), round(power, 1), round(gpw, 3)])
        step["i"] += 1
        next_step()

    def start_step_test():
        if step["running"]:
            return
        step["running"] = True
        step["i"] = 0
        step_results.clear()
        recent.clear()
        step_btn.config(text="SWEEPING...", bg="#291B00", fg=C_AMBER, highlightbackground=C_AMBER)
        log_event("Starting throttle sweep", "WARN")
        send_command("A")
        main_app.after(1000, next_step)

    # ==========================================
    # 10. 50 HZ SERIAL POLLING & HEARTBEAT LOOP
    # ==========================================
    def poll_serial():
        got_real_hardware_data = False

        if ser and ser.is_open:
            while ser.in_waiting > 0:
                line = ser.readline().decode('utf-8', errors='ignore').strip()
                if not line:
                    continue

                if line.startswith("DATA,"):
                    parts = line.split(",")
                    if len(parts) == 5:
                        got_real_hardware_data = True
                        update_telemetry_and_log(parts[1], parts[2], parts[3], parts[4])
                else:
                    if "STATE: IDLE" in line:
                        system_state["armed"] = False
                        system_state["hw_state"] = "IDLE"
                        set_state_ui("IDLE", C_GREEN)
                        log_event("RX < STATE: IDLE", "OK")
                    elif "STATE: TESTING" in line:
                        system_state["armed"] = True
                        system_state["hw_state"] = "TESTING"
                        set_state_ui("ARMED", C_AMBER)
                        log_event("RX < STATE: TESTING", "WARN")
                    elif "STATE: STOP" in line:
                        system_state["armed"] = False
                        system_state["hw_state"] = "STOP"
                        throttle_slider.set(1000)
                        set_state_ui("E-STOPPED", C_RED)
                        log_event("RX < STATE: STOP", "ERR")
                    elif "FAILSAFE" in line:
                        log_event(f"RX < {line}", "ERR")
                    else:
                        log_event(f"RX < {line}", "INFO")

            if system_state["armed"] and system_state["hw_state"] == "TESTING":
                current_pwm = throttle_slider.get()
                ser.write(f"T{current_pwm}\n".encode('utf-8'))

        if not got_real_hardware_data and system_state["sim_mode"] and not (ser and ser.is_open):
            pwm = throttle_slider.get() if system_state["armed"] else 1000
            pct = (pwm - 1000) / 1000.0
            if pct > 0.0:
                sim_thrust = (pct ** 1.85) * 1450.0 + random.uniform(-4.5, 4.5)
                sim_rpm    = int((pct ** 0.85) * 18500 + random.uniform(-60, 60))
                sim_curr   = (pct ** 2.1) * 34.0 + 0.6 + random.uniform(-0.15, 0.15)
                sim_volt   = 16.8 - (sim_curr * 0.045) + random.uniform(-0.03, 0.03)
            else:
                sim_thrust = max(0.0, random.uniform(-0.4, 0.4))
                sim_rpm    = 0
                sim_curr   = 0.08 + random.uniform(-0.01, 0.01)
                sim_volt   = 16.80 + random.uniform(-0.01, 0.01)

            update_telemetry_and_log(f"{sim_thrust:.1f}", f"{sim_rpm}", f"{sim_volt:.2f}", f"{sim_curr:.2f}")

        main_app.after(20, poll_serial)

    def on_close():
        try:
            if ser and ser.is_open:
                ser.write(b"E\nE\n")
                ser.flush()
                ser.close()
        except Exception as e:
            print(f"Shutdown warning: {e}")
        if log_state["file"]:
            log_state["file"].close()
        main_app.destroy()

    main_app.protocol("WM_DELETE_WINDOW", on_close)
    main_app.bind("<Escape>", lambda e: send_command("E"))
    main_app.bind("<space>", lambda e: send_command("I"))

    main_app.after(100, cache_background)
    poll_serial()
    main_app.mainloop()


# ==========================================
# BOOTER
# ==========================================
if __name__ == "__main__":
    splash = tk.Tk()
    splash.title("Loading...")
    splash.configure(bg="black")
    splash.overrideredirect(True)
    app = WaterfallSplash(splash, launch_dashboard)
    sw, sh = splash.winfo_screenwidth(), splash.winfo_screenheight()
    splash.geometry(f"{app.width}x{app.height}+{int(sw/2 - app.width/2)}+{int(sh/2 - app.height/2)}")
    splash.mainloop()