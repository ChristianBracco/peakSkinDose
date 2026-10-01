from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional
import os
import math
import numpy as np
import pandas as pd

try:
    from spectral_corrections import SpectralCorrections, SpectralConfig
except Exception:  # pragma: no cover - spectral module optional
    SpectralCorrections = None
    SpectralConfig = None

# ---------------------------------------------------------------------------
# Column model
# ---------------------------------------------------------------------------
# The structured Italian dose reports come in two shapes:
#   * "detailed" (event-level)  -> one row per irradiation event, used for mapping.
#   * "cumulative"/"general"    -> one row per exam (summary), NOT mappable.
#
# The reference air kerma at the interventional reference point (Ka,r / IRP)
# is stored in the column "Kerma in Aria" (unit Gy).  Some legacy exports used
# a column literally named "KAP" that also held Gy values; we keep it as a
# fallback so both layouts work.
#
# There are NO collimation columns in the supplied exports.  Per the literature
# (Johnson & Bolch 2011; Krajinovic 2021) the field size at the reference plane
# is reconstructed from DAP / Ka,r.  When that is impossible for a given event
# we fall back to a user-configurable fixed collimation.
# ---------------------------------------------------------------------------

# Candidate names for each logical field (first match wins, case handled elsewhere).
COLUMN_ALIASES = {
    "dap": ["DAP"],
    "dap_unit": ["Unità Misura DAP"],
    "kar": ["Kerma in Aria", "KAP"],
    "kar_unit": ["Unità Misura Kerma in Aria", "Unità Misura KAP"],
    # Summary/cumulative-only fields (one row per exam):
    "kar_total": ["Kerma in Aria Totale (Gy)", "Kerma in Aria"],
    "dap_total": ["DAP", "DAP Totale di Acquisizione"],
    "fluoro_time": ["Tempo Totale di Fluoroscopia (min)", "Tempo Totale Fluoroscopia",
                    "Tempo Totale di Fluoroscopia (s)"],
    "patient": ["Paziente"],
    "exam": ["Esame"],
    "exam_date": ["Data Esame"],
    "alpha": ["Angolazione primaria tubo (LL)"],
    "beta": ["Angolazione secondaria tubo (AP)"],
    "table_lat": ["Posizione laterale del tavolo"],
    "table_height": ["Altezza del tavolo"],
    "table_lon": ["Posizione longitudinale tavolo"],
    "sod": ["Distanza sorgente-isocentro"],
    "sid": ["Distanza sorgente-detettore"],
    "coll_h": ["Altezza Collimazione (mm)"],
    "coll_w": ["Larghezza Collimazione (mm)"],
    "event_type": ["Tipo evento irradiazione"],
    "protocol": ["Protocollo di acquisizione"],
    "accession": ["Accession number"],
    "kvp": ["KVP"],
    "filter_min": ["Spessore minimo del filtro"],
    "filter_max": ["Spessore massimo del filtro"],
    "filter_material": ["Materiale del filtro"],
}

# Logical fields that must be present (in some alias form) for event mapping.
ESSENTIAL_LOGICAL = ["kar", "alpha", "beta", "sod", "table_lat", "table_height", "table_lon"]

DAP_UNIT_OK = {"Gy*cm2", "Gy·cm2", "Gy cm2", "Gy.cm2", "Gycm2"}
KAR_UNIT_OK = {"Gy"}


@dataclass
class Fallbacks:
    """Values used when optional columns are missing or unusable for an event."""
    # Fixed collimation at the DETECTOR plane (mm) used when neither DAP/Ka,r
    # nor collimation columns can define the field for an event.
    fixed_coll_w_mm: float = 200.0
    fixed_coll_h_mm: float = 200.0
    # Fixed geometry used when SOD/SID columns are entirely absent.
    default_sod_mm: float = 720.0
    default_sid_mm: float = 1100.0
    # If True, reconstruct field area from DAP/Ka,r when available (preferred).
    use_dap_field: bool = True


def _num(series: pd.Series) -> pd.Series:
    """Coerce a column to numeric, robustly.

    Handles Italian decimals (comma), placeholder tokens like '-' or '', and
    already-numeric or mixed-type columns. Any value that cannot be parsed
    becomes NaN instead of raising.
    """
    if pd.api.types.is_numeric_dtype(series):
        return pd.to_numeric(series, errors="coerce")
    # Work entirely on strings so the .str accessor is always valid.
    s = series.astype(str).str.strip()
    s = s.str.replace(",", ".", regex=False)
    # Blank out placeholder / missing tokens.
    s = s.mask(s.isin(["-", "", "--", "n/a", "N/A", "nan", "NaN", "None"]))
    return pd.to_numeric(s, errors="coerce")


def _resolve_columns(df: pd.DataFrame) -> Dict[str, Optional[str]]:
    """Map each logical field to an actual column name present in df (or None)."""
    resolved: Dict[str, Optional[str]] = {}
    lower = {str(c).strip().lower(): c for c in df.columns}
    for key, aliases in COLUMN_ALIASES.items():
        found = None
        for a in aliases:
            if a in df.columns:
                found = a
                break
            if a.strip().lower() in lower:
                found = lower[a.strip().lower()]
                break
        resolved[key] = found
    return resolved


