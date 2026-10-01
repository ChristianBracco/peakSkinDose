from __future__ import annotations
import io
import html
import re
from datetime import datetime
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components


def render_plotly(fig, height: int = 700):
    """Render a Plotly figure reliably, including 3D/WebGL scenes.

    st.plotly_chart can silently fail to draw 3D figures in some
    Streamlit/browser combinations. Embedding the self-contained Plotly HTML
    via components.html forces plotly.js to load and draw the scene.
    """
    html = fig.to_html(include_plotlyjs="cdn", full_html=True, default_height=f"{height}px")
    components.html(html, height=height + 20, scrolling=False)


def _fmt(v):
    """Display helper: show an em-dash for missing/empty values."""
    if v is None or (isinstance(v, str) and not v.strip()):
        return "\u2014"
    return str(v)


def build_html_report(patient: dict, size: dict, dose: dict,
                      corr_summary: dict, contrib: "pd.DataFrame") -> str:
    """Build a complete, self-contained HTML exam report as a string.

    Pure function: depends only on the standard library (``html``,
    ``datetime``) plus the ``to_html`` method of the supplied ``contrib``
    DataFrame. No Streamlit, no new dependency. All patient-derived text is
    passed through ``html.escape`` to avoid broken/injected markup, and any
    ``None`` value is rendered as an em-dash ('\u2014').

    This report is a research/commissioning prototype artefact and carries a
    non-clinical disclaimer; it must NOT be used for clinical decisions.
    """
    DASH = "\u2014"

    def esc(v):
        """Escape a (possibly None) value for HTML text, None -> em-dash."""
        if v is None or (isinstance(v, str) and not v.strip()):
            return DASH
        return html.escape(str(v))

    def num(v, fmt="{:.2f}", suffix=""):
        """Format a numeric value, None -> em-dash. Non-numeric -> escaped str."""
        if v is None:
            return DASH
        try:
            return html.escape(fmt.format(float(v))) + suffix
        except (TypeError, ValueError):
            return esc(v)

    patient = patient or {}
    size = size or {}
    dose = dose or {}
    corr_summary = corr_summary or {}

    generated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # (6) contrib table (first 100 rows) as HTML.
    try:
        table_html = contrib.head(100).to_html(index=False, border=0)
    except Exception:
        table_html = "<p>Nessun evento disponibile.</p>"

    # (3) Patient size block.
    size_rows = [
        ("Modalità taglia", esc(size.get("mode"))),
        ("Width laterale (mm)", num(size.get("width_mm"), "{:.0f}")),
        ("AP (mm)", num(size.get("ap_mm"), "{:.0f}")),
        ("Lunghezza mappata (mm)", num(size.get("length_mm"), "{:.0f}")),
    ]
    size_note = ""
    if size.get("mode") == "Da peso + altezza":
        size_rows += [
            ("Peso (kg)", num(size.get("weight_kg"), "{:.1f}")),
            ("Altezza (cm)", num(size.get("height_cm"), "{:.1f}")),
            ("BMI", num(size.get("bmi"), "{:.1f}")),
        ]
        size_note = (
            "<p class='note'>La stima antropometrica di width/AP è "
            "approssimata e <strong>non clinica</strong>.</p>"
        )

    def kv_table(rows):
        body = "".join(
            f"<tr><th>{html.escape(k)}</th><td>{v}</td></tr>" for k, v in rows
        )
        return f"<table class='kv'>{body}</table>"

    patient_rows = [
        ("Paziente", esc(patient.get("patient"))),
        ("Sesso", esc(patient.get("sex"))),
        ("Data di nascita", esc(patient.get("birthdate"))),
        ("Esame", esc(patient.get("exam"))),
        ("Data esame", esc(patient.get("exam_date"))),
    ]

    # (4) Dose results.
    dose_rows = [
        ("PSD (Gy)", num(dose.get("psd_gy"))),
    ]
    if dose.get("kind") == "cylinder":
        dose_rows += [
            ("Angolo circonferenziale (°)", num(dose.get("theta_deg"), "{:.1f}")),
            ("Posizione longitudinale (mm)", num(dose.get("z_mm"), "{:.0f}")),
        ]
    dose_rows += [
        ("Eventi utilizzati", num(dose.get("used"), "{:.0f}")),
        ("Ka,r totale (Gy)", num(dose.get("sum_kar_gy"), "{:.3f}")),
        ("DAP totale (Gy·cm²)", num(dose.get("sum_dap_gy_cm2"), "{:.1f}")),
    ]

    # (5) Correction model.
    if corr_summary.get("use_spectral"):
        corr_model = "BSF/MEAC spettrali (Benmakhlouf 2011)"
    else:
        corr_model = "Costanti"
    corr_rows = [
        ("Modello correzione", esc(corr_model)),
    ]
    if corr_summary.get("use_spectral"):
        corr_rows.append(("kVp sorgente", esc(corr_summary.get("kvp_source"))))
    else:
        corr_rows += [
            ("BSF (costante)", num(corr_summary.get("bsf"), "{:.2f}")),
            ("MEAC (costante)", num(corr_summary.get("meac"), "{:.2f}")),
        ]
    corr_rows += [
        ("Attenuazione tavolo", esc(corr_summary.get("table_mode"))),
        ("Offset punto di riferimento (mm)", num(corr_summary.get("ref_offset_mm"), "{:.0f}")),
        ("SOD sorgente", esc(corr_summary.get("sod_source"))),
    ]
    if corr_summary.get("table_mode") == "measured":
        corr_rows.append(("Trasmissione tavolo", num(corr_summary.get("table_transmission"), "{:.3f}")))
    _anchor_mode = corr_summary.get("anchor_mode")
    if _anchor_mode is not None:
        _anchor_it = ("Schiena sul piano del tavolo" if _anchor_mode == "back_on_table"
                      else "Centro sull'isocentro (legacy)")
        corr_rows.append(("Ancoraggio paziente", esc(_anchor_it)))
        if _anchor_mode == "back_on_table":
            corr_rows.append(("Spessore materasso/pad (mm)",
                              num(corr_summary.get("pad_mm"), "{:.0f}")))

    return (
        "<!DOCTYPE html>\n"
        "<html lang='it'>\n<head>\n<meta charset='utf-8'>\n"
        "<title>Report esame PSD</title>\n"
        "<style>"
        "body{font-family:Arial,Helvetica,sans-serif;margin:2em;color:#222;}"
        "h1{font-size:1.6em;}h2{font-size:1.2em;margin-top:1.5em;border-bottom:1px solid #ccc;}"
        "table{border-collapse:collapse;margin:0.5em 0;}"
        "table.kv th{text-align:left;padding:2px 12px 2px 0;color:#555;}"
        "table.kv td{padding:2px 0;}"
        "table td,table th{padding:3px 8px;}"
        ".disclaimer{color:#a00;font-weight:bold;}"
        ".note{color:#666;font-style:italic;}"
        ".timestamp{color:#666;}"
        "</style>\n</head>\n<body>\n"
        "<h1>Report esame — Peak Skin Dose</h1>\n"
        f"<p class='timestamp'>Generato il {html.escape(generated)}</p>\n"
        "<p class='disclaimer'>research/commissioning prototype — not for clinical use</p>\n"
        "<h2>Paziente</h2>\n" + kv_table(patient_rows) + "\n"
        "<h2>Taglia paziente</h2>\n" + kv_table(size_rows) + size_note + "\n"
        "<h2>Risultati dose</h2>\n" + kv_table(dose_rows) + "\n"
        "<h2>Modello di correzione</h2>\n" + kv_table(corr_rows) + "\n"
        "<h2>Eventi che contribuiscono al punto PSD (primi 100)</h2>\n"
        + table_html + "\n"
        "</body>\n</html>\n"
    )

