from OpenGL.GL import *
from OpenGL.GLUT import *
from OpenGL.GLU import *
import math
import sys
import time
import random

# ---------------------------------------------------------------------
# Window & layout
# ---------------------------------------------------------------------
WIN_W, WIN_H = 1200, 640          # total window size
PANEL_W = WIN_W // 3              # each of 3 comparison panels
HUD_H   = 60                      # top strip for stats

# ---------------------------------------------------------------------
# Canvas camera (2D TRANSFORMATIONS): pan, zoom, rotation
# ---------------------------------------------------------------------
cam_pan_x   = 0.0
cam_pan_y   = 0.0
cam_zoom    = 1.0
cam_angle   = 0.0                 # in degrees, around canvas centre

# ---------------------------------------------------------------------
# Control points of the cubic Bezier curve, in world coordinates
# (canvas-local coordinates; origin at canvas centre)
# ---------------------------------------------------------------------
ctrl = [
    [-300.0, -150.0],   # P0  (start point)
    [-100.0,  220.0],   # P1  (control handle 1)
    [ 100.0, -220.0],   # P2  (control handle 2)
    [ 300.0,  150.0],   # P3  (end point)
]
selected_pt = 0                     # which control point arrow keys nudge
dragging    = False

# ---------------------------------------------------------------------
# Rendering options
# ---------------------------------------------------------------------
SEGMENTS       = 64                 # number of line segments per curve
fill_mode      = True               # draw GL_TRIANGLE_FAN glyph fill
clipping_on    = True               # demo toggle for clipping

# ---------------------------------------------------------------------
# Metrics: per-algorithm last-frame time in microseconds
# ---------------------------------------------------------------------
metrics = {
    "decasteljau": {"time_us": 0.0, "points": 0},
    "bernstein":   {"time_us": 0.0, "points": 0},
    "forward":     {"time_us": 0.0, "points": 0},
}
metrics_smooth = {k: 0.0 for k in metrics}   # smoothed display values


# =====================================================================
#  THE THREE BEZIER EVALUATION ALGORITHMS
# =====================================================================

def bezier_decasteljau(p0, p1, p2, p3, n):
    """de Casteljau: recursive linear interpolation -- the textbook stable way."""
    pts = []
    for i in range(n + 1):
        t = i / n
        # First-level lerps
        a = (p0[0] + (p1[0] - p0[0]) * t, p0[1] + (p1[1] - p0[1]) * t)
        b = (p1[0] + (p2[0] - p1[0]) * t, p1[1] + (p2[1] - p1[1]) * t)
        c = (p2[0] + (p3[0] - p2[0]) * t, p2[1] + (p3[1] - p2[1]) * t)
        # Second-level lerps
        d = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
        e = (b[0] + (c[0] - b[0]) * t, b[1] + (c[1] - b[1]) * t)
        # Third-level lerp = final point
        f = (d[0] + (e[0] - d[0]) * t, d[1] + (e[1] - d[1]) * t)
        pts.append(f)
    return pts


def bezier_bernstein(p0, p1, p2, p3, n):
    """Bernstein polynomial form: direct evaluation B(t) = sum(Bi * Pi)."""
    pts = []
    for i in range(n + 1):
        t = i / n
        u = 1.0 - t
        b0 = u * u * u
        b1 = 3.0 * u * u * t
        b2 = 3.0 * u * t * t
        b3 = t * t * t
        x = b0 * p0[0] + b1 * p1[0] + b2 * p2[0] + b3 * p3[0]
        y = b0 * p0[1] + b1 * p1[1] + b2 * p2[1] + b3 * p3[1]
        pts.append((x, y))
    return pts


