# PSD Mapper v0.1 — Excel prototype

Local prototype for estimating peak skin dose (PSD) and displaying 2D/3D skin-dose maps from the event-level Excel export used in this project.

## Important

This is a **commissioning/research prototype**, not a clinically validated dosimetry system. Validate geometry, Ka,r calibration, table/pad attenuation, backscatter and tissue conversion before clinical use.

## Dose model (per literature)

Peak skin dose is computed following Johnson & Bolch (2011, *Med. Phys.*) and
Krajinović et al. (2021, *J. Appl. Clin. Med. Phys.* 22(2):145–157, SkinCare):

```
Dose = Ka,r · CF · TAF · Fθ · (d_IRP / d_patient)² · BSF · MEAC
```

- `Ka,r` — reference air kerma at the interventional reference point (IRP)
- `CF` — Ka,r calibration factor
- `TAF` — table/pad transmission at 0° incidence
- `Fθ` — oblique factor for extra table/pad attenuation at non-zero incidence
- `(d_IRP / d_patient)²` — inverse-square correction from the reference point to the skin
- `BSF` — backscatter factor
- `MEAC` — air-to-soft-tissue mass energy-absorption coefficient ratio

Each event is projected as a four-sided pyramid (apex at the source, base at the
reference plane) onto an elliptical-cylinder patient model; only entrance-surface
points inside the beam are scored.

## Report types

Two report shapes exist in `Report strutturati dettagliati`:

- **Detailed (event-level)** — e.g. `Coronarografia.xlsx`, `EVAR.xlsx`, `PTCA.xlsx`,
  `Embolizzazione.xlsx`. One row per irradiation event. **These are mappable.**
- **Cumulative / general** — e.g. `*_cumulativo.xlsx`, `*_generale.xlsx`. One row per
  exam summary. These are rejected with an explanatory message.

## What the importer expects

The app reads the first worksheet and resolves columns by name (with aliases):

- `Kerma in Aria` **in Gy** → reference air kerma Ka,r (legacy fallback: a column named `KAP`)
- `DAP` in Gy·cm²
- primary and secondary tube angles
- lateral / height / longitudinal table positions
- source-isocentre and source-detector distances
- irradiation event type / protocol

## Fallbacks for missing columns

The supplied reports contain **no collimation columns**, so field size is handled
in this priority order per event:

1. **DAP / Ka,r** — field area at the reference plane (preferred; used for all
   supplied files). Aspect ratio taken from collimation columns if present, else square.
2. **Collimation columns** projected to the reference plane, if present.
3. **Fixed fallback collimation** (configurable in the sidebar) when neither is usable.

Geometry gaps are also filled: if `Distanza sorgente-isocentro` or
`Distanza sorgente-detettore` is missing/zero for an event, configurable default
distances are used instead of dropping the event. Essential columns (Ka,r, angles,
table positions) that are entirely absent produce a clear error rather than a silent
wrong result.

## Install on Windows

1. Install Python 3.11 or newer.
2. Open Command Prompt in this folder.
3. Run:

   `python -m pip install -r requirements.txt`

4. Start with:

   `run_windows.bat`

or:

   `python -m streamlit run app.py`

The browser app runs locally on the computer. The uploaded Excel is processed locally by Streamlit; the app contains no network-upload code.

## Current geometry model

- Supine patient represented by an elliptical cylinder.
- Each event is represented by a rectangular pyramidal X-ray beam.
- Primary/secondary angles rotate the beam in 3D.
- Relative table motions move the beam with respect to the patient.
- Only entrance-surface mesh points are scored.
- Ka,r is corrected by inverse square from the reference point to each skin point.
- Dose is multiplied by user-configurable BSF, MEAC (air-to-tissue) ratio, table/pad
  transmission (TAF), Ka,r calibration (CF) and the oblique table factor Fθ.

## Current limitations

- Anatomical position is relative, not absolute.
- Patient contour is simplified.
- Angle and table-axis conventions still need commissioning against the actual angiography system.
- BSF/MEAC can be beam-quality dependent when the spectral module and its tables are available; otherwise explicit constant fallbacks are used. Table/pad transmission still requires system-specific commissioning.
- No uncertainty budget yet.
- No DICOM/RDSR cross-check yet.

## Next validation step

Perform a simple phantom test with one AP field and several known LAO/RAO and CRA/CAU fields, recording the Excel export and measuring field position/dose with film or dosimeters. Use that to lock the axis signs, reference origin and dose correction model.