from psd_engine import (
    load_excel, field_consistency, prepare_events, Phantom, Corrections,
    GeometrySettings, Fallbacks, calculate_map, event_contributions_at_peak,
    build_spectral_corrections, estimate_thorax_dimensions, combine_summaries,
)

try:
    from spectral_corrections import SpectralConfig
except Exception:
    SpectralConfig = None

st.set_page_config(page_title="PSD Mapper", layout="wide")
st.title("PSD Mapper — Excel event-dose prototype")
st.caption(
    "Local prototype for commissioning/research. Peak skin dose follows the model below "
    "(Johnson et al. 2011; Krajinović et al. 2021). Validate geometry and correction factors before clinical use."
)
st.latex(
    r"\mathrm{PSD} = K_{a,r} \cdot CF \cdot TAF \cdot F_{\theta} \cdot "
    r"\left(\frac{d_{IRP}}{d_{patient}}\right)^{2} \cdot BSF \cdot MEAC"
)
st.caption("📖 Apri la **Guida** dal menu a sinistra per la spiegazione dettagliata di algoritmo e formule, con figure.")

uploaded_files = st.file_uploader(
    "Carica il Dettaglio (event-level, per la mappa) e/o il Cumulativo (riepilogo/anagrafica) (.xlsx)",
    type=["xlsx"],
    accept_multiple_files=True,
    help="Puoi caricare un solo file o entrambi. Il file di dettaglio (event-level) "
         "serve a ricostruire la mappa; il cumulativo porta l'anagrafica e i totali "
         "d'esame. La classificazione è automatica, in base al contenuto del file "
         "(non al nome).",
)
if not uploaded_files:
    st.info(
        "Upload a **detailed** (event-level) Excel export — e.g. Coronarografia.xlsx, EVAR.xlsx, "
        "PTCA.xlsx, Embolizzazione.xlsx — and/or the matching **cumulative/summary** export. "
        "Cumulative/summary exports carry anagraphic + exam totals but cannot be mapped on their own."
    )
    st.stop()

# Classify each uploaded file by its PARSED summary['kind'] (NOT the filename).
detailed_df = detailed_summary = None
cumulative_df = cumulative_summary = None
for uf in uploaded_files:
    try:
        f_df, f_summary = load_excel(uf)
    except Exception as exc:
        st.error(f"Cannot read '{getattr(uf, 'name', 'file')}': {exc}")
        st.stop()

    if f_summary.get("kind") == "detailed" or f_summary.get("mappable"):
        if detailed_summary is not None:
            st.warning(
                f"Più di un file di dettaglio caricato — uso il primo e ignoro "
                f"'{getattr(uf, 'name', 'file')}'."
            )
            continue
        detailed_df, detailed_summary = f_df, f_summary
    else:
        if cumulative_summary is not None:
            st.warning(
                f"Più di un file cumulativo caricato — uso il primo e ignoro "
                f"'{getattr(uf, 'name', 'file')}'."
            )
            continue
        cumulative_df, cumulative_summary = f_df, f_summary

