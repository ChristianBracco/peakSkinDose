"""
Generazione delle figure didattiche per la Guida spaziale del PSD Mapper.

Le figure usano la STESSA matematica del motore (psd_engine._beam_axes) per
essere coerenti col codice reale. Ogni funzione restituisce un oggetto Figure
di matplotlib; la pagina Streamlit le mostra con st.pyplot.
"""
from __future__ import annotations
import math
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import proj3d
from matplotlib.patches import FancyArrowPatch

from psd_engine import _beam_axes


# Parametri di esempio coerenti con un caso cardiaco tipico.
A = 180.0      # semiasse laterale (mm)
B = 120.0      # semiasse AP (mm)
L = 600.0      # lunghezza cilindro (mm)
SOD = 720.0    # sorgente-isocentro (mm)
DREF = SOD - 150.0
WREF = 140.0
HREF = 140.0

EV_PA = dict(alpha=0.0, beta=0.0, color="#1f77b4", label="PA (0°/0°)")
EV_OBL = dict(alpha=35.0, beta=25.0, color="#d62728", label="LAO 35° / CRA 25°")


class _Arrow3D(FancyArrowPatch):
    def __init__(self, xs, ys, zs, *a, **k):
        super().__init__((0, 0), (0, 0), *a, **k)
        self._v = xs, ys, zs

    def do_3d_projection(self, renderer=None):
        xs, ys, zs = self._v
        X, Y, Z = proj3d.proj_transform(xs, ys, zs, self.axes.M)
        self.set_positions((X[0], Y[0]), (X[1], Y[1]))
        return float(np.min(Z))


def _ellipse_xy(ax, alpha=1.0):
    tt = np.linspace(0, 2 * math.pi, 200)
    ax.fill(A * np.cos(tt), B * np.sin(tt), color="0.9", alpha=alpha, zorder=0)
    ax.plot(A * np.cos(tt), B * np.sin(tt), color="0.5", lw=1.4, zorder=1)


# ---------------------------------------------------------------------------
def fig_reference_frame():
    """Assi del mondo x/y/z e paziente supino."""
    fig, ax = plt.subplots(figsize=(4.6, 3.9))
    _ellipse_xy(ax)
    ax.annotate("", xy=(300, 0), xytext=(-300, 0),
                arrowprops=dict(arrowstyle="->", color="k", lw=1.5))
    ax.annotate("", xy=(0, 260), xytext=(0, -260),
                arrowprops=dict(arrowstyle="->", color="k", lw=1.5))
    ax.text(305, 0, "+x  laterale", va="center", fontsize=10)
    ax.text(0, 275, "+y  AP (anteriore)", ha="center", fontsize=10)
    ax.plot(0, 0, "k+", ms=12)
    ax.text(8, 8, "isocentro", fontsize=9)
    ax.scatter(0, -230, color="#444", s=60, marker="s")
    ax.text(0, -255, "sorgente a 0°/0°\n(sotto il paziente)", ha="center", fontsize=8)
    ax.annotate("", xy=(0, -60), xytext=(0, -220),
                arrowprops=dict(arrowstyle="->", color="#1f77b4", lw=2))
    ax.text(15, -140, "fascio", color="#1f77b4", fontsize=9)
    ax.text(-290, 200, "z (longitudinale)\nentra nel piano", fontsize=8, style="italic")
    ax.set_title("Sistema di riferimento e paziente supino")
    ax.set_aspect("equal"); ax.set_xlim(-330, 470); ax.set_ylim(-300, 310)
    ax.set_xticks([]); ax.set_yticks([])
    fig.tight_layout()
    return fig


