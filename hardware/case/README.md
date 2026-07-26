# Case

The Reco Kit enclosure is a 3D-printed case (PETG-CF or ASA) that holds the Jetson and both camera modules at the fixed stereo geometry the calibration assumes.

## Files

The printable case is split into parts (`reco-kit-case-*.stl`): main body, top, bottom, bracket, battery mount, insulation, thermoform, and extra parts. Print in **PETG-CF or ASA** (ASA is tougher and better outdoors, but harder to print and needs more careful handling).

Still to add: print settings (layer height, walls, infill, supports, orientation) and the parametric STEP source.

## Design notes to capture when adding the files

- The two camera cutouts fix the baseline and convergence angle of the stereo pair. Changing them changes calibration, so document the intended geometry.
- Cooling: the Jetson Orin Nano dev kit's active fan is more than enough in testing. The design keeps the fan's airflow outside the sealed case, so the electronics stay weather-resistant.
- Mount: how the case attaches to a pole or tripod at sideline height.
