import glfw
import OpenGL
OpenGL.ERROR_CHECKING = False
OpenGL.ERROR_LOGGING = False

from OpenGL.GL import *
from OpenGL.GLU import *

import math
import time
import random
import sys

# ---------------------------------------------------------------------
# Window & layout
# ---------------------------------------------------------------------
WIN_W, WIN_H = 1200, 640
PANEL_W = WIN_W // 3
HUD_H   = 60

# ---------------------------------------------------------------------
# Camera (2D TRANSFORMATIONS)
# ---------------------------------------------------------------------
cam_pan_x = 0.0
cam_pan_y = 0.0
cam_zoom  = 1.0
cam_angle = 0.0

# ---------------------------------------------------------------------
# Control points of the cubic Bezier curve (canvas-local coords)
# ---------------------------------------------------------------------
ctrl = [
    [-300.0, -150.0],
    [-100.0,  220.0],
    [ 100.0, -220.0],
    [ 300.0,  150.0],
]
selected_pt = 0
dragging    = False

# ---------------------------------------------------------------------
# Rendering options
# ---------------------------------------------------------------------
SEGMENTS    = 64
fill_mode   = True
clipping_on = True

# ---------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------
metrics_smooth = {"decasteljau": 0.0, "bernstein": 0.0, "forward": 0.0}


# =====================================================================
#  THE THREE BEZIER EVALUATION ALGORITHMS
# =====================================================================

def bezier_decasteljau(p0, p1, p2, p3, n):
    """de Casteljau: recursive linear interpolation (numerically stable)."""
    pts = []
    for i in range(n + 1):
        t = i / n
        a = (p0[0] + (p1[0]-p0[0])*t, p0[1] + (p1[1]-p0[1])*t)
        b = (p1[0] + (p2[0]-p1[0])*t, p1[1] + (p2[1]-p1[1])*t)
        c = (p2[0] + (p3[0]-p2[0])*t, p2[1] + (p3[1]-p2[1])*t)
        d = (a[0] + (b[0]-a[0])*t, a[1] + (b[1]-a[1])*t)
        e = (b[0] + (c[0]-b[0])*t, b[1] + (c[1]-b[1])*t)
        f = (d[0] + (e[0]-d[0])*t, d[1] + (e[1]-d[1])*t)
        pts.append(f)
    return pts


def bezier_bernstein(p0, p1, p2, p3, n):
    """Bernstein polynomial: direct B(t) = sum(Bi * Pi)."""
    pts = []
    for i in range(n + 1):
        t = i / n
        u = 1.0 - t
        b0 = u*u*u
        b1 = 3.0*u*u*t
        b2 = 3.0*u*t*t
        b3 = t*t*t
        x = b0*p0[0] + b1*p1[0] + b2*p2[0] + b3*p3[0]
        y = b0*p0[1] + b1*p1[1] + b2*p2[1] + b3*p3[1]
        pts.append((x, y))
    return pts


def bezier_forward_diff(p0, p1, p2, p3, n):
    """Forward Differencing: incremental update, re-seeded every 16 steps."""
    d1 = (3*(p1[0]-p0[0]), 3*(p1[1]-p0[1]))
    d2 = (3*(p0[0]-2*p1[0]+p2[0]), 3*(p0[1]-2*p1[1]+p2[1]))
    d3 = (p3[0]-3*p2[0]+3*p1[0]-p0[0], p3[1]-3*p2[1]+3*p1[1]-p0[1])
    dt = 1.0 / n
    s1 = (d1[0]*dt + d2[0]*dt*dt + d3[0]*dt*dt*dt,
          d1[1]*dt + d2[1]*dt*dt + d3[1]*dt*dt*dt)
    s2 = (2*d2[0]*dt*dt + 6*d3[0]*dt*dt*dt,
          2*d2[1]*dt*dt + 6*d3[1]*dt*dt*dt)
    s3 = (6*d3[0]*dt*dt*dt, 6*d3[1]*dt*dt*dt)
    x, y = p0
    pts = [(x, y)]
    for i in range(1, n + 1):
        if i % 16 == 0:
            t = i / n
            u = 1 - t
            x = (u*u*u*p0[0] + 3*u*u*t*p1[0] + 3*u*t*t*p2[0] + t*t*t*p3[0])
            y = (u*u*u*p0[1] + 3*u*u*t*p1[1] + 3*u*t*t*p2[1] + t*t*t*p3[1])
        else:
            x += s1[0]; y += s1[1]
            s1 = (s1[0]+s2[0], s1[1]+s2[1])
            s2 = (s2[0]+s3[0], s2[1]+s3[1])
        pts.append((x, y))
    return pts


# =====================================================================
#  2D TRANSFORMATIONS: world -> screen
# =====================================================================