def fig_beam_direction():
    """Come alpha (LL) e beta (AP) orientano la direzione del fascio."""
    fig, axes = plt.subplots(1, 2, figsize=(8.2, 3.6))
    # (a) vista assiale x-y: effetto di alpha
    ax = axes[0]
    _ellipse_xy(ax)
    ax.plot(0, 0, "k+", ms=10)
    for ev in (EV_PA, EV_OBL):
        d, _, _ = _beam_axes(ev["alpha"], 0.0)  # solo alpha per la vista assiale
        ax.annotate("", xy=(d[0] * 260, d[1] * 260), xytext=(-d[0] * 260, -d[1] * 260),
                    arrowprops=dict(arrowstyle="->", color=ev["color"], lw=2))
        ax.text(d[0] * 285, d[1] * 285, f"α={ev['alpha']:.0f}°",
                color=ev["color"], fontsize=10, ha="center")
    ax.set_title("(a) Angolo primario α (LL)\nruota nel piano assiale x–y")
    ax.set_aspect("equal"); ax.set_xlim(-330, 330); ax.set_ylim(-330, 330)
    ax.set_xticks([]); ax.set_yticks([])
    # (b) vista sagittale y-z: effetto di beta
    ax = axes[1]
    ax.axhline(0, color="0.7"); ax.axvline(0, color="0.7")
    ax.plot(0, 0, "k+", ms=10)
    for ev in (EV_PA, EV_OBL):
        d, _, _ = _beam_axes(0.0, ev["beta"])
        ax.annotate("", xy=(d[2] * 260, d[1] * 260), xytext=(-d[2] * 260, -d[1] * 260),
                    arrowprops=dict(arrowstyle="->", color=ev["color"], lw=2))
        ax.text(d[2] * 285, d[1] * 285, f"β={ev['beta']:.0f}°",
                color=ev["color"], fontsize=10, ha="center")
    ax.set_title("(b) Angolo secondario β (AP)\ninclina nel piano y–z (CRA/CAU)")
    ax.set_aspect("equal"); ax.set_xlim(-330, 330); ax.set_ylim(-330, 330)
    ax.set_xlabel("z longitudinale"); ax.set_ylabel("y AP")
    ax.set_xticks([]); ax.set_yticks([])
    fig.tight_layout()
    return fig


def _source_axes(alpha, beta, lat=0.0, height=0.0, lon=0.0):
    d, e1, e2 = _beam_axes(alpha, beta)
    q = np.array([-(lat), -(height), -(lon)], dtype=float)  # segni default -1
    source = q - SOD * d
    return source, d, e1, e2


def fig_pyramid():
    """La piramide a 4 lati: apice nel fuoco, base al piano IRP."""
    fig = plt.figure(figsize=(5.6, 4.2))
    ax = fig.add_subplot(111, projection="3d")
    source, d, e1, e2 = _source_axes(20.0, 15.0)
    center = source + DREF * d
    hw, hh = WREF / 2, HREF / 2
    base = [center + hw * e1 + hh * e2, center - hw * e1 + hh * e2,
            center - hw * e1 - hh * e2, center + hw * e1 - hh * e2]
    # spigoli
    for bpt in base:
        ax.plot([source[0], bpt[0]], [source[1], bpt[1]], [source[2], bpt[2]],
                color="#d62728", lw=1.2)
    bx = [p[0] for p in base] + [base[0][0]]
    by = [p[1] for p in base] + [base[0][1]]
    bz = [p[2] for p in base] + [base[0][2]]
    ax.plot(bx, by, bz, color="#d62728", lw=2)
    ax.scatter(*source, color="k", s=50)
    ax.text(source[0], source[1], source[2], "  fuoco (apice)", fontsize=9)
    a3 = _Arrow3D([source[0], center[0]], [source[1], center[1]], [source[2], center[2]],
                  mutation_scale=12, lw=1.6, arrowstyle="-|>", color="#1f77b4")
    ax.add_artist(a3)
    ax.text(center[0], center[1], center[2], "  base @ IRP\n  (w_rif × h_rif)", fontsize=9)
    ax.scatter(0, 0, 0, color="g", marker="+", s=90)
    ax.text(0, 0, 0, " isocentro", fontsize=8)
    ax.set_title("Piramide del fascio:\napice = fuoco, base al piano di riferimento",
                 fontsize=10)
    ax.set_xlabel("x"); ax.set_ylabel("y"); ax.set_zlabel("z")
    ax.view_init(elev=16, azim=-70)
    fig.tight_layout()
    return fig


def fig_inverse_square():
    """La correzione 1/d^2 tra IRP e pelle."""
    fig, ax = plt.subplots(figsize=(6.4, 3.6))
    d = np.linspace(200, 900, 300)
    ax.plot(d, (DREF / d) ** 2, color="#1f77b4", lw=2)
    ax.axvline(DREF, color="0.5", ls="--")
    ax.text(DREF + 8, 1.8, "IRP (d = d_IRP)\nfattore = 1", fontsize=9)
    ax.axhline(1.0, color="0.8", ls=":")
    ax.scatter([DREF], [1.0], color="#d62728", zorder=5)
    ax.fill_between(d, 1, (DREF / d) ** 2, where=(d < DREF), alpha=0.15, color="red")
    ax.fill_between(d, (DREF / d) ** 2, 1, where=(d > DREF), alpha=0.15, color="blue")
    ax.text(320, 2.6, "pelle più vicina\ndel punto di rif. →\ndose > Ka,r", color="darkred", fontsize=8)
    ax.text(700, 0.45, "pelle più lontana →\ndose < Ka,r", color="navy", fontsize=8)
    ax.set_xlabel("distanza fuoco–pelle  d  (mm)")
    ax.set_ylabel("fattore  (d_IRP / d)²")
    ax.set_title("Correzione inverse-square dal punto di riferimento alla pelle",
                 fontsize=11)
    ax.set_ylim(0, 3.2)
    fig.tight_layout()
    return fig


