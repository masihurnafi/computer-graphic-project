#!/opt/homebrew/bin/python3.13
# =====================================================================
#  বেজিয়ে কার্ভ ইভ্যালুয়েশন অ্যালগরিদম তুলনা ভিজুয়ালাইজার
#  ট্র্যাক B: অ্যালগরিদম তুলনা টুল / রিসার্চ ভিজুয়ালাইজার
#
#  এই প্রোগ্রামে তিনটি গাণিতিকভাবে সমতুল্য কিন্তু কম্পিউটেশনালি
#  ভিন্ন অ্যালগরিদম দিয়ে একই কিউবিক বেজিয়ে কার্ভ আঁকা হয়:
#     ১. দ্য কাস্টেলজো (de Casteljau)   -- সংখ্যাগতভাবে স্থিতিশীল, ধীর
#     ২. বার্নস্টাইন (Bernstein)         -- সরাসরি পলিনোমিয়াল মূল্যায়ন
#     ৩. ফরওয়ার্ড ডিফারেন্সিং           -- সবচেয়ে দ্রুত, কিন্তু ভুল জমা হয়
#
#  বাস্তব ব্যবহার: ফন্ট র‍্যাস্টারাইজার (FreeType, DirectWrite),
#  CAD/CAM কার্ভ ডিজাইন, SVG / PDF ভেক্টর রেন্ডারিং।
#
#  এই কোর্সে যে ৫টি CG টেকনিক লাগে, সবগুলো এখানে আছে:
#     [✓] বেজিয়ে কার্ভ      -- প্রজেক্টের মূল
#     [✓] লাইন ও শেপ আঁকা    -- GL_LINE_STRIP, GL_LINES, GL_LINE_LOOP
#     [✓] কালার ফিল         -- GL_TRIANGLE_FAN গ্লিফ ফিল + HUD বার
#     [✓] 2D ট্রান্সফরমেশন  -- প্যান / জুম / রোটেট ক্যামেরা ম্যাট্রিক্স
#     [✓] লাইন ক্লিপিং      -- কোহেন-সাদারল্যান্ড, 4-বিট রিজিওন কোড
#
#  কন্ট্রোল:
#     বাম-ক্লিক ড্র্যাগ : সবচেয়ে কাছের কন্ট্রোল পয়েন্ট সরাও
#     W A S D          : ক্যানভাস প্যান করো
#     + / -            : জুম ইন / আউট
#     Q / E            : ক্যানভাস ঘোরাও
#     0                : ক্যামেরা রিসেট
#     F                : ফিল মোড চালু/বন্ধ
#     C                : ক্লিপিং চালু/বন্ধ (ডেমো)
#     R                : কন্ট্রোল পয়েন্ট র‍্যান্ডম করো
#     [ / ]            : সেগমেন্ট সংখ্যা অর্ধেক / দ্বিগুণ
#     ESC              : বন্ধ করো
# =====================================================================

import glfw                    # উইন্ডো বানানোর লাইব্রেরি
import OpenGL
OpenGL.ERROR_CHECKING = False  # PyOpenGL এর error checker বন্ধ (GLFW এর সাথে conflict করে)
OpenGL.ERROR_LOGGING = False

from OpenGL.GL import *        # OpenGL এর সব ফাংশন (glBegin, glVertex2f ইত্যাদি)
from OpenGL.GLU import *

import math
import time
import random
import sys

# ---------------------------------------------------------------------
# উইন্ডো ও লেআউট
# ---------------------------------------------------------------------
WIN_W, WIN_H = 1200, 640       # উইন্ডোর প্রস্থ ও উচ্চতা
PANEL_W = WIN_W // 3           # তিনটি প্যানেল, প্রতিটি এক-তৃতীয়াংশ
HUD_H   = 60                   # উপরে HUD স্ট্রিপের উচ্চতা

