"""Run the *real* PySkinDose engine on the EVAR Excel report.

The Italian structured report is not an RDSR DICOM, so we build the normalized
DataFrame (data_norm) that PySkinDose expects directly from the Excel columns,
then call pyskindose.calculate_dose. Units are converted mm->cm as PySkinDose
works in cm. Field size at the detector is reconstructed from DAP/Ka,r (same
information the PSD_Mapper uses), projected to the detector plane.
"""
import os
import sys
import json
import numpy as np
import pandas as pd

# --- make pyskindose importable -------------------------------------------
PSK_SRC = r"d:\PeakSkinDoseCOnfronto\PySkinDose-master\src"
sys.path.insert(0, PSK_SRC)

from pyskindose.settings import PyskindoseSettings
from pyskindose.calculate_dose.calculate_dose import calculate_dose
from pyskindose.phantom_class import Phantom
from pyskindose.helpers.calculate_rotation_matrices import calculate_rotation_matrices
import pyskindose.constants as c

EXCEL = r"d:\PeakSkinDoseCOnfronto\PSD_Mapper_v0_1\Report strutturati dettagliati\EVAR.xlsx"
CORR_DB = os.path.join(PSK_SRC, "pyskindose", "corrections.db")


def num(s):
    return pd.to_numeric(s.astype(str).str.replace(",", ".", regex=False), errors="coerce")


def build_data_norm(df: pd.DataFrame) -> pd.DataFrame:
    n = len(df)
    dn = pd.DataFrame(index=range(n))

    # geometry (mm -> cm)
    dsd = num(df["Distanza sorgente-detettore"]).fillna(1100.0) / 10.0
    dsi = num(df["Distanza sorgente-isocentro"]).fillna(720.0) / 10.0
    dn["model"] = "AXIOM-Artis"                    # matches k_tab 'Single Plane'
    dn["DSD"] = dsd
    dn["DSI"] = dsi
    dn["DID"] = dn["DSD"] - dn["DSI"]
    dn[c.DATA_DS_IRP] = dn["DSI"] - 15.0           # DSIRP = DSI - 15 cm

    dn["acquisition_type"] = df["Tipo evento irradiazione"].astype(str)
    dn["acquisition_plane"] = "Single Plane"

    # table translations (mm -> cm). PySkinDose axes:
    #   Tx = longitudinal, Ty = vertical (height), Tz = lateral
    dn["Tx"] = num(df["Posizione longitudinale tavolo"]).fillna(0.0) / 10.0
    dn["Ty"] = num(df["Altezza del tavolo"]).fillna(0.0) / 10.0
    dn["Tz"] = num(df["Posizione laterale del tavolo"]).fillna(0.0) / 10.0
    dn["At1"] = 0
    dn["At2"] = 0
    dn["At3"] = 0

    # beam angulation
    dn["Ap1"] = num(df["Angolazione primaria tubo (LL)"]).fillna(0.0)
    dn["Ap2"] = num(df["Angolazione secondaria tubo (AP)"]).fillna(0.0)
    dn["Ap3"] = 0

    # detector side length (cm)
    dn["DSL"] = 40.0

    # --- field size at the detector plane, reconstructed from DAP / Ka,r ----
    kar = num(df["Kerma in Aria"])          # Gy at IRP
    dap = num(df["DAP"])                     # Gy*cm2
    # field area at the IRP plane (cm2)
    area_irp_cm2 = (dap / kar).replace([np.inf, -np.inf], np.nan)
    side_irp_cm = np.sqrt(area_irp_cm2.clip(lower=1.0))
    d_irp = dn[c.DATA_DS_IRP].values
    # project the square field from the IRP plane to the detector plane
    fs_det = side_irp_cm.values * (dn["DSD"].values / np.where(d_irp > 0, d_irp, np.nan))
    fs_det = np.nan_to_num(fs_det, nan=20.0)
    fs_det = np.clip(fs_det, 5.0, 40.0)
    dn["FS_lat"] = fs_det
    dn["FS_long"] = fs_det

    # spectrum
    dn["kVp"] = num(df["KVP"]).fillna(77.0)
    dn[c.DATA_KEY_NORMALIZATION_AIR_KERMA if hasattr(c, "DATA_KEY_NORMALIZATION_AIR_KERMA") else "K_IRP"] = (
        kar.fillna(0.0) * 1000.0  # Gy -> mGy
    )

    # filtration (mm). Report gives min/max thickness + material (Copper).
    fmin = num(df["Spessore minimo del filtro"]).fillna(0.0)
    fmax = num(df["Spessore massimo del filtro"]).fillna(0.0)
    fmean = (fmin + fmax) / 2.0
    mat = df["Materiale del filtro"].astype(str).str.lower()
    is_cu = mat.str.contains("copper") | mat.str.contains("cu")
    dn["filter_thickness_Cu"] = np.where(is_cu, fmean, 0.0)
    dn["filter_thickness_Al"] = np.where(is_cu, 0.0, fmean)

    return dn