# One combined summary feeds anagraphic, totals and the correction/report sections.
combined = combine_summaries(detailed_summary, cumulative_summary)

# Columns for prepare_events come from the mappable (detailed) file when present,
# otherwise from the cumulative file.
if detailed_summary is not None:
    cols = detailed_summary["columns"]
else:
    cols = cumulative_summary["columns"]

# Cumulative-only intake: no per-event geometry -> show totals, skip mapping.
if detailed_summary is None:
    summary = combined
    st.info(cumulative_summary.get("message", "This is a cumulative/summary report and cannot be mapped."))
    st.subheader("Exam dose summary")
    m1, m2, m3 = st.columns(3)
    m1.metric("Total Ka,r", f"{summary['sum_kar_gy']:.3f} Gy")
    m2.metric("Total DAP", f"{summary['sum_dap_gy_cm2']:.1f} Gy·cm²")
    if summary.get("fluoro_time") is not None:
        m3.metric("Fluoroscopy time", f"{summary['fluoro_time']:.1f}")
    st.subheader("Paziente")
    pc1, pc2, pc3, pc4, pc5 = st.columns(5)
    pc1.metric("Nome", _fmt(summary.get("patient")))
    pc2.metric("Sesso", _fmt(summary.get("sex")))
    pc3.metric("Data di nascita", _fmt(summary.get("birthdate")))
    pc4.metric("Esame", _fmt(summary.get("exam")))
    pc5.metric("Data esame", _fmt(summary.get("exam_date")))
    st.caption(
        "To reconstruct a peak-skin-dose map, upload the matching event-level "
        "'..._dettaglio' export for this patient/procedure."
    )
    st.stop()

# Detailed file present -> mapping path. Use the detailed df/columns for the map,
# but read anagraphic + totals from the COMBINED summary (cumulative totals win
# when a cumulative file was also uploaded).
df = detailed_df
summary = combined