def bezier_forward_diff(p0, p1, p2, p3, n):
    """
    Forward Differencing: incremental update using finite differences.
    Fastest, but accumulates floating-point drift. We re-seed every 16 steps
    from de Casteljau to keep the endpoint anchored (production trick).
    """
    # Compute the four finite-difference deltas
    d0 = p0
    d1 = (3 * (p1[0] - p0[0]), 3 * (p1[1] - p0[1]))
    d2 = (3 * (p0[0] - 2 * p1[0] + p2[0]),
          3 * (p0[1] - 2 * p1[1] + p2[1]))
    d3 = (p3[0] - 3 * p2[0] + 3 * p1[0] - p0[0],
          p3[1] - 3 * p2[1] + 3 * p1[1] - p0[1])

    dt = 1.0 / n
    # Step increments (order-3 forward difference for a cubic)
    s1 = (d1[0] * dt + d2[0] * dt * dt + d3[0] * dt * dt * dt,
          d1[1] * dt + d2[1] * dt * dt + d3[1] * dt * dt * dt)
    s2 = (2 * d2[0] * dt * dt + 6 * d3[0] * dt * dt * dt,
          2 * d2[1] * dt * dt + 6 * d3[1] * dt * dt * dt)
    s3 = (6 * d3[0] * dt * dt * dt,
          6 * d3[1] * dt * dt * dt)

    x, y = d0
    pts = [(x, y)]
    for i in range(1, n + 1):
        # Re-seed exactly every 16 steps to kill drift
        if i % 16 == 0:
            t = i / n
            u = 1 - t
            x = (u*u*u*p0[0] + 3*u*u*t*p1[0] + 3*u*t*t*p2[0] + t*t*t*p3[0])
            y = (u*u*u*p0[1] + 3*u*u*t*p1[1] + 3*u*t*t*p2[1] + t*t*t*p3[1])
        else:
            x += s1[0]; y += s1[1]
            s1 = (s1[0] + s2[0], s1[1] + s2[1])
            s2 = (s2[0] + s3[0], s2[1] + s3[1])
        pts.append((x, y))
    return pts


# =====================================================================
#  2D TRANSFORMATIONS: world -> panel-local screen pixel
# =====================================================================

def apply_camera(px, py, canvas_cx, canvas_cy):
    """
    Compose: translate -> rotate -> scale -> translate-to-canvas-centre.
    This is the standard 2D affine chain (a 3x3 matrix applied manually).
    """
    # 1) user pan offset
    x = px + cam_pan_x
    y = py + cam_pan_y
    # 2) rotation around origin
    rad = math.radians(cam_angle)
    cs, sn = math.cos(rad), math.sin(rad)
    xr = x * cs - y * sn
    yr = x * sn + y * cs
    # 3) zoom
    xz = xr * cam_zoom
    yz = yr * cam_zoom
    # 4) final canvas position
    return (canvas_cx + xz, canvas_cy + yz)


# =====================================================================
#  LINE CLIPPING: Cohen-Sutherland with 4-bit region codes
# =====================================================================
INSIDE, LEFT, RIGHT, BOTTOM, TOP = 0, 1, 2, 4, 8

def _region_code(x, y, xmin, ymin, xmax, ymax):
    code = INSIDE
    if x < xmin:   code |= LEFT
    elif x > xmax: code |= RIGHT
    if y < ymin:   code |= BOTTOM
    elif y > ymax: code |= TOP
    return code

def clip_line(x0, y0, x1, y1, xmin, ymin, xmax, ymax):
    """Return clipped segment (x0,y0,x1,y1) or None if fully outside."""
    c0 = _region_code(x0, y0, xmin, ymin, xmax, ymax)
    c1 = _region_code(x1, y1, xmin, ymin, xmax, ymax)
    while True:
        if not (c0 | c1):                     # both inside
            return x0, y0, x1, y1
        if c0 & c1:                           # both share outside region
            return None
        out = c0 or c1
        if out & TOP:
            x = x0 + (x1 - x0) * (ymax - y0) / (y1 - y0); y = ymax
        elif out & BOTTOM:
            x = x0 + (x1 - x0) * (ymin - y0) / (y1 - y0); y = ymin
        elif out & RIGHT:
            y = y0 + (y1 - y0) * (xmax - x0) / (x1 - x0); x = xmax
        else:  # LEFT
            y = y0 + (y1 - y0) * (xmin - x0) / (x1 - x0); x = xmin
        if out == c0:
            x0, y0 = x, y
            c0 = _region_code(x0, y0, xmin, ymin, xmax, ymax)
        else:
            x1, y1 = x, y
            c1 = _region_code(x1, y1, xmin, ymin, xmax, ymax)


# =====================================================================
#  DRAWING HELPERS
# =====================================================================