def make_settings() -> PyskindoseSettings:
    example = os.path.join(PSK_SRC, "pyskindose", "settings_example.json")
    s = json.loads(open(example, encoding="utf-8").read())
    s["mode"] = c.MODE_CALCULATE_DOSE
    s["estimate_k_tab"] = False           # use the measured table transmission
    s["inherent_filtration"] = 3.1        # for HVL lookup
    s["phantom"]["model"] = "cylinder"
    # widen/lengthen cylinder to a torso-like size comparable to the mapper's
    # 360x240 mm ellipse: radii a=18 cm, b=12 cm, length 80 cm
    s["phantom"]["dimension"]["cylinder_radii_a"] = 18
    s["phantom"]["dimension"]["cylinder_radii_b"] = 12
    s["phantom"]["dimension"]["cylinder_length"] = 80
    s["phantom"]["dimension"]["cylinder_resolution"] = "dense"
    s["corrections_db_path"] = CORR_DB
    return PyskindoseSettings(json.dumps(s))


def main():
    df = pd.read_excel(EXCEL)
    print("events:", len(df))
    dn = build_data_norm(df)
    print("data_norm columns:", list(dn.columns))
    print("K_IRP sum (mGy):", round(dn["K_IRP"].sum(), 1),
          "= %.4f Gy" % (dn["K_IRP"].sum() / 1000.0))
    print("kVp range:", dn["kVp"].min(), "-", dn["kVp"].max())
    print("FS_det range (cm):", round(float(dn["FS_lat"].min()), 1), "-",
          round(float(dn["FS_lat"].max()), 1))
    print("Cu filtration median (mm):", float(dn["filter_thickness_Cu"].median()))

    # Add the table rotation matrices (Rx, Ry, Rz) that phantom.position needs.
    # In the normal RDSR flow this is done inside check_new_geometry; here we
    # build data_norm manually, so we add them explicitly.
    dn = calculate_rotation_matrices(dn)

    settings = make_settings()

    # table and pad phantoms
    table = Phantom(phantom_model="table", phantom_dim=settings.phantom.dimension)
    pad = Phantom(phantom_model="pad", phantom_dim=settings.phantom.dimension)

    patient, output = calculate_dose(
        normalized_data=dn, settings=settings, table=table, pad=pad
    )

    dose_map = output[c.OUTPUT_KEY_DOSE_MAP]
    # PySkinDose carries K_IRP in mGy, so the dose map is in mGy -> convert to Gy.
    psd_mgy = float(np.max(dose_map))
    psd = psd_mgy / 1000.0
    print("\n[PYSKINDOSE]  PSD = %.4f Gy  (%.1f mGy)" % (psd, psd_mgy))
    print("              cells: %d   cells hit (>0): %d"
          % (len(dose_map), int(np.sum(dose_map > 0))))

    # report mean of the applied per-event corrections for context
    kbs = output[c.OUTPUT_KEY_CORRECTION_BACK_SCATTER]
    kmed = output[c.OUTPUT_KEY_CORRECTION_MEDIUM]
    ktab = output[c.OUTPUT_KEY_CORRECTION_TABLE]
    def _meanflat(x):
        vals = []
        for e in x:
            arr = np.atleast_1d(np.asarray(e, dtype=float))
            if arr.size:
                vals.append(float(np.mean(arr)))
        return float(np.mean(vals)) if vals else float("nan")
    print("              mean k_bs=%.3f  k_med=%.3f  k_tab=%.3f"
          % (_meanflat(kbs), _meanflat(kmed), _meanflat(ktab)))


if __name__ == "__main__":
    main()
