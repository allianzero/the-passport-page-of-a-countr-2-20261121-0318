#!/usr/bin/env python3
"""The Passport Page of a Country That Isn't There.

A program bounty entry for make.fun (program/v1). It draws one open
passport spread for an invented country -- the Republic of Aurelia --
and writes it to /output/entry.png (1024x768, under 1 MiB).

Everything is drawn from scratch with the Python standard library
only: a small supersampled rasteriser, a hand-authored single-stroke
vector font, and a hand-written PNG encoder. No network, no files
read, no randomness, no clock: the output is fully deterministic.

The spread is built to read as a real working document:
  * left page: the data page -- coat of arms, portrait, personal
    details, signature, and a machine-readable zone whose check
    digits are computed with the real ICAO 7-3-1 algorithm;
  * right page: the visas page -- a Sularia visa sticker with its
    registration condition, and arrival/departure stamps from the
    neighbouring countries Drenmar, Sularia and Porto Verde.
Every date agrees: the passport is issued 12 MAR 2023, the visa is
issued 28 AUG 2023 for a stay 07-21 SEP 2023 inside its 90 days, and
no stamp predates the passport.
"""

import math
import os
import struct
import zlib

W, H = 1024, 768          # final image size (max 1024 x 1024)
SS = 2                    # supersampling factor (anti-aliasing)
SW, SH = W * SS, H * SS   # working buffer size


# ---------------------------------------------------------------- canvas

class Canvas:
    """An RGB canvas drawn at SSx resolution, downsampled on output."""

    def __init__(self):
        self.buf = bytearray(SW * SH * 3)
        self.clip = (0, 0, SW, SH)

    def _idx(self, x, y):
        return (y * SW + x) * 3

    def px(self, x, y, color, alpha=1.0):
        """Blend one working-resolution pixel. x, y are working coords."""
        x0, y0, x1, y1 = self.clip
        if x < x0 or y < y0 or x >= x1 or y >= y1:
            return
        if alpha <= 0.0:
            return
        i = self._idx(x, y)
        r, g, b = color
        if alpha >= 1.0:
            self.buf[i] = r
            self.buf[i + 1] = g
            self.buf[i + 2] = b
        else:
            a = alpha
            self.buf[i] = int(self.buf[i] * (1 - a) + r * a)
            self.buf[i + 1] = int(self.buf[i + 1] * (1 - a) + g * a)
            self.buf[i + 2] = int(self.buf[i + 2] * (1 - a) + b * a)

    def fill_rect(self, x0, y0, x1, y1, color, alpha=1.0):
        ax0, ay0 = int(x0 * SS), int(y0 * SS)
        ax1, ay1 = int(x1 * SS), int(y1 * SS)
        for yy in range(max(ay0, 0), min(ay1, SH)):
            base = yy * SW * 3
            for xx in range(max(ax0, 0), min(ax1, SW)):
                i = base + xx * 3
                r, g, b = color
                if alpha >= 1.0:
                    self.buf[i] = r
                    self.buf[i + 1] = g
                    self.buf[i + 2] = b
                else:
                    a = alpha
                    self.buf[i] = int(self.buf[i] * (1 - a) + r * a)
                    self.buf[i + 1] = int(self.buf[i + 1] * (1 - a) + g * a)
                    self.buf[i + 2] = int(self.buf[i + 2] * (1 - a) + b * a)

    def poly(self, pts, color, alpha=1.0):
        """Fill a polygon given in final-pixel coordinates (scanline)."""
        sp = [(x * SS, y * SS) for x, y in pts]
        if len(sp) < 3:
            return
        ys = [p[1] for p in sp]
        y0, y1 = int(min(ys)), int(max(ys)) + 1
        n = len(sp)
        for yy in range(max(y0, 0), min(y1, SH)):
            xs = []
            for k in range(n):
                x1, y1p = sp[k]
                x2, y2p = sp[(k + 1) % n]
                if (y1p <= yy < y2p) or (y2p <= yy < y1p):
                    t = (yy - y1p) / (y2p - y1p)
                    xs.append(x1 + t * (x2 - x1))
            xs.sort()
            for j in range(0, len(xs) - 1, 2):
                xa, xb = int(xs[j]), int(xs[j + 1]) + 1
                for xx in range(max(xa, 0), min(xb, SW)):
                    self.px(xx, yy, color, alpha)

    def ellipse(self, cx, cy, rx, ry, color, alpha=1.0):
        """Fill an ellipse in final-pixel coordinates (scanline)."""
        cx, cy, rx, ry = cx * SS, cy * SS, rx * SS, ry * SS
        y0, y1 = int(cy - ry), int(cy + ry) + 1
        for yy in range(max(y0, 0), min(y1, SH)):
            dy = (yy - cy) / ry
            if abs(dy) >= 1.0:
                continue
            dx = rx * math.sqrt(1 - dy * dy)
            xa, xb = int(cx - dx), int(cx + dx) + 1
            for xx in range(max(xa, 0), min(xb, SW)):
                self.px(xx, yy, color, alpha)

    def line(self, x0, y0, x1, y1, width, color, alpha=1.0):
        """A thick line, drawn as a filled polygon (final-pixel coords)."""
        dx, dy = x1 - x0, y1 - y0
        ln = math.hypot(dx, dy)
        if ln < 1e-6:
            self.ellipse(x0, y0, width / 2, width / 2, color, alpha)
            return
        nx, ny = -dy / ln * width / 2, dx / ln * width / 2
        self.poly([(x0 + nx, y0 + ny), (x1 + nx, y1 + ny),
                   (x1 - nx, y1 - ny), (x0 - nx, y0 - ny)], color, alpha)

    def circle_outline(self, cx, cy, r, width, color, alpha=1.0, a0=0.0, a1=360.0):
        steps = max(24, int(r * 2.2))
        prev = None
        for k in range(steps + 1):
            a = math.radians(a0 + (a1 - a0) * k / steps)
            p = (cx + r * math.cos(a), cy + r * math.sin(a))
            if prev is not None:
                self.line(prev[0], prev[1], p[0], p[1], width, color, alpha)
            prev = p

    def star(self, cx, cy, r, color, alpha=1.0, rot=-90.0):
        pts = []
        for k in range(10):
            ang = math.radians(rot + k * 36.0)
            rr = r if k % 2 == 0 else r * 0.42
            pts.append((cx + rr * math.cos(ang), cy + rr * math.sin(ang)))
        self.poly(pts, color, alpha)