def detect_report_kind(df: pd.DataFrame) -> str:
    """Return 'detailed' (event-level, mappable) or 'cumulative' (summary)."""
    cols = _resolve_columns(df)
    has_event = cols["event_type"] is not None
    has_angles = cols["alpha"] is not None and cols["beta"] is not None
    has_table = cols["table_lat"] is not None and cols["table_height"] is not None
    if has_event and has_angles and has_table:
        return "detailed"
    return "cumulative"


def _score_sheet(df: pd.DataFrame) -> Tuple[int, int]:
    """Score a candidate sheet for how well it fits the detailed-report model.

    Returns (kind_rank, n_resolved_essentials):
      kind_rank = 2 if detailed, 1 if cumulative-with-data, 0 if unusable.
    Higher is better; used to pick the right worksheet in multi-sheet files.
    """
    if df is None or df.empty or df.shape[1] <= 1:
        return (0, 0)
    cols = _resolve_columns(df)
    n_ess = sum(1 for k in ESSENTIAL_LOGICAL if cols.get(k) is not None)
    kind = detect_report_kind(df)
    rank = 2 if kind == "detailed" else (1 if (cols.get("kar") or cols.get("dap")) else 0)
    return (rank, n_ess)


def _read_best_sheet(source) -> pd.DataFrame:
    """Read the worksheet most likely to contain event-level data.

    Many exports carry an empty/near-empty first sheet (e.g. 'Foglio1') plus a
    populated 'Sheet1'. We score every sheet and keep the best one.
    """
    all_sheets = pd.read_excel(source, sheet_name=None)  # dict{name: df}
    if not all_sheets:
        raise ValueError("The workbook contains no worksheets.")
    best_df, best_score = None, (-1, -1)
    for name, sdf in all_sheets.items():
        score = _score_sheet(sdf)
        if score > best_score:
            best_df, best_score = sdf, score
    if best_df is None:
        best_df = next(iter(all_sheets.values()))
    return best_df


def _first_value(df: pd.DataFrame, col: Optional[str], numeric: bool = False):
    if not col or col not in df.columns:
        return None
    s = df[col].dropna()
    if s.empty:
        return None
    if numeric:
        v = _num(s)
        v = v.dropna()
        return float(v.iloc[0]) if len(v) else None
    return str(s.iloc[0])


def _summarize_cumulative(df: pd.DataFrame, cols: Dict[str, Optional[str]]) -> Dict:
    """Build a summary dict for a cumulative/general (non-mappable) report."""
    kar_total = _first_value(df, cols.get("kar_total"), numeric=True)
    dap_total = _first_value(df, cols.get("dap_total"), numeric=True)
    fluoro = _first_value(df, cols.get("fluoro_time"), numeric=True)
    return {
        "kind": "cumulative",
        "rows": int(len(df)),
        "columns": cols,
        "warnings": [],
        "mappable": False,
        "message": (
            "Cumulative/summary report: one row per exam with dose totals only. "
            "It has no per-event tube angles or table positions, so a spatial PSD "
            "map cannot be reconstructed. Use the matching '..._dettaglio' file for mapping."
        ),
        "patient": _first_value(df, cols.get("patient")),
        "exam": _first_value(df, cols.get("exam")),
        "exam_date": _first_value(df, cols.get("exam_date")),
        "sum_kar_gy": kar_total if kar_total is not None else 0.0,
        "sum_dap_gy_cm2": dap_total if dap_total is not None else 0.0,
        "fluoro_time": fluoro,
        "event_types": {},
        "has_collimation": False,
        "has_dap": bool(dap_total is not None),
        "has_sid": False,
        "kar_source": cols.get("kar_total") or "",
    }