def apply_camera(px, py, canvas_cx, canvas_cy):
    x = px + cam_pan_x
    y = py + cam_pan_y
    rad = math.radians(cam_angle)
    cs, sn = math.cos(rad), math.sin(rad)
    xr = x*cs - y*sn
    yr = x*sn + y*cs
    return (canvas_cx + xr*cam_zoom, canvas_cy + yr*cam_zoom)


# =====================================================================
#  LINE CLIPPING (Cohen-Sutherland)
# =====================================================================
INSIDE, LEFT, RIGHT, BOTTOM, TOP = 0, 1, 2, 4, 8

def _rc(x, y, xmin, ymin, xmax, ymax):
    c = INSIDE
    if x < xmin:   c |= LEFT
    elif x > xmax: c |= RIGHT
    if y < ymin:   c |= BOTTOM
    elif y > ymax: c |= TOP
    return c

def clip_line(x0, y0, x1, y1, xmin, ymin, xmax, ymax):
    c0 = _rc(x0, y0, xmin, ymin, xmax, ymax)
    c1 = _rc(x1, y1, xmin, ymin, xmax, ymax)
    while True:
        if not (c0 | c1):
            return x0, y0, x1, y1
        if c0 & c1:
            return None
        out = c0 or c1
        if out & TOP:
            x = x0 + (x1-x0)*(ymax-y0)/(y1-y0); y = ymax
        elif out & BOTTOM:
            x = x0 + (x1-x0)*(ymin-y0)/(y1-y0); y = ymin
        elif out & RIGHT:
            y = y0 + (y1-y0)*(xmax-x0)/(x1-x0); x = xmax
        else:
            y = y0 + (y1-y0)*(xmin-x0)/(x1-x0); x = xmin
        if out == c0:
            x0, y0 = x, y
            c0 = _rc(x0, y0, xmin, ymin, xmax, ymax)
        else:
            x1, y1 = x, y
            c1 = _rc(x1, y1, xmin, ymin, xmax, ymax)


# =====================================================================
#  DRAW HELPERS
# =====================================================================

def draw_clipped_line(p, q, color, lw=1.0, clip_box=None):
    x0, y0 = p; x1, y1 = q
    if clipping_on and clip_box is not None:
        r = clip_line(x0, y0, x1, y1, *clip_box)
        if r is None:
            return
        x0, y0, x1, y1 = r
    glColor3f(*color)
    glLineWidth(lw)
    glBegin(GL_LINES)
    glVertex2f(x0, y0)
    glVertex2f(x1, y1)
    glEnd()


def draw_polyline(pts, color, lw=2.0, clip_box=None):
    if not pts:
        return
    glColor3f(*color)
    glLineWidth(lw)
    if clipping_on and clip_box is not None:
        glBegin(GL_LINES)
        for i in range(len(pts)-1):
            r = clip_line(pts[i][0], pts[i][1],
                          pts[i+1][0], pts[i+1][1], *clip_box)
            if r is not None:
                glVertex2f(r[0], r[1])
                glVertex2f(r[2], r[3])
        glEnd()
    else:
        glBegin(GL_LINE_STRIP)
        for p in pts:
            glVertex2f(*p)
        glEnd()


def draw_filled_region(pts, color, clip_box=None):
    if len(pts) < 3:
        return
    glColor3f(*color)
    glBegin(GL_TRIANGLE_FAN)
    for p in pts:
        x, y = p
        if clipping_on and clip_box is not None:
            x = max(clip_box[0], min(clip_box[2], x))
            y = max(clip_box[1], min(clip_box[3], y))
        glVertex2f(x, y)
    glEnd()


def draw_rect(x, y, w, h, color):
    glColor3f(*color)
    glBegin(GL_QUADS)
    glVertex2f(x,   y)
    glVertex2f(x+w, y)
    glVertex2f(x+w, y+h)
    glVertex2f(x,   y+h)
    glEnd()


def draw_circle(cx, cy, r, color, segments=16):
    glColor3f(*color)
    glBegin(GL_TRIANGLE_FAN)
    glVertex2f(cx, cy)
    for i in range(segments + 1):
        a = 2*math.pi*i/segments
        glVertex2f(cx + r*math.cos(a), cy + r*math.sin(a))
    glEnd()


# =====================================================================
#  PANEL RENDERER
# =====================================================================

