"""
Genera una figura esplicativa della catena geometrica del PSD Mapper:
come gli angoli del tubo (alpha=LL, beta=AP) e la posizione del lettino
determinano la sorgente, la piramide del fascio e la sua proiezione
sull'ellissoide (cilindro ellittico) del paziente.

Uso:
    python make_geometry_figure.py
Produce: geometry_explained.png
"""
from __future__ import annotations
import math
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch
from mpl_toolkits.mplot3d import proj3d
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

# Riusa la stessa matematica del motore per coerenza col codice reale.
from psd_engine import _beam_axes


class Arrow3D(FancyArrowPatch):
    """Freccia 3D per matplotlib."""
    def __init__(self, xs, ys, zs, *args, **kwargs):
        super().__init__((0, 0), (0, 0), *args, **kwargs)
        self._verts3d = xs, ys, zs

    def do_3d_projection(self, renderer=None):
        xs3d, ys3d, zs3d = self._verts3d
        xs, ys, zs = proj3d.proj_transform(xs3d, ys3d, zs3d, self.axes.M)
        self.set_positions((xs[0], ys[0]), (xs[1], ys[1]))
        return float(np.min(zs))


# ----------------------------------------------------------------------------
# Parametri di esempio (stessa convenzione del motore)
# ----------------------------------------------------------------------------
A = 180.0     # semiasse laterale ellisse (mm)  = larghezza/2
B = 120.0     # semiasse AP ellisse (mm)         = spessore/2
L = 600.0     # lunghezza cilindro (mm)
SOD = 720.0   # distanza sorgente-isocentro (mm)
DREF = SOD - 150.0   # distanza al punto di riferimento IRP
WREF = 140.0  # larghezza base piramide al piano IRP (mm)
HREF = 140.0  # altezza base piramide al piano IRP (mm)

# Due eventi di esempio: uno PA (0/0), uno obliquo LAO/CRA.
EVENTS = [
    dict(alpha=0.0,  beta=0.0,  lat=0.0,  height=0.0, lon=0.0,   color="#1f77b4", label="Evento A: PA (0°/0°)"),
    dict(alpha=35.0, beta=25.0, lat=40.0, height=0.0, lon=120.0, color="#d62728", label="Evento B: LAO 35° / CRA 25°, lettino spostato"),
]

# Riferimenti tavolo (mediane) -> qui 0 per semplicita'
REF = dict(lat=0.0, height=0.0, lon=0.0)
SIGN = dict(lat=-1.0, height=-1.0, lon=-1.0)


def source_and_axes(ev):
    d, e1, e2 = _beam_axes(ev["alpha"], ev["beta"])
    q = np.array([
        SIGN["lat"] * (ev["lat"] - REF["lat"]),
        SIGN["height"] * (ev["height"] - REF["height"]),
        SIGN["lon"] * (ev["lon"] - REF["lon"]),
    ], dtype=float)
    source = q - SOD * d
    return source, d, e1, e2, q


def pyramid_verts(source, d, e1, e2):
    """Restituisce apice e 4 vertici della base della piramide al piano IRP."""
    center = source + DREF * d
    hw, hh = WREF / 2.0, HREF / 2.0
    base = [
        center + hw * e1 + hh * e2,
        center - hw * e1 + hh * e2,
        center - hw * e1 - hh * e2,
        center + hw * e1 - hh * e2,
    ]
    return source, base


def ellipse_surface():
    th = np.linspace(-math.pi, math.pi, 80)
    zz = np.linspace(-L / 2, L / 2, 40)
    TH, ZZ = np.meshgrid(th, zz)
    X = A * np.cos(TH)
    Y = B * np.sin(TH)
    Z = ZZ
    return X, Y, Z, th, zz


def paint_dose_on_grid(events, th, zz):
    """Marca (semplificato) quali nodi della griglia sono colpiti da ciascun fascio,
    con lo stesso test del motore, per colorare l'ellissoide."""
    TH, ZZ = np.meshgrid(th, zz)
    X = (A * np.cos(TH)).ravel()
    Y = (B * np.sin(TH)).ravel()
    Z = ZZ.ravel()
    P = np.stack([X, Y, Z], axis=-1)
    # normali esterne
    nx = np.cos(TH).ravel() / A
    ny = np.sin(TH).ravel() / B
    nn = np.sqrt(nx**2 + ny**2)
    N = np.stack([nx / nn, ny / nn, np.zeros_like(nx)], axis=-1)

    hit_id = np.full(P.shape[0], -1)  # -1 = non colpito
    for idx, ev in enumerate(events):
        source, d, e1, e2, q = source_and_axes(ev)
        V = P - source
        t = V @ d
        u = V @ e1
        v = V @ e2
        incidence = (N @ d) < 0.0
        scale = np.maximum(t, 1e-9) / DREF
        inside = (t > 0) & incidence & (np.abs(u) <= 0.5 * WREF * scale) & (np.abs(v) <= 0.5 * HREF * scale)
        hit_id[inside] = idx
    return hit_id.reshape(TH.shape)


# ----------------------------------------------------------------------------
# FIGURA
# ----------------------------------------------------------------------------
fig = plt.figure(figsize=(17, 6.5))

