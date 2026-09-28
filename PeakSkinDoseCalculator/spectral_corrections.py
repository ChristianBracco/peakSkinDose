"""Spectral (beam-quality / field-size dependent) correction factors.

This module ports the correction model used by PySkinDose so that the
PSD_Mapper can, per irradiation event, compute:

    * k_bs  : backscatter factor            = f(kVp, HVL, field side length)
    * k_med : air -> water (MEAC) ratio     = f(kVp, HVL, field side length)
    * k_tab : patient-support transmission  = f(kVp, filtration, model, plane)

using the Benmakhlouf dose-conversion/backscatter formalism used by PySkinDose.
Primary reference: Benmakhlouf et al., Phys Med Biol 2011;56:7179-7204,
doi:10.1088/0031-9155/56/22/012. The related 2013 paper
(Phys Med Biol 58:247-260, doi:10.1088/0031-9155/58/2/247) addresses the
influence of phantom thickness/material on backscatter factors.

Everything degrades gracefully. The Italian event reports the PSD_Mapper reads
usually contain, at best, a KVP column and no HVL / filtration / device model.
So each factor is computed at the most detailed level the data supports and
otherwise falls back, in order, to:

    1. full spectral lookup (kVp + HVL + field size)         -- best
    2. spectral lookup with an *estimated* HVL from kVp       -- good
    3. spectral lookup with a fixed default kVp               -- ok
    4. the user-supplied constant factor (legacy behaviour)   -- fallback

The class :class:`SpectralCorrections` is the public entry point. It caches
the lookup tables (loaded once from ``correction_data``) and exposes
``k_bs``, ``k_med`` and ``k_tab`` methods plus ``estimate_hvl``.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Optional

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_DATA_DIR = os.path.join(_HERE, "correction_data")

# Tabulated field side lengths (cm) used by the Benmakhlouf backscatter model.
FSL_TAB = np.array([5.0, 10.0, 20.0, 25.0, 35.0])

# Benmakhlouf backscatter polynomial coefficients (eq. 8 of the paper), one
# column per tabulated field side length in FSL_TAB. Identical to the array in
# PySkinDose corrections.calculate_k_bs.
_BS_COEFF = np.array(
    [
        [+1.00870e0, +9.29969e-1, +8.65442e-1, +8.58665e-1, +8.57065e-1],
        [+2.35816e-3, +4.08549e-3, +5.36739e-3, +5.51579e-3, +5.55933e-3],
        [-9.48937e-6, -1.66271e-5, -2.21494e-5, -2.27532e-5, -2.28004e-5],
        [+1.03143e-1, +1.53605e-1, +1.72418e-1, +1.70826e-1, +1.66418e-1],
        [-1.04881e-3, -1.45187e-3, -1.46088e-3, -1.38540e-3, -1.28180e-3],
        [+3.59731e-6, +5.05312e-6, +5.17430e-6, +4.91192e-6, +4.53036e-6],
        [-7.31303e-3, -9.32427e-3, -8.30138e-3, -7.64330e-3, -6.81574e-3],
        [+7.93272e-5, +9.40568e-5, +7.13576e-5, +6.13126e-5, +4.94197e-5],
        [-2.74296e-7, -3.28449e-7, -2.54885e-7, -2.21399e-7, -1.79074e-7],
    ]
)


@dataclass
class SpectralConfig:
    """User-controllable spectral-correction behaviour and fallbacks."""

    enabled: bool = True

    # Fallback beam quality when the event has no usable kVp.
    default_kvp: float = 77.0
    # Fixed filtration assumptions used to estimate HVL when the report has no
    # filtration columns (typical interventional beam: ~3 mmAl inherent,
    # ~0.2 mmCu added). These only matter for the HVL estimate.
    default_inherent_mmal: float = 3.0
    default_added_cu_mm: float = 0.0
    default_added_al_mm: float = 0.0
    default_anode_angle_deg: int = 11

    # Device selection for the table/pad transmission lookup.
    device_model: str = "AlluraClarity"
    acquisition_plane: str = "Plane A"

    # Legacy constant factors, used when a spectral value cannot be obtained at
    # all (no table, or spectral disabled). These mirror the old Corrections
    # defaults so behaviour is unchanged when spectral mode is off.
    const_bsf: float = 1.35
    const_med: float = 1.06
    const_tab: float = 1.00

    # If True, still apply the constant BSF/MEAC on top of nothing when the
    # spectral lookup fails; if False, spectral failure returns the constant.
    # (Kept explicit for clarity; both branches return the constant.)


def _read_csv(name: str) -> Optional[pd.DataFrame]:
    path = os.path.join(_DATA_DIR, name)
    if not os.path.exists(path):
        return None
    try:
        return pd.read_csv(path)
    except Exception:
        return None


class SpectralCorrections:
    """Compute per-event k_bs, k_med, k_tab with graceful fallbacks."""

    def __init__(self, cfg: Optional[SpectralConfig] = None):
        self.cfg = cfg or SpectralConfig()
        self._med = _read_csv("k_med.csv")
        self._tab = _read_csv("k_tab.csv")
        self._hvl = _read_csv("hvl.csv")
        # Track, for diagnostics, which fallback level each factor used.
        self.notes: dict = {"k_bs": set(), "k_med": set(), "k_tab": set(), "hvl": set()}

    # ---- availability flags -------------------------------------------------
    @property
    def has_med_table(self) -> bool:
        return self._med is not None and not self._med.empty

    @property
    def has_tab_table(self) -> bool:
        return self._tab is not None and not self._tab.empty

    @property
    def has_hvl_table(self) -> bool:
        return self._hvl is not None and not self._hvl.empty

    # ---- HVL estimate -------------------------------------------------------
    def estimate_hvl(self, kvp: Optional[float],
                     inherent_mmal: Optional[float] = None,
                     added_cu_mm: Optional[float] = None,
                     added_al_mm: Optional[float] = None) -> Optional[float]:
        """Best-effort HVL (mmAl) for the given beam.

        Priority:
          1. direct lookup in the SpekPy-simulated HVL table (kVp + filtration)
          2. a smooth empirical fit HVL ~= a + b*kVp when the table is missing
        Returns None only if kVp itself is unknown.
        """
        if kvp is None or not np.isfinite(kvp) or kvp <= 0:
            return None

        inh = self.cfg.default_inherent_mmal if inherent_mmal is None else inherent_mmal
        cu = self.cfg.default_added_cu_mm if added_cu_mm is None else added_cu_mm
        al = self.cfg.default_added_al_mm if added_al_mm is None else added_al_mm

        if self.has_hvl_table:
            df = self._hvl
            # nearest kVp and nearest filtration entries
            sub = df[df["anode_angle_deg"] == self.cfg.default_anode_angle_deg]
            if sub.empty:
                sub = df
            k = _nearest(sub["kvp_kv"].values, kvp)
            sub = sub[sub["kvp_kv"] == k]
            # nearest inherent, Cu, Al
            for col, val in (("filtration_inherent_mmal", inh),
                             ("filtration_added_mmcu", cu),
                             ("filtration_added_mmal", al)):
                if sub[col].nunique() > 1:
                    nv = _nearest(sub[col].values, val)
                    sub = sub[np.isclose(sub[col].values, nv)]
            if not sub.empty:
                self.notes["hvl"].add("table")
                return float(sub["hvl_mmal"].iloc[0])

        # Empirical fallback: a monotone kVp->HVL relation for a ~3 mmAl-eq
        # interventional beam. Added Cu hardens the beam, so add a term.
        self.notes["hvl"].add("empirical")
        hvl = 0.7 + 0.031 * float(kvp)          # ~2.6 mmAl @ 60 kVp, 5.3 @ 150
        hvl += 3.0 * float(cu)                    # ~+0.3 mmAl per 0.1 mmCu
        return max(0.5, hvl)

    # ---- backscatter --------------------------------------------------------
    def k_bs(self, kvp: Optional[float], hvl: Optional[float],
             field_side_cm: Optional[float]) -> float:
        """Benmakhlouf backscatter factor.

        Falls back to the constant BSF if kVp/HVL cannot be resolved.
        """
        if not self.cfg.enabled:
            return self.cfg.const_bsf

        eff_kvp = kvp if (kvp and np.isfinite(kvp) and kvp > 0) else self.cfg.default_kvp
        if kvp and np.isfinite(kvp) and kvp > 0:
            self.notes["k_bs"].add("kvp")
        else:
            self.notes["k_bs"].add("default_kvp")

        eff_hvl = hvl
        if eff_hvl is None or not np.isfinite(eff_hvl) or eff_hvl <= 0:
            eff_hvl = self.estimate_hvl(eff_kvp)
        if eff_hvl is None:
            self.notes["k_bs"].add("const")
            return self.cfg.const_bsf

        # bs values at the five tabulated field sizes (eq. 8).
        c = _BS_COEFF
        bs = (
            (c[0] + c[1] * eff_kvp + c[2] * eff_kvp ** 2)
            + (c[3] + c[4] * eff_kvp + c[5] * eff_kvp ** 2) * eff_hvl
            + (c[6] + c[7] * eff_kvp + c[8] * eff_kvp ** 2) * eff_hvl ** 2
        )

        fsl = field_side_cm
        if fsl is None or not np.isfinite(fsl) or fsl <= 0:
            fsl = 20.0  # a sensible mid-range default field
            self.notes["k_bs"].add("default_field")
        # clamp then interpolate (PySkinDose uses a cubic spline; linear on the
        # 5 knots is within a fraction of a percent and needs no scipy).
        fsl = float(np.clip(fsl, FSL_TAB[0], FSL_TAB[-1]))
        return float(np.interp(fsl, FSL_TAB, bs))

    # ---- air -> medium ------------------------------------------------------
    def k_med(self, kvp: Optional[float], hvl: Optional[float],
              field_side_cm: Optional[float]) -> float:
        """MEAC (mu_en/rho) air->water ratio from the tabulated data."""
        if not self.cfg.enabled or not self.has_med_table:
            return self.cfg.const_med

        eff_kvp = kvp if (kvp and np.isfinite(kvp) and kvp > 0) else self.cfg.default_kvp
        eff_hvl = hvl
        if eff_hvl is None or not np.isfinite(eff_hvl) or eff_hvl <= 0:
            eff_hvl = self.estimate_hvl(eff_kvp)
        if eff_hvl is None:
            self.notes["k_med"].add("const")
            return self.cfg.const_med

        fsl = field_side_cm if (field_side_cm and np.isfinite(field_side_cm) and field_side_cm > 0) else 20.0
        df = self._med
        # nearest tabulated field side length
        fsl_sel = _nearest(FSL_TAB, fsl)
        sub = df[df["field_side_length_cm"] == fsl_sel]
        if sub.empty:
            self.notes["k_med"].add("const")
            return self.cfg.const_med
        # nearest kVp
        k = _nearest(sub["kvp_kv"].values, eff_kvp)
        sub = sub[sub["kvp_kv"] == k]
        # nearest HVL
        idx = (sub["hvl_mmal"] - eff_hvl).abs().idxmin()
        self.notes["k_med"].add("table")
        return float(sub.loc[idx, "mu_en_quotient"])

    # ---- table / pad transmission ------------------------------------------
    def k_tab(self, kvp: Optional[float],
              added_cu_mm: Optional[float] = None,
              added_al_mm: Optional[float] = None) -> float:
        """Patient-support transmission at normal incidence.

        Uses the measured PySkinDose table for the configured device/plane.
        Falls back to the constant transmission if no match is found.
        """
        if not self.cfg.enabled or not self.has_tab_table:
            return self.cfg.const_tab

        df = self._tab
        cu = self.cfg.default_added_cu_mm if added_cu_mm is None else added_cu_mm
        al = self.cfg.default_added_al_mm if added_al_mm is None else added_al_mm
        eff_kvp = kvp if (kvp and np.isfinite(kvp) and kvp > 0) else self.cfg.default_kvp

        sub = df[
            (df["device_model"] == self.cfg.device_model)
            & (df["acquisition_plane"] == self.cfg.acquisition_plane)
        ]
        if sub.empty:
            # try model alone, then any row
            sub = df[df["device_model"] == self.cfg.device_model]
        if sub.empty:
            self.notes["k_tab"].add("const")
            return self.cfg.const_tab

        # nearest filtration, then nearest kVp
        for col, val in (("filtration_added_mmcu", cu), ("filtration_added_mmal", al)):
            if col in sub.columns and sub[col].nunique() > 1:
                nv = _nearest(sub[col].values, val)
                sub = sub[np.isclose(sub[col].values, nv)]
        if sub.empty:
            self.notes["k_tab"].add("const")
            return self.cfg.const_tab
        k = _nearest(sub["kvp_kv"].values, eff_kvp)
        row = sub[sub["kvp_kv"] == k]
        self.notes["k_tab"].add("table")
        return float(row["k_patient_support"].iloc[0])

    # ---- diagnostics --------------------------------------------------------
    def summary(self) -> dict:
        return {
            "enabled": self.cfg.enabled,
            "has_med_table": self.has_med_table,
            "has_tab_table": self.has_tab_table,
            "has_hvl_table": self.has_hvl_table,
            "device_model": self.cfg.device_model,
            "acquisition_plane": self.cfg.acquisition_plane,
            "sources": {k: sorted(v) for k, v in self.notes.items()},
        }


def _nearest(values, target):
    """Return the entry in ``values`` closest to ``target``."""
    arr = np.asarray(values, dtype=float)
    return float(arr[int(np.argmin(np.abs(arr - float(target))))])
