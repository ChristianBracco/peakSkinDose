"""Run the PSD_Mapper engine on EVAR.xlsx in both constant and spectral modes."""
from psd_engine import (
    load_excel, prepare_events, Phantom, Corrections, GeometrySettings,
    Fallbacks, calculate_map, build_spectral_corrections,
)
from spectral_corrections import SpectralConfig

PATH = r"d:\PeakSkinDoseCOnfronto\PSD_Mapper_v0_1\Report strutturati dettagliati\EVAR.xlsx"

df, summary = load_excel(PATH)
print("kind:", summary["kind"], "mappable:", summary.get("mappable"))
print("rows:", summary["rows"], "sum Ka,r:", round(summary["sum_kar_gy"], 4),
      "Gy   sum DAP:", round(summary["sum_dap_gy_cm2"], 1), "Gy*cm2")
print("has_dap:", summary["has_dap"], "has_sid:", summary["has_sid"],
      "kar_source:", summary["kar_source"])
for w in summary.get("warnings", []):
    print("WARN:", w)

cols = summary["columns"]
fb = Fallbacks(use_dap_field=summary["has_dap"])
events, meta = prepare_events(df, cols, reference_offset_mm=150.0, fb=fb)
print("\nusable events:", meta["used"], "omitted:", meta["omitted"])
print("field-source counts:", meta["field_source_counts"])
print("ref table (lat,height,lon):", round(meta["ref_lat"], 1),
      round(meta["ref_height"], 1), round(meta["ref_lon"], 1))

phantom = Phantom(width_mm=360.0, ap_mm=240.0, length_mm=800.0, n_theta=180, n_z=240)
geom = GeometrySettings()

# --- constant mode (legacy) ---
corr_c = Corrections(bsf=1.35, tissue_f=1.06, support_transmission=1.0,
                     kar_calibration=1.0, use_oblique_factor=True, use_spectral=False)
res_c = calculate_map(events, meta, phantom, corr_c, geom)
print("\n[CONSTANT]  PSD = %.4f Gy   (product=%.3f)  event_hits=%d"
      % (res_c["peak"]["psd_gy"], corr_c.product, res_c["event_hits"]))
print("            peak theta=%.1f deg  z=%.0f mm"
      % (res_c["peak"]["theta_deg"], res_c["peak"]["z_mm"]))

# --- spectral mode (PySkinDose model) ---
cfg = SpectralConfig(enabled=True, default_kvp=77.0, default_inherent_mmal=3.0,
                     default_added_cu_mm=0.0, default_added_al_mm=0.0,
                     device_model="AlluraClarity", acquisition_plane="Single Plane",
                     const_bsf=1.35, const_med=1.06, const_tab=1.0)
spec = build_spectral_corrections(cfg)
corr_s = Corrections(kar_calibration=1.0, use_oblique_factor=True,
                     use_spectral=True, spectral=spec)
res_s = calculate_map(events, meta, phantom, corr_s, geom)
print("\n[SPECTRAL]  PSD = %.4f Gy   event_hits=%d"
      % (res_s["peak"]["psd_gy"], res_s["event_hits"]))
print("            peak theta=%.1f deg  z=%.0f mm"
      % (res_s["peak"]["theta_deg"], res_s["peak"]["z_mm"]))
print("            spectral sources:", spec.summary()["sources"])

print("\nspectral / constant PSD ratio = %.3f"
      % (res_s["peak"]["psd_gy"] / max(res_c["peak"]["psd_gy"], 1e-12)))