with st.sidebar:
    st.header("Patient phantom")

    # Anthropomorphic phantoms (male/female) are implemented in the engine but
    # DISABLED in the UI: without reliable anatomical landmarks from the Excel
    # report we cannot place the dose on the correct body location. The elliptic
    # cylinder remains the robust, vendor-independent choice for commissioning.
    # To re-enable, add "male"/"female" back to PHANTOM_OPTIONS below.
    PHANTOM_OPTIONS = ["cylinder"]
    phantom_model = st.selectbox(
        "Phantom model",
        PHANTOM_OPTIONS,
        index=0,
        format_func=lambda m: {
            "cylinder": "Elliptic cylinder (parametric)",
            "male": "Anthropomorphic — adult male",
            "female": "Anthropomorphic — adult female",
        }[m],
        help="Parametric elliptic cylinder: produces an unwrapped 2D skin-dose "
             "map and is independent of vendor/machine. Anthropomorphic phantoms "
             "are disabled because the report has no anatomical landmarks to "
             "position the dose reliably on the body.",
    )
    st.caption(
        "ℹ️ Anthropomorphic (male/female) phantoms are temporarily disabled: "
        "the dose cannot be anatomically located from this Excel alone."
    )

    if phantom_model == "cylinder":
        size_mode = st.selectbox(
            "Taglia paziente",
            ["Manuale", "Preset percentili", "Da peso + altezza"],
            index=0,
            help="Come impostare le dimensioni trasversali del cilindro ellittico "
                 "(width laterale e AP) su cui viene proiettata la dose alla cute. "
                 "'Manuale' è il comportamento di default. 'Preset percentili' usa "
                 "approssimazioni di popolazione adulta toracica. 'Da peso + altezza' "
                 "stima width/AP da un modello antropometrico (non clinico).",
        )

        # Default placeholders for the FEAT-003 size record.
        weight = height = bmi = None

        if size_mode == "Manuale":
            width = st.number_input("Lateral width (mm)", 180.0, 700.0, 360.0, 5.0)
            ap = st.number_input("AP thickness (mm)", 120.0, 600.0, 240.0, 5.0)
        elif size_mode == "Preset percentili":
            preset = st.selectbox("Percentile", ["Piccolo", "Medio", "Grande"], index=1)
            pre_w, pre_ap = {
                "Piccolo": (300.0, 200.0),
                "Medio": (360.0, 240.0),
                "Grande": (420.0, 280.0),
            }[preset]
            width = st.number_input("Lateral width (mm)", 180.0, 700.0, pre_w, 5.0)
            ap = st.number_input("AP thickness (mm)", 120.0, 600.0, pre_ap, 5.0)
            st.caption(
                "ℹ️ Valori indicativi di popolazione adulta (torace), non specifici "
                "del paziente. Modificabili sopra."
            )
        else:  # Da peso + altezza
            w0 = summary.get("weight_kg")
            h0 = summary.get("height_cm")
            weight = st.number_input("Peso (kg)", 30.0, 250.0, float(w0) if w0 else 75.0, 1.0)
            height = st.number_input("Altezza (cm)", 120.0, 220.0, float(h0) if h0 else 170.0, 1.0)
            est_w, est_ap = estimate_thorax_dimensions(weight, height)
            width = st.number_input("Lateral width (mm)", 180.0, 700.0, est_w, 5.0)
            ap = st.number_input("AP thickness (mm)", 120.0, 600.0, est_ap, 5.0)
            bmi = weight / (height / 100.0) ** 2
            st.caption(
                f"ℹ️ BMI ≈ **{bmi:.1f}**. Stima width/AP da modello antropometrico "
                "approssimato e **non clinico**; valori modificabili sopra."
            )

        length = st.number_input("Mapped longitudinal length (mm)", 300.0, 1800.0, 800.0, 25.0)
        resolution = st.selectbox("Map resolution", ["Fast", "Standard", "High"], index=1)
        res = {"Fast": (120, 160), "Standard": (180, 240), "High": (240, 320)}[resolution]
        human_scale = 1.0

        anchor_label = st.selectbox(
            "Ancoraggio paziente",
            ["Schiena sul piano del tavolo", "Centro sull'isocentro (legacy)"],
            index=0,
            help="Come viene posizionato verticalmente il cilindro ellittico. "
                 "'Schiena sul piano del tavolo' tiene la cute di entrata (la "
                 "schiena) a una distanza fissa e realistica dalla sorgente: "
                 "aumentando lo spessore AP il paziente cresce verso l'anteriore, "
                 "quindi la PSD non aumenta artificialmente con la taglia. "
                 "'Centro sull'isocentro (legacy)' riproduce il comportamento "
                 "precedente (centro del fantoccio sull'isocentro).",
        )
        anchor_mode = {
            "Schiena sul piano del tavolo": "back_on_table",
            "Centro sull'isocentro (legacy)": "center_on_isocentre",
        }[anchor_label]
        pad_mm = st.number_input(
            "Spessore materasso/pad (mm)", 0.0, 100.0, 0.0, 5.0,
            help="Spessore del materasso/pad tra il piano del tavolo e la schiena "
                 "del paziente. Rilevante solo con l'ancoraggio 'Schiena sul "
                 "piano del tavolo'.",
        )
    else:
        # Kept for when anthropomorphic phantoms are re-enabled.
        size_mode = "Manuale"
        weight = height = bmi = None
        human_scale = st.number_input("Body scale", 0.70, 1.40, 1.00, 0.01)
        width = ap = length = 0.0
        res = (180, 240)
        anchor_mode = "back_on_table"
        pad_mm = 0.0

    st.header("Dose corrections")
    st.caption("Commission these values for each X-ray system before clinical use.")

    use_spectral = st.checkbox(
        "Use beam-quality dependent BSF & MEAC (Benmakhlouf 2011)",
        value=(SpectralConfig is not None),
        help="Compute backscatter (BSF) and the air→water MEAC ratio per event "
             "from beam quality (kVp, HVL) and field size, using the Monte-Carlo "
             "tabulated data of Benmakhlouf et al. 2011 (PMB 56:7179). "
             "Generalises across vendors because it depends on beam quality, not "
             "on a specific machine. Falls back to the constants below when kVp is "
             "missing.",
    )

    bsf = st.number_input("Backscatter factor (BSF) — constant/fallback", 1.00, 1.80, 1.35, 0.01)
    tissue_f = st.number_input(
        "MEAC ratio μen/ρ (water/air) — constant/fallback", 0.80, 1.20, 1.06, 0.01,
        help="Ratio of mass energy-absorption coefficients water-to-air used to "
             "convert air kerma to skin (soft-tissue) dose. Literature value ≈ "
             "1.03–1.06 across interventional beam qualities (Benmakhlouf 2011; "
             "the water/soft-tissue difference is <1%, Grosswendt). The spectral "
             "option makes this kVp/HVL dependent and is the most defensible.",
    )
    calibration = st.number_input("Ka,r calibration factor (CF)", 0.80, 1.20, 1.00, 0.01)
    ref_offset = st.number_input("Reference point offset toward source (mm)", 0.0, 300.0, 150.0, 5.0)

    st.subheader("Table / pad attenuation")
    st.caption(
        "Beams entering from below the patient pass through the table and pad. "
        "Choose how to account for this attenuation."
    )
    table_choice = st.radio(
        "Table attenuation model",
        ["None (no attenuation)", "Measured transmission", "Spectral (kVp-dependent)"],
        index=0,
        help="Use 'Measured transmission' only if you have measured the table+pad "
             "transmission for this unit. 'Spectral' uses the tabulated kVp-dependent "
             "values (requires spectral BSF/MEAC on and a matching device in the DB). "
             "'None' makes no table correction.",
    )
    table_mode = {"None (no attenuation)": "none",
                  "Measured transmission": "measured",
                  "Spectral (kVp-dependent)": "spectral"}[table_choice]

    support = 1.0
    if table_mode == "measured":
        input_style = st.selectbox(
            "Provide transmission as", ["Transmission factor (TAF)", "Thickness + attenuation"],
            index=0,
        )
        if input_style == "Transmission factor (TAF)":
            support = st.number_input(
                "Measured table+pad transmission at 0° (TAF)", 0.40, 1.00, 0.80, 0.01,
                help="Ratio of air kerma with / without the table+pad in the beam, "
                     "measured at normal incidence. Typical modern tables: 0.6–0.85.",
            )
        else:
            thick_mm = st.number_input("Table+pad equivalent thickness (mm PMMA)", 0.0, 60.0, 20.0, 1.0)
            mu_cm = st.number_input("Linear attenuation μ (cm⁻¹, at working beam)", 0.05, 1.00, 0.20, 0.01,
                                    help="Effective μ of the support at the beam quality used. "
                                         "PMMA ≈ 0.2 cm⁻¹ around 80 kVp / heavy Cu filtration.")
            support = float(np.exp(-mu_cm * (thick_mm / 10.0)))
            st.caption(f"→ resulting transmission ≈ **{support:.3f}**")

    use_oblique = st.checkbox(
        "Apply oblique table factor Fθ", value=True,
        help="Increase table attenuation for oblique beams (path length ∝ 1/cosθ). "
             "Only affects beams that traverse the support.",
    )

    spectral_cfg = None
    if use_spectral and SpectralConfig is not None:
        with st.expander("Spectral-correction settings", expanded=False):
            st.caption(
                "HVL is looked up from kVp + filtration (SpekPy table). When the "
                "report lacks filtration columns, HVL is estimated from kVp."
            )
            dev_model = st.selectbox(
                "Device model (table transmission lookup)",
                ["AlluraClarity", "AXIOM-Artis"], index=0,
            )
            acq_plane = st.selectbox(
                "Acquisition plane", ["Single Plane", "Plane A", "Plane B"], index=0,
            )
            default_kvp = st.number_input("Default kVp (when missing)", 40.0, 150.0, 77.0, 1.0)
            inh_al = st.number_input("Assumed inherent filtration (mmAl)", 1.0, 6.0, 3.0, 0.1)
            add_cu = st.number_input("Assumed added Cu filtration (mm)", 0.0, 0.9, 0.0, 0.1)
            add_al = st.number_input("Assumed added Al filtration (mm)", 0.0, 3.0, 0.0, 1.0)
        spectral_cfg = SpectralConfig(
            enabled=True,
            default_kvp=default_kvp,
            default_inherent_mmal=inh_al,
            default_added_cu_mm=add_cu,
            default_added_al_mm=add_al,
            device_model=dev_model,
            acquisition_plane=acq_plane,
            const_bsf=bsf,
            const_med=tissue_f,
            const_tab=support,
        )

    # ---- Advanced settings: fallbacks & geometry (collapsed) ------------
    with st.expander("Advanced: fallbacks & geometry", expanded=False):
        st.caption(
            "Used only when a column is absent/unusable, or to fix a "
            "mirrored/reversed map during commissioning. The supplied reports "
            "have no collimation columns, so field size defaults to DAP/Ka,r."
        )
        use_dap_field = st.checkbox("Reconstruct field size from DAP/Ka,r (preferred)", value=summary["has_dap"])
        fixed_w = st.number_input("Fixed collimation width @ detector (mm)", 20.0, 500.0, 200.0, 5.0)
        fixed_h = st.number_input("Fixed collimation height @ detector (mm)", 20.0, 500.0, 200.0, 5.0)
        default_sod = st.number_input("Default source-isocentre distance (mm)", 400.0, 1200.0, 720.0, 5.0)
        default_sid = st.number_input("Default source-detector distance (mm)", 600.0, 1500.0, 1100.0, 5.0)
        st.markdown("**Geometry conventions**")
        lat_sign = st.selectbox("Table lateral sign", [-1.0, 1.0], index=0)
        h_sign = st.selectbox("Table height sign", [-1.0, 1.0], index=0)
        lon_sign = st.selectbox("Table longitudinal sign", [-1.0, 1.0], index=0)
        off_x = st.number_input("Patient lateral offset from isocentre (mm)", -300.0, 300.0, 0.0, 5.0)
        off_y = st.number_input("Patient AP offset from isocentre (mm)", -300.0, 300.0, 0.0, 5.0)
        off_z = st.number_input("Patient longitudinal offset (mm)", -1000.0, 1000.0, 0.0, 10.0)