def png_bytes(rgb, w, h):
    """Encode raw RGB bytes as a PNG (filter 0 scanlines, zlib)."""
    raw = bytearray()
    stride = w * 3
    for y in range(h):
        raw.append(0)
        raw += rgb[y * stride:(y + 1) * stride]

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
            + chunk(b"IEND", b""))


def downsample(cv):
    """Average each SSxSS block into the final RGB image."""
    out = bytearray(W * H * 3)
    for y in range(H):
        for x in range(W):
            r = g = b = 0
            for dy in range(SS):
                base = ((y * SS + dy) * SW + x * SS) * 3
                for dx in range(SS):
                    i = base + dx * 3
                    r += cv.buf[i]
                    g += cv.buf[i + 1]
                    b += cv.buf[i + 2]
            n = SS * SS
            o = (y * W + x) * 3
            out[o] = r // n
            out[o + 1] = g // n
            out[o + 2] = b // n
    return bytes(out)


# ------------------------------------------------------- stroke font
# One hand-authored single-stroke font. Grid: x 0..8, y 0..14.
# Cap top y=1, baseline y=11, x-height top y=6, descender y=14.
# Format: "x,y x,y|x,y ..." -- strokes separated by "|".
FONT_RAW = {
    "A": "0,11 4,1 8,11|2,7.5 6,7.5",
    "B": "0,1 0,11|0,1 5,1 7,2.5 7,4.5 5,6 0,6|0,6 5.5,6 7,7.5 7,9.5 5.5,11 0,11",
    "C": "7,2.5 5,1 2,1 0,3 0,9 2,11 5,11 7,9.5",
    "D": "0,1 0,11 5,11 8,8 8,4 5,1 0,1",
    "E": "0,1 0,11 7,11|0,1 6,1|0,6 5,6",
    "F": "0,1 0,11|0,1 6,1|0,6 5,6",
    "G": "7,2.5 5,1 2,1 0,3 0,9 2,11 5,11 7,9 7,6 4,6",
    "H": "0,1 0,11|8,1 8,11|0,6 8,6",
    "I": "0,1 8,1|4,1 4,11|0,11 8,11",
    "J": "8,1 8,9 6,11 2,11 0,9",
    "K": "0,1 0,11|7,1 0,6 7,11",
    "L": "0,1 0,11 7,11",
    "M": "0,11 0,1 4,6 8,1 8,11",
    "N": "0,11 0,1 8,11 8,1",
    "O": "2,1 6,1 8,3 8,9 6,11 2,11 0,9 0,3 2,1",
    "P": "0,11 0,1 5,1 7,3 7,5 5,6 0,6",
    "Q": "2,1 6,1 8,3 8,9 6,11 2,11 0,9 0,3 2,1|5.5,9 8,12",
    "R": "0,11 0,1 5,1 7,3 7,5 5,6 0,6|4,6 8,11",
    "S": "7,2.5 5,1 2,1 0,3 0,5 2,6 6,6 8,7 8,9 6,11 3,11 1,9.5",
    "T": "0,1 8,1|4,1 4,11",
    "U": "0,1 0,9 2,11 6,11 8,9 8,1",
    "V": "0,1 4,11 8,1",
    "W": "0,1 2,11 4,6 6,11 8,1",
    "X": "0,1 8,11|8,1 0,11",
    "Y": "0,1 4,6 8,1|4,6 4,11",
    "Z": "0,1 8,1 0,11 8,11",
    "a": "2,6 6,6 8,8 8,10 6,11 2,11 0,9 0,7 2,6|8,6 8,11",
    "b": "0,1 0,11|0,7 2,6 5,6 7,8 7,9.5 5,11 0,11",
    "c": "7,7 5,6 2,6 0,8 0,9.5 2,11 5,11 7,10",
    "d": "8,1 8,11|8,7 6,6 3,6 1,8 1,9.5 3,11 6,11 8,10",
    "e": "7,9 5,11 2,11 0,9 0,7 2,6 5,6 7,7 7,8.5 0,8.5",
    "f": "7,3 5,1 3,1 2,2.5|5,1 5,11|1.5,5 6,5",
    "g": "2,6 6,6 8,8 8,10 6,11 2,11 0,9 0,7 2,6|8,11 8,13 6,14 3,14 1,13",
    "h": "0,1 0,11|0,7 2,6 5,6 7,8 7,11",
    "i": "4,6 4,11|4,2.5 4,3.5",
    "j": "6,6 6,12 4,14 2,14|6,2.5 6,3.5",
    "k": "0,1 0,11|7,6 1,8.5 7,11",
    "l": "4,1 4,11",
    "m": "0,11 0,6 2.5,6 4,7.5 5.5,6 8,6 8,11",
    "n": "0,11 0,6 2,6 5,6 7,8 7,11",
    "o": "2,6 6,6 8,8 8,9.5 6,11 2,11 0,9.5 0,8 2,6",
    "p": "0,6 0,14|0,7 2,6 5,6 7,8 7,9.5 5,11 0,11",
    "q": "8,6 8,14|8,7 6,6 3,6 1,8 1,9.5 3,11 6,11 8,10",
    "r": "0,11 0,6|0,7 2,6 4,6 5,7",
    "s": "7,7 5,6 2,6 0,7.5 0,8.5 2,9.5 5,9.5 7,10.5 6,11 3,11 1,10",
    "t": "4,1 4,11|1,5 7,5",
    "u": "0,6 0,9.5 2,11 5,11 7,9.5 7,6",
    "v": "0,6 4,11 8,6",
    "w": "0,6 2,11 4,7.5 6,11 8,6",
    "x": "0,6 8,11|8,6 0,11",
    "y": "0,6 4,11 8,6|4,11 4,13 2,14",
    "z": "0,6 8,6 0,11 8,11",
    "0": "2,1 6,1 8,3 8,9 6,11 2,11 0,9 0,3 2,1",
    "1": "2,3 4,1 4,11|1,11 7,11",
    "2": "0,3 2,1 6,1 8,3 8,5 0,11 8,11",
    "3": "1,2 3,1 6,1 8,3 8,5 6,6 8,6 8,9 6,11 3,11 1,10",
    "4": "6,1 0,8 8,8|6,1 6,11",
    "5": "8,1 0,1 0,6 5,6 7,7.5 7,9.5 5,11 0,11",
    "6": "7,2.5 5,1 2,1 0,3 0,9 2,11 5,11 7,9.5 7,7.5 5,6 2,6 0,8",
    "7": "0,1 8,1 4,11",
    "8": "2,1 6,1 8,3 8,5 6,6 2,6 0,5 0,3 2,1|2,6 6,6 8,8 8,9.5 6,11 2,11 0,9.5 0,8 2,6",
    "9": "0,3 2,1 6,1 8,3 8,9 6,11 3,11 1,10|0,3 0,5.5 2,6.5 6,6.5",
    " ": "",
    ".": "3.5,10.5 4.5,10.5",
    ",": "3.5,10.5 4.5,10.5|4,11 3,13",
    "'": "4,1 3.5,4",
    "-": "1,6 7,6",
    "/": "7,1 1,11",
    ":": "3.5,4.5 4.5,4.5|3.5,9 4.5,9",
    ";": "3.5,4.5 4.5,4.5|3.5,9.5 4.5,9.5|4,10.5 3,13",
    "(": "6,1 3,3 3,9 6,11",
    ")": "2,1 5,3 5,9 2,11",
    "<": "7,2 1,6 7,10",
    ">": "1,2 7,6 1,10",
    "&": "6,1 2,1 0,3 0,5 3,6.5 7,6.5 8,8 6,11 2,11 0,9",
    "+": "4,3 4,9|1,6 7,6",
    "=": "1,4 7,4|1,8 7,8",
    "!": "4,1 4,8|3.5,10.5 4.5,10.5",
    "?": "2,2 4,1 6,2 6,4 4,6 4,7.5|3.5,10.5 4.5,10.5",
    '"': "2,1 1.5,4|6,1 5.5,4",
    "%": "7,1 1,11|1,1 3,1 3,3 1,3 1,1|5,9 7,9 7,11 5,11 5,9",
    "*": "4,1 4,11|1,3 7,9|7,3 1,9",
    "·": "3.5,6 4.5,6",
}

