"""Generate an explanatory figure of the PSD geometry:
source (focal spot), IRP, isocentre, patient skin, table — and the distances
that drive the inverse-square correction.

Standard frontal projection (alpha = beta = 0): X-ray tube UNDER the supine
patient, beam pointing upward (posterior -> anterior). Vertical axis = beam
axis. Produces geometry_distances.png in this folder.
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, Ellipse, Rectangle
import numpy as np

fig, ax = plt.subplots(figsize=(8.5, 10.5))

# --- vertical geometry (mm), tube at bottom, beam going up ------------------
y_source = 0.0        # focal spot (source)
SOD = 785.0           # source -> isocentre
IRP_off = 150.0       # isocentre -> IRP (toward source), IEC convention
y_irp = SOD - IRP_off # source -> IRP distance = d_ref = 635 mm
y_iso = SOD           # isocentre
y_skin = 470.0        # source -> patient posterior skin (example: t)
y_table = 430.0       # table top just below the skin
x0 = 0.0              # beam central axis (x)

# beam cone half-widths (just for drawing)
def hw(y):  # half width grows with distance from source
    return 15 + 0.11 * y

# --- draw beam cone ---------------------------------------------------------
top = SOD + 120
ax.fill_between([x0 - hw(top), x0 + hw(top)], y_source, y_source,
                color="none")
beam = plt.Polygon([[x0, y_source],
                    [x0 - hw(top), top],
                    [x0 + hw(top), top]],
                   closed=True, color="#ffe08a", alpha=0.45, zorder=1,
                   label="X-ray beam")
ax.add_patch(beam)

# --- table + pad ------------------------------------------------------------
ax.add_patch(Rectangle((x0 - 220, y_table), 440, 22, color="#9aa0a6",
                        alpha=0.9, zorder=2))
ax.add_patch(Rectangle((x0 - 220, y_table + 22), 440, 12, color="#cfd3d7",
                        alpha=0.9, zorder=2))
ax.text(x0 + 235, y_table + 8, "table + pad", va="center", fontsize=10,
        color="#5f6368")

# --- patient cross-section (ellipse), skin entrance at the bottom -----------
patient_cy = y_skin + 120   # centre of the body ellipse above the skin
ax.add_patch(Ellipse((x0, patient_cy), width=360, height=240,
                     facecolor="#ffd9c0", edgecolor="#d98b5f", lw=2,
                     alpha=0.9, zorder=3))
ax.text(x0 + 195, patient_cy, "patient\n(skin surface)", va="center",
        fontsize=10, color="#b5651d")

# entrance skin point (where PSD is highest)
ax.plot([x0], [y_skin], "o", color="#c1121f", ms=11, zorder=5)
ax.annotate("entrance skin cell\n(peak skin dose)", (x0, y_skin),
            xytext=(x0 - 300, y_skin - 25), fontsize=10, color="#c1121f",
            arrowprops=dict(arrowstyle="->", color="#c1121f"))

# --- key points -------------------------------------------------------------
def point(y, label, color, dx=12):
    ax.plot([x0], [y], "s", color=color, ms=9, zorder=6)
    ax.text(x0 + dx + 18, y, label, va="center", fontsize=11, color=color)

# focal spot
ax.plot([x0], [y_source], "*", color="#1d3557", ms=22, zorder=6)
ax.text(x0 + 30, y_source, "X-ray source (focal spot)", va="center",
        fontsize=11, color="#1d3557")

point(y_irp, "IRP  (interventional reference point)\nKa,r is stated HERE",
      "#2a9d8f")
point(y_iso, "isocentre", "#3a0ca3")

# --- distance arrows on the left --------------------------------------------
def dist(x, y1, y2, text, color):
    ax.add_patch(FancyArrowPatch((x, y1), (x, y2), arrowstyle="<->",
                                 mutation_scale=14, color=color, lw=2))
    ax.text(x - 14, (y1 + y2) / 2, text, va="center", ha="right",
            fontsize=10.5, color=color, rotation=90)

dist(-150, y_source, y_iso, "SOD  (source→isocentre)  = 785 mm", "#3a0ca3")
dist(-95,  y_source, y_irp, "d_ref (source→IRP) = SOD − 150 = 635 mm", "#2a9d8f")
dist(-40,  y_source, y_skin, "t  (source→skin, per cell)", "#c1121f")

# --- inverse-square note ----------------------------------------------------
ax.text(x0 - 300, top - 20,
        r"$\mathrm{PSD} = K_{a,r}\cdot\left(\dfrac{d_{ref}}{t}\right)^{2}"
        r"\cdot BSF\cdot MEAC\cdot TAF\cdot CF$",
        fontsize=13, color="#222",
        bbox=dict(boxstyle="round,pad=0.4", fc="#f1f3f4", ec="#bbb"))

ax.text(x0 - 300, top - 70,
        "• Ka,r is registered at the IRP (fixed 15 cm from isocentre).\n"
        "• Moving the TABLE does NOT change Ka,r, SOD or d_ref.\n"
        "• The table only moves the patient → changes t (source→skin).\n"
        "• Tube under patient: raising the table increases t → lower dose.",
        fontsize=10, color="#333", va="top",
        bbox=dict(boxstyle="round,pad=0.4", fc="#eef7f5", ec="#89c2bb"))

# --- cosmetics --------------------------------------------------------------
ax.set_xlim(-330, 330)
ax.set_ylim(-40, top + 20)
ax.set_aspect("equal")
ax.axis("off")
ax.set_title("PSD geometry — distances from source to reference point and skin\n"
             "(standard frontal projection, tube under the patient)",
             fontsize=13, pad=14)

fig.tight_layout()
out = "geometry_distances.png"
fig.savefig(out, dpi=140, bbox_inches="tight")
print("wrote", out)
