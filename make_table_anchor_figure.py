"""
Figura: dove sta il lettino? Confronto tra l'ancoraggio ATTUALE (centro del
paziente sull'isocentro) e un ancoraggio alternativo (schiena del paziente sul
piano del lettino). Mostra perche' nel modello attuale un paziente piu' spesso
avvicina la schiena alla sorgente (t diminuisce), mentre fisicamente la schiena
resta appoggiata sul lettino.

Uso: python make_table_anchor_figure.py  -> table_anchor_explained.png
"""
from __future__ import annotations
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Ellipse

SOD = 720.0  # sorgente -> isocentro (mm). Sorgente sotto l'isocentro (PA da sotto).
AP_SMALL = 200.0
AP_LARGE = 320.0
WIDTH = 360.0

# posizione sorgente nel piano y (verticale): sotto l'isocentro
SRC_Y = -SOD

fig, (axL, axR) = plt.subplots(1, 2, figsize=(13, 7), sharey=True)

def draw_common(ax, title):
    ax.set_title(title, fontsize=11)
    # sorgente
    ax.plot(0, SRC_Y, marker="o", color="#d62728", ms=10)
    ax.annotate("sorgente\n(fuoco raggi X)", (0, SRC_Y), textcoords="offset points",
                xytext=(10, -4), fontsize=8, color="#d62728")
    # isocentro
    ax.plot(0, 0, "k+", ms=12)
    ax.annotate("isocentro", (0, 0), textcoords="offset points", xytext=(8, 6), fontsize=8)
    ax.axhline(0, color="0.8", lw=0.8, ls=":")
    ax.set_xlim(-320, 320)
    ax.set_xlabel("x laterale (mm)")

def draw_patient(ax, ap, color, label, y_center):
    # ellisse sezione: semiasse x = WIDTH/2, semiasse y = ap/2
    e = Ellipse((0, y_center), WIDTH, ap, facecolor=color, alpha=0.35,
                edgecolor=color, lw=1.8, zorder=3)
    ax.add_patch(e)
    y_back = y_center - ap / 2.0   # schiena (verso la sorgente, sotto)
    y_front = y_center + ap / 2.0  # torace anteriore (sopra)
    # distanza sorgente -> schiena
    t_back = y_back - SRC_Y
    ax.plot([0, 0], [SRC_Y, y_back], color=color, lw=1.3, ls="--", zorder=2)
    ax.plot(0, y_back, marker="v", color=color, ms=8, zorder=4)
    ax.annotate(f"{label}\nschiena a t = {t_back:.0f} mm", (0, y_back),
                textcoords="offset points", xytext=(-150, -6), fontsize=8, color=color)
    return y_back, y_front

# ---- Pannello sinistro: ancoraggio ATTUALE (centro sull'isocentro) ----
draw_common(axL, "ATTUALE: centro paziente = isocentro\n→ paziente più spesso avvicina la schiena alla sorgente")
draw_patient(axL, AP_SMALL, "#1f77b4", "AP piccolo", y_center=0.0)
draw_patient(axL, AP_LARGE, "#ff7f0e", "AP grande", y_center=0.0)
axL.text(0, 60, "entrambi centrati\nsull'isocentro", ha="center", fontsize=8, style="italic", color="0.4")
# nessun lettino disegnato: non esiste nel modello
axL.text(-310, SRC_Y + 120, "NESSUN lettino\nnella geometria\n(solo attenuazione, opz.)",
         fontsize=8, color="0.5", style="italic")

# ---- Pannello destro: ancoraggio ALTERNATIVO (schiena sul lettino) ----
draw_common(axR, "ALTERNATIVO: schiena sul piano del lettino\n→ la schiena resta a distanza ~costante dalla sorgente")
# piano del lettino a quota fissa (es. schiena del paziente medio)
TABLE_Y = -AP_SMALL / 2.0  # scegliamo il piano dove sta la schiena del paziente piccolo
axR.axhline(TABLE_Y, color="#2ca02c", lw=3, zorder=1)
axR.text(-300, TABLE_Y - 28, "piano del lettino (quota fissa)", color="#2ca02c", fontsize=8)
# paziente piccolo: schiena sul lettino -> centro = TABLE_Y + ap/2
draw_patient(axR, AP_SMALL, "#1f77b4", "AP piccolo", y_center=TABLE_Y + AP_SMALL / 2.0)
# paziente grande: schiena sul lettino -> cresce verso l'alto (anteriore)
draw_patient(axR, AP_LARGE, "#ff7f0e", "AP grande", y_center=TABLE_Y + AP_LARGE / 2.0)
axR.text(150, TABLE_Y + 90, "più spesso = cresce\nverso l'ALTO (torace),\nla schiena non si muove",
         ha="center", fontsize=8, style="italic", color="0.4")

for ax in (axL, axR):
    ax.set_aspect("equal")
    ax.set_ylim(SRC_Y - 40, 260)
axL.set_ylabel("y verticale / AP (mm) — sorgente in basso")

fig.suptitle("Dove sta il lettino? Ancoraggio del paziente e distanza sorgente→schiena (t)",
             fontsize=13, y=0.98)
fig.tight_layout(rect=(0, 0, 1, 0.95))
out = "table_anchor_explained.png"
fig.savefig(out, dpi=140)
print("Salvato:", out)