# ---------------------------------------------------------------------
# ক্যামেরা (2D ট্রান্সফরমেশন)
# ---------------------------------------------------------------------
cam_pan_x = 0.0                # ক্যামেরার X-অক্ষে সরানো
cam_pan_y = 0.0                # ক্যামেরার Y-অক্ষে সরানো
cam_zoom  = 1.0                # জুম লেভেল (১ = স্বাভাবিক)
cam_angle = 0.0                # ঘোরানোর কোণ (ডিগ্রিতে)

# ---------------------------------------------------------------------
# কিউবিক বেজিয়ে কার্ভের ৪টি কন্ট্রোল পয়েন্ট (ক্যানভাস-লোকাল কোঅর্ডিনেট)
# ---------------------------------------------------------------------
ctrl = [
    [-300.0, -150.0],          # P0 -- শুরুর বিন্দু
    [-100.0,  220.0],          # P1 -- প্রথম কন্ট্রোল হ্যান্ডেল
    [ 100.0, -220.0],          # P2 -- দ্বিতীয় কন্ট্রোল হ্যান্ডেল
    [ 300.0,  150.0],          # P3 -- শেষ বিন্দু
]
selected_pt = 0                # এখন কোন কন্ট্রোল পয়েন্ট সিলেক্ট করা আছে
dragging    = False            # মাউস এখন ড্র্যাগ করছে কি না

# ---------------------------------------------------------------------
# রেন্ডারিং অপশন
# ---------------------------------------------------------------------
SEGMENTS    = 64               # প্রতি কার্ভে কতটি সরলরেখা দিয়ে ভাঙা হবে
fill_mode   = True             # গ্লিফ ফিল দেখাবে কি না
clipping_on = True             # লাইন ক্লিপিং চালু আছে কি না

# ---------------------------------------------------------------------
# মেট্রিক্স -- প্রতিটি অ্যালগরিদমের শেষ ফ্রেমের সময় (মাইক্রোসেকেন্ডে)
# ---------------------------------------------------------------------
metrics_smooth = {"decasteljau": 0.0, "bernstein": 0.0, "forward": 0.0}


# =====================================================================
#  তিনটি বেজিয়ে ইভ্যালুয়েশন অ্যালগরিদম
# =====================================================================

def bezier_decasteljau(p0, p1, p2, p3, n):
    """
    দ্য কাস্টেলজো: বারবার লিনিয়ার ইন্টারপোলেশন করে কার্ভের প্রতিটি বিন্দু বের করা হয়।
    এটি সংখ্যাগতভাবে সবচেয়ে স্থিতিশীল -- ছোট রাউন্ডিং ভুল জমা হয় না।
    কিন্তু ধীর, কারণ প্রতিটি বিন্দুর জন্য অনেকগুলো ধাপ লাগে।
    """
    pts = []
    for i in range(n + 1):
        t = i / n                        # t হলো ০ থেকে ১ পর্যন্ত প্যারামিটার
        # প্রথম স্তরের ইন্টারপোলেশন -- P0->P1, P1->P2, P2->P3
        a = (p0[0] + (p1[0]-p0[0])*t, p0[1] + (p1[1]-p0[1])*t)
        b = (p1[0] + (p2[0]-p1[0])*t, p1[1] + (p2[1]-p1[1])*t)
        c = (p2[0] + (p3[0]-p2[0])*t, p2[1] + (p3[1]-p2[1])*t)
        # দ্বিতীয় স্তরের ইন্টারপোলেশন -- a->b, b->c
        d = (a[0] + (b[0]-a[0])*t, a[1] + (b[1]-a[1])*t)
        e = (b[0] + (c[0]-b[0])*t, b[1] + (c[1]-b[1])*t)
        # তৃতীয় স্তরের ইন্টারপোলেশন -- d->e -- এটাই চূড়ান্ত বিন্দু
        f = (d[0] + (e[0]-d[0])*t, d[1] + (e[1]-d[1])*t)
        pts.append(f)
    return pts