def load_excel(source) -> Tuple[pd.DataFrame, Dict]:
    """Read an Excel dose report and normalize key columns.

    Automatically picks the worksheet holding the data (handles workbooks whose
    first sheet is empty). Detailed (event-level) reports are prepared for
    mapping; cumulative/summary reports are loaded with dose totals and flagged
    as non-mappable (summary['mappable'] == False).
    """
    df = _read_best_sheet(source)
    cols = _resolve_columns(df)

    kind = detect_report_kind(df)
    if kind != "detailed":
        # Cumulative/summary report: cannot be mapped, but we still load it and
        # expose the dose totals so no file is "rejected" outright.
        return df, _summarize_cumulative(df, cols)

    missing_logical = [k for k in ESSENTIAL_LOGICAL if cols.get(k) is None]
    if missing_logical:
        friendly = {
            "kar": "reference air kerma ('Kerma in Aria' in Gy)",
            "alpha": "primary tube angle ('Angolazione primaria tubo (LL)')",
            "beta": "secondary tube angle ('Angolazione secondaria tubo (AP)')",
            "sod": "source-isocentre distance ('Distanza sorgente-isocentro')",
            "table_lat": "lateral table position",
            "table_height": "table height",
            "table_lon": "longitudinal table position",
        }
        raise ValueError(
            "Missing essential columns for mapping: "
            + ", ".join(friendly.get(k, k) for k in missing_logical)
        )

    # Drop trailing summary/statistics rows. Some exports append rows whose unit
    # cells read 'media'/'mediana' (means/medians) instead of a real unit.
    summary_tokens = {"media", "mediana", "medio", "sum", "somma", "totale", "total",
                      "min", "max", "sd", "dev.std", "deviazione"}
    for unit_key in ("kar_unit", "dap_unit"):
        uc = cols.get(unit_key)
        if uc is not None and uc in df.columns:
            u = df[uc].astype(str).str.strip().str.lower()
            df = df[~u.isin(summary_tokens)].copy()

    # Normalise numeric columns that exist.
    numeric_keys = ["dap", "kar", "alpha", "beta", "table_lat", "table_height",
                    "table_lon", "sod", "sid", "coll_h", "coll_w", "kvp",
                    "filter_min", "filter_max"]  # kvp/filter for spectral corrections
    for key in numeric_keys:
        c = cols.get(key)
        if c is not None:
            df[c] = _num(df[c])

    # Drop trailing/export-artefact rows without an accession number.
    if cols.get("accession"):
        df = df[df[cols["accession"]].notna()].copy()

    # ---- unit checks (only warn/flag, never hard-fail on formatting) ----
    warnings: List[str] = []
    kar_used_col = cols["kar"]
    if kar_used_col.strip().lower() == "kap":
        warnings.append(
            "Air kerma is being read from a column literally named 'KAP' (unit Gy). "
            "Confirm during commissioning that this is the reference air kerma Ka,r."
        )

    if cols.get("kar_unit"):
        kar_units = {u for u in df[cols["kar_unit"]].dropna().astype(str).str.strip() if u}
        if kar_units and not kar_units.issubset(KAR_UNIT_OK):
            warnings.append(f"Unexpected air-kerma units {sorted(kar_units)} (expected Gy).")
    if cols.get("dap") and cols.get("dap_unit"):
        dap_units = {u.replace(" ", "") for u in df[cols["dap_unit"]].dropna().astype(str).str.strip()}
        ok = {u.replace(" ", "") for u in DAP_UNIT_OK}
        if dap_units and not dap_units.issubset(ok):
            warnings.append(f"Unexpected DAP units {sorted(dap_units)} (expected Gy*cm2).")

    # Canonical working columns.
    df["Ka_r_Gy"] = df[cols["kar"]]
    df["DAP_Gy_cm2"] = df[cols["dap"]] if cols.get("dap") else np.nan

    summary = {
        "kind": kind,
        "mappable": True,
        "rows": int(len(df)),
        "sum_kar_gy": float(pd.to_numeric(df["Ka_r_Gy"], errors="coerce").fillna(0).sum()),
        "sum_dap_gy_cm2": float(pd.to_numeric(df["DAP_Gy_cm2"], errors="coerce").fillna(0).sum()),
        "event_types": (
            df[cols["event_type"]].fillna("Unknown").astype(str).value_counts().to_dict()
            if cols.get("event_type") else {}
        ),
        "columns": cols,
        "warnings": warnings,
        "has_collimation": bool(cols.get("coll_w") and cols.get("coll_h")),
        "has_dap": bool(cols.get("dap")),
        "has_sid": bool(cols.get("sid")),
        "kar_source": kar_used_col,
    }
    return df, summary


def nonzero_median(s: pd.Series, default: float = 0.0) -> float:
    x = _num(s).dropna()
    x = x[x != 0]
    return float(x.median()) if len(x) else float(default)


def field_consistency(df: pd.DataFrame, cols: Dict[str, Optional[str]],
                      reference_offset_mm: float = 150.0) -> Dict:
    """Cross-check observed field area (DAP/Ka,r) vs projected collimation area.

    Only meaningful when collimation columns exist. Returns n=0 otherwise.
    """
    if not (cols.get("coll_w") and cols.get("coll_h") and cols.get("sid")):
        return {"n": 0, "median_ratio": np.nan, "p05": np.nan, "p95": np.nan}
    d = df.copy()
    sod = _num(d[cols["sod"]])
    sid = _num(d[cols["sid"]])
    kar = _num(d["Ka_r_Gy"])
    dap = _num(d["DAP_Gy_cm2"])
    h = _num(d[cols["coll_h"]])
    w = _num(d[cols["coll_w"]])
    mask = (kar > 0) & (dap > 0) & (sod > reference_offset_mm) & (sid > 0) & (h > 0) & (w > 0)
    if not mask.any():
        return {"n": 0, "median_ratio": np.nan, "p05": np.nan, "p95": np.nan}
    observed_area_cm2 = dap[mask] / kar[mask]
    detector_area_cm2 = (h[mask] * w[mask]) / 100.0
    projected_area_cm2 = detector_area_cm2 * ((sod[mask] - reference_offset_mm) / sid[mask]) ** 2
    ratio = observed_area_cm2 / projected_area_cm2
    return {
        "n": int(mask.sum()),
        "median_ratio": float(ratio.median()),
        "p05": float(ratio.quantile(0.05)),
        "p95": float(ratio.quantile(0.95)),
    }