def fig_entrance_exit():
    """Solo la superficie di ENTRATA viene conteggiata (N·d < 0)."""
    fig, ax = plt.subplots(figsize=(4.6, 3.9))
    _ellipse_xy(ax)
    d, _, _ = _beam_axes(0.0, 0.0)  # fascio verso +y
    th = np.linspace(-math.pi, math.pi, 220)
    X = A * np.cos(th); Y = B * np.sin(th)
    nx = np.cos(th) / A; ny = np.sin(th) / B
    nn = np.hypot(nx, ny); nx /= nn; ny /= nn
    dotND = nx * d[0] + ny * d[1]
    entra = dotND < 0
    ax.scatter(X[entra], Y[entra], c="#2ca02c", s=14, label="entrata (N·d<0) → conteggiata")
    ax.scatter(X[~entra], Y[~entra], c="0.6", s=10, label="uscita (N·d≥0) → scartata")
    ax.annotate("", xy=(0, 40), xytext=(0, -230),
                arrowprops=dict(arrowstyle="->", color="#1f77b4", lw=2))
    ax.text(-315, -240, "fascio", color="#1f77b4", fontsize=9)
    ax.set_title("Superficie di entrata vs uscita")
    ax.set_aspect("equal"); ax.set_xlim(-330, 330); ax.set_ylim(-300, 300)
    ax.set_xticks([]); ax.set_yticks([])
    ax.legend(loc="upper center", fontsize=8, bbox_to_anchor=(0.5, -0.02), ncol=1)
    fig.tight_layout()
    return fig


def fig_unwrap():
    """Corrispondenza mappa planare (θ,z) ↔ superficie 3D."""
    fig = plt.figure(figsize=(8.2, 3.5))
    # dose sintetica: due macchie
    th = np.linspace(-math.pi, math.pi, 180)
    zz = np.linspace(-L / 2, L / 2, 120)
    TH, ZZ = np.meshgrid(th, zz)
    dose = (np.exp(-(((TH + 1.3) / 0.5) ** 2 + ((ZZ + 60) / 90) ** 2))
            + 0.7 * np.exp(-(((TH - 1.8) / 0.4) ** 2 + ((ZZ - 40) / 70) ** 2)))
    ax1 = fig.add_subplot(1, 2, 1)
    im = ax1.pcolormesh(np.degrees(th), zz, dose, shading="auto", cmap="inferno")
    ax1.set_title("Mappa planare (cilindro srotolato)")
    ax1.set_xlabel("θ angolo circonferenziale (°)")
    ax1.set_ylabel("z longitudinale (mm)")
    fig.colorbar(im, ax=ax1, label="dose (a.u.)")
    ax2 = fig.add_subplot(1, 2, 2, projection="3d")
    X = A * np.cos(TH); Y = B * np.sin(TH); Z = ZZ
    norm = (dose - dose.min()) / (dose.max() - dose.min() + 1e-9)
    ax2.plot_surface(X, Y, Z, facecolors=plt.cm.inferno(norm),
                     linewidth=0, antialiased=False, shade=False)
    ax2.set_title("Stessa dose sull'ellissoide 3D")
    ax2.set_xlabel("x"); ax2.set_ylabel("y"); ax2.set_zlabel("z")
    ax2.view_init(elev=18, azim=-60)
    fig.tight_layout()
    return fig