def draw_clipped_line(p, q, color, lw=1.0, clip_box=None):
    """Draw line p->q; clip to clip_box=(xmin,ymin,xmax,ymax) if clipping_on."""
    x0, y0 = p; x1, y1 = q
    if clipping_on and clip_box is not None:
        result = clip_line(x0, y0, x1, y1, *clip_box)
        if result is None:
            return
        x0, y0, x1, y1 = result
    glColor3f(*color)
    glLineWidth(lw)
    glBegin(GL_LINES)
    glVertex2f(x0, y0)
    glVertex2f(x1, y1)
    glEnd()


def draw_polyline(pts, color, lw=2.0, clip_box=None):
    """Draw a connected polyline, optionally clipped segment by segment."""
    if not pts:
        return
    glColor3f(*color)
    glLineWidth(lw)
    if clipping_on and clip_box is not None:
        glBegin(GL_LINES)
        for i in range(len(pts) - 1):
            result = clip_line(pts[i][0], pts[i][1],
                               pts[i+1][0], pts[i+1][1], *clip_box)
            if result is not None:
                glVertex2f(result[0], result[1])
                glVertex2f(result[2], result[3])
        glEnd()
    else:
        glBegin(GL_LINE_STRIP)
        for p in pts:
            glVertex2f(*p)
        glEnd()


def draw_filled_region(pts, color, clip_box=None):
    """
    Glyph fill: triangulate the region between the curve and its chord.
    Uses GL_TRIANGLE_FAN -- matches how TrueType outlines become solid.
    """
    if len(pts) < 3:
        return
    glColor3f(*color)
    glBegin(GL_TRIANGLE_FAN)
    for p in pts:
        x, y = p
        if clipping_on and clip_box is not None:
            # Simple point clamp to viewport; interior triangles that
            # fully fall outside are silently dropped by the GPU.
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


def draw_text(x, y, text, color, font=GLUT_BITMAP_HELVETICA_12):
    glColor3f(*color)
    glRasterPos2f(x, y)
    for ch in text:
        glutBitmapCharacter(font, ord(ch))


def draw_circle(cx, cy, r, color, segments=16):
    glColor3f(*color)
    glBegin(GL_TRIANGLE_FAN)
    glVertex2f(cx, cy)
    for i in range(segments + 1):
        a = 2 * math.pi * i / segments
        glVertex2f(cx + r * math.cos(a), cy + r * math.sin(a))
    glEnd()


# =====================================================================
#  PER-PANEL RENDERER
# =====================================================================

def draw_panel(panel_index, title, algorithm_name, algorithm_fn, curve_color):
    """
    Draw one of the three comparison panels:
      * background, border, title
      * control polygon (dashed)
      * evaluated Bezier curve
      * optional glyph fill
      * control point handles
    Also measures evaluation time and stores it in metrics.
    """
    # Panel bounds in pixels
    panel_x0 = panel_index * PANEL_W
    panel_x1 = panel_x0 + PANEL_W
    panel_y0 = 0
    panel_y1 = WIN_H - HUD_H

    # Panels are separated by a thin strip; the clip box is slightly inside
    pad = 6
    clip_box = (panel_x0 + pad, panel_y0 + pad,
                panel_x1 - pad, panel_y1 - pad)

    # --- background ---
    draw_rect(panel_x0, panel_y0, PANEL_W, panel_y1, (0.10, 0.11, 0.14))
    # --- border ---
    glColor3f(0.30, 0.32, 0.38)
    glLineWidth(2.0)
    glBegin(GL_LINE_LOOP)
    glVertex2f(panel_x0 + 1, panel_y0 + 1)
    glVertex2f(panel_x1 - 1, panel_y0 + 1)
    glVertex2f(panel_x1 - 1, panel_y1 - 1)
    glVertex2f(panel_x0 + 1, panel_y1 - 1)
    glEnd()

    # --- canvas centre for this panel ---
    canvas_cx = (panel_x0 + panel_x1) / 2.0
    canvas_cy = panel_y0 + (panel_y1 - panel_y0) * 0.55

    # --- transform control points to screen ---
    screen_ctrl = [apply_camera(p[0], p[1], canvas_cx, canvas_cy) for p in ctrl]

    # --- evaluate the Bezier curve with the assigned algorithm ---
    p0, p1, p2, p3 = ctrl
    t0 = time.perf_counter()
    curve_pts = algorithm_fn(p0, p1, p2, p3, SEGMENTS)
    t1 = time.perf_counter()
    dt_us = (t1 - t0) * 1e6

    # update metrics with exponential smoothing so HUD is readable
    metrics[algorithm_name]["time_us"] = dt_us
    metrics[algorithm_name]["points"] = len(curve_pts)
    metrics_smooth[algorithm_name] = (0.9 * metrics_smooth[algorithm_name]
                                      + 0.1 * dt_us)

    # --- transform curve points to screen ---
    screen_curve = [apply_camera(x, y, canvas_cx, canvas_cy) for (x, y) in curve_pts]

    # --- glyph fill (drawn FIRST, under the outline) ---
    if fill_mode and len(screen_curve) >= 2:
        # close the contour along the chord between endpoint and start point
        contour = screen_curve + [screen_ctrl[0]]
        draw_filled_region(contour, (curve_color[0]*0.45,
                                     curve_color[1]*0.45,
                                     curve_color[2]*0.45),
                           clip_box)

    # --- control polygon (dashed look via segments) ---
    for i in range(3):
        draw_clipped_line(screen_ctrl[i], screen_ctrl[i+1],
                          (0.45, 0.45, 0.50), 1.0, clip_box)

    # --- the curve itself ---
    draw_polyline(screen_curve, curve_color, 3.0, clip_box)

    # --- control point handles ---
    for i, p in enumerate(screen_ctrl):
        inside = (clip_box[0] <= p[0] <= clip_box[2]
                  and clip_box[1] <= p[1] <= clip_box[3])
        if not inside:
            continue
        color = (1.0, 0.85, 0.2) if i == selected_pt else (0.85, 0.85, 0.9)
        draw_circle(p[0], p[1], 6, color)
        draw_circle(p[0], p[1], 3, (0.15, 0.15, 0.18))

    # --- panel title ---
    draw_text(panel_x0 + 12, panel_y1 - 22, title, (0.95, 0.95, 0.95),
              GLUT_BITMAP_HELVETICA_18)
    draw_text(panel_x0 + 12, panel_y1 - 42,
              f"algorithm: {algorithm_name}", (0.7, 0.75, 0.85))