def prepare_events(df: pd.DataFrame, cols: Dict[str, Optional[str]],
                   reference_offset_mm: float = 150.0,
                   fb: Optional[Fallbacks] = None) -> Tuple[List[Dict], Dict]:
    """Turn detailed rows into geometric irradiation events.

    Field size at the reference plane is reconstructed, in priority order:
      1. DAP / Ka,r  (preferred; independent of collimation columns)
      2. collimation columns projected to the reference plane (if present)
      3. a fixed fallback collimation (user configurable)
    """
    fb = fb or Fallbacks()

    ref_lat = nonzero_median(df[cols["table_lat"]])
    ref_height = nonzero_median(df[cols["table_height"]])
    ref_lon = nonzero_median(df[cols["table_lon"]])

    fb_counts = {"dap": 0, "collimation": 0, "fixed": 0}
    events: List[Dict] = []
    omitted = 0

    has_dap = bool(cols.get("dap"))
    has_coll = bool(cols.get("coll_w") and cols.get("coll_h"))
    has_sid = bool(cols.get("sid"))

    for i, row in df.iterrows():
        kar = row.get("Ka_r_Gy")
        dap = row.get("DAP_Gy_cm2") if has_dap else np.nan
        alpha = row.get(cols["alpha"])
        beta = row.get(cols["beta"])
        sod = row.get(cols["sod"])
        sid = row.get(cols["sid"]) if has_sid else np.nan
        lat = row.get(cols["table_lat"])
        height = row.get(cols["table_height"])
        lon = row.get(cols["table_lon"])
        wdet = row.get(cols["coll_w"]) if has_coll else np.nan
        hdet = row.get(cols["coll_h"]) if has_coll else np.nan

        # Fill geometry gaps from fallbacks rather than dropping the event.
        if pd.isna(sod) or sod <= 0:
            sod = fb.default_sod_mm
        if (pd.isna(sid) or sid <= 0):
            sid = fb.default_sid_mm

        essentials = [kar, alpha, beta, lat, height, lon]
        if any(pd.isna(v) for v in essentials) or kar <= 0 or sod <= reference_offset_mm:
            omitted += 1
            continue

        dref = float(sod - reference_offset_mm)
        wref = href = None
        src = None

        # 1) Preferred: field area at reference plane from DAP / Ka,r.
        if fb.use_dap_field and pd.notna(dap) and dap > 0:
            area_ref_mm2 = float(dap / kar) * 100.0  # cm2 -> mm2
            # Aspect ratio from collimation if available, else square.
            if pd.notna(wdet) and pd.notna(hdet) and wdet > 0 and hdet > 0:
                aspect = float(wdet / hdet)
            else:
                aspect = 1.0
            wref = math.sqrt(area_ref_mm2 * aspect)
            href = math.sqrt(area_ref_mm2 / aspect)
            src = "dap"

        # 2) Collimation projected to the reference plane.
        if (not wref or not href) and has_coll and pd.notna(wdet) and pd.notna(hdet) and wdet > 0 and hdet > 0:
            wref = float(wdet) * dref / float(sid)
            href = float(hdet) * dref / float(sid)
            src = "collimation"

        # 3) Fixed fallback collimation.
        if not wref or not href:
            wref = float(fb.fixed_coll_w_mm) * dref / float(sid)
            href = float(fb.fixed_coll_h_mm) * dref / float(sid)
            src = "fixed"

        fb_counts[src] += 1

        kvp_val = row.get(cols["kvp"]) if cols.get("kvp") else np.nan

        # Optional event-specific added filtration. Some structured Excel exports
        # provide minimum/maximum filter thickness plus material; use their mean
        # thickness when available. Values are assumed to be in mm.
        fmin = pd.to_numeric(row.get(cols["filter_min"]), errors="coerce") if cols.get("filter_min") else np.nan
        fmax = pd.to_numeric(row.get(cols["filter_max"]), errors="coerce") if cols.get("filter_max") else np.nan
        fmat = str(row.get(cols["filter_material"], "")) if cols.get("filter_material") else ""
        vals = [float(v) for v in (fmin, fmax) if pd.notna(v)]
        fmean = float(sum(vals) / len(vals)) if vals else np.nan
        mat_l = fmat.strip().lower()
        added_cu_mm = fmean if pd.notna(fmean) and ("copper" in mat_l or "rame" in mat_l or mat_l == "cu") else np.nan
        added_al_mm = fmean if pd.notna(fmean) and ("aluminium" in mat_l or "aluminum" in mat_l or "alluminio" in mat_l or mat_l == "al") else np.nan

        # Equivalent square field side at the reference plane (cm), used to
        # drive the field-size dependence of the spectral k_bs / k_med.
        field_side_cm = math.sqrt(max(wref * href, 0.0)) / 10.0

        events.append({
            "row": int(i) + 2,
            "kar": float(kar),
            "dap": float(dap) if pd.notna(dap) else np.nan,
            "alpha": float(alpha),
            "beta": float(beta),
            "sod": float(sod),
            "dref": dref,
            "lat": float(lat),
            "height": float(height),
            "lon": float(lon),
            "wref": float(wref),
            "href": float(href),
            "field_side_cm": float(field_side_cm),
            "kvp": float(kvp_val) if pd.notna(kvp_val) else np.nan,
            "added_cu_mm": float(added_cu_mm) if pd.notna(added_cu_mm) else np.nan,
            "added_al_mm": float(added_al_mm) if pd.notna(added_al_mm) else np.nan,
            "field_src": src,
            "type": str(row.get(cols["event_type"], "")) if cols.get("event_type") else "",
            "protocol": str(row.get(cols["protocol"], "")) if cols.get("protocol") else "",
        })

    meta = {
        "ref_lat": ref_lat,
        "ref_height": ref_height,
        "ref_lon": ref_lon,
        "omitted": omitted,
        "used": len(events),
        "field_source_counts": fb_counts,
    }
    return events, meta