FONT = {}
for _ch, _raw in FONT_RAW.items():
    _strokes = []
    if _raw:
        for _s in _raw.split("|"):
            _strokes.append([tuple(map(float, _p.split(","))) for _p in _s.split()])
    FONT[_ch] = _strokes


def text_width(s, size, tracking=0.0):
    """Width in final pixels of s at cap-height `size`."""
    scale = size / 10.0
    return len(s) * (9.0 * scale + tracking) - tracking


def draw_text(cv, s, x, y, size, color, alpha=1.0, align="left",
              rotate=0.0, tracking=0.0, bold=False):
    """Draw text; (x, y) is the baseline start (or centre for align).

    size is the cap height in final pixels. Rotation is in degrees
    around the anchor point.
    """
    scale = size / 10.0
    adv = 9.0 * scale + tracking
    w = len(s) * adv - tracking
    if align == "center":
        x -= w / 2.0
    elif align == "right":
        x -= w
    lw = max(1.0, size * 0.13)
    if bold:
        lw *= 1.7
    th = math.radians(rotate)
    ct, st = math.cos(th), math.sin(th)
    cx = x
    for ch in s:
        for stroke in FONT.get(ch, FONT["?"]):
            prev = None
            for gx, gy in stroke:
                # offsets from the anchor, rotated, then placed at (x, y)
                ox = (cx - x) + gx * scale
                oy = (gy - 11.0) * scale
                p = (x + ox * ct - oy * st, y + ox * st + oy * ct)
                if prev is not None:
                    cv.line(prev[0], prev[1], p[0], p[1], lw, color, alpha)
                prev = p
        cx += adv