# =====================================================================
#  MAIN DISPLAY
# =====================================================================

def display():
    glClearColor(0.05, 0.05, 0.07, 1.0)
    glClear(GL_COLOR_BUFFER_BIT)

    # Panel 1: de Casteljau
    draw_panel(0, "de Casteljau", "decasteljau",
               bezier_decasteljau, (0.35, 0.75, 1.0))

    # Panel 2: Bernstein
    draw_panel(1, "Bernstein Polynomial", "bernstein",
               bezier_bernstein, (0.55, 0.95, 0.45))

    # Panel 3: Forward Differencing
    draw_panel(2, "Forward Differencing", "forward",
               bezier_forward_diff, (1.0, 0.65, 0.35))

    # ---------- HUD across the top ----------
    draw_rect(0, WIN_H - HUD_H, WIN_W, HUD_H, (0.08, 0.09, 0.11))

    # Left: title
    draw_text(12, WIN_H - 22,
              "Bezier Evaluation Algorithm Comparison  |  "
              "font rasterisation / CAD curve design",
              (0.85, 0.88, 0.95), GLUT_BITMAP_HELVETICA_12)

    # Right: per-algorithm timings
    txt = (f"deCasteljau {metrics_smooth['decasteljau']:7.1f} us   |   "
           f"Bernstein {metrics_smooth['bernstein']:7.1f} us   |   "
           f"FwdDiff {metrics_smooth['forward']:7.1f} us   |   "
           f"segments={SEGMENTS}   "
           f"fill={'ON' if fill_mode else 'OFF'}   "
           f"clip={'ON' if clipping_on else 'OFF'}   "
           f"zoom={cam_zoom:.2f}x   rot={cam_angle:.0f}deg")
    draw_text(12, WIN_H - 44, txt, (0.75, 0.80, 0.90))

    # Bottom-left helper line
    draw_text(12, 10,
              "drag mouse to move nearest point  |  "
              "WASD pan  |  +/- zoom  |  Q/E rotate  |  "
              "0 reset  |  F fill  |  C clip  |  R random  |  ESC quit",
              (0.55, 0.60, 0.70))

    glutSwapBuffers()


# =====================================================================
#  INPUT HANDLERS
# =====================================================================

