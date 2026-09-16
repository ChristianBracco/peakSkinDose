from __future__ import annotations
import io
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from psd_engine import (
    load_excel, field_consistency, prepare_events, Phantom, Corrections,
    GeometrySettings, Fallbacks, calculate_map, event_contributions_at_peak,
)

st.set_page_config(page_title="PSD Mapper", layout="wide")
st.title("PSD Mapper — Excel event-dose prototype")
st.caption(
    "Local prototype for commissioning/research. Peak skin dose follows the model below "
    "(Johnson & Bolch 2011; Krajinović 2021). Validate geometry and correction factors before clinical use."
)
st.latex(
    r"\mathrm{PSD} = K_{a,r} \cdot CF \cdot TAF \cdot F_{\theta} \cdot "
    r"\left(\frac{d_{IRP}}{d_{patient}}\right)^{2} \cdot BSF \cdot MEAC"
)

uploaded = st.file_uploader("Drop the event-level Excel dose report (.xlsx)", type=["xlsx"])
if uploaded is None:
    st.info(
        "Upload a **detailed** (event-level) Excel export — e.g. Coronarografia.xlsx, EVAR.xlsx, "
        "PTCA.xlsx, Embolizzazione.xlsx. Cumulative/summary exports cannot be mapped."
    )
    st.stop()

try:
    df, summary = load_excel(uploaded)
except Exception as exc:
    st.error(f"Cannot read this file: {exc}")
    st.stop()

cols = summary["columns"]

# Cumulative/summary reports: no per-event geometry -> show totals, skip mapping.
if not summary.get("mappable", True):
    st.info(summary.get("message", "This is a cumulative/summary report and cannot be mapped."))
    st.subheader("Exam dose summary")
    m1, m2, m3 = st.columns(3)
    m1.metric("Total Ka,r", f"{summary['sum_kar_gy']:.3f} Gy")
    m2.metric("Total DAP", f"{summary['sum_dap_gy_cm2']:.1f} Gy·cm²")
    if summary.get("fluoro_time") is not None:
        m3.metric("Fluoroscopy time", f"{summary['fluoro_time']:.1f}")
    details = {k: summary.get(k) for k in ("patient", "exam", "exam_date") if summary.get(k)}
    if details:
        st.write(details)
    st.caption(
        "To reconstruct a peak-skin-dose map, upload the matching event-level "
        "'..._dettaglio' export for this patient/procedure."
    )
    st.stop()

with st.sidebar:
    st.header("Patient phantom")
    width = st.number_input("Lateral width (mm)", 180.0, 700.0, 360.0, 5.0)
    ap = st.number_input("AP thickness (mm)", 120.0, 600.0, 240.0, 5.0)
    length = st.number_input("Mapped longitudinal length (mm)", 300.0, 1800.0, 800.0, 25.0)
    resolution = st.selectbox("Map resolution", ["Fast", "Standard", "High"], index=1)
    res = {"Fast": (120, 160), "Standard": (180, 240), "High": (240, 320)}[resolution]

    st.header("Dose corrections")
    st.caption("Commission these values for each X-ray system before clinical use.")
    bsf = st.number_input("Backscatter factor (BSF)", 1.00, 1.80, 1.35, 0.01)
    tissue_f = st.number_input("Air-to-tissue factor (MEAC ratio)", 0.80, 1.20, 1.06, 0.01)
    support = st.number_input("Table/pad transmission at 0° (TAF)", 0.50, 1.10, 1.00, 0.01)
    calibration = st.number_input("Ka,r calibration factor (CF)", 0.80, 1.20, 1.00, 0.01)
    use_oblique = st.checkbox("Apply oblique table factor Fθ", value=True)
    ref_offset = st.number_input("Reference point offset toward source (mm)", 0.0, 300.0, 150.0, 5.0)

    st.header("Fallbacks (missing columns)")
    st.caption(
        "Used when a column is absent or unusable. The supplied reports contain no "
        "collimation columns, so field size defaults to DAP/Ka,r reconstruction."
    )
    use_dap_field = st.checkbox("Reconstruct field size from DAP/Ka,r (preferred)", value=summary["has_dap"])
    fixed_w = st.number_input("Fixed collimation width @ detector (mm)", 20.0, 500.0, 200.0, 5.0)
    fixed_h = st.number_input("Fixed collimation height @ detector (mm)", 20.0, 500.0, 200.0, 5.0)
    default_sod = st.number_input("Default source-isocentre distance (mm)", 400.0, 1200.0, 720.0, 5.0)
    default_sid = st.number_input("Default source-detector distance (mm)", 600.0, 1500.0, 1100.0, 5.0)

    with st.expander("Geometry conventions"):
        st.caption("Use these only during commissioning if a mapped shift is mirrored/reversed.")
        lat_sign = st.selectbox("Table lateral sign", [-1.0, 1.0], index=0)
        h_sign = st.selectbox("Table height sign", [-1.0, 1.0], index=0)
        lon_sign = st.selectbox("Table longitudinal sign", [-1.0, 1.0], index=0)
        off_x = st.number_input("Patient lateral offset from isocentre (mm)", -300.0, 300.0, 0.0, 5.0)
        off_y = st.number_input("Patient AP offset from isocentre (mm)", -300.0, 300.0, 0.0, 5.0)
        off_z = st.number_input("Patient longitudinal offset (mm)", -1000.0, 1000.0, 0.0, 10.0)

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