def draw_text_lines(cv, lines, x, y, size, color, leading=None, **kw):
    """Draw lines of text; lines are (text, size) or plain strings."""
    if leading is None:
        leading = size * 1.55
    for item in lines:
        if isinstance(item, tuple):
            t, sz = item
        else:
            t, sz = item, size
        draw_text(cv, t, x, y, sz, color, **kw)
        y += leading if isinstance(item, tuple) else size * 1.55
    return y


# ------------------------------------------------------------- colours
NAVY = (27, 42, 74)        # document ink
NAVY_SOFT = (58, 74, 110)
GOLD = (176, 141, 63)
PAPER = (247, 242, 228)    # passport page cream
PAPER_DARK = (238, 231, 210)
INK_BLUE = (28, 74, 148)
INK_PURPLE = (104, 52, 130)
INK_GREEN = (28, 110, 72)
INK_RED = (168, 44, 40)
LEATHER = (20, 28, 46)     # backdrop the spread lies on
GREY = (110, 108, 96)
SKIN = (238, 195, 154)
SKIN_SH = (214, 168, 126)
HAIR = (52, 38, 26)
JACKET = (43, 58, 85)


# ------------------------------------------------------------- MRZ
def mrz_check(s):
    """ICAO 9303 check digit: values A=10..Z=35, '<'=0; weights 7,3,1."""
    total = 0
    for i, ch in enumerate(s):
        if ch == "<":
            v = 0
        elif ch.isdigit():
            v = int(ch)
        else:
            v = ord(ch) - 55
        total += v * (7, 3, 1)[i % 3]
    return str(total % 10)


def build_mrz():
    doc = "AU4829173"
    line1 = "P<AUR" + "MARLOWE<<ELENA<SOFIA" + "<" * 19
    c_doc = mrz_check(doc)
    c_dob = mrz_check("940614")
    c_exp = mrz_check("330311")
    opt = "<" * 14
    c_opt = mrz_check(opt)
    # Composite check: ICAO 9303 covers positions 1-10, 14-20, 22-28, 29-43
    # (document+check, birth+check, expiry+check, optional+check) --
    # nationality and sex are NOT included.
    composite = mrz_check(doc + c_doc + "940614" + c_dob
                          + "330311" + c_exp + opt + c_opt)
    line2 = (doc + c_doc + "AUR" + "940614" + c_dob + "F"
             + "330311" + c_exp + opt + c_opt + composite)
    assert len(line1) == 44 and len(line2) == 44, (len(line1), len(line2))
    return line1, line2