# --- Pannello 1: assi del fascio dagli angoli (vista assiale x-y) ---
ax1 = fig.add_subplot(1, 3, 1)
ax1.set_title("1) Angoli del tubo → direzione del fascio\n(vista assiale x–y)", fontsize=11)
# ellisse sezione
tt = np.linspace(0, 2 * math.pi, 200)
ax1.plot(A * np.cos(tt), B * np.sin(tt), color="0.5", lw=1.5)
ax1.fill(A * np.cos(tt), B * np.sin(tt), color="0.9")
ax1.plot(0, 0, "k+", ms=10)
ax1.annotate("isocentro", (0, 0), textcoords="offset points", xytext=(6, 6), fontsize=8)
for ev in EVENTS:
    d, e1, e2 = _beam_axes(ev["alpha"], ev["beta"])
    # proiezione della direzione nel piano x-y
    ax1.annotate("", xy=(d[0] * 250, d[1] * 250), xytext=(-d[0] * 250, -d[1] * 250),
                 arrowprops=dict(arrowstyle="->", color=ev["color"], lw=2))
    ax1.text(d[0] * 270, d[1] * 270, f"α={ev['alpha']:.0f}°", color=ev["color"], fontsize=9)
ax1.set_xlim(-320, 320); ax1.set_ylim(-320, 320)
ax1.set_aspect("equal"); ax1.set_xlabel("x laterale (mm)"); ax1.set_ylabel("y AP (mm)")
ax1.text(0, -300, "α (LL) ruota nel piano assiale\nβ (AP) inclina fuori dal piano",
         ha="center", fontsize=8, style="italic")

# --- Pannello 2: catena completa 3D ---
ax2 = fig.add_subplot(1, 3, 2, projection="3d")
ax2.set_title("2) Sorgente + piramide del fascio\nsull'ellissoide (3D)", fontsize=11)
X, Y, Z, th, zz = ellipse_surface()
ax2.plot_surface(X, Y, Z, color="0.85", alpha=0.25, linewidth=0, shade=False)

for ev in EVENTS:
    source, d, e1, e2, q = source_and_axes(ev)
    apex, base = pyramid_verts(source, d, e1, e2)
    # sorgente
    ax2.scatter(*apex, color=ev["color"], s=45)
    # spigoli della piramide apice->base
    for bpt in base:
        ax2.plot([apex[0], bpt[0]], [apex[1], bpt[1]], [apex[2], bpt[2]],
                 color=ev["color"], lw=1.0, alpha=0.8)
    # base (rettangolo)
    faces = [base + [base[0]]]
    bx = [p[0] for p in base] + [base[0][0]]
    by = [p[1] for p in base] + [base[0][1]]
    bz = [p[2] for p in base] + [base[0][2]]
    ax2.plot(bx, by, bz, color=ev["color"], lw=1.5)
    # asse centrale
    center = source + DREF * d
    a3 = Arrow3D([apex[0], center[0]], [apex[1], center[1]], [apex[2], center[2]],
                 mutation_scale=12, lw=1.6, arrowstyle="-|>", color=ev["color"])
    ax2.add_artist(a3)

ax2.scatter(0, 0, 0, color="k", marker="+", s=80)
ax2.set_xlabel("x lat (mm)"); ax2.set_ylabel("y AP (mm)"); ax2.set_zlabel("z long (mm)")
ax2.set_box_aspect((1, 1, 1.4))
try:
    ax2.set_xlim(-800, 800); ax2.set_ylim(-800, 800); ax2.set_zlim(-400, 400)
except Exception:
    pass
ax2.view_init(elev=18, azim=-60)

# --- Pannello 3: dose "dipinta" sull'ellissoide ---
ax3 = fig.add_subplot(1, 3, 3, projection="3d")
ax3.set_title("3) Punti di ENTRATA colpiti\n→ mappa sull'ellissoide", fontsize=11)
hit = paint_dose_on_grid(EVENTS, th, zz)
# colori: grigio non colpito, blu evento A, rosso evento B
facecolor = np.empty(hit.shape + (4,), dtype=float)
base_gray = np.array([0.85, 0.85, 0.85, 0.5])
cmap = {0: np.array([31/255, 119/255, 180/255, 0.95]),
        1: np.array([214/255, 39/255, 40/255, 0.95])}
for i in range(hit.shape[0]):
    for j in range(hit.shape[1]):
        facecolor[i, j] = cmap.get(int(hit[i, j]), base_gray)
ax3.plot_surface(X, Y, Z, facecolors=facecolor, linewidth=0, antialiased=False, shade=False)
ax3.set_xlabel("x lat (mm)"); ax3.set_ylabel("y AP (mm)"); ax3.set_zlabel("z long (mm)")
ax3.set_box_aspect((1, 1, 1.6))
ax3.view_init(elev=18, azim=-60)

# legenda comune
handles = [plt.Line2D([0], [0], color=ev["color"], lw=3, label=ev["label"]) for ev in EVENTS]
handles.append(plt.Line2D([0], [0], color="0.7", lw=8, label="Superficie non irradiata"))
fig.legend(handles=handles, loc="lower center", ncol=3, fontsize=9, frameon=False)

fig.suptitle(
    "PSD Mapper — dalla geometria (angoli tubo + posizione lettino) alla mappa sull'ellissoide del paziente",
    fontsize=13, y=0.99,
)
fig.tight_layout(rect=(0, 0.06, 1, 0.96))
out = "geometry_explained.png"
fig.savefig(out, dpi=140)
print("Salvato:", out)
