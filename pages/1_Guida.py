"""Guida al PSD Mapper.

Carica e mostra la guida HTML autonoma preparata a parte
(``Guida_PSD_Mapper_v3.html``), che contiene già testo, formule MathML native,
figure (SVG/raster incorporate in base64), CSS e indice. È completamente offline:
tutte le risorse sono inline nel file, quindi non servono rete né asset esterni.
"""
from __future__ import annotations
import os
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(page_title="HELP PSD Mapper", layout="wide")

# La guida HTML sta accanto a app.py (un livello sopra pages/).
_APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_GUIDE_HTML = os.path.join(_APP_DIR, "Guida_PSD_Mapper_v3.html")


def _load_guide_html(path: str) -> str | None:
    """Legge la guida HTML; ritorna None se il file non esiste/non è leggibile."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None


html = _load_guide_html(_GUIDE_HTML)

if html is None:
    st.title("Guida al PSD Mapper")
    st.error(
        "File della guida non trovato: **Guida_PSD_Mapper_v3.html**.\n\n"
        "Deve trovarsi nella cartella dell'app "
        f"(`{_APP_DIR}`). Copialo lì e ricarica la pagina."
    )
    st.stop()

# La guida HTML porta il proprio layout, CSS, indice e figure: la mostriamo
# a tutta larghezza/altezza con scroll interno via components.html, così
# conserva esattamente l'aspetto previsto dall'autore.
components.html(html, height=1400, scrolling=True)

st.caption(
    "La guida è un documento HTML autonomo (offline) incorporato in questa pagina. "
    "Per aprirla a schermo intero o stamparla, apri direttamente il file "
    "`Guida_PSD_Mapper_v3.html` nel browser."
)