# ------------------------------------------------------- coat of arms
def coat_of_arms(cv, cx, cy, s):
    """A small shield with a star and laurel sprigs, s = shield height."""
    w = s * 0.78
    top, bot = cy - s / 2, cy + s / 2
    pts = [(cx - w / 2, top), (cx + w / 2, top), (cx + w / 2, cy + s * 0.08),
           (cx, bot), (cx - w / 2, cy + s * 0.08)]
    cv.poly(pts, NAVY)
    cv.star(cx, cy - s * 0.06, s * 0.20, GOLD)
    # laurel sprigs: two arcs of dots flanking the shield
    for side in (-1, 1):
        for k in range(4):
            a = math.radians(200 + side * 0 + k * 16) if side < 0 else math.radians(-20 - k * 16)
            r = s * 0.62
            px = cx + side * r * math.cos(math.radians(38 + k * 14))
            py = cy + s * 0.30 - k * s * 0.13
            cv.ellipse(px, py, 1.6, 2.6, GOLD, 0.9)


# ---------------------------------------------------------- portrait
def portrait(cv, x0, y0, x1, y1):
    """A flat-style passport photograph of the holder, drawn by hand."""
    # backdrop: pale blue-grey, lighter at the top
    bands = 12
    for k in range(bands):
        t = k / (bands - 1)
        c = (int(206 - 22 * t), int(216 - 20 * t), int(226 - 16 * t))
        cv.fill_rect(x0, y0 + (y1 - y0) * k / bands,
                     x1, y0 + (y1 - y0) * (k + 1) / bands, c)
    cx = (x0 + x1) / 2
    # shoulders / jacket
    cv.poly([(x0, y1), (x1, y1), (x1, y1 - 52), (cx + 52, y1 - 78),
             (cx + 26, y1 - 88), (cx - 26, y1 - 88), (cx - 52, y1 - 78),
             (x0, y1 - 52)], JACKET)
    # shirt V and collar
    cv.poly([(cx - 16, y1 - 86), (cx + 16, y1 - 86), (cx, y1 - 52)],
            (240, 238, 230))
    cv.poly([(cx - 16, y1 - 86), (cx, y1 - 66), (cx - 4, y1 - 88)], (250, 248, 240))
    cv.poly([(cx + 16, y1 - 86), (cx, y1 - 66), (cx + 4, y1 - 88)], (250, 248, 240))
    # neck
    cv.fill_rect(cx - 13, y1 - 118, cx + 13, y1 - 82, SKIN)
    cv.ellipse(cx, y1 - 84, 15, 6, SKIN_SH, 0.55)
    # ears
    cv.ellipse(x0 + 30, y0 + 96, 7, 11, SKIN)
    cv.ellipse(x1 - 30, y0 + 96, 7, 11, SKIN)
    # face
    cv.ellipse(cx, y0 + 96, 36, 44, SKIN)
    # cheek shading, right side
    cv.ellipse(cx + 16, y0 + 104, 16, 30, SKIN_SH, 0.35)
    # hair: cap over the top of the head, strands down both sides
    cv.ellipse(cx, y0 + 62, 39, 34, HAIR)
    cv.ellipse(cx, y0 + 100, 37, 40, SKIN)   # face back over the cap
    cv.ellipse(cx, y0 + 60, 39, 30, HAIR)    # hairline sweep
    cv.poly([(cx - 39, y0 + 58), (cx - 30, y0 + 58), (cx - 34, y0 + 128),
             (cx - 41, y0 + 128)], HAIR)
    cv.poly([(cx + 39, y0 + 58), (cx + 30, y0 + 58), (cx + 34, y0 + 128),
             (cx + 41, y0 + 128)], HAIR)
    # brows, eyes, nose, mouth
    cv.line(cx - 26, y0 + 88, cx - 8, y0 + 86, 2.6, HAIR)
    cv.line(cx + 8, y0 + 86, cx + 26, y0 + 88, 2.6, HAIR)
    for ex in (cx - 17, cx + 17):
        cv.ellipse(ex, y0 + 98, 7.5, 4.5, (248, 246, 240))
        cv.ellipse(ex, y0 + 98, 3.4, 3.4, (46, 34, 26))
        cv.ellipse(ex - 1, y0 + 97, 1.4, 1.4, (255, 255, 255))
    cv.line(cx - 1, y0 + 100, cx - 3, y0 + 116, 2.0, SKIN_SH)
    cv.line(cx - 3, y0 + 116, cx + 2, y0 + 118, 2.0, SKIN_SH)
    cv.ellipse(cx, y0 + 130, 9, 2.6, (150, 84, 74))
    # soft vignette inside the frame
    cv.fill_rect(x0, y0, x1, y0 + 3, (255, 255, 255), 0.25)
    cv.fill_rect(x0, y1 - 3, x1, y1, (0, 0, 0), 0.12)