# Surface loader warnings and missing-column fallbacks.
for w in summary.get("warnings", []):
    st.warning(w)
if not summary["has_dap"]:
    st.warning("No DAP column found — field size relies on collimation/fixed fallbacks.")
if not summary["has_collimation"]:
    st.info("No collimation columns in this export — field aspect ratio is assumed square unless DAP/Ka,r defines it.")
if not summary["has_sid"]:
    st.info(f"No source-detector distance column — using the fallback value {default_sid:.0f} mm.")

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

phantom = Phantom(width_mm=width, ap_mm=ap, length_mm=length, n_theta=res[0], n_z=res[1])
corr = Corrections(
    bsf=bsf, tissue_f=tissue_f, support_transmission=support,
    kar_calibration=calibration, use_oblique_factor=use_oblique,
)
geom = GeometrySettings(
    lateral_sign=lat_sign, height_sign=h_sign, longitudinal_sign=lon_sign,
    offset_x_mm=off_x, offset_y_mm=off_y, offset_z_mm=off_z,
)

if meta["used"] == 0:
    st.error("No mappable irradiation events after preparation. Check the input columns and fallbacks.")
    st.stop()

with st.spinner("Reconstructing beam overlap and accumulating skin dose..."):
    result = calculate_map(events, meta, phantom, corr, geom)
    contrib = event_contributions_at_peak(events, meta, phantom, corr, geom, result["peak"])

peak = result["peak"]
st.subheader("Peak skin dose estimate")
p1, p2, p3, p4 = st.columns(4)
p1.metric("PSD", f"{peak['psd_gy']:.3f} Gy")
p2.metric("Circumferential angle", f"{peak['theta_deg']:.1f}°")
p3.metric("Relative longitudinal position", f"{peak['z_mm']:.0f} mm")
p4.metric("Correction product", f"{corr.product:.3f}")

st.caption(
    "Coordinates are relative to the phantom/reference table position. Absolute anatomical location cannot be inferred reliably from this Excel alone."
)

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
    st.plotly_chart(surf, use_container_width=True)

st.subheader("Events contributing to the PSD point")
if contrib.empty:
    st.info("No contributing events were identified at the selected peak grid point.")
else:
    st.dataframe(contrib.head(100), use_container_width=True, hide_index=True)
    csv = contrib.to_csv(index=False).encode("utf-8")
    st.download_button("Download PSD-point event contributions (CSV)", csv, "psd_event_contributions.csv", "text/csv")

st.divider()
st.markdown("**Commissioning items before clinical use**")
st.markdown(
    "1. Confirm the Ka,r source column and its calibration (CF) against QC measurements.  "
    "\n2. Verify primary/secondary angle sign conventions and table-motion axes with known test exposures.  "
    "\n3. Measure table + mattress transmission (TAF) and its angular dependence (Fθ).  "
    "\n4. Replace fixed BSF/MEAC with beam-quality/field-size dependent factors (e.g. Benmakhlouf 2011).  "
    "\n5. Validate PSD and map position against film/OSLD/TLD or a commissioned dose-tracking system."
)