def fig_table_motion():
    """Il movimento del lettino trasla la geometria del fascio."""
    fig, ax = plt.subplots(figsize=(4.8, 4.2))
    _ellipse_xy(ax)
    ax.plot(0, 0, "k+", ms=10); ax.text(10, 10, "isocentro", fontsize=8)
    sy = -250.0  # y della sorgente (dentro i limiti, per chiarezza schematica)
    # fascio senza spostamento: sorgente sotto l'isocentro, punta all'isocentro
    ax.scatter(0, sy, color="#1f77b4", s=50, zorder=5)
    ax.annotate("", xy=(0, -B), xytext=(0, sy),
                arrowprops=dict(arrowstyle="->", color="#1f77b4", lw=1.6))
    ax.text(-20, sy, "lettino\na riposo", color="#1f77b4", fontsize=8,
            ha="right", va="center")
    # fascio con lettino spostato: sorgente e target traslati di +90 mm in x
    dx = 90.0
    ax.scatter(dx, sy, color="#d62728", s=50, zorder=5)
    ax.annotate("", xy=(dx, -B + 6), xytext=(dx, sy),
                arrowprops=dict(arrowstyle="->", color="#d62728", lw=1.6))
    ax.text(dx + 20, sy, "lettino spostato\n(lat +90 mm)", color="#d62728",
            fontsize=8, ha="left", va="center")
    ax.set_title("Il movimento del lettino sposta il fascio\nrispetto al paziente",
                 fontsize=10)
    ax.set_aspect("equal"); ax.set_xlim(-320, 340); ax.set_ylim(-300, 240)
    ax.set_xticks([]); ax.set_yticks([])
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
def fig_beam_coordinates():
    """Le coordinate (t, u, v) di un punto nel riferimento del fascio.

    Vista nel piano (d, e1): mostra come V = P - sorgente si scompone in
    profondita' t (lungo d) e scarto trasversale u (lungo e1), e come il cono
    si allarga linearmente con t. Etichette posizionate per non sovrapporsi.
    """
    fig, ax = plt.subplots(figsize=(6.8, 3.4))
    src = np.array([0.0, 0.0])
    dref = 5.7          # profondita' del piano IRP (unita' arbitrarie)
    half_at_ref = 1.05  # semi-apertura al piano IRP (piu' piatta per lasciare spazio)
    tmax = 9.0

    # cono (due bordi) dal fuoco che si allarga
    slope = half_at_ref / dref
    ax.plot([0, tmax], [0, slope * tmax], color="#d62728", lw=2, zorder=2)
    ax.plot([0, tmax], [0, -slope * tmax], color="#d62728", lw=2, zorder=2)
    ax.fill_between([0, tmax], [0, -slope * tmax], [0, slope * tmax],
                    color="#d62728", alpha=0.07, zorder=1)

    # asse d (profondita')
    ax.annotate("", xy=(tmax + 0.4, 0), xytext=(-0.3, 0),
                arrowprops=dict(arrowstyle="->", color="k", lw=1.3), zorder=3)
    ax.text(tmax + 0.55, 0, r"$\mathbf{d}$ (profondità)", va="center", fontsize=11)

    # piano di riferimento IRP (barra blu)
    ax.plot([dref, dref], [-half_at_ref, half_at_ref], color="#1f77b4", lw=2.2, zorder=4)
    ax.annotate("", xy=(dref, half_at_ref), xytext=(dref, -half_at_ref),
                arrowprops=dict(arrowstyle="<->", color="#1f77b4", lw=1.1), zorder=4)
    # etichetta piano IRP: in alto a sinistra della barra, ben staccata
    ax.text(dref - 0.25, half_at_ref + 0.30, "piano IRP\n(base piramide)",
            color="#1f77b4", ha="right", va="bottom", fontsize=9)
    # etichetta w_rif: a sinistra della barra blu, a mezza altezza
    ax.text(dref - 0.22, 0.45, r"$w_{rif}$", color="#1f77b4", fontsize=11,
            va="center", ha="right")

    # fuoco
    ax.scatter(*src, color="k", s=55, zorder=6)
    ax.text(-0.35, 0.30, "sorgente\n(fuoco)", ha="center", va="bottom", fontsize=9)

    # punto P generico e sue proiezioni
    tP, uP = 7.6, 0.62
    ax.scatter([tP], [uP], color="#2ca02c", s=60, zorder=6)
    ax.text(tP + 0.55, uP + 0.55, "P\n(punto di pelle)", color="#2ca02c",
            ha="center", fontsize=9)
    # linea tratteggiata verticale da P all'asse
    ax.plot([tP, tP], [0, uP], color="0.5", ls=":", zorder=3)

    # semi-apertura del cono alla profondita' di P (tratteggio rosso)
    half_tP = slope * tP
    ax.plot([tP, tP], [-half_tP, half_tP], color="#d62728", ls="--", lw=1, zorder=2)
    ax.text(tP + 0.15, -half_tP - 0.10, r"$0.5\,w_{rif}\,t/d_{IRP}$",
            color="#d62728", ha="left", va="top", fontsize=9)

    # quota t sotto l'asse
    ax.annotate("", xy=(tP, -1.35), xytext=(0, -1.35),
                arrowprops=dict(arrowstyle="<->", color="0.35", lw=1.1), zorder=3)
    ax.text(tP / 2, -1.62, r"$t = \mathbf{V}\cdot\mathbf{d}$", color="0.2",
            ha="center", va="top", fontsize=11)

    # scarto u (verticale, a destra)
    ax.annotate("", xy=(tP, uP), xytext=(tP, 0),
                arrowprops=dict(arrowstyle="<->", color="#2ca02c", lw=1.4), zorder=5)
    ax.text(tP - 0.18, uP / 2, r"$u = \mathbf{V}\cdot\mathbf{e}_1$",
            color="#2ca02c", fontsize=10, va="center", ha="right")

    ax.set_title("Coordinate del punto nel riferimento del fascio (piano d–e₁)",
                 fontsize=11)
    ax.set_xlim(-1.8, tmax + 4.0)
    ax.set_ylim(-2.4, 2.4)
    ax.set_aspect("equal")
    ax.axis("off")
    fig.tight_layout()
    return fig