def reshape(w, h):
    glViewport(0, 0, w, h)
    glMatrixMode(GL_PROJECTION)
    glLoadIdentity()
    gluOrtho2D(0, WIN_W, 0, WIN_H)          # 2D pixel-space projection
    glMatrixMode(GL_MODELVIEW)
    glLoadIdentity()


def screen_to_world_in_panel(px, py, panel_index):
    """Inverse of apply_camera: convert mouse pixel back to canvas coords."""
    canvas_cx = panel_index * PANEL_W + PANEL_W / 2.0
    canvas_cy = 0 + (WIN_H - HUD_H) * 0.55
    # undo final translate
    x = px - canvas_cx
    y = py - canvas_cy
    # undo zoom
    if cam_zoom == 0:
        return 0, 0
    x /= cam_zoom
    y /= cam_zoom
    # undo rotation
    rad = math.radians(-cam_angle)
    cs, sn = math.cos(rad), math.sin(rad)
    xr = x * cs - y * sn
    yr = x * sn + y * cs
    # undo pan
    xr -= cam_pan_x
    yr -= cam_pan_y
    return xr, yr


def mouse(button, state, mx, my):
    global dragging, selected_pt
    y = WIN_H - my                        # flip y so origin is bottom-left
    if button == GLUT_LEFT_BUTTON:
        if state == GLUT_DOWN:
            panel_index = min(mx // PANEL_W, 2)
            wx, wy = screen_to_world_in_panel(mx, y, panel_index)
            # pick nearest control point
            best_i, best_d = 0, 1e18
            for i, (cx, cy) in enumerate(ctrl):
                d = (cx - wx) ** 2 + (cy - wy) ** 2
                if d < best_d:
                    best_d, best_i = d, i
            selected_pt = best_i
            dragging = True
        else:
            dragging = False
    glutPostRedisplay()


def motion(mx, my):
    if not dragging:
        return
    y = WIN_H - my
    panel_index = min(mx // PANEL_W, 2)
    wx, wy = screen_to_world_in_panel(mx, y, panel_index)
    ctrl[selected_pt][0] = wx
    ctrl[selected_pt][1] = wy
    glutPostRedisplay()


def keyboard(key, x, y):
    global cam_pan_x, cam_pan_y, cam_zoom, cam_angle
    global fill_mode, clipping_on, SEGMENTS, selected_pt

    if key == b'\x1b':                     # ESC
        sys.exit(0)
    elif key == b'w':   cam_pan_y += 15
    elif key == b's':   cam_pan_y -= 15
    elif key == b'a':   cam_pan_x -= 15
    elif key == b'd':   cam_pan_x += 15
    elif key == b'+':   cam_zoom *= 1.15
    elif key == b'-':   cam_zoom /= 1.15
    elif key == b'q':   cam_angle += 5
    elif key == b'e':   cam_angle -= 5
    elif key == b'0':
        cam_pan_x = cam_pan_y = 0.0
        cam_zoom  = 1.0
        cam_angle = 0.0
    elif key == b'f':
        fill_mode = not fill_mode
    elif key == b'c':
        clipping_on = not clipping_on
    elif key == b'r':
        for p in ctrl:
            p[0] = random.uniform(-320, 320)
            p[1] = random.uniform(-200, 200)
    elif key in (b'1', b'2', b'3', b'4'):
        selected_pt = int(key) - 1
    elif key == b'[':
        SEGMENTS = max(8, SEGMENTS // 2)
    elif key == b']':
        SEGMENTS = min(512, SEGMENTS * 2)
    glutPostRedisplay()


def timer(_):
    glutPostRedisplay()
    glutTimerFunc(16, timer, 0)            # ~60 fps


# =====================================================================
#  ENTRY POINT
# =====================================================================

def main():
    glutInit(sys.argv)
    glutInitDisplayMode(GLUT_DOUBLE | GLUT_RGB)
    glutInitWindowSize(WIN_W, WIN_H)
    glutCreateWindow(b"Bezier Algorithm Comparison - Font Rasterisation Visualiser")
    reshape(WIN_W, WIN_H)

    glutDisplayFunc(display)
    glutReshapeFunc(reshape)
    glutMouseFunc(mouse)
    glutMotionFunc(motion)
    glutKeyboardFunc(keyboard)
    glutTimerFunc(16, timer, 0)

    glutMainLoop()


if __name__ == "__main__":
    main()