@dataclass
class Phantom:
    """Patient phantom description.

    model:
        "cylinder"  -> parametric elliptic cylinder (default, unwrappable to a
                       2D heat-map). Uses width_mm / ap_mm / length_mm and the
                       n_theta / n_z grid resolution.
        "male" / "female" -> anthropomorphic surface mesh loaded from the
                       reduced STL phantoms shipped in ./phantom_data. These are
                       the same meshes PySkinDose uses (adult male/female).
                       They give an irregular set of skin cells (no unwrapped
                       heat-map) and are scaled to the requested torso size.
    """
    model: str = "cylinder"
    width_mm: float = 360.0
    ap_mm: float = 240.0
    length_mm: float = 800.0
    n_theta: int = 180
    n_z: int = 240
    # Anthropomorphic-only: uniform scale applied to the STL (1.0 = native size,
    # native adult male ~ 1740 mm tall). Kept separate so the cylinder controls
    # stay meaningful.
    human_scale: float = 1.0

    @property
    def is_human(self) -> bool:
        return self.model in ("male", "female")


# STL phantom files. Prefer the full-resolution meshes (~27k triangles) for a
# dense, well-resolved skin-dose surface; fall back to the reduced meshes.
_HUMAN_STL = {
    "male": ["adult_male.stl", "adult_male_reduced_1000t.stl"],
    "female": ["adult_female.stl", "adult_female_reduced_1000t.stl"],
}


def _resolve_human_stl(model: str) -> str:
    candidates = _HUMAN_STL.get(model)
    if candidates is None:
        raise ValueError(f"Unknown human phantom model: {model}")
    base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "phantom_data")
    for fname in candidates:
        p = os.path.join(base, fname)
        if os.path.exists(p):
            return p
    raise FileNotFoundError(
        f"Anthropomorphic phantom '{model}' not found in {base}. "
        f"Expected one of {candidates}."
    )


def _load_human_cells(phantom: Phantom):
    """Load an anthropomorphic phantom as a set of skin cells + a draw mesh.

    Skin cells are the UNIQUE MESH VERTICES (one dose value per vertex), which
    lets us colour the body surface directly (Mesh3d intensity per vertex) for a
    smooth, visible dose map. Returns:
        P     : (n_vert, 3) vertex positions (mm) = skin-cell locations
        N     : (n_vert, 3) outward unit normals at the vertices
        faces : (n_tri, 3) integer vertex indices for the triangles
    Coordinates: x=lateral, y=AP (anterior +), z=longitudinal, in mm.
    """
    from stl import mesh as _stl_mesh  # local import; optional dependency

    path = _resolve_human_stl(phantom.model)
    m = _stl_mesh.Mesh.from_file(path)
    tri = np.asarray(m.vectors, dtype=float) * 10.0 * float(phantom.human_scale)  # cm->mm
    tri_normals = np.asarray(m.normals, dtype=float)

    n_tri = tri.shape[0]
    flat = tri.reshape(-1, 3)                      # (3*n_tri, 3)

    # Weld duplicate vertices so shared triangle corners become one skin cell.
    key = np.round(flat, 2)                        # 0.01 mm tolerance
    _, inverse, uniq_idx = _unique_rows(key)
    P = flat[uniq_idx]                             # unique vertex positions
    faces = inverse.reshape(n_tri, 3)              # triangles as vertex indices

    # Vertex normals: average the (area-weighted) triangle normals meeting there.
    tn = tri_normals.copy()
    tlen = np.linalg.norm(tn, axis=1, keepdims=True)
    tlen[tlen == 0] = 1.0
    tn = tn / tlen
    N = np.zeros_like(P)
    for c in range(3):
        np.add.at(N, faces[:, c], tn)
    nlen = np.linalg.norm(N, axis=1, keepdims=True)
    nlen[nlen == 0] = 1.0
    N = N / nlen

    # Orient normals outward (away from the body central axis in the x-y plane).
    centre = np.array([P[:, 0].mean(), P[:, 1].mean(), 0.0])
    radial = P - centre
    radial[:, 2] = 0.0
    flip = np.sum(N * radial, axis=1) < 0.0
    N[flip] *= -1.0

    # Recentre the whole phantom (same offset applied to vertices, so the dose
    # surface and the body always overlap).
    offset = np.array([
        P[:, 0].mean(),
        (P[:, 1].max() + P[:, 1].min()) / 2.0,
        (P[:, 2].max() + P[:, 2].min()) / 2.0,
    ])
    P = P - offset

    return P, N, faces