# Build the spectral-correction engine (or None if unavailable / disabled).
spectral = None
if use_spectral and SpectralConfig is not None:
    spectral = build_spectral_corrections(spectral_cfg)
    if spectral is None:
        st.warning("Spectral-correction module/data unavailable — using constant factors.")

fb = Fallbacks(
    fixed_coll_w_mm=fixed_w, fixed_coll_h_mm=fixed_h,
    default_sod_mm=default_sod, default_sid_mm=default_sid,
    use_dap_field=use_dap_field,
)

try:
    events, meta = prepare_events(df, cols, reference_offset_mm=ref_offset, fb=fb)
except Exception as exc:
    st.error(f"Event preparation failed: {exc}")
    st.stop()

qc = field_consistency(df, cols, reference_offset_mm=ref_offset)

# Record the chosen patient-size parameters for the downstream report (FEAT-003).
size_detail = {
    "mode": size_mode,
    "width_mm": width,
    "ap_mm": ap,
    "length_mm": length,
    "weight_kg": weight,
    "height_cm": height,
    "bmi": bmi,
}

phantom = Phantom(
    model=phantom_model,
    width_mm=width, ap_mm=ap, length_mm=length, n_theta=res[0], n_z=res[1],
    human_scale=human_scale,
)

corr = Corrections(
    bsf=bsf, tissue_f=tissue_f, support_transmission=support,
    kar_calibration=calibration, use_oblique_factor=use_oblique,
    table_mode=table_mode,
    use_spectral=bool(spectral is not None), spectral=spectral,
)