def bezier_bernstein(p0, p1, p2, p3, n):
    """
    বার্নস্টাইন পলিনোমিয়াল: সরাসরি সূত্র দিয়ে B(t) = Σ(Bi · Pi) হিসাব করা হয়।
    দ্য কাস্টেলজোর মতোই নির্ভুল, কিন্তু একটু ভিন্ন পদ্ধতি।
    """
    pts = []
    for i in range(n + 1):
        t = i / n
        u = 1.0 - t
        # চারটি বার্নস্টাইন ভিত্তি পলিনোমিয়াল
        b0 = u*u*u
        b1 = 3.0*u*u*t
        b2 = 3.0*u*t*t
        b3 = t*t*t
        # প্রতিটি কন্ট্রোল পয়েন্টকে তার ভিত্তি দিয়ে গুণ করে যোগ
        x = b0*p0[0] + b1*p1[0] + b2*p2[0] + b3*p3[0]
        y = b0*p0[1] + b1*p1[1] + b2*p2[1] + b3*p3[1]
        pts.append((x, y))
    return pts


def bezier_forward_diff(p0, p1, p2, p3, n):
    """
    ফরওয়ার্ড ডিফারেন্সিং: আগের বিন্দুর সাথে ছোট একটা ধ্রুবক যোগ করে পরের বিন্দু বের করা হয়।
    সবচেয়ে দ্রুত, কিন্তু ছোট ছোট ভুল জমা হতে হতে কার্ভ সরে যায় (drift)।
    প্রতি ১৬ ধাপে আবার সঠিক সূত্র দিয়ে রিসেট করা হয়, যাতে drift কমে।
    """
    # প্রথম, দ্বিতীয়, তৃতীয় পরিমিতি পার্থক্য (finite differences)
    d1 = (3*(p1[0]-p0[0]), 3*(p1[1]-p0[1]))
    d2 = (3*(p0[0]-2*p1[0]+p2[0]), 3*(p0[1]-2*p1[1]+p2[1]))
    d3 = (p3[0]-3*p2[0]+3*p1[0]-p0[0], p3[1]-3*p2[1]+3*p1[1]-p0[1])
    dt = 1.0 / n
    # প্রতিটি ধাপে কত যোগ হবে সেই ইনক্রিমেন্ট
    s1 = (d1[0]*dt + d2[0]*dt*dt + d3[0]*dt*dt*dt,
          d1[1]*dt + d2[1]*dt*dt + d3[1]*dt*dt*dt)
    s2 = (2*d2[0]*dt*dt + 6*d3[0]*dt*dt*dt,
          2*d2[1]*dt*dt + 6*d3[1]*dt*dt*dt)
    s3 = (6*d3[0]*dt*dt*dt, 6*d3[1]*dt*dt*dt)
    x, y = p0
    pts = [(x, y)]
    for i in range(1, n + 1):
        if i % 16 == 0:
            # প্রতি ১৬ ধাপে সরাসরি সঠিক সূত্র দিয়ে রিসেট
            # এতে জমে থাকা ভুল মুছে যায়
            t = i / n
            u = 1 - t
            x = (u*u*u*p0[0] + 3*u*u*t*p1[0] + 3*u*t*t*p2[0] + t*t*t*p3[0])
            y = (u*u*u*p0[1] + 3*u*u*t*p1[1] + 3*u*t*t*p2[1] + t*t*t*p3[1])
        else:
            # শুধু ছোট ইনক্রিমেন্ট যোগ করে পরের বিন্দু
            x += s1[0]; y += s1[1]
            s1 = (s1[0]+s2[0], s1[1]+s2[1])
            s2 = (s2[0]+s3[0], s2[1]+s3[1])
        pts.append((x, y))
    return pts


# =====================================================================
#  2D ট্রান্সফরমেশন: ওয়ার্ল্ড কোঅর্ডিনেট -> স্ক্রিন কোঅর্ডিনেট
# =====================================================================