def _unique_rows(a: np.ndarray):
    """Return (unique_rows, inverse_indices, first_occurrence_indices)."""
    order = np.lexsort(a.T[::-1])
    a_sorted = a[order]
    diff = np.any(a_sorted[1:] != a_sorted[:-1], axis=1)
    flag = np.concatenate(([True], diff))
    uniq_sorted_idx = order[flag]
    # group id for each sorted row, then scatter back to original order
    group = np.cumsum(flag) - 1
    inverse = np.empty(len(a), dtype=int)
    inverse[order] = group
    unique = a[uniq_sorted_idx]
    return unique, inverse, uniq_sorted_idx


@dataclass
class Corrections:
    bsf: float = 1.35
    tissue_f: float = 1.06          # MEAC / MAEC ratio (skin/air)
    support_transmission: float = 1.0  # TAF at 0 deg (table + pad)
    kar_calibration: float = 1.0    # CF
    # Fθ oblique factor: relative transmission at oblique incidence through the
    # table/pad. Modelled as taf^(1/cos - 1) when the beam traverses the support.
    use_oblique_factor: bool = True

    # ---- table/pad attenuation model ------------------------------------
    # The user chooses whether to apply table attenuation at all. Three modes:
    #   "none"      -> no table attenuation (transmission = 1.0). Use when the
    #                  effect is unknown / not commissioned.
    #   "measured"  -> apply a measured transmission value (support_transmission,
    #                  i.e. TAF at 0 deg) that the user has actually measured for
    #                  their unit. This is the recommended, defensible option.
    #   "spectral"  -> use the tabulated, kVp-dependent table transmission k_tab
    #                  from the spectral module (only when use_spectral is on).
    table_mode: str = "none"

    # ---- spectral (PySkinDose-style) corrections ------------------------
    # When enabled, BSF and MEAC (tissue_f) are replaced per-event by
    # beam-quality / field-size dependent factors (Benmakhlouf 2011),
    # falling back to the constants above when kVp/HVL data is missing.
    use_spectral: bool = False
    spectral: object = None  # SpectralCorrections instance (or None)

    @property
    def product(self) -> float:
        """Constant correction product (used when spectral mode is off)."""
        return self.bsf * self.tissue_f * self.support_transmission * self.kar_calibration

    def _table_transmission(self, kvp: Optional[float], beam_through_table: bool) -> float:
        """Table/pad transmission for one event, per the selected table_mode.

        Returns 1.0 (no attenuation) for beams that do not traverse the support,
        regardless of mode.
        """
        if not beam_through_table:
            return 1.0
        if self.table_mode == "measured":
            return float(self.support_transmission)
        if self.table_mode == "spectral" and self.use_spectral and self.spectral is not None:
            return float(self.spectral.k_tab(kvp))
        # "none" or spectral unavailable
        return 1.0

    def event_factors(self, kvp: Optional[float], field_side_cm: Optional[float],
                      beam_through_table: bool,
                      added_cu_mm: Optional[float] = None,
                      added_al_mm: Optional[float] = None) -> Tuple[float, float, float, float]:
        """Return (bsf, meac, support_transmission, cf) for one event.

        BSF/MEAC follow the spectral model when enabled (constants otherwise).
        Table transmission is independent and follows table_mode, so the user
        can e.g. use spectral MEAC but a measured table transmission, or no
        table attenuation at all. CF is always a constant.
        """
        if not (self.use_spectral and self.spectral is not None):
            support = self._table_transmission(kvp, beam_through_table)
            return self.bsf, self.tissue_f, support, self.kar_calibration

        sc = self.spectral
        cu = None if added_cu_mm is None or not np.isfinite(added_cu_mm) else float(added_cu_mm)
        al = None if added_al_mm is None or not np.isfinite(added_al_mm) else float(added_al_mm)
        hvl = sc.estimate_hvl(kvp, added_cu_mm=cu, added_al_mm=al)
        bsf = sc.k_bs(kvp, hvl, field_side_cm)
        meac = sc.k_med(kvp, hvl, field_side_cm)
        if not beam_through_table:
            support = 1.0
        elif self.table_mode == "spectral":
            support = float(sc.k_tab(kvp, added_cu_mm=cu, added_al_mm=al))
        elif self.table_mode == "measured":
            support = float(self.support_transmission)
        else:
            support = 1.0
        return bsf, meac, support, self.kar_calibration