# ---------------------------------------------------------- signature
# Flowing strokes in a 140 x 26 box, drawn like a pen signature.
SIGNATURE = [
    [(4, 14), (10, 4), (16, 12), (12, 20), (20, 18), (26, 8), (34, 14),
     (40, 10), (46, 16), (52, 12), (58, 15), (64, 11), (70, 14)],
    [(74, 16), (78, 5), (84, 13), (80, 20), (88, 16), (94, 9), (100, 15),
     (106, 12), (112, 15), (118, 11), (124, 14)],
    [(6, 22), (60, 24), (132, 20)],
]


def signature(cv, x0, y0, x1, y1):
    sx = (x1 - x0) / 140.0
    sy = (y1 - y0) / 26.0
    for stroke in SIGNATURE:
        prev = None
        for px, py in stroke:
            p = (x0 + px * sx, y0 + py * sy)
            if prev is not None:
                cv.line(prev[0], prev[1], p[0], p[1], 1.6, NAVY, 0.9)
            prev = p


# -------------------------------------------------------------- stamps
def stamp_oval(cv, cx, cy, rw, rh, rot, color, lines, alpha=0.8):
    """An oval border stamp; lines are (text, size) centred on (cx, cy)."""
    th = math.radians(rot)
    ct, st = math.cos(th), math.sin(th)

    def rot_pt(px, py):
        return (cx + px * ct - py * st, cy + px * st + py * ct)

    # double oval border, rotated: approximate with rotated polyline
    for rr, ww in ((1.0, 2.2), (0.88, 1.2)):
        pts = []
        for k in range(49):
            a = math.radians(k * 360.0 / 48)
            pts.append(rot_pt(rw * rr * math.cos(a), rh * rr * math.sin(a)))
        for k in range(48):
            cv.line(pts[k][0], pts[k][1], pts[k + 1][0], pts[k + 1][1],
                    ww, color, alpha)
    total = sum(sz * 1.5 for _, sz in lines)
    y = cy - total / 2 + 4
    for text, sz in lines:
        w = text_width(text, sz, tracking=0.4)
        draw_text(cv, text, cx - w / 2, y + sz, sz, color, alpha=alpha,
                  rotate=rot, tracking=0.4)
        y += sz * 1.5


def stamp_rect(cv, cx, cy, w, h, rot, color, lines, alpha=0.8):
    """A rectangular border stamp; lines are (text, size)."""
    th = math.radians(rot)
    ct, st = math.cos(th), math.sin(th)

    def rot_pt(px, py):
        return (cx + px * ct - py * st, cy + px * st + py * ct)

    for inset, ww in ((0, 2.2), (7, 1.2)):
        corners = [(-w / 2 + inset, -h / 2 + inset), (w / 2 - inset, -h / 2 + inset),
                   (w / 2 - inset, h / 2 - inset), (-w / 2 + inset, h / 2 - inset)]
        rp = [rot_pt(px, py) for px, py in corners]
        for k in range(4):
            cv.line(rp[k][0], rp[k][1], rp[(k + 1) % 4][0], rp[(k + 1) % 4][1],
                    ww, color, alpha)
    total = sum(sz * 1.5 for _, sz in lines)
    y = cy - total / 2 + 4
    for text, sz in lines:
        wdt = text_width(text, sz, tracking=0.4)
        draw_text(cv, text, cx - wdt / 2, y + sz, sz, color, alpha=alpha,
                  rotate=rot, tracking=0.4)
        y += sz * 1.5


# -------------------------------------------------------------- pages
def guilloche(cv, x0, y0, x1, y1, cx, cy):
    """Faint concentric security arcs, clipped to the page."""
    old = cv.clip
    cv.clip = (int(x0 * SS), int(y0 * SS), int(x1 * SS), int(y1 * SS))
    for r in range(30, 560, 9):
        cv.circle_outline(cx, cy, r, 0.8, NAVY, 0.05)
    cv.clip = old


def watermark(cv, x0, y0, x1, y1, text):
    old = cv.clip
    cv.clip = (int(x0 * SS), int(y0 * SS), int(x1 * SS), int(y1 * SS))
    for row in range(4):
        for col in range(3):
            draw_text(cv, text, x0 + 40 + col * 180, y0 + 130 + row * 150,
                      30, NAVY, alpha=0.045, rotate=-32, tracking=6)
    cv.clip = old


