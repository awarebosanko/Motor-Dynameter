# This dashboard was developed by Aiden Ware Bosanko
import serial
import matplotlib.pyplot as plt
import pandas as pd
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
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# ==========================================
# TUNING KNOBS
# ==========================================
W, H = 960, 600
FONT_PX = 6              # hashtag size in PIXELS. 5 = even tinier, 8 = chunkier
FRAME_MS = 30            # lower = faster/smoother (if laggy, raise to 40)
RAIN_COLOR = "#8c8c8c"   # dim tail of the hashtags
HEAD_COLOR = "#ffffff"   # bright leading edge / wave front
EDGE_COLOR = "#ffffff"   # the hashtags that trace the letters
MAX_RED = 42             # darkest-red strength at the bottom (0-255)

EDGE_X, EDGE_Y = 2, 1    # outline thickness in cells (x is wide, y is tall)
HALO_X, HALO_Y = 4, 2    # dark gap around letters where the rain parts

# Timeline (1 frame = FRAME_MS)
T_NAME = 110             # rain has been falling this long, then your name forms
T_CLEAR_1 = 250          # name starts washing away
T_TITLE_2 = 310          # second title starts forming (keep ~60 after T_CLEAR_1)
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
    """Grow a True/False grid outward by ry rows and rx columns."""
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

    # Shrink font until the text fits nicely
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

    # One pixel per character cell (area-averaged), then threshold
    small = img.resize((cols, rows), Image.BOX)
    filled = np.asarray(small) > 90

    edge = filled & dilate(~filled, EDGE_Y, EDGE_X, pad=True)   # letter outline
    blocked = filled | dilate(filled, HALO_Y, HALO_X)           # letters + halo
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

        # Background gradient strips (red fades in later)
        self.num_strips = 24
        self.strips = []
        sh = self.height / self.num_strips
        for i in range(self.num_strips):
            self.strips.append(self.canvas.create_rectangle(
                0, i * sh, self.width, (i + 1) * sh + 1, fill="#000000", outline=""))

        # Three layers, one text item per row: dim rain, bright rain, letter outline
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

        # Everything below scales with row count so speed looks the same at any font size
        n = self.cols
        S = self.rows / 40.0
        self.S = S
        self.rr = np.arange(self.rows)[:, None]
        self.delay = np.random.randint(0, 61, n)                  # staggered start = slow build-up
        self.speed = np.random.uniform(0.9, 1.5, n) * S
        self.tail = (np.random.randint(24, 41, n) * S).astype(int)
        self.gap = (np.random.randint(4, 13, n) * S).astype(int)
        self.cyc = self.tail + self.gap

        self.banner = None
        self.clear_t0 = None
        self.frame = 0
        self.animate()

    # ---- banner control ----
    def start_banner(self, lines):
        self.banner = build_banner(lines, self.cols, self.rows, self.cw, self.ch)
        self.t0 = self.frame
        self.rd = np.random.randint(0, 25, self.cols)
        self.rs = np.random.uniform(0.7, 1.1, self.cols) * self.S   # slower reveal wave
        self.clear_t0 = None

    def start_clear(self):
        self.clear_t0 = self.frame
        self.cd = np.random.randint(0, 15, self.cols)
        self.cs = np.random.uniform(1.2, 1.9, self.cols) * self.S

    # ---- drawing ----
    def push(self, ids, key, mask):
        b = np.where(mask, 35, 32).astype(np.uint8)   # 35 = '#', 32 = ' '
        cache = self.cache[key]
        for r in range(self.rows):
            s = b[r].tobytes().decode("ascii")
            if s != cache[r]:
                cache[r] = s
                self.canvas.itemconfig(ids[r], text=s)

    def render(self):
        f, rr = self.frame, self.rr

        # Falling rain for every cell at once
        d = ((f - self.delay) * self.speed)[None, :] - rr
        dm = np.floor(d).astype(np.int64) % self.cyc[None, :]
        rain = (d >= 0) & (dm < self.tail[None, :])
        bright = rain & (dm < 3)
        edge_on = np.zeros_like(rain)

        if self.banner is not None:
            edge, blocked = self.banner
            rev = (f - self.t0 - self.rd) * self.rs
            dr = rev[None, :] - rr
            front = (dr >= 0) & (dr < 3)                 # bright wave front sweeping in
            if self.clear_t0 is not None:
                clr = (f - self.clear_t0 - self.cd) * self.cs
                dc = clr[None, :] - rr
                front |= (dc >= 0) & (dc < 3)            # bright wave front washing away
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
        eased = progress ** RED_EASE  # slow creep, then settles
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
# DASHBOARD
# ==========================================
def launch_dashboard():
    main_app = tk.Tk()
    main_app.title("PROPELLER DYNA PRO - CONTROL CENTER")
    main_app.geometry("1200x900")
    main_app.configure(bg="#1e1e1e")

    # ==========================================
    # 1. HEADER & LIVE STATE READOUT
    # ==========================================
    header_frame = tk.Frame(main_app, bg="#141414", pady=18)
    header_frame.pack(fill="x")

    title_label = tk.Label(
        header_frame,
        text="PROPELLER DYNA PRO - CONTROL CENTER",
        fg="#ffffff",
        bg="#141414",
        font=("Courier", 16, "bold")
    )
    title_label.pack(side="left", padx=20)

    state_label = tk.Label(
        header_frame,
        text="STATE: DISCONNECTED",
        fg="#ffaa00",
        bg="#141414",
        font=("Courier", 16, "bold")
    )
    state_label.pack(side="right", padx=20)

    # ==========================================
    # 2. USB SERIAL CONNECTION (COM5)
    # ==========================================
    ser = None
    system_state = {"armed": False, "sim_mode": True}

    try:
        ser = serial.Serial('COM5', 115200, timeout=0.01)
        state_label.config(text="STATE: CONNECTED (WAITING)", fg="#00ffcc")
    except Exception as e:
        print(f"COM5 not available ({e}) -> Running in Offline Simulation Mode")
        state_label.config(text="STATE: SIMULATED MODE", fg="#ffaa00")

    # ==========================================
    # 3. COMMAND SENDER & CONTROL DECK BUTTONS
    # ==========================================
    def send_command(cmd):
        print(f"Sending command: {cmd}")
        if cmd == "A":
            system_state["armed"] = True
            if not (ser and ser.is_open):
                state_label.config(text="STATE: TESTING (SIM ARMED)", fg="#28a745")
        elif cmd == "I":
            system_state["armed"] = False
            throttle_slider.set(1000)
            if not (ser and ser.is_open):
                state_label.config(text="STATE: IDLE (SIM)", fg="#007acc")
        elif cmd == "E":
            system_state["armed"] = False
            throttle_slider.set(1000)
            if not (ser and ser.is_open):
                state_label.config(text="STATE: E-STOPPED (SIM)", fg="#dc3545")

        if ser and ser.is_open:
            ser.write((cmd + "\n").encode('utf-8'))

    control_frame = tk.Frame(main_app, bg="#1e1e1e", pady=20)
    control_frame.pack(fill="x")

    arm_btn = tk.Button(
        control_frame,
        text="ARM MOTOR (A)",
        bg="#28a745",
        fg="#ffffff",
        font=("Courier", 14, "bold"),
        width=16,
        pady=10,
        command=lambda: send_command("A")
    )
    arm_btn.pack(side="left", padx=20)

    idle_btn = tk.Button(
        control_frame,
        text="IDLE (I)",
        bg="#007acc",
        fg="#ffffff",
        font=("Courier", 14, "bold"),
        width=16,
        pady=10,
        command=lambda: send_command("I")
    )
    idle_btn.pack(side="left", padx=10)

    estop_btn = tk.Button(
        control_frame,
        text="EMERGENCY STOP (E)",
        bg="#dc3545",
        fg="#ffffff",
        font=("Courier", 14, "bold"),
        width=22,
        pady=10,
        command=lambda: send_command("E")
    )
    estop_btn.pack(side="right", padx=20)

    # ==========================================
    # 3.5 THROTTLE CONTROL SLIDER (1000 - 2000 us)
    # ==========================================
    throttle_frame = tk.Frame(main_app, bg="#141414", pady=15)
    throttle_frame.pack(fill="x", padx=20, pady=10)

    throttle_label = tk.Label(
        throttle_frame,
        text="THROTTLE PWM (µs):",
        fg="#ffffff",
        bg="#141414",
        font=("Courier", 14, "bold")
    )
    throttle_label.pack(side="left", padx=20)

    throttle_slider = tk.Scale(
        throttle_frame,
        from_=1000,
        to=2000,
        resolution=10,
        orient="horizontal",
        bg="#141414",
        fg="#00ffcc",
        troughcolor="#2d2d2d",
        highlightthickness=0,
        font=("Courier", 12, "bold"),
        length=600
    )
    throttle_slider.set(1000)
    throttle_slider.pack(side="left", padx=20)

    # ==========================================
    # 3.8 LIVE TELEMETRY READOUT CARDS
    # ==========================================
    telemetry_frame = tk.Frame(main_app, bg="#1e1e1e", pady=10)
    telemetry_frame.pack(fill="x", padx=20)

    def create_gauge_card(parent, title, unit, col):
        card = tk.Frame(parent, bg="#141414", padx=25, pady=15, highlightthickness=1, highlightbackground="#2d2d2d")
        card.grid(row=0, column=col, padx=10, sticky="nsew")
        parent.grid_columnconfigure(col, weight=1)

        tk.Label(card, text=f"{title} ({unit})", fg="#888888", bg="#141414", font=("Courier", 12, "bold")).pack(anchor="w")
        val_label = tk.Label(card, text="0.0", fg="#00ffcc", bg="#141414", font=("Courier", 28, "bold"))
        val_label.pack(anchor="w", pady=(5, 0))
        return val_label

    thrust_val_lbl  = create_gauge_card(telemetry_frame, "THRUST", "g", 0)
    rpm_val_lbl     = create_gauge_card(telemetry_frame, "MOTOR SPEED", "RPM", 1)
    voltage_val_lbl = create_gauge_card(telemetry_frame, "VOLTAGE", "V", 2)
    current_val_lbl = create_gauge_card(telemetry_frame, "CURRENT", "A", 3)

    # ==========================================
    # 3.9 CSV TELEMETRY LOGGER (AUTO-SAVE & POP OPEN)
    # ==========================================
    log_state = {"recording": False, "file": None, "writer": None, "filepath": ""}

    def toggle_logging():
        if not log_state["recording"]:
            log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
            os.makedirs(log_dir, exist_ok=True)

            timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"dyna_run_{timestamp_str}.csv"
            filepath = os.path.join(log_dir, filename)

            f = open(filepath, mode="w", newline="")
            writer = csv.writer(f)
            writer.writerow(["Timestamp", "State", "Throttle_PWM_us", "Thrust_g", "RPM", "Voltage_V", "Current_A"])
            f.flush()

            log_state["file"] = f
            log_state["writer"] = writer
            log_state["filepath"] = filepath
            log_state["recording"] = True

            log_btn.config(text=f"● REC: {filename} (CLICK TO STOP & OPEN CSV)", bg="#ff8800", fg="#000000")
            print(f"[LOGGER]: Recording started -> {filepath}")
        else:
            if log_state["file"]:
                log_state["file"].close()

            saved_path = log_state["filepath"]
            log_state["recording"] = False
            log_state["file"] = None
            log_state["writer"] = None

            log_btn.config(text="START CSV RECORDING", bg="#2d2d2d", fg="#00ffcc")
            print(f"[LOGGER]: Saved -> {saved_path}")

            # Automatically pop open the CSV file in Windows!
            try:
                os.startfile(saved_path)
            except Exception as e:
                print(f"Could not auto-open file: {e}")

    log_frame = tk.Frame(main_app, bg="#1e1e1e", pady=10)
    log_frame.pack(fill="x", padx=20)

    log_btn = tk.Button(
        log_frame,
        text="START CSV RECORDING",
        bg="#2d2d2d",
        fg="#00ffcc",
        font=("Courier", 13, "bold"),
        pady=8,
        command=toggle_logging
    )
    log_btn.pack(fill="x", padx=10)

    # Helper to update UI gauges and write to CSV
    def update_telemetry_and_log(thrust_s, rpm_s, volt_s, curr_s):
        thrust_val_lbl.config(text=thrust_s)
        rpm_val_lbl.config(text=rpm_s)
        voltage_val_lbl.config(text=volt_s)
        current_val_lbl.config(text=curr_s)

        try:
            update_graphs(float(thrust_s), float(rpm_s))
            recent.append((time.time(), float(thrust_s), float(rpm_s), float(volt_s), float(curr_s)))
        except ValueError:
            pass  # ignore a garbled line from the Teensy

        if log_state["recording"] and log_state["writer"]:
            now_time = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            mode_str = "ARMED" if system_state["armed"] else "IDLE"
            log_state["writer"].writerow([
                now_time, mode_str, throttle_slider.get(),
                thrust_s, rpm_s, volt_s, curr_s
            ])
            log_state["file"].flush()

    # ==========================================
    # 3.95 LIVE GRAPHS
    # ==========================================
    N = 300  # points kept on screen (~30 s at 10 Hz)
    t_data      = deque(maxlen=N)
    thrust_data = deque(maxlen=N)
    rpm_data    = deque(maxlen=N)
    pwm_data    = deque(maxlen=N)
    t_start = time.time()

    fig = Figure(figsize=(10, 3.2), dpi=100, facecolor="#1e1e1e")
    ax_thrust = fig.add_subplot(131)
    ax_rpm    = fig.add_subplot(132)
    ax_pwm    = fig.add_subplot(133)

    def style_axis(ax, title, ylabel):
        ax.set_facecolor("#141414")
        ax.set_title(title, color="#ffffff", fontsize=10, fontfamily="monospace")
        ax.set_xlabel("time (s)", color="#888888")
        ax.set_ylabel(ylabel, color="#888888")
        ax.tick_params(colors="#888888")
        ax.grid(True, color="#2d2d2d")
        for spine in ax.spines.values():
            spine.set_color("#2d2d2d")

    style_axis(ax_thrust, "THRUST", "g")
    style_axis(ax_rpm, "MOTOR SPEED", "RPM")
    style_axis(ax_pwm, "THROTTLE PWM", "µs")

    (thrust_line,) = ax_thrust.plot([], [], color="#00ffcc")
    (rpm_line,)    = ax_rpm.plot([], [], color="#ffaa00")
    (pwm_line,)    = ax_pwm.plot([], [], color="#ff00ff")
    fig.tight_layout()
    ax_pwm.set_ylim(950, 2050)

    graph_canvas = FigureCanvasTkAgg(fig, master=main_app)
    graph_canvas.get_tk_widget().pack(fill="both", expand=True, padx=20, pady=10)

    def update_graphs(thrust, rpm):
        t_data.append(time.time() - t_start)
        thrust_data.append(thrust)
        rpm_data.append(rpm)
        pwm_data.append(throttle_slider.get())

        thrust_line.set_data(list(t_data), list(thrust_data))
        rpm_line.set_data(list(t_data), list(rpm_data))
        pwm_line.set_data(list(t_data), list(pwm_data))

        for ax in (ax_thrust, ax_rpm, ax_pwm):
            ax.relim()
            ax.autoscale_view()
        graph_canvas.draw_idle()

    # ==========================================
    # 4. SERIAL LISTENER + FEIGNED TELEMETRY ENGINE
    # ==========================================
    def poll_serial():
        got_real_hardware_data = False

        if ser and ser.is_open:
            while ser.in_waiting > 0:
                line = ser.readline().decode('utf-8', errors='ignore').strip()
                if line:
                    print(f"[Teensy]: {line}")
                    if "STATE: IDLE" in line:
                        state_label.config(text="STATE: IDLE", fg="#007acc")
                    elif "STATE: TESTING" in line:
                        state_label.config(text="STATE: TESTING (ARMED)", fg="#28a745")
                    elif "STATE: STOP" in line:
                        state_label.config(text="STATE: E-STOPPED", fg="#dc3545")
                        system_state["armed"] = False
                        throttle_slider.set(1000)
                    elif line.startswith("DATA,"):
                        parts = line.split(",")
                        if len(parts) == 5:
                            got_real_hardware_data = True
                            update_telemetry_and_log(parts[1], parts[2], parts[3], parts[4])
                            try:
                                update_graphs(float(parts[1]), float(parts[2]))
                            except ValueError:
                                pass  # ignore a garbled line from the Teensy


            if system_state["armed"]:
                current_pwm = throttle_slider.get()
                ser.write(f"T{current_pwm}\n".encode('utf-8'))