def apply_camera(px, py, canvas_cx, canvas_cy):
    """
    ক্যামেরার ট্রান্সফরমেশন প্রয়োগ করি।
    ধাপ: ১) প্যান  ->  ২) রোটেট  ->  ৩) জুম  ->  ৪) প্যানেলের কেন্দ্রে সরাও
    এটাই একক 3x3 affine ম্যাট্রিক্স হিসেবে কাজ করে।
    """
    x = px + cam_pan_x                # প্যান
    y = py + cam_pan_y
    rad = math.radians(cam_angle)     # ডিগ্রি থেকে রেডিয়ান
    cs, sn = math.cos(rad), math.sin(rad)
    xr = x*cs - y*sn                  # রোটেট
    yr = x*sn + y*cs
    # জুম করে প্যানেলের কেন্দ্রে বসাই
    return (canvas_cx + xr*cam_zoom, canvas_cy + yr*cam_zoom)


# =====================================================================
#  লাইন ক্লিপিং (কোহেন-সাদারল্যান্ড অ্যালগরিদম)
#  প্রতিটি বিন্দু কোথায় আছে সেটা ৪টি বিট দিয়ে প্রকাশ করি:
#  INSIDE=0, LEFT=1, RIGHT=2, BOTTOM=4, TOP=8
# =====================================================================
INSIDE, LEFT, RIGHT, BOTTOM, TOP = 0, 1, 2, 4, 8

def _rc(x, y, xmin, ymin, xmax, ymax):
    """এই বিন্দুর ৪-বিট রিজিওন কোড বের করি।"""
    c = INSIDE
    if x < xmin:   c |= LEFT
    elif x > xmax: c |= RIGHT
    if y < ymin:   c |= BOTTOM
    elif y > ymax: c |= TOP
    return c

def clip_line(x0, y0, x1, y1, xmin, ymin, xmax, ymax):
    """
    কোহেন-সাদারল্যান্ড অ্যালগরিদম।
    লাইনের যে অংশ বক্সের বাইরে, সেটা কেটে ফেলি।
    ফেরত দেয় ক্লিপ করা লাইন, বা None যদি পুরোটাই বাইরে থাকে।
    """
    c0 = _rc(x0, y0, xmin, ymin, xmax, ymax)
    c1 = _rc(x1, y1, xmin, ymin, xmax, ymax)
    while True:
        if not (c0 | c1):             # দুটো বিন্দুই ভিতরে -> পুরো লাইন ভিতরে
            return x0, y0, x1, y1
        if c0 & c1:                   # দুটোই একই বাইরের এলাকায় -> লাইন সম্পূর্ণ বাইরে
            return None
        # একটা বিন্দু বাইরে -- কোন দিকে সেটা দেখে সীমানায় কেটে ফেলি
        out = c0 or c1
        if out & TOP:
            x = x0 + (x1-x0)*(ymax-y0)/(y1-y0); y = ymax
        elif out & BOTTOM:
            x = x0 + (x1-x0)*(ymin-y0)/(y1-y0); y = ymin
        elif out & RIGHT:
            y = y0 + (y1-y0)*(xmax-x0)/(x1-x0); x = xmax
        else:  # LEFT
            y = y0 + (y1-y0)*(xmin-x0)/(x1-x0); x = xmin
        if out == c0:
            x0, y0 = x, y
            c0 = _rc(x0, y0, xmin, ymin, xmax, ymax)
        else:
            x1, y1 = x, y
            c1 = _rc(x1, y1, xmin, ymin, xmax, ymax)


# =====================================================================
#  আঁকার হেল্পার ফাংশন
# =====================================================================

def draw_clipped_line(p, q, color, lw=1.0, clip_box=None):
    """দুই বিন্দুর মধ্যে একটা লাইন আঁকি, ক্লিপিং সহ।"""
    x0, y0 = p; x1, y1 = q
    if clipping_on and clip_box is not None:
        r = clip_line(x0, y0, x1, y1, *clip_box)
        if r is None:
            return
        x0, y0, x1, y1 = r
    glColor3f(*color)              # রঙ ঠিক করি
    glLineWidth(lw)                # লাইনের পুরুত্ব
    glBegin(GL_LINES)
    glVertex2f(x0, y0)
    glVertex2f(x1, y1)
    glEnd()