geom = GeometrySettings(
    lateral_sign=lat_sign, height_sign=h_sign, longitudinal_sign=lon_sign,
    offset_x_mm=off_x, offset_y_mm=off_y, offset_z_mm=off_z,
    anchor_mode=anchor_mode, pad_mm=pad_mm,
)

if meta["used"] == 0:
    st.error("No mappable irradiation events after preparation. Check the input columns and fallbacks.")
    st.stop()

try:
    with st.spinner("Reconstructing beam overlap and accumulating skin dose..."):
        result = calculate_map(events, meta, phantom, corr, geom)
        contrib = event_contributions_at_peak(events, meta, phantom, corr, geom, result["peak"])
except FileNotFoundError as exc:
    st.error(
        f"Anthropomorphic phantom data missing: {exc}\n\n"
        "Copy the reduced STL meshes into the ./phantom_data folder, or switch "
        "back to the cylinder phantom."
    )
    st.stop()
except Exception as exc:
    st.error(f"Dose calculation failed: {exc}")
    st.exception(exc)
    st.stop()

peak = result["peak"]

st.subheader("Paziente")
pc1, pc2, pc3, pc4, pc5 = st.columns(5)
pc1.metric("Nome", _fmt(summary.get("patient")))
pc2.metric("Sesso", _fmt(summary.get("sex")))
pc3.metric("Data di nascita", _fmt(summary.get("birthdate")))
pc4.metric("Esame", _fmt(summary.get("exam")))
pc5.metric("Data esame", _fmt(summary.get("exam_date")))

st.header("🎯 Peak skin dose")
p1, p2, p3, p4 = st.columns([1.4, 1, 1, 1])
p1.metric("PSD", f"{peak['psd_gy']:.2f} Gy")
if result["kind"] == "cylinder":
    p2.metric("Circumferential angle", f"{peak['theta_deg']:.1f}°")
    p3.metric("Longitudinal position", f"{peak['z_mm']:.0f} mm")
else:
    p2.metric("Peak position (lat, AP)", f"{peak['x_mm']:.0f}, {peak['y_mm']:.0f} mm")
    p3.metric("Longitudinal position", f"{peak['z_mm']:.0f} mm")
if spectral is not None:
    if not contrib.empty and "BSF" in contrib.columns:
        prod = float((contrib["BSF"] * contrib["MEAC"] * contrib["Table transm."] * calibration).mean())
        p4.metric("Correction product (mean @ peak)", f"{prod:.3f}")
    else:
        p4.metric("Correction product", "per-event")
else:
    p4.metric("Correction product", f"{corr.product:.3f}")

# Quick context line so the essentials sit together at the top.
_totals_src = (
    " (totali dal cumulativo)" if summary.get("totals_source") == "cumulative"
    else ""
)
st.caption(
    f"From **{meta['used']}** irradiation events · total Ka,r **{summary['sum_kar_gy']:.2f} Gy** · "
    f"total DAP **{summary['sum_dap_gy_cm2']:.0f} Gy·cm²**{_totals_src}. "
    "Map coordinates are relative to the phantom/reference table position; "
    "absolute anatomical location cannot be inferred from this Excel alone."
)

st.subheader("Skin-dose map")
if result["kind"] == "cylinder":
    angle_deg = np.degrees(result["theta"])
    heat = go.Figure(go.Heatmap(
        x=angle_deg, y=result["z"], z=result["dose"],
        colorbar=dict(title="Gy"), hovertemplate="Angle %{x:.1f}°<br>z %{y:.0f} mm<br>Dose %{z:.3f} Gy<extra></extra>"
    ))
    heat.add_trace(go.Scatter(
        x=[peak["theta_deg"]], y=[peak["z_mm"]], mode="markers+text",
        marker=dict(size=11, symbol="x"), text=[f"PSD {peak['psd_gy']:.2f} Gy"], textposition="top center",
        name="PSD"
    ))
    heat.update_layout(
        title="Unwrapped skin-dose map",
        xaxis_title="Circumferential angle (deg; -90° ≈ posterior for default convention)",
        yaxis_title="Relative longitudinal position (mm)",
        height=600,
    )
    st.plotly_chart(heat, use_container_width=True)

    with st.expander("3D skin-dose surface", expanded=False):
        surf = go.Figure(go.Surface(
            x=result["X"], y=result["Y"], z=result["Z"], surfacecolor=result["dose"],
            colorbar=dict(title="Gy"), cmin=0, cmax=max(float(result["dose"].max()), 1e-9),
        ))
        surf.add_trace(go.Scatter3d(
            x=[peak["x_mm"]], y=[peak["y_mm"]], z=[peak["z_mm"]],
            mode="markers", marker=dict(size=5), name=f"PSD {peak['psd_gy']:.2f} Gy"
        ))
        surf.update_layout(
            scene=dict(xaxis_title="Lateral mm", yaxis_title="AP mm", zaxis_title="Longitudinal mm", aspectmode="data"),
            height=700, margin=dict(l=0, r=0, t=40, b=0),
        )
        render_plotly(surf, height=700)