def fig_inside_test():
    """Sezione trasversale del fascio a profondita' t: il rettangolo w×h e
    quali punti stanno dentro/fuori (coordinate u, v)."""
    fig, ax = plt.subplots(figsize=(5.2, 4.2))
    hw, hh = 1.0, 0.75  # semi-larghezza/semi-altezza alla profondita' t
    from matplotlib.patches import Rectangle
    ax.add_patch(Rectangle((-hw, -hh), 2 * hw, 2 * hh, fill=True,
                           facecolor="#d62728", alpha=0.12, edgecolor="#d62728", lw=2))
    ax.axhline(0, color="0.8", lw=0.8); ax.axvline(0, color="0.8", lw=0.8)
    # punti dentro/fuori
    rng = np.random.default_rng(3)
    pts = rng.uniform(-1.6, 1.6, size=(40, 2))
    inside = (np.abs(pts[:, 0]) <= hw) & (np.abs(pts[:, 1]) <= hh)
    ax.scatter(pts[inside, 0], pts[inside, 1], color="#2ca02c", s=45, label="dentro il campo")
    ax.scatter(pts[~inside, 0], pts[~inside, 1], color="0.6", s=30, marker="x", label="fuori dal campo")
    # quote
    ax.annotate("", xy=(hw, -hh - 0.18), xytext=(-hw, -hh - 0.18),
                arrowprops=dict(arrowstyle="<->", color="#d62728", lw=1.1))
    ax.text(0, -hh - 0.34, "$w_{rif}\\,t/d_{IRP}$", color="#d62728", ha="center", fontsize=10)
    ax.annotate("", xy=(hw + 0.18, hh), xytext=(hw + 0.18, -hh),
                arrowprops=dict(arrowstyle="<->", color="#d62728", lw=1.1))
    ax.text(hw + 0.3, 0, "$h_{rif}\\,t/d_{IRP}$", color="#d62728", va="center", fontsize=10, rotation=90)
    ax.set_xlabel("$u$  (asse $\\mathbf{e}_1$, larghezza)")
    ax.set_ylabel("$v$  (asse $\\mathbf{e}_2$, altezza)")
    ax.set_title("Sezione del fascio a profondità t:\n"
                 "un punto è nel campo se |u| e |v|\nstanno nel rettangolo",
                 fontsize=10)
    ax.set_xlim(-1.9, 2.1); ax.set_ylim(-1.7, 1.6)
    ax.set_aspect("equal")
    ax.legend(loc="upper left", fontsize=8)
    fig.tight_layout()
    return fig