def draw_polyline(pts, color, lw=2.0, clip_box=None):
    """অনেকগুলো বিন্দুকে জোড়া দিয়ে একটা পলিলাইন আঁকি।"""
    if not pts:
        return
    glColor3f(*color)
    glLineWidth(lw)
    if clipping_on and clip_box is not None:
        # প্রতিটা সেগমেন্ট আলাদা করে ক্লিপ করি
        glBegin(GL_LINES)
        for i in range(len(pts)-1):
            r = clip_line(pts[i][0], pts[i][1],
                          pts[i+1][0], pts[i+1][1], *clip_box)
            if r is not None:
                glVertex2f(r[0], r[1])
                glVertex2f(r[2], r[3])
        glEnd()
    else:
        # ক্লিপিং ছাড়া সোজা পলিলাইন আঁকি
        glBegin(GL_LINE_STRIP)
        for p in pts:
            glVertex2f(*p)
        glEnd()


def draw_filled_region(pts, color, clip_box=None):
    """বদ্ধ এলাকা রঙে ভরাট করি (কালার ফিল টেকনিক)।"""
    if len(pts) < 3:
        return
    glColor3f(*color)
    glBegin(GL_TRIANGLE_FAN)       # কেন্দ্র থেকে ত্রিভুজের পাখার মতো
    for p in pts:
        x, y = p
        if clipping_on and clip_box is not None:
            # ক্লিপ বক্সের ভিতরে বিন্দুটা ঢুকিয়ে রাখি
            x = max(clip_box[0], min(clip_box[2], x))
            y = max(clip_box[1], min(clip_box[3], y))
        glVertex2f(x, y)
    glEnd()


def draw_rect(x, y, w, h, color):
    """একটা রঙিন আয়তক্ষেত্র আঁকি (GL_QUADS)।"""
    glColor3f(*color)
    glBegin(GL_QUADS)
    glVertex2f(x,   y)
    glVertex2f(x+w, y)
    glVertex2f(x+w, y+h)
    glVertex2f(x,   y+h)
    glEnd()


def draw_circle(cx, cy, r, color, segments=16):
    """কেন্দ্র (cx,cy), ব্যাসার্ধ r -- একটা ভরাট বৃত্ত আঁকি।"""
    glColor3f(*color)
    glBegin(GL_TRIANGLE_FAN)
    glVertex2f(cx, cy)
    for i in range(segments + 1):
        a = 2*math.pi*i/segments
        glVertex2f(cx + r*math.cos(a), cy + r*math.sin(a))
    glEnd()


# =====================================================================
#  একটা প্যানেল আঁকার ফাংশন
# =====================================================================