else:
    # Anthropomorphic mesh phantom — colour the body surface directly by dose.
    P = result["P"]               # (n_vert, 3) vertex skin cells
    faces = result["faces"]       # (n_tri, 3) vertex indices
    dose = result["dose"]         # (n_vert,) dose per vertex
    n_hit = int((dose > 0).sum())
    cmax = max(float(dose.max()), 1e-9)

    st.caption(
        f"Anthropomorphic **{phantom_model}** phantom "
        f"({P.shape[0]} surface cells, {n_hit} irradiated). "
        "The body surface is coloured directly by skin dose (blue → red). "
        "No unwrapped 2D map for mesh phantoms."
    )

    mesh_fig = go.Figure()
    # Body surface coloured by per-vertex dose. Vertices with zero dose stay
    # blue, irradiated regions turn towards red — the map is painted on the skin.
    mesh_fig.add_trace(go.Mesh3d(
        x=P[:, 0], y=P[:, 1], z=P[:, 2],
        i=faces[:, 0], j=faces[:, 1], k=faces[:, 2],
        intensity=dose, intensitymode="vertex",
        colorscale="Jet", cmin=0.0, cmax=cmax,
        colorbar=dict(title="Gy"), showscale=True,
        flatshading=False, name="skin dose",
        hovertemplate="Dose %{intensity:.3f} Gy<extra></extra>",
    ))
    # Peak marker.
    mesh_fig.add_trace(go.Scatter3d(
        x=[peak["x_mm"]], y=[peak["y_mm"]], z=[peak["z_mm"]],
        mode="markers+text", marker=dict(size=7, color="black", symbol="x"),
        text=[f"PSD {peak['psd_gy']:.2f} Gy"], textposition="top center",
        name="PSD",
    ))
    mesh_fig.update_layout(
        title=f"Skin-dose map — {phantom_model} phantom (PSD {peak['psd_gy']:.2f} Gy)",
        scene=dict(xaxis_title="Lateral mm", yaxis_title="AP mm",
                   zaxis_title="Longitudinal mm", aspectmode="data"),
        height=700, margin=dict(l=0, r=0, t=40, b=0),
    )
    render_plotly(mesh_fig, height=700)

st.subheader("Events contributing to the PSD point")
if contrib.empty:
    st.info("No contributing events were identified at the selected peak grid point.")
else:
    st.dataframe(contrib.head(100), use_container_width=True, hide_index=True)
    csv = contrib.to_csv(index=False).encode("utf-8")
    st.download_button("Download PSD-point event contributions (CSV)", csv, "psd_event_contributions.csv", "text/csv")

    # ---- Self-contained HTML exam report (FEAT-003) --------------------
    _report_patient = {
        "patient": summary.get("patient"),
        "sex": summary.get("sex"),
        "birthdate": summary.get("birthdate"),
        "exam": summary.get("exam"),
        "exam_date": summary.get("exam_date"),
    }
    _report_dose = {
        "kind": result["kind"],
        "psd_gy": peak.get("psd_gy"),
        "theta_deg": peak.get("theta_deg"),
        "z_mm": peak.get("z_mm"),
        "used": meta["used"],
        "sum_kar_gy": summary.get("sum_kar_gy"),
        "sum_dap_gy_cm2": summary.get("sum_dap_gy_cm2"),
    }
    _report_corr = {
        "use_spectral": bool(spectral is not None),
        "kvp_source": ("per-event kVp" if cols.get("kvp")
                       else (f"default {spectral_cfg.default_kvp:.0f} kVp"
                             if spectral is not None else None)),
        "bsf": bsf,
        "meac": tissue_f,
        "table_mode": table_mode,
        "table_transmission": support,
        "ref_offset_mm": ref_offset,
        "sod_source": f"default {default_sod:.0f} mm",
        "anchor_mode": anchor_mode,
        "pad_mm": pad_mm,
    }
    # Filesystem-safe slug from accession/patient name, fallback 'esame'.
    _stem_src = summary.get("patient") or "esame"
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", str(_stem_src)).strip("_") or "esame"
    st.download_button(
        "Scarica report esame (HTML)",
        data=build_html_report(_report_patient, size_detail, _report_dose,
                               _report_corr, contrib).encode("utf-8"),
        file_name=f"PSD_report_{stem}.html",
        mime="text/html",
    )

st.divider()
st.subheader("Imported data & correction settings used")

# Patient-size mode and resulting phantom cross-section used for this map.
_size_line = (
    f"Taglia paziente: **{size_detail['mode']}** · "
    f"width {size_detail['width_mm']:.0f} mm · AP {size_detail['ap_mm']:.0f} mm · "
    f"length {size_detail['length_mm']:.0f} mm"
)
if size_detail["bmi"] is not None:
    _size_line += f" · BMI {size_detail['bmi']:.1f}"
_anchor_label_it = ("schiena sul piano del tavolo" if geom.anchor_mode == "back_on_table"
                    else "centro sull'isocentro (legacy)")
_size_line += f" · ancoraggio {_anchor_label_it}"
if geom.anchor_mode == "back_on_table" and geom.pad_mm:
    _size_line += f" · pad {geom.pad_mm:.0f} mm"
st.caption(_size_line + ".")