def draw_panel(panel_index, algo_name, algo_fn, curve_color):
    px0 = panel_index * PANEL_W
    px1 = px0 + PANEL_W
    py0 = 0
    py1 = WIN_H - HUD_H

    pad = 6
    clip_box = (px0 + pad, py0 + pad, px1 - pad, py1 - pad)

    # Panel background
    draw_rect(px0, py0, PANEL_W, py1, (0.10, 0.11, 0.14))

    # Panel border
    glColor3f(0.30, 0.32, 0.38)
    glLineWidth(2.0)
    glBegin(GL_LINE_LOOP)
    glVertex2f(px0 + 1, py0 + 1)
    glVertex2f(px1 - 1, py0 + 1)
    glVertex2f(px1 - 1, py1 - 1)
    glVertex2f(px0 + 1, py1 - 1)
    glEnd()

    ccx = (px0 + px1) / 2.0
    ccy = py0 + (py1 - py0) * 0.55

    screen_ctrl = [apply_camera(p[0], p[1], ccx, ccy) for p in ctrl]

    p0, p1, p2, p3 = ctrl
    t0 = time.perf_counter()
    curve_pts = algo_fn(p0, p1, p2, p3, SEGMENTS)
    t1 = time.perf_counter()
    dt_us = (t1 - t0) * 1e6

    metrics_smooth[algo_name] = 0.9*metrics_smooth[algo_name] + 0.1*dt_us

    screen_curve = [apply_camera(x, y, ccx, ccy) for (x, y) in curve_pts]

    # Glyph fill (Color Fill technique)
    if fill_mode and len(screen_curve) >= 2:
        contour = screen_curve + [screen_ctrl[0]]
        draw_filled_region(contour,
                           (curve_color[0]*0.45,
                            curve_color[1]*0.45,
                            curve_color[2]*0.45),
                           clip_box)

    # Control polygon
    for i in range(3):
        draw_clipped_line(screen_ctrl[i], screen_ctrl[i+1],
                          (0.45, 0.45, 0.50), 1.0, clip_box)

    # The curve itself
    draw_polyline(screen_curve, curve_color, 3.0, clip_box)

    # Control point handles
    for i, p in enumerate(screen_ctrl):
        if not (clip_box[0] <= p[0] <= clip_box[2]
                and clip_box[1] <= p[1] <= clip_box[3]):
            continue
        color = (1.0, 0.85, 0.2) if i == selected_pt else (0.85, 0.85, 0.9)
        draw_circle(p[0], p[1], 6, color)
        draw_circle(p[0], p[1], 3, (0.15, 0.15, 0.18))


# =====================================================================
#  SCREEN-TO-WORLD (inverse camera transform, for mouse picking)
# =====================================================================

def screen_to_world(px, py, panel_index):
    ccx = panel_index * PANEL_W + PANEL_W / 2.0
    ccy = (WIN_H - HUD_H) * 0.55
    x = px - ccx
    y = py - ccy
    if cam_zoom == 0:
        return 0, 0
    x /= cam_zoom
    y /= cam_zoom
    rad = math.radians(-cam_angle)
    cs, sn = math.cos(rad), math.sin(rad)
    xr = x*cs - y*sn
    yr = x*sn + y*cs
    xr -= cam_pan_x
    yr -= cam_pan_y
    return xr, yr


# =====================================================================
#  GLFW CALLBACKS
# =====================================================================