# FEIGNED TELEMETRY GENERATOR (Runs automatically when sensors aren't sending DATA,)
        if not got_real_hardware_data and system_state["sim_mode"] and not (ser and ser.is_open):
            pwm = throttle_slider.get() if system_state["armed"] else 1000
            pct = (pwm - 1000) / 1000.0  # 0.0 to 1.0 throttle ratio

            if pct > 0.0:
                # Non-linear propeller physics curves + realistic sensor jitter
                sim_thrust = (pct ** 1.85) * 1450.0 + random.uniform(-4.5, 4.5)
                sim_rpm    = int((pct ** 0.85) * 18500 + random.uniform(-60, 60))
                sim_curr   = (pct ** 2.1) * 34.0 + 0.6 + random.uniform(-0.15, 0.15)
                sim_volt   = 16.8 - (sim_curr * 0.045) + random.uniform(-0.03, 0.03)
            else:
                sim_thrust = max(0.0, random.uniform(-0.4, 0.4))
                sim_rpm    = 0
                sim_curr   = 0.08 + random.uniform(-0.01, 0.01)
                sim_volt   = 16.80 + random.uniform(-0.01, 0.01)

            update_telemetry_and_log(
                f"{sim_thrust:.1f}",
                f"{sim_rpm}",
                f"{sim_volt:.2f}",
                f"{sim_curr:.2f}"
            )

        main_app.after(100, poll_serial)
    def on_close():
        try:
            if ser and ser.is_open:
                ser.write(b"E\n")   # cut throttle before letting go of the port
                ser.close()
        except Exception as e:
            print(f"Shutdown warning: {e}")
        if log_state["file"]:
            log_state["file"].close()
        main_app.destroy()

    main_app.protocol("WM_DELETE_WINDOW", on_close)
    poll_serial()
    main_app.mainloop()

    # ==========================================
    # 3.97 AUTOMATED STEP TEST
    # ==========================================
    recent = deque(maxlen=400)           # (time, thrust, rpm, volt, curr) samples
    step = {"running": False, "i": 0}
    SETPOINTS = list(range(1100, 2001, 100))
    HOLD_MS = 3000                       # time spent at each setpoint
    AVG_MS = 1000                        # average only the last 1 s of each hold
    step_results = []

    def reset_step_button():
        step_btn.config(text="RUN STEP TEST", bg="#2d2d2d", fg="#00ffcc")

    def abort_step_test(reason):
        step["running"] = False
        reset_step_button()
        print(f"[STEP TEST]: aborted ({reason})")

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
        print(f"[STEP TEST]: saved -> {path}")

    def next_step():
        if not step["running"]:
            return
        if not system_state["armed"]:
            abort_step_test("disarmed")
            return
        if step["i"] >= len(SETPOINTS):
            finish_step_test()
            return
        throttle_slider.set(SETPOINTS[step["i"]])
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
        step_btn.config(text="STEP TEST RUNNING (E-STOP TO ABORT)", bg="#ff8800", fg="#000000")
        send_command("A")
        main_app.after(1000, next_step)

    step_btn = tk.Button(
        main_app,
        text="RUN STEP TEST",
        bg="#2d2d2d",
        fg="#00ffcc",
        font=("Courier", 13, "bold"),
        pady=8,
        command=start_step_test
    )
    step_btn.pack(fill="x", padx=30, pady=(0, 5))

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

