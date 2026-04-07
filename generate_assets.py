"""Generate assets/icon.png and assets/thumbnail.png using cairo."""
import math
import os
import cairo

os.makedirs("assets", exist_ok=True)


def draw_knob(ctx: cairo.Context, cx: float, cy: float, r: float, angle: float) -> None:
    """Draw a rotary knob at (cx, cy) with radius r, indicator at angle (radians)."""
    # Knob body
    ctx.arc(cx, cy, r, 0, 2 * math.pi)
    grad = cairo.RadialGradient(cx - r * 0.3, cy - r * 0.3, r * 0.05, cx, cy, r)
    grad.add_color_stop_rgb(0, 0.55, 0.55, 0.60)
    grad.add_color_stop_rgb(1, 0.18, 0.18, 0.22)
    ctx.set_source(grad)
    ctx.fill_preserve()
    ctx.set_source_rgba(0.6, 0.6, 0.65, 0.5)
    ctx.set_line_width(r * 0.05)
    ctx.stroke()

    # Arc track
    start = math.pi * 0.75
    end = math.pi * 2.25
    ctx.set_source_rgba(0.2, 0.2, 0.25, 1)
    ctx.set_line_width(r * 0.12)
    ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    ctx.arc(cx, cy, r * 0.82, start, end)
    ctx.stroke()

    # Active arc (teal)
    ctx.set_source_rgba(0.18, 0.75, 0.65, 1)
    ctx.arc(cx, cy, r * 0.82, start, start + (angle / (1.5 * math.pi)) * (end - start))
    ctx.stroke()

    # Indicator dot
    ind_angle = start + (angle / (1.5 * math.pi)) * (end - start)
    ix = cx + math.cos(ind_angle) * r * 0.82
    iy = cy + math.sin(ind_angle) * r * 0.82
    ctx.arc(ix, iy, r * 0.08, 0, 2 * math.pi)
    ctx.set_source_rgba(1, 1, 1, 0.95)
    ctx.fill()


def draw_bars(ctx: cairo.Context, x: float, y: float, w: float, h: float, levels: list[float]) -> None:
    """Draw a small group of vertical volume bars."""
    n = len(levels)
    gap = w * 0.15 / (n - 1) if n > 1 else 0
    bar_w = (w - gap * (n - 1)) / n
    for i, level in enumerate(levels):
        bx = x + i * (bar_w + gap)
        bh = h * level
        by = y + h - bh
        ctx.rectangle(bx, by, bar_w, bh)
        grad = cairo.LinearGradient(bx, by, bx, by + bh)
        grad.add_color_stop_rgba(0, 0.18, 0.75, 0.65, 1)
        grad.add_color_stop_rgba(1, 0.10, 0.45, 0.40, 1)
        ctx.set_source(grad)
        ctx.fill()


def make_icon(path: str, size: int = 100) -> None:
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
    ctx = cairo.Context(surf)

    # Background
    ctx.rectangle(0, 0, size, size)
    ctx.set_source_rgb(0.12, 0.12, 0.15)
    ctx.fill()

    cx, cy, r = size / 2, size * 0.45, size * 0.30
    draw_knob(ctx, cx, cy, r, math.pi * 0.90)

    draw_bars(ctx, size * 0.12, size * 0.70, size * 0.76, size * 0.22,
              [0.55, 0.80, 0.80, 0.65])

    surf.write_to_png(path)
    print(f"wrote {path}")


def make_thumbnail(path: str, w: int = 300, h: int = 200) -> None:
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    ctx = cairo.Context(surf)

    # Background
    ctx.rectangle(0, 0, w, h)
    ctx.set_source_rgb(0.10, 0.10, 0.13)
    ctx.fill()

    # Three knobs representing three groups
    knob_r = h * 0.20
    positions = [(w * 0.22, h * 0.42), (w * 0.50, h * 0.42), (w * 0.78, h * 0.42)]
    angles   = [math.pi * 0.60, math.pi * 0.90, math.pi * 1.10]
    for (kx, ky), ang in zip(positions, angles):
        draw_knob(ctx, kx, ky, knob_r, ang)

    # Bar groups below each knob
    bar_levels = [[0.50, 0.55], [0.75, 0.80], [0.90, 0.85]]
    bw = knob_r * 1.0
    for (kx, _), levels in zip(positions, bar_levels):
        draw_bars(ctx, kx - bw / 2, h * 0.72, bw, h * 0.18, levels)

    # Title text
    ctx.set_source_rgba(1, 1, 1, 0.90)
    ctx.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
    ctx.set_font_size(h * 0.11)
    text = "Volume Group Mixer"
    te = ctx.text_extents(text)
    ctx.move_to((w - te.width) / 2 - te.x_bearing, h * 0.93)
    ctx.show_text(text)

    surf.write_to_png(path)
    print(f"wrote {path}")


make_icon("assets/icon.png")
make_thumbnail("assets/thumbnail.png")