def mouse_button_callback(window, button, action, mods):
    global dragging, selected_pt
    if button != glfw.MOUSE_BUTTON_LEFT:
        return
    if action == glfw.PRESS:
        mx, my = glfw.get_cursor_pos(window)
        # GLFW y is top-down; flip to bottom-up
        y = WIN_H - my
        panel_index = min(int(mx // PANEL_W), 2)
        wx, wy = screen_to_world(mx, y, panel_index)
        best_i, best_d = 0, 1e18
        for i, (cx, cy) in enumerate(ctrl):
            d = (cx-wx)**2 + (cy-wy)**2
            if d < best_d:
                best_d, best_i = d, i
        selected_pt = best_i
        dragging = True
    elif action == glfw.RELEASE:
        dragging = False


def cursor_pos_callback(window, mx, my):
    if not dragging:
        return
    y = WIN_H - my
    panel_index = min(int(mx // PANEL_W), 2)
    wx, wy = screen_to_world(mx, y, panel_index)
    ctrl[selected_pt][0] = wx
    ctrl[selected_pt][1] = wy


def key_callback(window, key, scancode, action, mods):
    global cam_pan_x, cam_pan_y, cam_zoom, cam_angle
    global fill_mode, clipping_on, SEGMENTS, selected_pt
    if action not in (glfw.PRESS, glfw.REPEAT):
        return

    if key == glfw.KEY_ESCAPE:
        glfw.set_window_should_close(window, True)
    elif key == glfw.KEY_W: cam_pan_y += 15
    elif key == glfw.KEY_S: cam_pan_y -= 15
    elif key == glfw.KEY_A: cam_pan_x -= 15
    elif key == glfw.KEY_D: cam_pan_x += 15
    elif key in (glfw.KEY_EQUAL, glfw.KEY_KP_ADD):     cam_zoom *= 1.15
    elif key in (glfw.KEY_MINUS, glfw.KEY_KP_SUBTRACT): cam_zoom /= 1.15
    elif key == glfw.KEY_Q: cam_angle += 5
    elif key == glfw.KEY_E: cam_angle -= 5
    elif key == glfw.KEY_0:
        cam_pan_x = cam_pan_y = 0.0
        cam_zoom = 1.0
        cam_angle = 0.0
    elif key == glfw.KEY_F: fill_mode = not fill_mode
    elif key == glfw.KEY_C: clipping_on = not clipping_on
    elif key == glfw.KEY_R:
        for p in ctrl:
            p[0] = random.uniform(-320, 320)
            p[1] = random.uniform(-200, 200)
    elif key in (glfw.KEY_1, glfw.KEY_2, glfw.KEY_3, glfw.KEY_4):
        selected_pt = key - glfw.KEY_1
    elif key == glfw.KEY_LEFT_BRACKET:
        SEGMENTS = max(8, SEGMENTS // 2)
    elif key == glfw.KEY_RIGHT_BRACKET:
        SEGMENTS = min(512, SEGMENTS * 2)


# =====================================================================
#  MAIN
# =====================================================================

def main():
    if not glfw.init():
        raise SystemExit("Failed to initialize GLFW")

    # Request an OpenGL 2.1 context (fixed-function pipeline)
    glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 2)
    glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 1)
    glfw.window_hint(glfw.SAMPLES, 4)         # antialiasing

    window = glfw.create_window(
        WIN_W, WIN_H,
        "Bezier Algorithm Comparison - Font Rasterisation Visualiser",
        None, None)
    if not window:
        glfw.terminate()
        raise SystemExit("Failed to create GLFW window")

    glfw.make_context_current(window)
    glfw.swap_interval(1)                     # vsync

    # Register input callbacks
    glfw.set_mouse_button_callback(window, mouse_button_callback)
    glfw.set_cursor_pos_callback(window, cursor_pos_callback)
    glfw.set_key_callback(window, key_callback)

    # Initial projection setup (also reset every frame inside loop)
    glViewport(0, 0, WIN_W, WIN_H)

    while not glfw.window_should_close(window):
        # --- Per-frame: reset viewport and projection ---
        fb_w, fb_h = glfw.get_framebuffer_size(window)
        glViewport(0, 0, fb_w, fb_h)

        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        glOrtho(0.0, float(WIN_W), 0.0, float(WIN_H), -1.0, 1.0)

        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()

        # --- Clear ---
        glClearColor(0.05, 0.05, 0.07, 1.0)
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

        # --- Draw the three panels ---
        draw_panel(0, "decasteljau", bezier_decasteljau, (0.35, 0.75, 1.0))
        draw_panel(1, "bernstein",   bezier_bernstein,   (0.55, 0.95, 0.45))
        draw_panel(2, "forward",     bezier_forward_diff,(1.0, 0.65, 0.35))

        # --- HUD bar strip with per-algorithm timing ---
        draw_rect(0, WIN_H - HUD_H, WIN_W, HUD_H, (0.08, 0.09, 0.11))

        names = ["decasteljau", "bernstein", "forward"]
        colors = [(0.35, 0.75, 1.0), (0.55, 0.95, 0.45), (1.0, 0.65, 0.35)]
        max_us = max(max(metrics_smooth.values()), 1.0)
        for i, (n, c) in enumerate(zip(names, colors)):
            bar_x = 20 + i * 390
            bar_w = int(360 * (metrics_smooth[n] / max_us))
            bar_y = WIN_H - 40
            draw_rect(bar_x, bar_y, 360, 16, (0.15, 0.16, 0.19))
            draw_rect(bar_x, bar_y, bar_w, 16, c)
            draw_rect(bar_x - 6, bar_y, 4, 16, c)

        # --- Update the window title with live metrics ---
        glfw.set_window_title(
            window,
            f"Bezier Comparison | "
            f"deCasteljau={metrics_smooth['decasteljau']:.0f}us  "
            f"Bernstein={metrics_smooth['bernstein']:.0f}us  "
            f"FwdDiff={metrics_smooth['forward']:.0f}us | "
            f"segments={SEGMENTS}  fill={'ON' if fill_mode else 'OFF'}  "
            f"clip={'ON' if clipping_on else 'OFF'}  "
            f"zoom={cam_zoom:.2f}x  rot={cam_angle:.0f}deg")

        # --- Present ---
        glfw.swap_buffers(window)
        glfw.poll_events()

    glfw.terminate()


if __name__ == "__main__":
    main()