def draw_panel(panel_index, algo_name, algo_fn, curve_color):
    """
    একটা প্যানেলের ভিতরে সবকিছু আঁকি:
    ব্যাকগ্রাউন্ড, বর্ডার, কন্ট্রোল পলিগন, কার্ভ, কন্ট্রোল পয়েন্ট হ্যান্ডেল।
    সাথে অ্যালগরিদমের সময় মাপি।
    """
    px0 = panel_index * PANEL_W         # প্যানেলের বাম প্রান্ত
    px1 = px0 + PANEL_W                 # প্যানেলের ডান প্রান্ত
    py0 = 0
    py1 = WIN_H - HUD_H                 # HUD এর নিচের অংশ পর্যন্ত

    pad = 6
    clip_box = (px0 + pad, py0 + pad, px1 - pad, py1 - pad)

    # প্যানেলের ব্যাকগ্রাউন্ড রঙ
    draw_rect(px0, py0, PANEL_W, py1, (0.10, 0.11, 0.14))

    # প্যানেলের বর্ডার আঁকি
    glColor3f(0.30, 0.32, 0.38)
    glLineWidth(2.0)
    glBegin(GL_LINE_LOOP)
    glVertex2f(px0 + 1, py0 + 1)
    glVertex2f(px1 - 1, py0 + 1)
    glVertex2f(px1 - 1, py1 - 1)
    glVertex2f(px0 + 1, py1 - 1)
    glEnd()

    # প্যানেলের কেন্দ্র (ক্যানভাসের মূলবিন্দু)
    ccx = (px0 + px1) / 2.0
    ccy = py0 + (py1 - py0) * 0.55

    # কন্ট্রোল পয়েন্টগুলোকে স্ক্রিন কোঅর্ডিনেটে রূপান্তর করি
    screen_ctrl = [apply_camera(p[0], p[1], ccx, ccy) for p in ctrl]

    # অ্যালগরিদম কল করি এবং সময় মাপি
    p0, p1, p2, p3 = ctrl
    t0 = time.perf_counter()
    curve_pts = algo_fn(p0, p1, p2, p3, SEGMENTS)
    t1 = time.perf_counter()
    dt_us = (t1 - t0) * 1e6             # সেকেন্ড -> মাইক্রোসেকেন্ড

    # স্মুথিং করে মেট্রিক্স আপডেট করি (HUD এ সুন্দর দেখানোর জন্য)
    metrics_smooth[algo_name] = 0.9*metrics_smooth[algo_name] + 0.1*dt_us

    # কার্ভের প্রতিটি বিন্দুকে স্ক্রিনে রূপান্তর করি
    screen_curve = [apply_camera(x, y, ccx, ccy) for (x, y) in curve_pts]

    # গ্লিফ ফিল (কালার ফিল) -- কার্ভের ভিতরের এলাকা রঙে ভরাট
    if fill_mode and len(screen_curve) >= 2:
        contour = screen_curve + [screen_ctrl[0]]   # বন্ধ কনট্যুর বানাই
        draw_filled_region(contour,
                           (curve_color[0]*0.45,
                            curve_color[1]*0.45,
                            curve_color[2]*0.45),
                           clip_box)

    # কন্ট্রোল পলিগন -- P0->P1, P1->P2, P2->P3 রেখা দিয়ে দেখাই
    for i in range(3):
        draw_clipped_line(screen_ctrl[i], screen_ctrl[i+1],
                          (0.45, 0.45, 0.50), 1.0, clip_box)

    # কার্ভ নিজে
    draw_polyline(screen_curve, curve_color, 3.0, clip_box)

    # কন্ট্রোল পয়েন্ট হ্যান্ডেল (ছোট গোল) দেখাই
    for i, p in enumerate(screen_ctrl):
        if not (clip_box[0] <= p[0] <= clip_box[2]
                and clip_box[1] <= p[1] <= clip_box[3]):
            continue
        # সিলেক্ট করা পয়েন্ট হলুদ, বাকিগুলো সাদা
        color = (1.0, 0.85, 0.2) if i == selected_pt else (0.85, 0.85, 0.9)
        draw_circle(p[0], p[1], 6, color)
        draw_circle(p[0], p[1], 3, (0.15, 0.15, 0.18))


# =====================================================================
#  স্ক্রিন-টু-ওয়ার্ল্ড (মাউস পজিশন থেকে ওয়ার্ল্ড কোঅর্ডিনেট বের করা)
# =====================================================================

def screen_to_world(px, py, panel_index):
    """apply_camera এর উল্টো কাজ -- মাউসের পিক্সেল থেকে ওয়ার্ল্ড কোঅর্ডিনেট।"""
    ccx = panel_index * PANEL_W + PANEL_W / 2.0
    ccy = (WIN_H - HUD_H) * 0.55
    x = px - ccx
    y = py - ccy
    if cam_zoom == 0:
        return 0, 0
    x /= cam_zoom                    # উল্টো জুম
    y /= cam_zoom
    rad = math.radians(-cam_angle)   # উল্টো রোটেট
    cs, sn = math.cos(rad), math.sin(rad)
    xr = x*cs - y*sn
    yr = x*sn + y*cs
    xr -= cam_pan_x                  # উল্টো প্যান
    yr -= cam_pan_y
    return xr, yr


# =====================================================================
#  GLFW কলব্যাক -- মাউস ও কীবোর্ড ইনপুট হ্যান্ডলার
# =====================================================================