def build_spectral_corrections(cfg: Optional["SpectralConfig"] = None):
    """Factory that returns a SpectralCorrections instance, or None if the
    optional module/data is unavailable."""
    if SpectralCorrections is None:
        return None
    try:
        return SpectralCorrections(cfg)
    except Exception:
        return None


@dataclass
class GeometrySettings:
    lateral_sign: float = -1.0
    height_sign: float = -1.0
    longitudinal_sign: float = -1.0
    offset_x_mm: float = 0.0
    offset_y_mm: float = 0.0
    offset_z_mm: float = 0.0


def _beam_axes(alpha_deg: float, beta_deg: float):
    a = math.radians(alpha_deg)
    b = math.radians(beta_deg)
    # At 0/0, source is below the supine patient and beam points posterior -> anterior (+y).
    d = np.array([math.sin(a) * math.cos(b), math.cos(a) * math.cos(b), math.sin(b)], dtype=float)
    d /= np.linalg.norm(d)
    e1 = np.array([math.cos(a), -math.sin(a), 0.0], dtype=float)
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(e1, d)
    e2 /= np.linalg.norm(e2)
    return d, e1, e2


def _oblique_factor(corr: Corrections, d: np.ndarray, taf: float) -> float:
    """Fθ: extra table/pad attenuation for beams that traverse the support obliquely.

    ``taf`` is the *same event-specific normal-incidence transmission* that is
    multiplied into the dose. This matters in spectral table mode, where TAF can
    vary with beam quality. The model follows SkinCare Eq. (5):
    Fθ = TAF**(sec(theta)-1).
    """
    if not corr.use_oblique_factor:
        return 1.0
    dy = float(d[1])
    if dy <= 0:  # beam does not traverse the patient support
        return 1.0
    cos_inc = min(1.0, max(1e-3, dy))
    if not np.isfinite(taf) or taf >= 1.0 or taf <= 0.0:
        return 1.0
    return float(taf ** (1.0 / cos_inc - 1.0))


def make_skin_grid(phantom: Phantom):
    theta = np.linspace(-math.pi, math.pi, phantom.n_theta, endpoint=False)
    z = np.linspace(-phantom.length_mm / 2, phantom.length_mm / 2, phantom.n_z)
    TH, Z = np.meshgrid(theta, z, indexing="xy")
    a = phantom.width_mm / 2.0
    b = phantom.ap_mm / 2.0
    X = a * np.cos(TH)
    Y = b * np.sin(TH)
    P = np.stack([X, Y, Z], axis=-1).reshape(-1, 3)

    nx = np.cos(TH) / a
    ny = np.sin(TH) / b
    norm = np.sqrt(nx * nx + ny * ny)
    nx /= norm
    ny /= norm
    N = np.stack([nx, ny, np.zeros_like(nx)], axis=-1).reshape(-1, 3)
    return theta, z, TH, Z, X, Y, P, N


def _accumulate_dose(events: List[Dict], meta: Dict, corr: Corrections,
                     geom: GeometrySettings, P: np.ndarray, N: np.ndarray):
    """Accumulate skin dose over an arbitrary set of skin cells (P, N).

    Shared by the cylinder and anthropomorphic phantoms.
    """
    dose = np.zeros(P.shape[0], dtype=float)
    event_hits = 0
    for e in events:
        d, e1, e2 = _beam_axes(e["alpha"], e["beta"])
        beam_through_table = float(d[1]) > 0.0
        bsf, meac, support, cf = corr.event_factors(
            kvp=e.get("kvp"), field_side_cm=e.get("field_side_cm"),
            beam_through_table=beam_through_table,
            added_cu_mm=e.get("added_cu_mm"), added_al_mm=e.get("added_al_mm"),
        )
        f_theta = _oblique_factor(corr, d, support)
        corr_product = bsf * meac * support * cf
        q = np.array([
            geom.lateral_sign * (e["lat"] - meta["ref_lat"]) + geom.offset_x_mm,
            geom.height_sign * (e["height"] - meta["ref_height"]) + geom.offset_y_mm,
            geom.longitudinal_sign * (e["lon"] - meta["ref_lon"]) + geom.offset_z_mm,
        ], dtype=float)
        source = q - e["sod"] * d
        V = P - source
        t = V @ d
        u = V @ e1
        v = V @ e2
        incidence = (N @ d) < 0.0  # keep entrance surface, reject exit surface
        scale = np.maximum(t, 1e-9) / e["dref"]
        inside = (
            (t > 0) & incidence &
            (np.abs(u) <= 0.5 * e["wref"] * scale) &
            (np.abs(v) <= 0.5 * e["href"] * scale)
        )
        if np.any(inside):
            dose[inside] += e["kar"] * (e["dref"] / t[inside]) ** 2 * corr_product * f_theta
            event_hits += 1
    return dose, event_hits


