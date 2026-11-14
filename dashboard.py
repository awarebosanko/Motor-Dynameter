# This dashboard was developed by Aiden Ware Bosanko
import serial
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import tkinter as tk
import tkinter.font as tkfont
from PIL import Image, ImageDraw, ImageFont

# ==========================================
# TUNING KNOBS (change these to learn how it works)
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
# Text -> grid mask (which character cells are "inside" the letters)
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
# THIS IS WHERE YOU WILL BUILD YOUR DASHBOARD
# ==========================================
def launch_dashboard():
    main_app = tk.Tk()
    main_app.title("Propeller Dyna Pro - Control Center")
    main_app.geometry("800x600")
    main_app.configure(bg="#1e1e1e")

    tk.Label(
        main_app,
        text="Aiden, the keyboard is yours. Let's build the GUI.",
        fg="#00ffcc", bg="#1e1e1e", font=("Helvetica", 16)
    ).pack(pady=250)

    main_app.mainloop()


# ==========================================
# BOOT SEQUENCE
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