def left_page(cv):
    x0, y0, x1, y1 = 24, 22, 504, 746
    cv.fill_rect(x0, y0, x1, y1, PAPER)
    guilloche(cv, x0, y0, x1, y1, 264, 420)
    watermark(cv, x0, y0, x1, y1, "AURELIA")
    # header
    coat_of_arms(cv, 264, 62, 52)
    draw_text(cv, "REPUBLIC OF AURELIA", 264, 108, 21, NAVY, align="center",
              tracking=1.2, bold=True)
    draw_text(cv, "PASSPORT", 264, 132, 14, NAVY, align="center", tracking=4)
    draw_text(cv, "PASSEPORT", 264, 150, 10, NAVY_SOFT, align="center",
              tracking=3)
    cv.line(x0 + 24, 164, x1 - 24, 164, 1.4, NAVY)
    draw_text(cv, "8", x1 - 34, 44, 11, GREY, align="center")
    # type / code / number row
    draw_text(cv, "Type", 48, 186, 8, GREY)
    draw_text(cv, "P", 48, 202, 14, NAVY, bold=True)
    draw_text(cv, "Code", 128, 186, 8, GREY)
    draw_text(cv, "AUR", 128, 202, 14, NAVY, bold=True)
    draw_text(cv, "Passport No.", 216, 186, 8, GREY)
    draw_text(cv, "AU 4829173", 216, 202, 14, NAVY, bold=True)
    # photograph
    px0, py0, px1, py1 = 44, 222, 184, 412
    cv.fill_rect(px0 - 3, py0 - 3, px1 + 3, py1 + 3, NAVY)
    portrait(cv, px0, py0, px1, py1)
    # ghost image: faint profile echo at the photo's lower corner
    cv.ellipse(px1 - 22, py1 - 18, 12, 15, NAVY, 0.10)
    # signature under the photo
    draw_text(cv, "Holder's signature", 44, 434, 8, GREY)
    signature(cv, 48, 440, 180, 466)
    cv.line(44, 470, 184, 470, 1.0, NAVY_SOFT, 0.7)
    # personal details, right of the photo
    fields = [
        ("SURNAME / NOM", "MARLOWE"),
        ("GIVEN NAMES / PRENOMS", "ELENA SOFIA"),
        ("NATIONALITY / NATIONALITE", "AURELIAN"),
        ("DATE OF BIRTH / DATE DE NAISSANCE", "14 JUN 1994"),
        ("PLACE OF BIRTH / LIEU DE NAISSANCE", "PORT AURELINE"),
        ("SEX / SEXE", "F"),
        ("DATE OF ISSUE / DATE DE DELIVRANCE", "12 MAR 2023"),
        ("DATE OF EXPIRY / DATE D'EXPIRATION", "11 MAR 2033"),
        ("AUTHORITY / AUTORITE", "MINISTRY OF FOREIGN AFFAIRS"),
    ]
    fy = 232
    for label, value in fields:
        draw_text(cv, label, 204, fy, 7.5, GREY, tracking=0.3)
        draw_text(cv, value, 204, fy + 15, 11, NAVY, bold=True)
        fy += 27
    # machine-readable zone
    line1, line2 = build_mrz()
    cv.fill_rect(x0 + 20, 596, x1 - 20, 716, (255, 255, 255), 0.55)
    draw_text(cv, line1, 264, 636, 10, NAVY, align="center", tracking=0)
    draw_text(cv, line2, 264, 668, 10, NAVY, align="center", tracking=0)
    cv.line(x0 + 20, 596, x1 - 20, 596, 1.0, NAVY_SOFT, 0.5)


