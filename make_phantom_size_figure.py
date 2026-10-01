"""
Figura esplicativa delle DIMENSIONI del fantoccio (il "paziente") su cui
proiettiamo la dose alla cute.

Il fantoccio di default NON e' un ellissoide: e' un CILINDRO A SEZIONE
ELLITTICA. Tre parametri (impostabili dall'utente nella sidebar) ne fissano
la taglia:
    - width_mm  (larghezza laterale)  -> semiasse ellisse a = width/2   (asse x)
    - ap_mm     (spessore AP)         -> semiasse ellisse b = ap/2       (asse y)
    - length_mm (lunghezza mappata)   -> estrusione lungo z

Uso:
    python make_phantom_size_figure.py
Produce: phantom_size_explained.png
"""
from __future__ import annotations
import math
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# Stessi default della sidebar di app.py
WIDTH = 360.0   # larghezza laterale (mm)
AP = 240.0      # spessore antero-posteriore (mm)
LENGTH = 800.0  # lunghezza longitudinale mappata (mm)

A = WIDTH / 2.0   # semiasse laterale ellisse
B = AP / 2.0      # semiasse AP ellisse

fig = plt.figure(figsize=(16, 5.5))

# ---------------------------------------------------------------------------
# Pannello 1: sezione trasversale (l'ellisse) con i due semiassi
# ---------------------------------------------------------------------------
ax1 = fig.add_subplot(1, 3, 1)
ax1.set_title("1) Sezione trasversale = ELLISSE\n(piano x–y, vista assiale)", fontsize=11)
tt = np.linspace(0, 2 * math.pi, 300)
ax1.fill(A * np.cos(tt), B * np.sin(tt), color="#cde3f0", zorder=1)
ax1.plot(A * np.cos(tt), B * np.sin(tt), color="#1f77b4", lw=2, zorder=2)

# semiasse a (laterale)
ax1.annotate("", xy=(A, 0), xytext=(0, 0),
             arrowprops=dict(arrowstyle="<->", color="#d62728", lw=2))
ax1.text(A / 2, 12, f"a = width/2 = {A:.0f} mm", color="#d62728", ha="center", fontsize=9)
# semiasse b (AP)
ax1.annotate("", xy=(0, B), xytext=(0, 0),
             arrowprops=dict(arrowstyle="<->", color="#2ca02c", lw=2))
ax1.text(8, B / 2, f"b = AP/2 = {B:.0f} mm", color="#2ca02c", va="center", fontsize=9, rotation=90)

# larghezza totale e spessore totale
ax1.annotate("", xy=(-A, -B - 35), xytext=(A, -B - 35),
             arrowprops=dict(arrowstyle="<->", color="0.3", lw=1.3))
ax1.text(0, -B - 55, f"width = {WIDTH:.0f} mm (laterale)", ha="center", fontsize=9, color="0.2")
ax1.annotate("", xy=(-A - 35, -B), xytext=(-A - 35, B),
             arrowprops=dict(arrowstyle="<->", color="0.3", lw=1.3))
ax1.text(-A - 48, 0, f"AP = {AP:.0f} mm", va="center", rotation=90, fontsize=9, color="0.2")

ax1.plot(0, 0, "k+", ms=10)
ax1.text(6, 6, "isocentro", fontsize=8)
ax1.set_aspect("equal")
ax1.set_xlim(-A - 90, A + 60)
ax1.set_ylim(-B - 90, B + 50)
ax1.set_xlabel("x laterale (mm)")
ax1.set_ylabel("y AP (mm)")
ax1.annotate("anteriore (+y)", xy=(0, B), xytext=(0, B + 25), ha="center", fontsize=8, color="0.4")
ax1.annotate("posteriore (−y)", xy=(0, -B), xytext=(0, -B - 72), ha="center", fontsize=8, color="0.4")

# ---------------------------------------------------------------------------
# Pannello 2: estrusione lungo z -> cilindro ellittico 3D
# ---------------------------------------------------------------------------
ax2 = fig.add_subplot(1, 3, 2, projection="3d")
ax2.set_title("2) Estrusione lungo z = CILINDRO ELLITTICO\n(la superficie laterale = pelle)", fontsize=11)
th = np.linspace(-math.pi, math.pi, 120)
zz = np.linspace(-LENGTH / 2, LENGTH / 2, 60)
TH, ZZ = np.meshgrid(th, zz)
X = A * np.cos(TH)
Y = B * np.sin(TH)
Z = ZZ
ax2.plot_surface(X, Y, Z, color="#9ecae1", alpha=0.6, linewidth=0, shade=True)

# ellisse evidenziata alle due estremita'
for z_end in (-LENGTH / 2, LENGTH / 2):
    ax2.plot(A * np.cos(th), B * np.sin(th), np.full_like(th, z_end), color="#1f77b4", lw=1.5)

# freccia lunghezza
ax2.plot([A + 60, A + 60], [0, 0], [-LENGTH / 2, LENGTH / 2], color="#d62728", lw=2)
ax2.text(A + 90, 0, 0, f"length = {LENGTH:.0f} mm", color="#d62728", fontsize=9)

ax2.set_xlabel("x lat (mm)")
ax2.set_ylabel("y AP (mm)")
ax2.set_zlabel("z long (mm)")
ax2.set_box_aspect((1, 1, 1.8))
ax2.view_init(elev=16, azim=-62)

# ---------------------------------------------------------------------------
# Pannello 3: la mappa "srotolata" (quello che vedi come heatmap)
# ---------------------------------------------------------------------------
ax3 = fig.add_subplot(1, 3, 3)
ax3.set_title("3) Cilindro SROTOLATO = mappa 2D\n(asse angolare × asse longitudinale)", fontsize=11)
# perimetro ellisse per asse x della mappa
ax3.add_patch(plt.Rectangle((-180, -LENGTH / 2), 360, LENGTH, facecolor="#eef5fb", edgecolor="#1f77b4", lw=1.5))
for ang, lab in [(-180, "−180°"), (-90, "−90°\n(post.)"), (0, "0°\n(ant.)"), (90, "+90°"), (180, "+180°")]:
    ax3.axvline(ang, color="0.75", lw=0.8, ls="--")
    ax3.text(ang, -LENGTH / 2 - 55, lab, ha="center", fontsize=8, color="0.3")
ax3.set_xlim(-210, 210)
ax3.set_ylim(-LENGTH / 2 - 90, LENGTH / 2 + 30)
ax3.set_xlabel("angolo circonferenziale (deg)")
ax3.set_ylabel("z posizione longitudinale (mm)")
ax3.text(0, LENGTH / 2 - 60,
         "ogni cella = un punto di pelle\ncolore = dose accumulata (Gy)",
         ha="center", fontsize=8, style="italic", color="0.3")

fig.suptitle(
    "PSD Mapper — dimensioni del 'paziente': cilindro a sezione ellittica definito da width, AP e length",
    fontsize=13, y=0.99,
)
fig.tight_layout(rect=(0, 0.02, 1, 0.95))
out = "phantom_size_explained.png"
fig.savefig(out, dpi=140)
print("Salvato:", out)