# What correction model was applied.
if spectral is not None:
    has_kvp = bool(cols.get("kvp"))
    st.info(
        "Beam-quality dependent BSF & MEAC requested (Benmakhlouf 2011): computed per event from "
        + ("the event **kVp**" if has_kvp else f"the default kVp ({spectral_cfg.default_kvp:.0f})")
        + ". HVL is looked up/estimated from kVp and filtration; constants are the fallback. "
        + f"Table attenuation model: **{table_mode}**"
        + (f" (transmission {support:.3f})" if table_mode == 'measured' else "") + "."
    )
    if not has_kvp:
        st.warning(
            "No KVP column in this report — spectral factors use the default kVp "
            "for every event. Results are less specific than with per-event kVp."
        )
    has_filter = bool(cols.get("filter_min") or cols.get("filter_max")) and bool(cols.get("filter_material"))
    if not has_filter:
        st.info(
            "No event-level filtration columns were resolved — HVL estimation uses the "
            "configured default filtration. If the export contains filter material/thickness, "
            "check the column names in the importer aliases."
        )
    spec_status = spectral.summary()
    if not spec_status.get("has_med_table"):
        st.warning("k_med.csv is unavailable: MEAC falls back to the constant value.")
    if table_mode == "spectral" and not spec_status.get("has_tab_table"):
        st.warning("k_tab.csv is unavailable: spectral table transmission falls back to the configured constant.")
else:
    st.info(
        f"Constant corrections: BSF={bsf:.2f}, MEAC={tissue_f:.2f}, "
        f"table model **{table_mode}**"
        + (f" (transmission {support:.3f})" if table_mode == 'measured' else "") + "."
    )
if table_mode == "spectral" and spectral is None:
    st.warning("Spectral table attenuation selected but spectral module is off/unavailable — no table attenuation applied.")

# Loader warnings / missing-column fallbacks.
for w in summary.get("warnings", []):
    st.warning(w)
if not summary["has_dap"]:
    st.warning("No DAP column found — field size relies on collimation/fixed fallbacks.")
if not summary["has_collimation"]:
    st.info("No collimation columns in this export — field aspect ratio is assumed square unless DAP/Ka,r defines it.")
if not summary["has_sid"]:
    st.info(f"No source-detector distance column — using the fallback value {default_sid:.0f} mm.")

# Summary metrics of the imported report.
c1, c2, c3, c4 = st.columns(4)
c1.metric("Dose-report rows", f"{summary['rows']}")
c2.metric("Usable irradiation events", f"{meta['used']}")
c3.metric("Total Ka,r", f"{summary['sum_kar_gy']:.3f} Gy")
c4.metric("Total DAP", f"{summary['sum_dap_gy_cm2']:.1f} Gy·cm²")

with st.expander("Input/QC details", expanded=False):
    st.write(f"Air-kerma source column: **{summary['kar_source']}**")
    st.write("Event types", summary["event_types"])
    st.write("Field-size source per event", meta["field_source_counts"])
    st.write(
        f"Reference table coordinates (non-zero medians): lateral {meta['ref_lat']:.1f}, "
        f"height {meta['ref_height']:.1f}, longitudinal {meta['ref_lon']:.1f} mm"
    )
    st.write(f"Rows omitted from mapping: {meta['omitted']}")
    if qc["n"]:
        st.write(
            "DAP/Ka,r field-area consistency: observed / geometrically projected collimation area "
            f"median = {qc['median_ratio']:.3f} (5th–95th percentile {qc['p05']:.3f}–{qc['p95']:.3f}, n={qc['n']})."
        )
    else:
        st.write("Field-area consistency check unavailable (no collimation columns).")
    if spectral is not None:
        st.write("Spectral-correction status", spectral.summary())

st.divider()
st.markdown("**Commissioning items before clinical use**")
st.markdown(
    "1. Confirm the Ka,r source column and its calibration (CF) against QC measurements.  "
    "\n2. Verify primary/secondary angle sign conventions and table-motion axes with known test exposures.  "
    "\n3. If using 'Measured transmission', measure the table + mattress transmission (TAF) for the unit; otherwise leave table attenuation as 'None'.  "
    "\n4. Spectral BSF/MEAC use Benmakhlouf 2011 (kVp/HVL/field-size dependent) — generalises across vendors; the MEAC water/air ratio (~1.03–1.06) is beam-quality dependent.  "
    "\n5. Validate PSD and map position against film/OSLD/TLD or a commissioned dose-tracking system."
)

with st.expander("References for the correction model"):
    st.markdown(
        "- **Johnson PB, Borrego D, Balter S, et al. (2011)**. *Skin dose mapping for "
        "fluoroscopically guided interventions.* Med Phys 38(10):5490–5499. "
        "doi:10.1118/1.3633935.  \n"
        "- **Krajinović M, Kržanović N, Ciraj-Bjelac O (2021)**. *Vendor-independent "
        "skin dose mapping application for interventional radiology and cardiology.* "
        "J Appl Clin Med Phys 22(2):145–157. doi:10.1002/acm2.13167.  \n"
        "- **Benmakhlouf H, Bouchard H, Fransson A, Andreo P (2011)**. *Backscatter "
        "factors and mass energy-absorption coefficient ratios for diagnostic radiology "
        "dosimetry.* Phys Med Biol 56(22):7179–7204. "
        "doi:10.1088/0031-9155/56/22/012.  \n"
        "- **Benmakhlouf H, Fransson A, Andreo P (2013)**. *Influence of phantom "
        "thickness and material on the backscatter factors for diagnostic x-ray beam "
        "dosimetry.* Phys Med Biol 58(2):247–260. doi:10.1088/0031-9155/58/2/247."
    )