def fig_surface_normal():
    """Definizione della normale esterna N e del prodotto N·d (entrata vs uscita)."""
    fig, ax = plt.subplots(figsize=(4.8, 4.2))
    _ellipse_xy(ax)
    d, _, _ = _beam_axes(0.0, 0.0)  # fascio verso +y
    # scegli due punti: uno di entrata (in basso) e uno di uscita (in alto)
    for th, tag in [(-math.pi / 2, "entrata"), (math.pi / 2, "uscita")]:
        X = A * math.cos(th); Y = B * math.sin(th)
        nx = math.cos(th) / A; ny = math.sin(th) / B
        nn = math.hypot(nx, ny); nx /= nn; ny /= nn
        col = "#2ca02c" if tag == "entrata" else "0.55"
        ax.scatter([X], [Y], color=col, s=55, zorder=5)
        ax.annotate("", xy=(X + nx * 90, Y + ny * 90), xytext=(X, Y),
                    arrowprops=dict(arrowstyle="->", color=col, lw=2))
        dot = nx * d[0] + ny * d[1]
        ax.text(X + nx * 100, Y + ny * 100,
                f"$\\mathbf{{N}}$\n$\\mathbf{{N}}\\cdot\\mathbf{{d}}={dot:+.1f}$",
                color=col, ha="center", fontsize=9)
        ax.text(X - 60 if tag == "entrata" else X + 60, Y,
                tag, color=col, ha="right" if tag == "entrata" else "left",
                va="center", fontsize=9)
    ax.annotate("", xy=(0, 30), xytext=(0, -210),
                arrowprops=dict(arrowstyle="->", color="#1f77b4", lw=2))
    ax.text(150, -170, "$\\mathbf{d}$ (fascio)", color="#1f77b4", fontsize=10, ha="center")
    ax.set_title("Normale esterna $\\mathbf{N}$ e prodotto $\\mathbf{N}\\cdot\\mathbf{d}$", fontsize=10)
    ax.set_aspect("equal"); ax.set_xlim(-360, 360); ax.set_ylim(-300, 320)
    ax.set_xticks([]); ax.set_yticks([])
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Figure sulle DISTANZE della correzione inverse-square, con la geometria
# ANCORATA ALLA SCHIENA sul piano del tavolo (default "back_on_table").
# Mostrano SOD, d_ref e t, e perche' aumentare lo spessore del paziente non
# avvicina piu' la schiena alla sorgente.
# ---------------------------------------------------------------------------
def fig_distances_anchored():
    """Distanze sorgente→IRP→pelle con la schiena appoggiata sul tavolo.

    Proiezione frontale standard (0°/0°): tubo SOTTO il paziente supino, fascio
    verso l'alto (+y). Mostra sorgente, IRP, isocentro, piano del lettino e il
    paziente (sezione ellittica) a DIMENSIONI UMANE leggibili.

    Per rendere il paziente visibile nonostante la grande distanza fuoco-isocentro
    (~720 mm) rispetto allo spessore del corpo (~240 mm), l'asse verticale ha una
    INTERRUZIONE DI SCALA (axis break): il tratto fuoco→vicino-al-corpo, privo di
    dettaglio, è compresso; il tratto del paziente è in scala reale. I valori
    numerici nelle etichette restano quelli veri.
    """
    from matplotlib.patches import Rectangle, Ellipse
    offset_irp = 150.0
    y_irp = SOD - offset_irp      # d_ref dal fuoco (570 mm)
    y_iso = SOD                   # isocentro (720 mm)
    ap = 2 * B                    # spessore AP (240 mm)
    width = 2 * A                 # larghezza laterale (360 mm)
    y_table = y_irp - 70.0        # piano del lettino (500 mm dal fuoco)
    y_back = y_table              # schiena = piano tavolo
    y_center = y_back + ap / 2.0  # centro ellisse spostato di +AP/2
    y_front = y_back + ap         # torace anteriore
    t_back = y_back               # distanza fuoco→schiena

    # Due pannelli con interruzione di scala condivisa: in basso la zona fuoco
    # (compressa), in alto la zona paziente in scala reale. Altezze relative
    # scelte per dare al corpo un aspetto "umano" ben proporzionato.
    fig, (ax_top, ax_bot) = plt.subplots(
        2, 1, figsize=(6.6, 7.4), sharex=True,
        gridspec_kw=dict(height_ratios=[3.0, 1.0], hspace=0.06),
    )
    # Margini espliciti: lasciano spazio sopra per il titolo e sotto per il
    # riquadro esplicativo, ed evitano che le etichette ai bordi vengano tagliate.
    fig.subplots_adjust(left=0.06, right=0.97, top=0.90, bottom=0.17)
    # finestre verticali (mm)
    bot_lo, bot_hi = -30.0, 180.0                  # zona fuoco (compressa)
    top_lo, top_hi = y_table - 60.0, y_iso + 260.0 # zona paziente (scala reale)

    for ax in (ax_top, ax_bot):
        ax.set_xlim(-300, 360)
        ax.axvline(0, color="#ffe08a", lw=14, alpha=0.5, zorder=0)  # fascio schematico
        ax.set_xticks([])

    # --- pannello superiore: paziente, tavolo, IRP, isocentro (scala reale) ---
    ax_top.set_ylim(top_lo, top_hi)
    ax_top.add_patch(Rectangle((-200, y_table - 22), 400, 18,
                               color="#9aa0a6", alpha=0.9, zorder=2))
    ax_top.text(210, y_table - 13, "piano del lettino", va="center",
                fontsize=9, color="#5f6368")
    ax_top.add_patch(Ellipse((0, y_center), width=width, height=ap,
                             facecolor="#ffd9c0", edgecolor="#d98b5f", lw=2,
                             alpha=0.9, zorder=3))
    ax_top.text(A + 15, y_center, "paziente\n(sezione\nellittica)", va="center",
                fontsize=9, color="#b5651d")
    ax_top.plot([0], [y_back], "o", color="#c1121f", ms=11, zorder=5)
    ax_top.annotate("pelle d'ingresso (schiena)\n= punto di dose massima",
                    (0, y_back), xytext=(-250, y_back + ap * 0.9), fontsize=9,
                    color="#c1121f", arrowprops=dict(arrowstyle="->", color="#c1121f"))
    ax_top.plot([0], [y_irp], "s", color="#2a9d8f", ms=9, zorder=6)
    ax_top.text(18, y_irp, "IRP — qui è dichiarato Ka,r", va="center",
                fontsize=9, color="#2a9d8f")
    ax_top.plot([0], [y_iso], "s", color="#3a0ca3", ms=9, zorder=6)
    ax_top.text(18, y_iso, "isocentro", va="center", fontsize=9, color="#3a0ca3")

    # --- pannello inferiore: la sorgente (zona compressa) ---
    ax_bot.set_ylim(bot_lo, bot_hi)
    ax_bot.plot([0], [0], "*", color="#1d3557", ms=22, zorder=6)
    ax_bot.text(18, 0, "sorgente (fuoco)", va="center", fontsize=9, color="#1d3557")

    # --- segni di rottura scala tra i due pannelli ---
    d = 0.012
    kw = dict(transform=ax_top.transAxes, color="k", clip_on=False, lw=1)
    ax_top.plot((-d, +d), (-d, +d), **kw); ax_top.plot((1 - d, 1 + d), (-d, +d), **kw)
    kw = dict(transform=ax_bot.transAxes, color="k", clip_on=False, lw=1)
    ax_bot.plot((-d, +d), (1 - 3 * d, 1 + 3 * d), **kw)
    ax_bot.plot((1 - d, 1 + d), (1 - 3 * d, 1 + 3 * d), **kw)

    # --- quote delle distanze (etichette coi valori reali) ---
    # Le quote principali stanno nel pannello superiore (dove c'è il corpo);
    # indichiamo che partono dal fuoco con una freccia verso il basso + testo.
    # Frecce-quota (solo linee): indicano visivamente le tre distanze, tutte
    # misurate dal fuoco. I valori numerici sono riportati nel riquadro-legenda
    # qui sotto, cosi' le etichette non si accavallano ne' vengono tagliate.
    def dist_arrow(x, y2, color, y1=None):
        y1 = top_lo + 4 if y1 is None else y1
        ax_top.annotate("", xy=(x, y2), xytext=(x, y1),
                        arrowprops=dict(arrowstyle="-|>", color=color, lw=2))

    dist_arrow(-200, y_iso, "#3a0ca3")   # SOD
    dist_arrow(-150, y_irp, "#2a9d8f")   # d_ref
    dist_arrow(-100, y_back, "#c1121f")  # t

    # legenda delle distanze (valori reali): proxy-handle colorati, riquadro
    # ancorato in alto a sinistra del pannello, dove c'e' spazio libero.
    from matplotlib.lines import Line2D
    handles = [
        Line2D([0], [0], color="#3a0ca3", lw=2.5,
               label=f"SOD = {SOD:.0f} mm (dal fuoco)"),
        Line2D([0], [0], color="#2a9d8f", lw=2.5,
               label=f"d_ref = SOD − {offset_irp:.0f} = {y_irp:.0f} mm"),
        Line2D([0], [0], color="#c1121f", lw=2.5,
               label=f"t (fuoco→schiena) = {t_back:.0f} mm"),
    ]
    ax_top.legend(handles=handles, loc="upper left", fontsize=8.5,
                  framealpha=0.92, borderpad=0.6,
                  title="Distanze (dal fuoco)", title_fontsize=9)

    # formula della correzione: in alto a destra, sotto il titolo, cosi' non
    # si sovrappone alla legenda delle distanze (in alto a sinistra).
    ax_top.text(0.98, 0.985,
                r"$D = K_{a,r}\left(\dfrac{d_{ref}}{t}\right)^{2}BSF\cdot MEAC\cdot TAF\cdot CF$",
                transform=ax_top.transAxes, ha="right", va="top", fontsize=10.5,
                bbox=dict(boxstyle="round,pad=0.35", fc="#f1f3f4", ec="#bbb"))

    # riquadro esplicativo: come testo della figura nel margine inferiore riservato
    fig.text(0.5, 0.015,
             "Ancoraggio SCHIENA sul tavolo: la schiena poggia sul piano del lettino;\n"
             "aumentare lo spessore AP alza il TORACE, non la schiena → t invariata\n"
             "→ la PSD non cresce artificialmente con la taglia del paziente.",
             ha="center", va="bottom", fontsize=8,
             bbox=dict(boxstyle="round,pad=0.35", fc="#eef7f5", ec="#89c2bb"))

    for ax in (ax_top, ax_bot):
        ax.set_yticks([])
        for s in ("top", "right", "left"):
            ax.spines[s].set_visible(False)
    ax_top.spines["bottom"].set_visible(False)
    ax_bot.spines["bottom"].set_visible(False)
    ax_top.set_title("Distanze della correzione inverse-square\n"
                     "(schiena ancorata al tavolo; asse verticale con rottura di scala)",
                     fontsize=11.5, pad=10)
    return fig