def calculate_map(events: List[Dict], meta: Dict, phantom: Phantom, corr: Corrections, geom: GeometrySettings):
    """Compute the skin-dose map for either a cylinder or a human phantom."""
    if phantom.is_human:
        return _calculate_map_human(events, meta, phantom, corr, geom)

    theta, z, TH, Z, X, Y, P, N = make_skin_grid(phantom)
    dose, event_hits = _accumulate_dose(events, meta, corr, geom, P, N)

    dose2d = dose.reshape(phantom.n_z, phantom.n_theta)
    peak_flat = int(np.argmax(dose))
    peak_iz, peak_it = np.unravel_index(peak_flat, dose2d.shape)
    peak = {
        "psd_gy": float(dose2d[peak_iz, peak_it]),
        "theta_deg": float(np.degrees(theta[peak_it])),
        "z_mm": float(z[peak_iz]),
        "x_mm": float(X[peak_iz, peak_it]),
        "y_mm": float(Y[peak_iz, peak_it]),
        "iz": int(peak_iz),
        "it": int(peak_it),
    }
    return {
        "kind": "cylinder",
        "theta": theta, "z": z, "TH": TH, "Z": Z, "X": X, "Y": Y,
        "dose": dose2d, "peak": peak, "event_hits": event_hits,
    }


def _calculate_map_human(events: List[Dict], meta: Dict, phantom: Phantom,
                         corr: Corrections, geom: GeometrySettings):
    """Skin-dose map on an anthropomorphic mesh phantom (male/female)."""
    P, N, faces = _load_human_cells(phantom)
    dose, event_hits = _accumulate_dose(events, meta, corr, geom, P, N)

    peak_idx = int(np.argmax(dose))
    peak = {
        "psd_gy": float(dose[peak_idx]),
        "x_mm": float(P[peak_idx, 0]),
        "y_mm": float(P[peak_idx, 1]),
        "z_mm": float(P[peak_idx, 2]),
        "idx": peak_idx,
        # normal at the peak cell, used by event_contributions_at_peak
        "nx": float(N[peak_idx, 0]),
        "ny": float(N[peak_idx, 1]),
        "nz": float(N[peak_idx, 2]),
    }
    return {
        "kind": "human",
        "P": P, "N": N, "faces": faces, "dose": dose,
        "peak": peak, "event_hits": event_hits,
    }


def event_contributions_at_peak(events: List[Dict], meta: Dict, phantom: Phantom, corr: Corrections,
                                geom: GeometrySettings, peak: Dict) -> pd.DataFrame:
    p = np.array([peak["x_mm"], peak["y_mm"], peak["z_mm"]], dtype=float)
    if phantom.is_human and "nx" in peak:
        # Use the stored mesh normal at the peak cell.
        n = np.array([peak["nx"], peak["ny"], peak["nz"]], dtype=float)
    else:
        a = phantom.width_mm / 2.0
        b = phantom.ap_mm / 2.0
        n = np.array([p[0] / (a * a), p[1] / (b * b), 0.0], dtype=float)
    n /= np.linalg.norm(n)
    out = []

    for e in events:
        d, e1, e2 = _beam_axes(e["alpha"], e["beta"])
        beam_through_table = float(d[1]) > 0.0
        bsf, meac, support, cf = corr.event_factors(
            kvp=e.get("kvp"), field_side_cm=e.get("field_side_cm"),
            beam_through_table=beam_through_table,
            added_cu_mm=e.get("added_cu_mm"), added_al_mm=e.get("added_al_mm"),
        )
        f_theta = _oblique_factor(corr, d, support)
        corr_product = bsf * meac * support * cf
        q = np.array([
            geom.lateral_sign * (e["lat"] - meta["ref_lat"]) + geom.offset_x_mm,
            geom.height_sign * (e["height"] - meta["ref_height"]) + geom.offset_y_mm,
            geom.longitudinal_sign * (e["lon"] - meta["ref_lon"]) + geom.offset_z_mm,
        ], dtype=float)
        source = q - e["sod"] * d
        V = p - source
        t = float(V @ d)
        if t <= 0 or float(n @ d) >= 0:
            continue
        u = float(V @ e1)
        v = float(V @ e2)
        scale = t / e["dref"]
        if abs(u) <= 0.5 * e["wref"] * scale and abs(v) <= 0.5 * e["href"] * scale:
            dose = e["kar"] * (e["dref"] / t) ** 2 * corr_product * f_theta
            out.append({
                "Excel row": e["row"], "Dose at peak (Gy)": dose, "Ka,r (Gy)": e["kar"],
                "Primary angle (deg)": e["alpha"], "Secondary angle (deg)": e["beta"],
                "kVp": e.get("kvp"), "BSF": bsf, "MEAC": meac, "Table transm.": support,
                "Field source": e["field_src"], "Type": e["type"], "Protocol": e["protocol"],
            })
    return pd.DataFrame(out).sort_values("Dose at peak (Gy)", ascending=False) if out else pd.DataFrame()