def mouse_button_callback(window, button, action, mods):
    """মাউস ক্লিক করলে কোন কন্ট্রোল পয়েন্ট সিলেক্ট হবে সেটা ঠিক করি।"""
    global dragging, selected_pt
    if button != glfw.MOUSE_BUTTON_LEFT:
        return
    if action == glfw.PRESS:
        mx, my = glfw.get_cursor_pos(window)
        # GLFW এর Y উল্টো (উপর থেকে শুরু), তাই ঠিক করি
        y = WIN_H - my
        panel_index = min(int(mx // PANEL_W), 2)
        wx, wy = screen_to_world(mx, y, panel_index)
        # সবচেয়ে কাছের কন্ট্রোল পয়েন্ট বের করি
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
    """মাউস নাড়ালে সিলেক্ট করা কন্ট্রোল পয়েন্ট সরাই।"""
    if not dragging:
        return
    y = WIN_H - my
    panel_index = min(int(mx // PANEL_W), 2)
    wx, wy = screen_to_world(mx, y, panel_index)
    ctrl[selected_pt][0] = wx
    ctrl[selected_pt][1] = wy


def key_callback(window, key, scancode, action, mods):
    """কীবোর্ড থেকে ক্যামেরা নিয়ন্ত্রণ, ফিল ও ক্লিপিং টগল।"""
    global cam_pan_x, cam_pan_y, cam_zoom, cam_angle
    global fill_mode, clipping_on, SEGMENTS, selected_pt
    if action not in (glfw.PRESS, glfw.REPEAT):
        return

    if key == glfw.KEY_ESCAPE:                          # বন্ধ
        glfw.set_window_should_close(window, True)
    elif key == glfw.KEY_W: cam_pan_y += 15             # উপরে প্যান
    elif key == glfw.KEY_S: cam_pan_y -= 15             # নিচে প্যান
    elif key == glfw.KEY_A: cam_pan_x -= 15             # বামে প্যান
    elif key == glfw.KEY_D: cam_pan_x += 15             # ডানে প্যান
    elif key in (glfw.KEY_EQUAL, glfw.KEY_KP_ADD):     cam_zoom *= 1.15   # জুম ইন
    elif key in (glfw.KEY_MINUS, glfw.KEY_KP_SUBTRACT): cam_zoom /= 1.15  # জুম আউট
    elif key == glfw.KEY_Q: cam_angle += 5              # ঘড়ির কাঁটার দিকে
    elif key == glfw.KEY_E: cam_angle -= 5              # উল্টো দিকে
    elif key == glfw.KEY_0:                             # ক্যামেরা রিসেট
        cam_pan_x = cam_pan_y = 0.0
        cam_zoom = 1.0
        cam_angle = 0.0
    elif key == glfw.KEY_F: fill_mode = not fill_mode   # ফিল টগল
    elif key == glfw.KEY_C: clipping_on = not clipping_on  # ক্লিপিং টগল
    elif key == glfw.KEY_R:                             # র‍্যান্ডম কন্ট্রোল পয়েন্ট
        for p in ctrl:
            p[0] = random.uniform(-320, 320)
            p[1] = random.uniform(-200, 200)
    elif key in (glfw.KEY_1, glfw.KEY_2, glfw.KEY_3, glfw.KEY_4):
        selected_pt = key - glfw.KEY_1                  # কোন পয়েন্ট সিলেক্ট
    elif key == glfw.KEY_LEFT_BRACKET:                  # সেগমেন্ট অর্ধেক
        SEGMENTS = max(8, SEGMENTS // 2)
    elif key == glfw.KEY_RIGHT_BRACKET:                 # সেগমেন্ট দ্বিগুণ
        SEGMENTS = min(512, SEGMENTS * 2)


# =====================================================================
#  মূল প্রোগ্রাম
# =====================================================================

def main():
    # GLFW চালু করি
    if not glfw.init():
        raise SystemExit("GLFW চালু করা যায়নি")

    # OpenGL 2.1 কনটেক্সট চাই (যেখানে glBegin/glEnd কাজ করে)
    glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 2)
    glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 1)
    glfw.window_hint(glfw.SAMPLES, 4)         # অ্যান্টিএলিয়াসিং

    # উইন্ডো বানাই
    window = glfw.create_window(
        WIN_W, WIN_H,
        "Bezier Algorithm Comparison - Font Rasterisation Visualiser",
        None, None)
    if not window:
        glfw.terminate()
        raise SystemExit("GLFW উইন্ডো বানানো যায়নি")

    glfw.make_context_current(window)         # এই উইন্ডোর GL কনটেক্সট চালু
    glfw.swap_interval(1)                     # vsync -- ৬০ FPS এ লক

    # ইনপুট কলব্যাক রেজিস্টার করি
    glfw.set_mouse_button_callback(window, mouse_button_callback)
    glfw.set_cursor_pos_callback(window, cursor_pos_callback)
    glfw.set_key_callback(window, key_callback)

    glViewport(0, 0, WIN_W, WIN_H)

    # ---------- মূল লুপ: প্রতি ফ্রেমে আঁকি ----------
    while not glfw.window_should_close(window):
        # প্রতি ফ্রেমে ভিউপোর্ট ও প্রজেকশন ম্যাট্রিক্স রিসেট করি
        fb_w, fb_h = glfw.get_framebuffer_size(window)
        glViewport(0, 0, fb_w, fb_h)

        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        glOrtho(0.0, float(WIN_W), 0.0, float(WIN_H), -1.0, 1.0)

        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()

        # স্ক্রিন পরিষ্কার করি
        glClearColor(0.05, 0.05, 0.07, 1.0)
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

        # ---- তিনটি প্যানেল আঁকি ----
        draw_panel(0, "decasteljau", bezier_decasteljau, (0.35, 0.75, 1.0))   # নীল
        draw_panel(1, "bernstein",   bezier_bernstein,   (0.55, 0.95, 0.45))  # সবুজ
        draw_panel(2, "forward",     bezier_forward_diff,(1.0, 0.65, 0.35))   # কমলা

        # ---- HUD স্ট্রিপ -- উপরে তিনটি সময়ের বার ----
        draw_rect(0, WIN_H - HUD_H, WIN_W, HUD_H, (0.08, 0.09, 0.11))

        names = ["decasteljau", "bernstein", "forward"]
        colors = [(0.35, 0.75, 1.0), (0.55, 0.95, 0.45), (1.0, 0.65, 0.35)]
        max_us = max(max(metrics_smooth.values()), 1.0)
        for i, (n, c) in enumerate(zip(names, colors)):
            bar_x = 20 + i * 390
            bar_w = int(360 * (metrics_smooth[n] / max_us))
            bar_y = WIN_H - 40
            draw_rect(bar_x, bar_y, 360, 16, (0.15, 0.16, 0.19))  # ব্যাকগ্রাউন্ড
            draw_rect(bar_x, bar_y, bar_w, 16, c)                  # সময়ের সমানুপাতিক বার
            draw_rect(bar_x - 6, bar_y, 4, 16, c)                  # ছোট মার্কার

        # ---- উইন্ডোর টাইটেলে লাইভ মেট্রিক্স দেখাই ----
        glfw.set_window_title(
            window,
            f"Bezier Comparison | "
            f"deCasteljau={metrics_smooth['decasteljau']:.0f}us  "
            f"Bernstein={metrics_smooth['bernstein']:.0f}us  "
            f"FwdDiff={metrics_smooth['forward']:.0f}us | "
            f"segments={SEGMENTS}  fill={'ON' if fill_mode else 'OFF'}  "
            f"clip={'ON' if clipping_on else 'OFF'}  "
            f"zoom={cam_zoom:.2f}x  rot={cam_angle:.0f}deg")

        # ---- ব্যাক বাফার ও ফ্রন্ট বাফার অদলবদল ----
        glfw.swap_buffers(window)
        glfw.poll_events()                    # ইনপুট ইভেন্ট প্রসেস করি

    # লুপ শেষ -- GLFW বন্ধ করি
    glfw.terminate()


# =====================================================================
#  এন্ট্রি পয়েন্ট
# =====================================================================

if __name__ == "__main__":
    main()