def fig_anchor_comparison():
    """Confronto ancoraggio CENTRO-isocentro vs SCHIENA-tavolo al variare dell'AP.

    Mostra due pazienti (AP sottile e spesso) con i due ancoraggi, evidenziando
    come cambia (o non cambia) la distanza fuoco→schiena e quindi la dose.
    """
    from matplotlib.patches import Ellipse
    fig, (axL, axR) = plt.subplots(1, 2, figsize=(9.2, 5.6), sharey=True)
    y_src = -SOD                 # sorgente sotto (schema con isocentro a y=0)
    ap_small, ap_big = 200.0, 360.0

    def panel(ax, title, mode):
        ax.set_title(title, fontsize=10.5)
        ax.plot(0, y_src, marker="*", color="#1d3557", ms=18, zorder=6)
        ax.text(20, y_src, "sorgente", va="center", fontsize=8, color="#1d3557")
        ax.plot(0, 0, "k+", ms=11, zorder=6)
        ax.text(14, 10, "isocentro", fontsize=8)
        ax.axhline(0, color="0.85", ls=":", lw=0.8)
        # scostamento verticale delle etichette per evitare sovrapposizioni
        # (in modalita' "back" le due schiene coincidono sul piano del tavolo)
        label_dy = {"center": {ap_small: 0.0, ap_big: 0.0},
                    "back": {ap_small: 30.0, ap_big: -30.0}}[mode]
        for ap, col, lab in [(ap_small, "#1f77b4", "AP sottile"),
                             (ap_big, "#ff7f0e", "AP spesso")]:
            if mode == "center":
                y_center = 0.0
            else:  # back on a fixed table plane
                y_table = -140.0
                y_center = y_table + ap / 2.0
                if ap == ap_small:
                    ax.axhline(y_table, color="#2ca02c", lw=2.5, zorder=1)
                    ax.text(A + 10, y_table - 16, "piano\ndel lettino",
                            color="#2ca02c", fontsize=8, ha="left", va="top")
            ax.add_patch(Ellipse((0, y_center), 2 * A, ap, facecolor=col, alpha=0.28,
                                 edgecolor=col, lw=1.6, zorder=3))
            y_back = y_center - ap / 2.0
            t_back = y_back - y_src
            ax.plot([0], [y_back], "v", color=col, ms=9, zorder=5)
            ax.annotate("", xy=(0, y_back), xytext=(0, y_src),
                        arrowprops=dict(arrowstyle="->", color=col, lw=1.2, alpha=0.7))
            ax.text(-A - 20, y_back + label_dy[ap], f"{lab}\nt≈{t_back:.0f}", color=col,
                    fontsize=8, ha="right", va="center")
        ax.set_aspect("equal")
        ax.set_xlim(-A - 175, A + 95)
        ax.set_xticks([])

    panel(axL, "CENTRO sull'isocentro (legacy):\nAP spesso → schiena più vicina → dose ↑", "center")
    panel(axR, "SCHIENA sul tavolo (default):\nAP spesso cresce verso l'alto → t invariata", "back")
    axL.set_ylim(y_src - 50, 280)
    axL.set_ylabel("y verticale (mm) — sorgente in basso")
    fig.suptitle("Perché la taglia del paziente non deve gonfiare la PSD",
                 fontsize=12, y=0.995)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    return fig