def right_page(cv):
    x0, y0, x1, y1 = 520, 22, 1000, 746
    cv.fill_rect(x0, y0, x1, y1, PAPER)
    guilloche(cv, x0, y0, x1, y1, 760, 420)
    draw_text(cv, "VISAS", 760, 56, 17, NAVY, align="center", tracking=6)
    cv.line(x0 + 24, 70, x1 - 24, 70, 1.4, NAVY)
    draw_text(cv, "9", x1 - 34, 44, 11, GREY, align="center")
    # --- Sularia visa sticker (the telling paperwork detail)
    vx0, vy0, vx1, vy1 = 544, 88, 976, 268
    cv.fill_rect(vx0, vy0, vx1, vy1, (223, 232, 238))
    cv.fill_rect(vx0, vy0, vx1, vy0 + 30, NAVY)
    draw_text(cv, "VISA", vx0 + 16, vy0 + 21, 13, (255, 255, 255), bold=True,
              tracking=2)
    draw_text(cv, "REPUBLIC OF SULARIA", vx0 + 96, vy0 + 21, 10,
              (255, 255, 255), tracking=1)
    draw_text(cv, "No. SV-2023-08417", vx1 - 16, vy0 + 21, 10,
              (255, 255, 255), align="right")
    vy = vy0 + 52
    draw_text(cv, "Type: C  -  SINGLE ENTRY", vx0 + 16, vy, 11.5, NAVY, bold=True)
    draw_text(cv, "Valid: 28 AUG 2023  to  26 NOV 2023  (90 DAYS)",
              vx0 + 16, vy + 20, 10, NAVY, bold=True)
    draw_text(cv, "Issued at: PORT AURELINE", vx0 + 16, vy + 40, 11.5, NAVY)
    draw_text(cv, "CONDITION:", vx0 + 16, vy + 64, 11, INK_RED, bold=True)
    draw_text(cv, "HOLDER MUST REGISTER WITH THE", vx0 + 16,
              vy + 82, 10.5, INK_RED)
    draw_text(cv, "PREFECTURE OF CALVENTO WITHIN 7 DAYS.", vx0 + 16,
              vy + 99, 10.5, INK_RED)
    draw_text(cv, "NO EMPLOYMENT PERMITTED.", vx0 + 16, vy + 116, 10.5, INK_RED)
    # visa seal
    cv.circle_outline(vx1 - 52, vy1 - 34, 20, 1.4, NAVY, 0.75)
    cv.star(vx1 - 52, vy1 - 34, 8, NAVY, 0.75)
    # visa border
    cv.line(vx0, vy0, vx1, vy0, 1.6, NAVY)
    cv.line(vx0, vy1, vx1, vy1, 1.6, NAVY)
    cv.line(vx0, vy0, vx0, vy1, 1.6, NAVY)
    cv.line(vx1, vy0, vx1, vy1, 1.6, NAVY)
    # --- fee stamp overlapping the visa sticker's bottom-right corner
    stamp_rect(cv, 925, 268, 140, 28, -10, INK_RED,
               [("FEE PAID  -  25 AUR", 9)], alpha=0.85)
    # --- arrival / departure stamps from neighbouring countries
    stamp_oval(cv, 650, 350, 88, 52, -7, INK_BLUE, [
        ("KINGDOM OF DRENMAR", 9),
        ("ARRIVAL", 13),
        ("HARROWGATE", 10),
        ("02 MAY 2023", 11),
    ])
    stamp_oval(cv, 870, 350, 88, 52, 5, INK_BLUE, [
        ("KINGDOM OF DRENMAR", 9),
        ("DEPARTURE", 13),
        ("HARROWGATE", 10),
        ("18 MAY 2023", 11),
    ])
    stamp_rect(cv, 650, 480, 188, 96, 4, INK_PURPLE, [
        ("REPUBLIC OF SULARIA", 9.5),
        ("ARRIVED", 13),
        ("CALVENTO", 10),
        ("07 SEP 2023", 11),
    ])
    stamp_rect(cv, 870, 480, 188, 96, -5, INK_PURPLE, [
        ("REPUBLIC OF SULARIA", 9.5),
        ("DEPARTED", 13),
        ("CALVENTO", 10),
        ("21 SEP 2023", 11),
    ])
    stamp_oval(cv, 650, 612, 88, 52, -4, INK_GREEN, [
        ("PORTO VERDE", 11),
        ("ARRIVAL", 13),
        ("SAO MIGUEL", 10),
        ("11 FEB 2024", 11),
    ])
    stamp_oval(cv, 870, 612, 88, 52, 6, INK_GREEN, [
        ("PORTO VERDE", 11),
        ("DEPARTURE", 13),
        ("SAO MIGUEL", 10),
        ("02 MAR 2024", 11),
    ])
    # small handwritten-style note under the last stamps
    draw_text(cv, "Holder travelled as a marine research guest of the",
              760, 700, 10, NAVY_SOFT, align="center")
    draw_text(cv, "Calvento Institute of Oceanography.",
              760, 716, 10, NAVY_SOFT, align="center")


def build():
    cv = Canvas()
    # backdrop: the spread lies on dark leather, with a soft shadow
    cv.fill_rect(0, 0, W, H, LEATHER)
    cv.fill_rect(28, 30, 1012, 754, (8, 12, 22), 0.55)
    left_page(cv)
    right_page(cv)
    # gutter shadow between the pages
    cv.fill_rect(504, 22, 520, 746, (0, 0, 0), 0.18)
    cv.line(504, 22, 504, 746, 1.0, (60, 52, 40), 0.8)
    cv.line(520, 22, 520, 746, 1.0, (60, 52, 40), 0.8)
    # page edge rules
    cv.line(24, 22, 504, 22, 1.2, NAVY, 0.6)
    cv.line(520, 22, 1000, 22, 1.2, NAVY, 0.6)
    return downsample(cv)


def main():
    out_dir = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")
    os.makedirs(out_dir, exist_ok=True)
    rgb = build()
    data = png_bytes(rgb, W, H)
    path = os.path.join(out_dir, "entry.png")
    with open(path, "wb") as f:
        f.write(data)
    print(f"wrote {path}: {W}x{H}, {len(data)} bytes "
          f"(limit 1048576, {W}x{H} max)")
    line1, line2 = build_mrz()
    print("MRZ line 1:", line1)
    print("MRZ line 2:", line2)


if __name__ == "__main__":
    main()
