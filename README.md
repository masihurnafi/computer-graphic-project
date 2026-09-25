# Bezier Curve Evaluation Algorithm Comparison Visualiser

An interactive OpenGL tool that compares three mathematically equivalent algorithms for evaluating cubic Bezier curves — the same computation that powers font rasterisers (FreeType, DirectWrite), SVG renderers, PDF viewers, and CAD curve editors.

**Course:** Computer Graphics Sessional — Track B (Algorithm Comparison Tool / Research Visualiser)

---

## The Real-World Problem

Every time you read text on a screen, the operating system evaluates Bezier curves (stored in the font file) into pixel coordinates. Three common algorithms exist, and they are mathematically equivalent but computationally different:

| Algorithm             | Speed    | Accuracy                    |
|-----------------------|----------|-----------------------------|
| de Casteljau          | Slower   | Exact, numerically stable   |
| Bernstein polynomial  | Medium   | Exact                       |
| Forward Differencing  | Fastest  | Accumulates floating-point drift |

The differences only become visible when the result is rendered to a pixel grid. This tool makes that comparison visible in real time across three side-by-side panels.

**Real-world systems using the same techniques:**
- **FreeType Font Rasteriser** — used by Android, Chrome, Linux, and every PDF reader
- **Adobe Illustrator Pen Tool / FontForge** — vector design and font authoring

---

## Computer Graphics Techniques Demonstrated

All five techniques from the course requirement list are used:

| Technique | Where it appears |
|-----------|------------------|
| **Bezier Curves** | Three evaluation algorithms (de Casteljau, Bernstein, Forward Differencing) rendered side by side |
| **Line & Shape Drawing** | `GL_LINE_STRIP` for the curve, `GL_LINES` for the control polygon, `GL_LINE_LOOP` for panel borders |
| **Color Fill** | `GL_TRIANGLE_FAN` glyph-fill of the closed curve region + HUD timing bars |
| **2D Transformations** | Pan (W/A/S/D), zoom (+/-), rotate (Q/E) via a manually-composed affine transform chain |
| **Line Clipping** | Cohen-Sutherland 4-bit region-code algorithm clips the curve, control polygon, and fill to each panel's viewport |

---

## Requirements

- Python **3.11 / 3.12 / 3.13** (NOT 3.14 — incompatible with PyOpenGL on macOS)
- PyOpenGL
- PyOpenGL_accelerate
- GLFW

Install:

    pip3 install -r requirements.txt

Or on macOS with Homebrew Python:

    /opt/homebrew/bin/python3.13 -m pip install --user --break-system-packages -r requirements.txt

---

## Run

    python3 bezier_visualizer.py

Or on macOS (recommended):

    /opt/homebrew/bin/python3.13 bezier_visualizer.py

---

## Controls

| Input          | Action                                |
|----------------|---------------------------------------|
| Left-drag      | Move the nearest control point        |
| W A S D        | Pan the canvas                        |
| + / -          | Zoom in / out                         |
| Q / E          | Rotate canvas                         |
| 0              | Reset camera                          |
| F              | Toggle glyph fill                     |
| C              | Toggle line clipping (demo)           |
| R              | Randomise control points              |
| [ / ]          | Halve / double curve segments         |
| ESC            | Quit                                  |

---

## What to Observe in the Demo

1. **Press `]` a few times** to raise segments to 512. The Forward Differencing curve (orange, right panel) visibly drifts away from the other two. This is accumulated floating-point error made visible — the central scientific claim of the project.

2. **Watch the HUD timing bars.** Forward Differencing is typically 2–3× faster per frame than de Casteljau, even though all three are O(n) in segment count.

3. **Press `C` to disable clipping, then `+` to zoom in.** Curve segments bleed across panel boundaries. Press `C` again — Cohen-Sutherland clipping trims them cleanly at the panel edge.

4. **Press `Q` and `E` to rotate.** The curve, control points, control polygon, and glyph fill all respond consistently because they share the same world-to-screen transform.

---

## macOS Deployment Note

PyOpenGL's GLUT backend does not create visible windows on macOS Sequoia with Apple Silicon on Python 3.13/3.14. Both the freeglut 3.8 backend and the pyglet backend fail silently — `glutCreateWindow` returns a valid window ID but the window is never mapped to the display.

This project uses **GLFW** as the windowing layer instead. GLFW is a pure windowing library that hands the OpenGL context to PyOpenGL cleanly, with no conflicts. All rendering code uses raw OpenGL 2.1 fixed-function calls (`glBegin`, `glVertex2f`, `glColor3f`, `glLineWidth`) and does not change between backends.

---

## Author

Masihur Rahman Nafi — Computer Graphics Sessional, Track B
