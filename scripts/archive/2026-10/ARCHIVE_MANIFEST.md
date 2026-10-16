# Archive manifest: scripts and scratch, 2026-10

Archived 2026-10-16 (batch 1a, Owner decision 2026-10-16). Pure git mv; nothing deleted. Pre-move ref: archive/2026-10-16-batch-1a-pre.

Target layout: scripts/<rel> -> scripts/archive/2026-10/<rel>; scratch/<rel> and scripts/scratch/<rel> -> scripts/archive/2026-10/scratch/<rel>. Scripts that wrote output to docs/reports/ by default would now do so relative to their old path; they are archived, not maintained.

Evidence: ~/Workspace/nexus-handoffs/2026-10-13-online-ab/ARCHIVE_CLASSIFICATION_20261016.md (and _toplevel.tsv); re-verified by git grep of basename and path at archive time (only descriptive docs/inventory mentions remain).

Files: 359

| original path | new path | class | last commit | evidence |
|---|---|---|---|---|
| scratch/ask_next_task_and_commit.py | scripts/archive/2026-10/scratch/ask_next_task_and_commit.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-20 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/ask_next_task.py | scripts/archive/2026-10/scratch/ask_next_task.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-20 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_12907/core.py | scripts/archive/2026-10/scratch/astropy_12907/core.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/__init__.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/__init__.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/angle_formats.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/angle_formats.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/angle_lextab.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/angle_lextab.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/angle_parsetab.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/angle_parsetab.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/angle_utilities.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/angle_utilities.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/angles.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/angles.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/attributes.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/attributes.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/builtin_frames/__init__.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/builtin_frames/__init__.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/builtin_frames/altaz.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/builtin_frames/altaz.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/builtin_frames/baseradec.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/builtin_frames/baseradec.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/builtin_frames/cirs_observed_transforms.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/builtin_frames/cirs_observed_transforms.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/builtin_frames/cirs.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/builtin_frames/cirs.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/builtin_frames/ecliptic_transforms.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/builtin_frames/ecliptic_transforms.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/builtin_frames/ecliptic.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/builtin_frames/ecliptic.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/builtin_frames/equatorial.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/builtin_frames/equatorial.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/builtin_frames/fk4_fk5_transforms.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/builtin_frames/fk4_fk5_transforms.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/builtin_frames/fk4.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/builtin_frames/fk4.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/builtin_frames/fk5.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/builtin_frames/fk5.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/builtin_frames/galactic_transforms.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/builtin_frames/galactic_transforms.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/builtin_frames/galactic.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/builtin_frames/galactic.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/builtin_frames/galactocentric.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/builtin_frames/galactocentric.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/builtin_frames/gcrs.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/builtin_frames/gcrs.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/builtin_frames/hadec.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/builtin_frames/hadec.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/builtin_frames/hcrs.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/builtin_frames/hcrs.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/builtin_frames/icrs_cirs_transforms.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/builtin_frames/icrs_cirs_transforms.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/builtin_frames/icrs_fk5_transforms.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/builtin_frames/icrs_fk5_transforms.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/builtin_frames/icrs_observed_transforms.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/builtin_frames/icrs_observed_transforms.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/builtin_frames/icrs.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/builtin_frames/icrs.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/builtin_frames/lsr.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/builtin_frames/lsr.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/builtin_frames/skyoffset.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/builtin_frames/skyoffset.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/builtin_frames/supergalactic_transforms.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/builtin_frames/supergalactic_transforms.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/builtin_frames/supergalactic.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/builtin_frames/supergalactic.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/builtin_frames/utils.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/builtin_frames/utils.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/calculation.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/calculation.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/data/constellation_data_roman87.dat | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/data/constellation_data_roman87.dat | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/data/constellation_names.dat | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/data/constellation_names.dat | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/data/sites.json | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/data/sites.json | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/distances.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/distances.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/earth_orientation.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/earth_orientation.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/erfa_astrom.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/erfa_astrom.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/errors.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/errors.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/jparser.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/jparser.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/matching.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/matching.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/matrix_utilities.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/matrix_utilities.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/name_resolve.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/name_resolve.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/orbital_elements.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/orbital_elements.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/sky_coordinate_parsers.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/sky_coordinate_parsers.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/solar_system.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/solar_system.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/spectral_coordinate.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/spectral_coordinate.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/spectral_quantity.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/spectral_quantity.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/tests/__init__.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/tests/__init__.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/tests/accuracy/__init__.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/tests/accuracy/__init__.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/tests/accuracy/data/fk4_no_e_fk4.csv | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/tests/accuracy/data/fk4_no_e_fk4.csv | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/tests/accuracy/data/fk4_no_e_fk5.csv | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/tests/accuracy/data/fk4_no_e_fk5.csv | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/tests/accuracy/data/galactic_fk4.csv | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/tests/accuracy/data/galactic_fk4.csv | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/tests/accuracy/data/icrs_fk5.csv | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/tests/accuracy/data/icrs_fk5.csv | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/tests/accuracy/data/rv.ecsv | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/tests/accuracy/data/rv.ecsv | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/tests/accuracy/generate_ref_ast.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/tests/accuracy/generate_ref_ast.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/tests/accuracy/generate_spectralcoord_ref.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/tests/accuracy/generate_spectralcoord_ref.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/tests/accuracy/test_altaz_icrs.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/tests/accuracy/test_altaz_icrs.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/tests/accuracy/test_ecliptic.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/tests/accuracy/test_ecliptic.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/tests/accuracy/test_fk4_no_e_fk4.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/tests/accuracy/test_fk4_no_e_fk4.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/tests/accuracy/test_fk4_no_e_fk5.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/tests/accuracy/test_fk4_no_e_fk5.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/tests/accuracy/test_galactic_fk4.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/tests/accuracy/test_galactic_fk4.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/tests/accuracy/test_icrs_fk5.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/tests/accuracy/test_icrs_fk5.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/tests/test_angle_generators.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/tests/test_angle_generators.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/tests/test_angles.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/tests/test_angles.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/tests/test_angular_separation.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/tests/test_angular_separation.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/tests/test_api_ape5.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/tests/test_api_ape5.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/tests/test_arrays.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/tests/test_arrays.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/tests/test_atc_replacements.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/tests/test_atc_replacements.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/tests/test_celestial_transformations.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/tests/test_celestial_transformations.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/tests/test_distance.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/tests/test_distance.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/tests/test_earth_orientation.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/tests/test_earth_orientation.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/tests/test_earth.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/tests/test_earth.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/tests/test_erfa_astrom.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/tests/test_erfa_astrom.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/tests/test_finite_difference_velocities.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/tests/test_finite_difference_velocities.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/tests/test_formatting.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/tests/test_formatting.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/tests/test_frames_with_velocity.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/tests/test_frames_with_velocity.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/tests/test_frames.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/tests/test_frames.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/tests/test_funcs.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/tests/test_funcs.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/tests/test_geodetic_representations.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/tests/test_geodetic_representations.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/tests/test_iau_fullstack.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/tests/test_iau_fullstack.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/tests/test_icrs_observed_transformations.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/tests/test_icrs_observed_transformations.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/tests/test_matching.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/tests/test_matching.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/tests/test_matrix_utilities.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/tests/test_matrix_utilities.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/tests/test_name_resolve.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/tests/test_name_resolve.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/tests/test_regression.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/tests/test_regression.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/tests/test_representation_arithmetic.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/tests/test_representation_arithmetic.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/tests/test_representation_methods.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/tests/test_representation_methods.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/tests/test_representation.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/tests/test_representation.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/tests/test_shape_manipulation.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/tests/test_shape_manipulation.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/tests/test_sites.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/tests/test_sites.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/tests/test_sky_coord_velocities.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/tests/test_sky_coord_velocities.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/tests/test_skyoffset_transformations.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/tests/test_skyoffset_transformations.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/tests/test_solar_system.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/tests/test_solar_system.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/tests/test_spectral_coordinate.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/tests/test_spectral_coordinate.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/tests/test_spectral_quantity.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/tests/test_spectral_quantity.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/tests/test_transformations.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/tests/test_transformations.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/tests/test_unit_representation.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/tests/test_unit_representation.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/astropy_emulation/coordinates/tests/test_velocity_corrs.py | scripts/archive/2026-10/scratch/astropy_emulation/coordinates/tests/test_velocity_corrs.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/audit_formal_evidence.py | scripts/archive/2026-10/scratch/audit_formal_evidence.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-20 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/audit_tracked_changes.py | scripts/archive/2026-10/scratch/audit_tracked_changes.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-20 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/benchmark_all_models.py | scripts/archive/2026-10/scratch/benchmark_all_models.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-14 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/check_task_detail.py | scripts/archive/2026-10/scratch/check_task_detail.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-20 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/compare_advisor_and_coder.py | scripts/archive/2026-10/scratch/compare_advisor_and_coder.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-14 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/context_slicer.py | scripts/archive/2026-10/scratch/context_slicer.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-20 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/debug_localizer.py | scripts/archive/2026-10/scratch/debug_localizer.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-06 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/diagnose_reanchor.py | scripts/archive/2026-10/scratch/diagnose_reanchor.py | ARCHIVE (top-level scratch/, batch 1) | 2026-07-08 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/execute_cleanup.py | scripts/archive/2026-10/scratch/execute_cleanup.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-20 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/execute_codeintel_graph_builder_commit_gate.py | scripts/archive/2026-10/scratch/execute_codeintel_graph_builder_commit_gate.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-20 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/execute_delivery_models_commit_gate.py | scripts/archive/2026-10/scratch/execute_delivery_models_commit_gate.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-20 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/execute_duplicate_adr_cleanup.py | scripts/archive/2026-10/scratch/execute_duplicate_adr_cleanup.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-20 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/execute_formal_commit.py | scripts/archive/2026-10/scratch/execute_formal_commit.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-20 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/execute_local_model_policy_commit_gate.py | scripts/archive/2026-10/scratch/execute_local_model_policy_commit_gate.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-20 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/execute_modified_split.py | scripts/archive/2026-10/scratch/execute_modified_split.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-20 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/execute_pipeline_metadata_commit_gate.py | scripts/archive/2026-10/scratch/execute_pipeline_metadata_commit_gate.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-20 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/execute_precise_delete.py | scripts/archive/2026-10/scratch/execute_precise_delete.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-20 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/execute_restore_generated.py | scripts/archive/2026-10/scratch/execute_restore_generated.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-20 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/execute_runtime_review.py | scripts/archive/2026-10/scratch/execute_runtime_review.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-20 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/execute_s2t_export_guard_commit_gate.py | scripts/archive/2026-10/scratch/execute_s2t_export_guard_commit_gate.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-20 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/execute_strategy_envelope_commit_gate.py | scripts/archive/2026-10/scratch/execute_strategy_envelope_commit_gate.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-20 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/execute_submodule_dirty_state_audit.py | scripts/archive/2026-10/scratch/execute_submodule_dirty_state_audit.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-20 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/get_complete_gpt_reply.py | scripts/archive/2026-10/scratch/get_complete_gpt_reply.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-20 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/local_heal_batch_readiness_review.py | scripts/archive/2026-10/scratch/local_heal_batch_readiness_review.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-20 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/parse_to_md.py | scripts/archive/2026-10/scratch/parse_to_md.py | ARCHIVE (top-level scratch/, batch 1) | 2026-07-08 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/patch_14b_clean.py | scripts/archive/2026-10/scratch/patch_14b_clean.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/patch_attributes.py | scripts/archive/2026-10/scratch/patch_attributes.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/patch_skycoord.py | scripts/archive/2026-10/scratch/patch_skycoord.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/phase3_test_review_packet.py | scripts/archive/2026-10/scratch/phase3_test_review_packet.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-20 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/phase4_rust_main_gate.py | scripts/archive/2026-10/scratch/phase4_rust_main_gate.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-20 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/phase5_docs_evidence_review.py | scripts/archive/2026-10/scratch/phase5_docs_evidence_review.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-20 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/qdp_buggy.py | scripts/archive/2026-10/scratch/qdp_buggy.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-06 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/run_all_matrix.py | scripts/archive/2026-10/scratch/run_all_matrix.py | ARCHIVE (top-level scratch/, batch 1) | 2026-07-05 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/run_anchored_repairs.py | scripts/archive/2026-10/scratch/run_anchored_repairs.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-20 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/run_b1e_c13453.py | scripts/archive/2026-10/scratch/run_b1e_c13453.py | ARCHIVE (top-level scratch/, batch 1) | 2026-07-08 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/run_b2c_12b_gated.py | scripts/archive/2026-10/scratch/run_b2c_12b_gated.py | ARCHIVE (top-level scratch/, batch 1) | 2026-07-08 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/run_b4c_constrained.py | scripts/archive/2026-10/scratch/run_b4c_constrained.py | ARCHIVE (top-level scratch/, batch 1) | 2026-07-08 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/run_b6_autonomous.py | scripts/archive/2026-10/scratch/run_b6_autonomous.py | ARCHIVE (top-level scratch/, batch 1) | 2026-07-08 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/run_c3_curve.py | scripts/archive/2026-10/scratch/run_c3_curve.py | ARCHIVE (top-level scratch/, batch 1) | 2026-07-08 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/run_g6_c12481.py | scripts/archive/2026-10/scratch/run_g6_c12481.py | ARCHIVE (top-level scratch/, batch 1) | 2026-07-08 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/run_g6_c13453.py | scripts/archive/2026-10/scratch/run_g6_c13453.py | ARCHIVE (top-level scratch/, batch 1) | 2026-07-08 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/run_heal.sh | scripts/archive/2026-10/scratch/run_heal.sh | ARCHIVE (top-level scratch/, batch 1) | 2026-06-06 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/run_l7_benchmark.py | scripts/archive/2026-10/scratch/run_l7_benchmark.py | ARCHIVE (top-level scratch/, batch 1) | 2026-07-08 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/run_m2_prompt_upgrade.py | scripts/archive/2026-10/scratch/run_m2_prompt_upgrade.py | ARCHIVE (top-level scratch/, batch 1) | 2026-07-08 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/run_m3_benchmark.py | scripts/archive/2026-10/scratch/run_m3_benchmark.py | ARCHIVE (top-level scratch/, batch 1) | 2026-07-08 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/run_m3_m6_c13453.py | scripts/archive/2026-10/scratch/run_m3_m6_c13453.py | ARCHIVE (top-level scratch/, batch 1) | 2026-07-08 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/run_n2_prompt_benchmark.py | scripts/archive/2026-10/scratch/run_n2_prompt_benchmark.py | ARCHIVE (top-level scratch/, batch 1) | 2026-07-08 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/run_o2_o3.py | scripts/archive/2026-10/scratch/run_o2_o3.py | ARCHIVE (top-level scratch/, batch 1) | 2026-07-08 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/run_only_ollama_bench.py | scripts/archive/2026-10/scratch/run_only_ollama_bench.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-14 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/run_p11_hard_tasks.py | scripts/archive/2026-10/scratch/run_p11_hard_tasks.py | ARCHIVE (top-level scratch/, batch 1) | 2026-07-08 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/run_p13a_correction.py | scripts/archive/2026-10/scratch/run_p13a_correction.py | ARCHIVE (top-level scratch/, batch 1) | 2026-07-08 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/run_p13b_hardened_contract.py | scripts/archive/2026-10/scratch/run_p13b_hardened_contract.py | ARCHIVE (top-level scratch/, batch 1) | 2026-07-08 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/run_p2_council_benchmark.py | scripts/archive/2026-10/scratch/run_p2_council_benchmark.py | ARCHIVE (top-level scratch/, batch 1) | 2026-07-08 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/run_q2_swarm.py | scripts/archive/2026-10/scratch/run_q2_swarm.py | ARCHIVE (top-level scratch/, batch 1) | 2026-07-08 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/run_qdp_tests.py | scripts/archive/2026-10/scratch/run_qdp_tests.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-06 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/run_real_repairs.py | scripts/archive/2026-10/scratch/run_real_repairs.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-20 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/run_x4_c13453.py | scripts/archive/2026-10/scratch/run_x4_c13453.py | ARCHIVE (top-level scratch/, batch 1) | 2026-07-08 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/scan_cleanup_candidates.py | scripts/archive/2026-10/scratch/scan_cleanup_candidates.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-20 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/set_gpt_msg.py | scripts/archive/2026-10/scratch/set_gpt_msg.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-20 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/smoke_test_models.py | scripts/archive/2026-10/scratch/smoke_test_models.py | ARCHIVE (top-level scratch/, batch 1) | 2026-07-08 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/smoke_test_ornith_v3.py | scripts/archive/2026-10/scratch/smoke_test_ornith_v3.py | ARCHIVE (top-level scratch/, batch 1) | 2026-07-08 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/smoke_test_ornith.py | scripts/archive/2026-10/scratch/smoke_test_ornith.py | ARCHIVE (top-level scratch/, batch 1) | 2026-07-08 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/spa_protocol_interface_context_gate.py | scripts/archive/2026-10/scratch/spa_protocol_interface_context_gate.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-20 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/spb_localizer_repomap_compactor_gate.py | scripts/archive/2026-10/scratch/spb_localizer_repomap_compactor_gate.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-20 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/spc_reproduction_planning_gate.py | scripts/archive/2026-10/scratch/spc_reproduction_planning_gate.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-20 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/test_14b_patch.py | scripts/archive/2026-10/scratch/test_14b_patch.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/test_ast_speed.py | scripts/archive/2026-10/scratch/test_ast_speed.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-06 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/test_exc.py | scripts/archive/2026-10/scratch/test_exc.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/test_getattr.py | scripts/archive/2026-10/scratch/test_getattr.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/test_pregate_verification.py | scripts/archive/2026-10/scratch/test_pregate_verification.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-13 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/test_property.py | scripts/archive/2026-10/scratch/test_property.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/test_pure_prop.py | scripts/archive/2026-10/scratch/test_pure_prop.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/test_skycoord.py | scripts/archive/2026-10/scratch/test_skycoord.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/test_tsp_refinement_skycoord.py | scripts/archive/2026-10/scratch/test_tsp_refinement_skycoord.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/test_tsp_refinement.py | scripts/archive/2026-10/scratch/test_tsp_refinement.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/verify_bug_14096_local.py | scripts/archive/2026-10/scratch/verify_bug_14096_local.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-20 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/verify_bug_14096.py | scripts/archive/2026-10/scratch/verify_bug_14096.py | ARCHIVE (top-level scratch/, batch 1) | 2026-06-01 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scratch/write_predictions.py | scripts/archive/2026-10/scratch/write_predictions.py | ARCHIVE (top-level scratch/, batch 1) | 2026-05-30 | scratch/ dir row in ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv: only generic runtime-path mentions |
| scripts/bench/capability_flash_tasks_v1.json | scripts/archive/2026-10/bench/capability_flash_tasks_v1.json | STALE (batch 1) | 2026-04-26 | no caller found |
| scripts/bench/evaluate_sidecar_shadow.py | scripts/archive/2026-10/bench/evaluate_sidecar_shadow.py | STALE (batch 1) | 2026-06-14 | no caller found |
| scripts/bench/experimental/formal_fused_from_pilot.py | scripts/archive/2026-10/bench/experimental/formal_fused_from_pilot.py | STALE (batch 1) | 2026-07-17 | no caller found |
| scripts/bench/experimental/run_apple_fm_worker_pool.py | scripts/archive/2026-10/bench/experimental/run_apple_fm_worker_pool.py | STALE (batch 1) | 2026-09-28 | no caller found |
| scripts/bench/gate3_canonical_eval_v2.py | scripts/archive/2026-10/bench/gate3_canonical_eval_v2.py | STALE (batch 1) | 2026-07-12 | no caller found |
| scripts/bench/line_span_patch_protocol_v1.py | scripts/archive/2026-10/bench/line_span_patch_protocol_v1.py | STALE (batch 1) | 2026-06-20 | no caller found |
| scripts/bench/n30r_c1_verifier_evidence.py | scripts/archive/2026-10/bench/n30r_c1_verifier_evidence.py | STALE (batch 1) | 2026-07-10 | no caller found |
| scripts/bench/n30r_v1_live_7b_trace.py | scripts/archive/2026-10/bench/n30r_v1_live_7b_trace.py | STALE (batch 1) | 2026-10-12 | no caller found |
| scripts/bench/public_benchmark_manifest.schema.json | scripts/archive/2026-10/bench/public_benchmark_manifest.schema.json | STALE (batch 1) | 2026-05-14 | no caller found |
| scripts/bench/rebuild_bf_probe.py | scripts/archive/2026-10/bench/rebuild_bf_probe.py | STALE (batch 1) | 2026-06-21 | no caller found |
| scripts/bench/rebuild_bg_compression.py | scripts/archive/2026-10/bench/rebuild_bg_compression.py | STALE (batch 1) | 2026-06-21 | no caller found |
| scripts/bench/run_aa1_generalization.py | scripts/archive/2026-10/bench/run_aa1_generalization.py | STALE (batch 1) | 2026-06-21 | no caller found |
| scripts/bench/run_aa2_stress.py | scripts/archive/2026-10/bench/run_aa2_stress.py | STALE (batch 1) | 2026-06-21 | no caller found |
| scripts/bench/run_ab1_definition.py | scripts/archive/2026-10/bench/run_ab1_definition.py | STALE (batch 1) | 2026-06-21 | no caller found |
| scripts/bench/run_ab2_benchmark.py | scripts/archive/2026-10/bench/run_ab2_benchmark.py | STALE (batch 1) | 2026-06-21 | no caller found |
| scripts/bench/run_c_15000_regression.py | scripts/archive/2026-10/bench/run_c_15000_regression.py | STALE (batch 1) | 2026-06-21 | no caller found |
| scripts/bench/run_c_15010_regression.py | scripts/archive/2026-10/bench/run_c_15010_regression.py | STALE (batch 1) | 2026-06-21 | no caller found |
| scripts/bench/run_c_15020_regression.py | scripts/archive/2026-10/bench/run_c_15020_regression.py | STALE (batch 1) | 2026-06-21 | no caller found |
| scripts/bench/run_c_15030_regression.py | scripts/archive/2026-10/bench/run_c_15030_regression.py | STALE (batch 1) | 2026-06-21 | no caller found |
| scripts/bench/run_c_15040_regression.py | scripts/archive/2026-10/bench/run_c_15040_regression.py | STALE (batch 1) | 2026-06-21 | no caller found |
| scripts/bench/run_c_15050_regression.py | scripts/archive/2026-10/bench/run_c_15050_regression.py | STALE (batch 1) | 2026-06-21 | no caller found |
| scripts/bench/run_c_15060_regression.py | scripts/archive/2026-10/bench/run_c_15060_regression.py | STALE (batch 1) | 2026-06-21 | no caller found |
| scripts/bench/run_c_15070_regression.py | scripts/archive/2026-10/bench/run_c_15070_regression.py | STALE (batch 1) | 2026-06-21 | no caller found |
| scripts/bench/run_c_15080_regression.py | scripts/archive/2026-10/bench/run_c_15080_regression.py | STALE (batch 1) | 2026-06-21 | no caller found |
| scripts/bench/run_c_15090_regression.py | scripts/archive/2026-10/bench/run_c_15090_regression.py | STALE (batch 1) | 2026-06-21 | no caller found |
| scripts/bench/run_c_15100_regression.py | scripts/archive/2026-10/bench/run_c_15100_regression.py | STALE (batch 1) | 2026-06-21 | no caller found |
| scripts/bench/run_c_15110_regression.py | scripts/archive/2026-10/bench/run_c_15110_regression.py | STALE (batch 1) | 2026-06-21 | no caller found |
| scripts/bench/run_c_15120_regression.py | scripts/archive/2026-10/bench/run_c_15120_regression.py | STALE (batch 1) | 2026-06-21 | no caller found |
| scripts/bench/run_c_15130_regression.py | scripts/archive/2026-10/bench/run_c_15130_regression.py | STALE (batch 1) | 2026-06-21 | no caller found |
| scripts/bench/run_c_15140_regression.py | scripts/archive/2026-10/bench/run_c_15140_regression.py | STALE (batch 1) | 2026-06-21 | no caller found |
| scripts/bench/run_c_15150_regression.py | scripts/archive/2026-10/bench/run_c_15150_regression.py | STALE (batch 1) | 2026-06-21 | no caller found |
| scripts/bench/run_c_15160_regression.py | scripts/archive/2026-10/bench/run_c_15160_regression.py | STALE (batch 1) | 2026-06-21 | no caller found |
| scripts/bench/run_c_15170_regression.py | scripts/archive/2026-10/bench/run_c_15170_regression.py | STALE (batch 1) | 2026-06-21 | no caller found |
| scripts/bench/run_c_15180_regression.py | scripts/archive/2026-10/bench/run_c_15180_regression.py | STALE (batch 1) | 2026-06-21 | no caller found |
| scripts/bench/run_c_15190_regression.py | scripts/archive/2026-10/bench/run_c_15190_regression.py | STALE (batch 1) | 2026-06-21 | no caller found |
| scripts/bench/run_c_15200_regression.py | scripts/archive/2026-10/bench/run_c_15200_regression.py | STALE (batch 1) | 2026-06-21 | no caller found |
| scripts/bench/run_c_15210_regression.py | scripts/archive/2026-10/bench/run_c_15210_regression.py | STALE (batch 1) | 2026-06-21 | no caller found |
| scripts/bench/run_c_15220_regression.py | scripts/archive/2026-10/bench/run_c_15220_regression.py | STALE (batch 1) | 2026-06-21 | no caller found |
| scripts/bench/run_c_15230_regression.py | scripts/archive/2026-10/bench/run_c_15230_regression.py | STALE (batch 1) | 2026-06-21 | no caller found |
| scripts/bench/run_c_15240_regression.py | scripts/archive/2026-10/bench/run_c_15240_regression.py | STALE (batch 1) | 2026-06-21 | no caller found |
| scripts/bench/run_c_15250_regression.py | scripts/archive/2026-10/bench/run_c_15250_regression.py | STALE (batch 1) | 2026-06-21 | no caller found |
| scripts/bench/run_c_15260_regression.py | scripts/archive/2026-10/bench/run_c_15260_regression.py | STALE (batch 1) | 2026-06-21 | no caller found |
| scripts/bench/run_c_15270_regression.py | scripts/archive/2026-10/bench/run_c_15270_regression.py | STALE (batch 1) | 2026-06-21 | no caller found |
| scripts/bench/run_c_15280_regression.py | scripts/archive/2026-10/bench/run_c_15280_regression.py | STALE (batch 1) | 2026-06-21 | no caller found |
| scripts/bench/run_c_15290_regression.py | scripts/archive/2026-10/bench/run_c_15290_regression.py | STALE (batch 1) | 2026-06-21 | no caller found |
| scripts/bench/run_c_15300_regression.py | scripts/archive/2026-10/bench/run_c_15300_regression.py | STALE (batch 1) | 2026-06-21 | no caller found |
| scripts/bench/run_c_15310_regression.py | scripts/archive/2026-10/bench/run_c_15310_regression.py | STALE (batch 1) | 2026-06-21 | no caller found |
| scripts/bench/run_c_15320_regression.py | scripts/archive/2026-10/bench/run_c_15320_regression.py | STALE (batch 1) | 2026-06-21 | no caller found |
| scripts/bench/run_p12_real_replay.py | scripts/archive/2026-10/bench/run_p12_real_replay.py | STALE (batch 1) | 2026-06-29 | no caller found |
| scripts/bench/run_r2_microbench.py | scripts/archive/2026-10/bench/run_r2_microbench.py | STALE (batch 1) | 2026-06-21 | no caller found |
| scripts/bench/run_real_local_only_pilot.py | scripts/archive/2026-10/bench/run_real_local_only_pilot.py | STALE (batch 1) | 2026-07-14 | no caller found |
| scripts/bench/run_t1_leak_audit.py | scripts/archive/2026-10/bench/run_t1_leak_audit.py | STALE (batch 1) | 2026-06-21 | no caller found |
| scripts/bench/run_t2_route_integration.py | scripts/archive/2026-10/bench/run_t2_route_integration.py | STALE (batch 1) | 2026-06-21 | no caller found |
| scripts/bench/run_t3_expanded_bench.py | scripts/archive/2026-10/bench/run_t3_expanded_bench.py | STALE (batch 1) | 2026-06-21 | no caller found |
| scripts/bench/run_v1_integrity_audit.py | scripts/archive/2026-10/bench/run_v1_integrity_audit.py | STALE (batch 1) | 2026-06-21 | no caller found |
| scripts/bench/run_v2_policy_calibration.py | scripts/archive/2026-10/bench/run_v2_policy_calibration.py | STALE (batch 1) | 2026-06-21 | no caller found |
| scripts/bench/run_w1_trigger_integration.py | scripts/archive/2026-10/bench/run_w1_trigger_integration.py | STALE (batch 1) | 2026-06-21 | no caller found |
| scripts/bench/run_w2_route_wiring.py | scripts/archive/2026-10/bench/run_w2_route_wiring.py | STALE (batch 1) | 2026-06-21 | no caller found |
| scripts/bench/run_w3_policy_validation.py | scripts/archive/2026-10/bench/run_w3_policy_validation.py | STALE (batch 1) | 2026-06-21 | no caller found |
| scripts/bench/run_x1_task_expansion.py | scripts/archive/2026-10/bench/run_x1_task_expansion.py | STALE (batch 1) | 2026-06-21 | no caller found |
| scripts/bench/run_x2_frontier_bench.py | scripts/archive/2026-10/bench/run_x2_frontier_bench.py | STALE (batch 1) | 2026-06-21 | no caller found |
| scripts/bench/run_y1_graph_builder.py | scripts/archive/2026-10/bench/run_y1_graph_builder.py | STALE (batch 1) | 2026-06-21 | no caller found |
| scripts/bench/run_y2_protocol_generator.py | scripts/archive/2026-10/bench/run_y2_protocol_generator.py | STALE (batch 1) | 2026-06-21 | no caller found |
| scripts/bench/run_y3_frontier_bench.py | scripts/archive/2026-10/bench/run_y3_frontier_bench.py | STALE (batch 1) | 2026-06-21 | no caller found |
| scripts/bench/run_z1_audit.py | scripts/archive/2026-10/bench/run_z1_audit.py | STALE (batch 1) | 2026-06-21 | no caller found |
| scripts/bench/run_z2_binding_executor.py | scripts/archive/2026-10/bench/run_z2_binding_executor.py | STALE (batch 1) | 2026-06-21 | no caller found |
| scripts/bench/run_z3_integrated_bench.py | scripts/archive/2026-10/bench/run_z3_integrated_bench.py | STALE (batch 1) | 2026-06-21 | no caller found |
| scripts/bench/swe-bench-pro-100.json | scripts/archive/2026-10/bench/swe-bench-pro-100.json | ARCHIVE (batch 1) | 2026-05-24 |  |
| scripts/bench/t1_6_regression_astropy_13236.py | scripts/archive/2026-10/bench/t1_6_regression_astropy_13236.py | STALE (batch 1) | 2026-06-20 | no caller found |
| scripts/bench/t1_9_two_task_regression.py | scripts/archive/2026-10/bench/t1_9_two_task_regression.py | STALE (batch 1) | 2026-06-20 | no caller found |
| scripts/bench/t2_0_five_task_regression.py | scripts/archive/2026-10/bench/t2_0_five_task_regression.py | STALE (batch 1) | 2026-06-20 | no caller found |
| scripts/bench/t2_1_five_task_regression.py | scripts/archive/2026-10/bench/t2_1_five_task_regression.py | STALE (batch 1) | 2026-06-20 | no caller found |
| scripts/bench/t2_2_ten_task_diagnostic.py | scripts/archive/2026-10/bench/t2_2_ten_task_diagnostic.py | STALE (batch 1) | 2026-06-20 | no caller found |
| scripts/bench/t2_3_three_failure_triage.py | scripts/archive/2026-10/bench/t2_3_three_failure_triage.py | STALE (batch 1) | 2026-06-20 | no caller found |
| scripts/bench/t2_4_dependency_closure.py | scripts/archive/2026-10/bench/t2_4_dependency_closure.py | STALE (batch 1) | 2026-06-20 | no caller found |
| scripts/bench/t2_5_fifteen_task_diagnostic.py | scripts/archive/2026-10/bench/t2_5_fifteen_task_diagnostic.py | STALE (batch 1) | 2026-06-20 | no caller found |
| scripts/bench/t2_6_sympy_13031_closure.py | scripts/archive/2026-10/bench/t2_6_sympy_13031_closure.py | STALE (batch 1) | 2026-06-20 | no caller found |
| scripts/bench/t2_8_twenty_task_diagnostic.py | scripts/archive/2026-10/bench/t2_8_twenty_task_diagnostic.py | STALE (batch 1) | 2026-06-20 | no caller found |
| scripts/bench/t2_9_replay_20_task_baseline.py | scripts/archive/2026-10/bench/t2_9_replay_20_task_baseline.py | STALE (batch 1) | 2026-06-20 | no caller found |
| scripts/bench/t3_0_controlled_model_call_reintroduction.py | scripts/archive/2026-10/bench/t3_0_controlled_model_call_reintroduction.py | STALE (batch 1) | 2026-06-20 | no caller found |
| scripts/bench/t3_1_qwen14b_single_task_smoke.py | scripts/archive/2026-10/bench/t3_1_qwen14b_single_task_smoke.py | STALE (batch 1) | 2026-06-20 | no caller found |
| scripts/bench/t3_2_replace_only_format_refinement.py | scripts/archive/2026-10/bench/t3_2_replace_only_format_refinement.py | STALE (batch 1) | 2026-06-20 | no caller found |
| scripts/bench/t3_3_controlled_3_task_model_call.py | scripts/archive/2026-10/bench/t3_3_controlled_3_task_model_call.py | STALE (batch 1) | 2026-06-20 | no caller found |
| scripts/bench/t3_4_syntax_aware_replace_contract.py | scripts/archive/2026-10/bench/t3_4_syntax_aware_replace_contract.py | STALE (batch 1) | 2026-06-20 | no caller found |
| scripts/bench/t3_5_context_aware_syntax_gate.py | scripts/archive/2026-10/bench/t3_5_context_aware_syntax_gate.py | STALE (batch 1) | 2026-06-20 | no caller found |
| scripts/bench/t3_6_controlled_4_task_mixed.py | scripts/archive/2026-10/bench/t3_6_controlled_4_task_mixed.py | STALE (batch 1) | 2026-06-20 | no caller found |
| scripts/bench/t3_7_controlled_6_task_expansion.py | scripts/archive/2026-10/bench/t3_7_controlled_6_task_expansion.py | STALE (batch 1) | 2026-06-20 | no caller found |
| scripts/bench/t3_8_no_op_guard_and_8_task.py | scripts/archive/2026-10/bench/t3_8_no_op_guard_and_8_task.py | STALE (batch 1) | 2026-06-20 | no caller found |
| scripts/bench/t3_9_indentation_normalized_gate.py | scripts/archive/2026-10/bench/t3_9_indentation_normalized_gate.py | STALE (batch 1) | 2026-06-20 | no caller found |
| scripts/bench/t4_0_source_anchoring_repair.py | scripts/archive/2026-10/bench/t4_0_source_anchoring_repair.py | STALE (batch 1) | 2026-06-20 | no caller found |
| scripts/bench/t4_2_clean_room_replay.py | scripts/archive/2026-10/bench/t4_2_clean_room_replay.py | STALE (batch 1) | 2026-06-20 | no caller found |
| scripts/bench/t4_3_source_snapshot_backfill.py | scripts/archive/2026-10/bench/t4_3_source_snapshot_backfill.py | ONE-OFF (batch 1) | 2026-06-20 | name-pattern |
| scripts/bench/t4_4_fixture_backed_replay.py | scripts/archive/2026-10/bench/t4_4_fixture_backed_replay.py | STALE (batch 1) | 2026-06-20 | no caller found |
| scripts/bench/t4_6_controlled_expansion.py | scripts/archive/2026-10/bench/t4_6_controlled_expansion.py | STALE (batch 1) | 2026-06-20 | no caller found |
| scripts/bench/t4_8_indentation_adapter_recovery.py | scripts/archive/2026-10/bench/t4_8_indentation_adapter_recovery.py | STALE (batch 1) | 2026-06-20 | no caller found |
| scripts/bench/t4_9_consolidation_replay.py | scripts/archive/2026-10/bench/t4_9_consolidation_replay.py | STALE (batch 1) | 2026-06-20 | no caller found |
| scripts/bench/test_campaign_shadow.py | scripts/archive/2026-10/bench/test_campaign_shadow.py | STALE (batch 1) | 2026-06-02 | no caller found |
| scripts/bench/test_persistent_worker.py | scripts/archive/2026-10/bench/test_persistent_worker.py | STALE (batch 1) | 2026-06-20 | no caller found |
| scripts/bench/verifier_guided_retry_v1.py | scripts/archive/2026-10/bench/verifier_guided_retry_v1.py | STALE (batch 1) | 2026-06-20 | no caller found |
| scripts/bench/verify_canary_telemetry.py | scripts/archive/2026-10/bench/verify_canary_telemetry.py | STALE (batch 1) | 2026-06-13 | no caller found |
| scripts/bench/verify_same_model_lock.py | scripts/archive/2026-10/bench/verify_same_model_lock.py | STALE (batch 1) | 2026-05-28 | no caller found |
| scripts/bench/wisdom_verification_run.py | scripts/archive/2026-10/bench/wisdom_verification_run.py | STALE (batch 1) | 2026-04-09 | no caller found |
| scripts/ops/ab_test_runner.py | scripts/archive/2026-10/ops/ab_test_runner.py | STALE (batch 1) | 2026-06-05 | no caller found |
| scripts/ops/analyze_phase4_audit.py | scripts/archive/2026-10/ops/analyze_phase4_audit.py | ONE-OFF (batch 1) | 2026-06-02 | name-pattern |
| scripts/ops/apply_sf_skill_cleanup.py | scripts/archive/2026-10/ops/apply_sf_skill_cleanup.py | STALE (batch 1) | 2026-05-20 | no caller found |
| scripts/ops/bench_ab_comparison.py | scripts/archive/2026-10/ops/bench_ab_comparison.py | STALE (batch 1) | 2026-06-04 | no caller found |
| scripts/ops/bench_concurrency_committee.py | scripts/archive/2026-10/ops/bench_concurrency_committee.py | STALE (batch 1) | 2026-06-04 | no caller found |
| scripts/ops/bench_cross_gen.py | scripts/archive/2026-10/ops/bench_cross_gen.py | STALE (batch 1) | 2026-06-04 | no caller found |
| scripts/ops/bench_new_deepswe_20.py | scripts/archive/2026-10/ops/bench_new_deepswe_20.py | STALE (batch 1) | 2026-06-04 | no caller found |
| scripts/ops/build_capability_skill_promotion_policy.py | scripts/archive/2026-10/ops/build_capability_skill_promotion_policy.py | STALE (batch 1) | 2026-05-20 | no caller found |
| scripts/ops/build_evidence_retention_dry_run.py | scripts/archive/2026-10/ops/build_evidence_retention_dry_run.py | STALE (batch 1) | 2026-05-20 | no caller found |
| scripts/ops/build_sf_flash_pair_rollup.py | scripts/archive/2026-10/ops/build_sf_flash_pair_rollup.py | STALE (batch 1) | 2026-05-20 | no caller found |
| scripts/ops/build_sf_research_tiebreak_and_governance_curation.py | scripts/archive/2026-10/ops/build_sf_research_tiebreak_and_governance_curation.py | STALE (batch 1) | 2026-05-20 | no caller found |
| scripts/ops/build_sf_skill_discovery_scheduler.py | scripts/archive/2026-10/ops/build_sf_skill_discovery_scheduler.py | STALE (batch 1) | 2026-05-20 | no caller found |
| scripts/ops/build_skill_fit_status_rollup.py | scripts/archive/2026-10/ops/build_skill_fit_status_rollup.py | STALE (batch 1) | 2026-05-20 | no caller found |
| scripts/ops/challenge_7b_counterattack.py | scripts/archive/2026-10/ops/challenge_7b_counterattack.py | STALE (batch 1) | 2026-06-04 | no caller found |
| scripts/ops/challenge_7b_swarm.py | scripts/archive/2026-10/ops/challenge_7b_swarm.py | STALE (batch 1) | 2026-06-04 | no caller found |
| scripts/ops/challenge_contamination.py | scripts/archive/2026-10/ops/challenge_contamination.py | STALE (batch 1) | 2026-06-04 | no caller found |
| scripts/ops/challenge_gpt55_level.py | scripts/archive/2026-10/ops/challenge_gpt55_level.py | STALE (batch 1) | 2026-06-04 | no caller found |
| scripts/ops/challenge_hard_task.py | scripts/archive/2026-10/ops/challenge_hard_task.py | STALE (batch 1) | 2026-06-04 | no caller found |
| scripts/ops/challenge_omega_swarm.py | scripts/archive/2026-10/ops/challenge_omega_swarm.py | STALE (batch 1) | 2026-10-14 | no caller found |
| scripts/ops/com.nexus.pilot.proxy.plist | scripts/archive/2026-10/ops/com.nexus.pilot.proxy.plist | STALE (batch 1) | 2026-03-28 | no caller found |
| scripts/ops/consistency_harness.py | scripts/archive/2026-10/ops/consistency_harness.py | STALE (batch 1) | 2026-06-04 | no caller found |
| scripts/ops/daily_hybrid_regression.sh | scripts/archive/2026-10/ops/daily_hybrid_regression.sh | STALE (batch 1) | 2026-07-10 | no caller found |
| scripts/ops/diag_7b_forward.py | scripts/archive/2026-10/ops/diag_7b_forward.py | STALE (batch 1) | 2026-06-04 | no caller found |
| scripts/ops/e2e_comparison_audit.py | scripts/archive/2026-10/ops/e2e_comparison_audit.py | STALE (batch 1) | 2026-06-04 | no caller found |
| scripts/ops/eval_1_5b_rigorous.py | scripts/archive/2026-10/ops/eval_1_5b_rigorous.py | STALE (batch 1) | 2026-06-04 | no caller found |
| scripts/ops/eval_aligned_final.py | scripts/archive/2026-10/ops/eval_aligned_final.py | STALE (batch 1) | 2026-06-04 | no caller found |
| scripts/ops/eval_router_final.py | scripts/archive/2026-10/ops/eval_router_final.py | STALE (batch 1) | 2026-06-04 | no caller found |
| scripts/ops/eval_router_v3.py | scripts/archive/2026-10/ops/eval_router_v3.py | STALE (batch 1) | 2026-06-04 | no caller found |
| scripts/ops/export_3b_student_data.py | scripts/archive/2026-10/ops/export_3b_student_data.py | STALE (batch 1) | 2026-06-13 | no caller found |
| scripts/ops/export_s2t_traces.py | scripts/archive/2026-10/ops/export_s2t_traces.py | STALE (batch 1) | 2026-06-20 | no caller found |
| scripts/ops/final_impossible_challenges.py | scripts/archive/2026-10/ops/final_impossible_challenges.py | STALE (batch 1) | 2026-06-04 | no caller found |
| scripts/ops/fix_denoiser_restructure.py | scripts/archive/2026-10/ops/fix_denoiser_restructure.py | ONE-OFF (batch 1) | 2026-06-04 | name-pattern |
| scripts/ops/fix_denoiser.py | scripts/archive/2026-10/ops/fix_denoiser.py | ONE-OFF (batch 1) | 2026-06-04 | name-pattern |
| scripts/ops/fix_swe_indent.py | scripts/archive/2026-10/ops/fix_swe_indent.py | ONE-OFF (batch 1) | 2026-06-04 | name-pattern |
| scripts/ops/fix_swe_logic.py | scripts/archive/2026-10/ops/fix_swe_logic.py | ONE-OFF (batch 1) | 2026-06-04 | name-pattern |
| scripts/ops/gemini_worker_loop.py | scripts/archive/2026-10/ops/gemini_worker_loop.py | STALE (batch 1) | 2026-05-14 | no caller found |
| scripts/ops/generate_anonymized_dataset.py | scripts/archive/2026-10/ops/generate_anonymized_dataset.py | STALE (batch 1) | 2026-06-04 | no caller found |
| scripts/ops/generate_consolidated_ledger.py | scripts/archive/2026-10/ops/generate_consolidated_ledger.py | STALE (batch 1) | 2026-06-04 | no caller found |
| scripts/ops/generate_enriched_master_ledger.py | scripts/archive/2026-10/ops/generate_enriched_master_ledger.py | STALE (batch 1) | 2026-06-04 | no caller found |
| scripts/ops/generate_final_master_ledger.py | scripts/archive/2026-10/ops/generate_final_master_ledger.py | STALE (batch 1) | 2026-06-04 | no caller found |
| scripts/ops/generate_heldout_dataset.py | scripts/archive/2026-10/ops/generate_heldout_dataset.py | STALE (batch 1) | 2026-06-20 | no caller found |
| scripts/ops/generate_hybrid_dataset.py | scripts/archive/2026-10/ops/generate_hybrid_dataset.py | STALE (batch 1) | 2026-06-04 | no caller found |
| scripts/ops/generate_module_inventory.py | scripts/archive/2026-10/ops/generate_module_inventory.py | STALE (batch 1) | 2026-10-14 | no caller found |
| scripts/ops/generate_perplexity_reports.py | scripts/archive/2026-10/ops/generate_perplexity_reports.py | STALE (batch 1) | 2026-06-04 | no caller found |
| scripts/ops/generate_router_dataset.py | scripts/archive/2026-10/ops/generate_router_dataset.py | STALE (batch 1) | 2026-06-04 | no caller found |
| scripts/ops/generate_s2t_training_data.py | scripts/archive/2026-10/ops/generate_s2t_training_data.py | STALE (batch 1) | 2026-06-20 | no caller found |
| scripts/ops/generate_shadow_events.py | scripts/archive/2026-10/ops/generate_shadow_events.py | STALE (batch 1) | 2026-06-12 | no caller found |
| scripts/ops/generate_sidecar_fixtures.py | scripts/archive/2026-10/ops/generate_sidecar_fixtures.py | STALE (batch 1) | 2026-06-14 | no caller found |
| scripts/ops/generate_strict_router_dataset.py | scripts/archive/2026-10/ops/generate_strict_router_dataset.py | STALE (batch 1) | 2026-06-04 | no caller found |
| scripts/ops/local_heal_manifest_report.py | scripts/archive/2026-10/ops/local_heal_manifest_report.py | STALE (batch 1) | 2026-06-01 | no caller found |
| scripts/ops/manifest_coverage_check.py | scripts/archive/2026-10/ops/manifest_coverage_check.py | STALE (batch 1) | 2026-06-15 | no caller found |
| scripts/ops/merge_nexus_ledgers.py | scripts/archive/2026-10/ops/merge_nexus_ledgers.py | STALE (batch 1) | 2026-06-04 | no caller found |
| scripts/ops/nexus_core_effectiveness_g0.py | scripts/archive/2026-10/ops/nexus_core_effectiveness_g0.py | STALE (batch 1) | 2026-10-01 | no caller found |
| scripts/ops/nexus_self_hosted_mcp.py | scripts/archive/2026-10/ops/nexus_self_hosted_mcp.py | STALE (batch 1) | 2026-07-26 | no caller found |
| scripts/ops/p0t5_live_provider_canary.py | scripts/archive/2026-10/ops/p0t5_live_provider_canary.py | STALE (batch 1) | 2026-08-22 | no caller found |
| scripts/ops/p5_monitor.sh | scripts/archive/2026-10/ops/p5_monitor.sh | STALE (batch 1) | 2026-07-10 | no caller found |
| scripts/ops/policy_friction_calibration.py | scripts/archive/2026-10/ops/policy_friction_calibration.py | STALE (batch 1) | 2026-06-15 | no caller found |
| scripts/ops/policy_lane_friction_report.py | scripts/archive/2026-10/ops/policy_lane_friction_report.py | STALE (batch 1) | 2026-06-15 | no caller found |
| scripts/ops/pre_commit_governance.py | scripts/archive/2026-10/ops/pre_commit_governance.py | STALE (batch 1) | 2026-05-27 | no caller found |
| scripts/ops/preheat_models.py | scripts/archive/2026-10/ops/preheat_models.py | STALE (batch 1) | 2026-10-13 | no caller found |
| scripts/ops/prepare_all_repro.py | scripts/archive/2026-10/ops/prepare_all_repro.py | STALE (batch 1) | 2026-06-06 | no caller found |
| scripts/ops/solve_completion_trace.py | scripts/archive/2026-10/ops/solve_completion_trace.py | STALE (batch 1) | 2026-06-04 | no caller found |
| scripts/ops/test_gemini_escalation.py | scripts/archive/2026-10/ops/test_gemini_escalation.py | STALE (batch 1) | 2026-06-04 | no caller found |
| scripts/ops/test_integration_hybrid.py | scripts/archive/2026-10/ops/test_integration_hybrid.py | STALE (batch 1) | 2026-06-04 | no caller found |
| scripts/ops/trace_real_decisions.py | scripts/archive/2026-10/ops/trace_real_decisions.py | STALE (batch 1) | 2026-06-04 | no caller found |
| scripts/ops/val_1_5b_pivot.py | scripts/archive/2026-10/ops/val_1_5b_pivot.py | STALE (batch 1) | 2026-06-04 | no caller found |
| scripts/ops/verify_1_5b_adapter.py | scripts/archive/2026-10/ops/verify_1_5b_adapter.py | STALE (batch 1) | 2026-06-04 | no caller found |
| scripts/ops/verify_anonymized.py | scripts/archive/2026-10/ops/verify_anonymized.py | STALE (batch 1) | 2026-06-04 | no caller found |
| scripts/ops/verify_v25_performance.py | scripts/archive/2026-10/ops/verify_v25_performance.py | STALE (batch 1) | 2026-06-04 | no caller found |
| scripts/scratch/phase14_acceptance.py | scripts/archive/2026-10/scratch/phase14_acceptance.py | ONE-OFF (batch 1) | 2026-04-09 | name-pattern |
| scripts/scratch/phase14_hardened_acceptance.py | scripts/archive/2026-10/scratch/phase14_hardened_acceptance.py | ONE-OFF (batch 1) | 2026-04-09 | name-pattern |
| scripts/scratch/phase9_anamnesis_test.py | scripts/archive/2026-10/scratch/phase9_anamnesis_test.py | ONE-OFF (batch 1) | 2026-04-09 | name-pattern |
| scripts/scratch/test_compactor_v2.py | scripts/archive/2026-10/scratch/test_compactor_v2.py | STALE (batch 1) | 2026-04-17 | no caller found |
| scripts/scratch/verify_all_models.py | scripts/archive/2026-10/scratch/verify_all_models.py | STALE (batch 1) | 2026-06-01 | no caller found |
| scripts/scratch/verify_nexus_routing.py | scripts/archive/2026-10/scratch/verify_nexus_routing.py | STALE (batch 1) | 2026-06-01 | no caller found |

## Kept (not moved: a referrer was found at archive time)

| path | referrers (first 3) |
|---|---|
| scratch/astropy_12907/separable.py | benchmarking/swebench_lite/patch_fix_12907.jsonl, benchmarking/swebench_lite/patch_fix_results.jsonl, benchmarking/swebench_lite/patch_fix_v2_12907.jsonl |
| scratch/astropy_emulation/coordinates/baseframe.py | scripts/bench/benchmark_tasks.jsonl, scripts/bench/swe-bench-verified.json |
| scratch/astropy_emulation/coordinates/builtin_frames/intermediate_rotation_transforms.py | scripts/bench/swe-bench-verified.json |
| scratch/astropy_emulation/coordinates/builtin_frames/itrs_observed_transforms.py | scripts/bench/swe-bench-verified.json |
| scratch/astropy_emulation/coordinates/builtin_frames/itrs.py | scripts/bench/swe-bench-verified.json |
| scratch/astropy_emulation/coordinates/earth.py | scripts/run_full_rerun_local_qwen.py, scripts/run_source_anchor_fix.py |
| scratch/astropy_emulation/coordinates/funcs.py | benchmarking/swebench_lite/predictions_real_7.jsonl, benchmarking/swebench_lite/predictions_real_idx_6.jsonl, scripts/bench/benchmark_tasks.jsonl |
| scratch/astropy_emulation/coordinates/representation.py | nexus/contracts/owner_representation.py, nexus/orchestrator/owner_representation.py, nexus/security/owner_representation_transport_inventory.py |
| scratch/astropy_emulation/coordinates/sites.py | scripts/bench/benchmark_tasks.jsonl, scripts/bench/swe-bench-verified.json |
| scratch/astropy_emulation/coordinates/sky_coordinate.py | scripts/bench/benchmark_tasks.jsonl, scripts/bench/swe-bench-verified.json |
| scratch/astropy_emulation/coordinates/tests/helper.py | .codex_lessons.md, scripts/bench/m1_real_local_solve_benchmark.py, tests/benchmark/test_local_model_executor_real_isolated_solve.py |
| scratch/astropy_emulation/coordinates/tests/test_intermediate_transformations.py | scripts/bench/benchmark_tasks.jsonl, scripts/bench/swe-bench-verified.json |
| scratch/astropy_emulation/coordinates/tests/test_pickle.py | scripts/bench/benchmark_tasks.jsonl, scripts/bench/swe-bench-verified.json |
| scratch/astropy_emulation/coordinates/tests/test_sky_coord.py | scripts/bench/benchmark_tasks.jsonl, scripts/bench/swe-bench-verified.json |
| scratch/astropy_emulation/coordinates/tests/test_utils.py | scripts/bench/benchmark_tasks.jsonl, scripts/bench/swe-bench-verified.json |
| scratch/astropy_emulation/coordinates/transformations.py | scripts/bench/benchmark_tasks.jsonl, scripts/bench/swe-bench-verified.json |
| scratch/dummy_repo/dummy.py | scripts/bench/s2t_shadow_eval.py, tests/benchmark/test_capability_ab_runner_4_quadrants.py, tests/ops/test_delivery_gate_contract.py |
| scratch/dummy_repo/reproduce_bug.py | benchmarking/swebench_lite/patch_fix_13579.jsonl, benchmarking/swebench_lite/patch_fix_v2_13579.jsonl, benchmarking/swebench_lite/phase1_A.jsonl |
| scripts/scratch/phase13_acceptance.py | tests/services/test_archived_legacy_engine_2026_10_13.py |
| scripts/scratch/phase13_closed_loop_test.py | tests/services/test_archived_legacy_engine_2026_10_13.py |

## Batch 2 (scripts moved with their tests)

Evidence: ~/Workspace/nexus-handoffs/2026-10-13-online-ab/ARCHIVE_CLASSIFICATION_20261016.md (batch 2) re-derived on main c48689bb4 by whole-repo basename/path scans; each script moves only together with every test that imports it. Pre-move ref: archive/2026-10-17-batch-2-pre.

Files: 52

| original path | new path | class | last commit |
|---|---|---|---|
| scripts/bench/export_s2t_shadow_policy.py | scripts/archive/2026-10/bench/export_s2t_shadow_policy.py | script (batch 2) | 2026-05-14 |
| scripts/bench/flash_baseline_summary.py | scripts/archive/2026-10/bench/flash_baseline_summary.py | script (batch 2) | 2026-05-06 |
| scripts/bench/h5_cloud_fallback_e2e_smoke.py | scripts/archive/2026-10/bench/h5_cloud_fallback_e2e_smoke.py | script (batch 2) | 2026-06-23 |
| scripts/bench/h5_local_committee_e2e_smoke.py | scripts/archive/2026-10/bench/h5_local_committee_e2e_smoke.py | script (batch 2) | 2026-06-23 |
| scripts/bench/n30r_task_gate.py | scripts/archive/2026-10/bench/n30r_task_gate.py | script (batch 2) | 2026-07-11 |
| scripts/bench/n30r_v1_acceptance_oracle.py | scripts/archive/2026-10/bench/n30r_v1_acceptance_oracle.py | script (batch 2) | 2026-07-11 |
| scripts/bench/nexus_value_comparison_report.py | scripts/archive/2026-10/bench/nexus_value_comparison_report.py | script (batch 2) | 2026-05-02 |
| scripts/bench/refine_route_cost_policy_from_runs.py | scripts/archive/2026-10/bench/refine_route_cost_policy_from_runs.py | script (batch 2) | 2026-05-14 |
| scripts/bench/route_cost_optimizer.py | scripts/archive/2026-10/bench/route_cost_optimizer.py | script (batch 2) | 2026-05-29 |
| scripts/bench/route_decision_simulator.py | scripts/archive/2026-10/bench/route_decision_simulator.py | script (batch 2) | 2026-05-14 |
| scripts/bench/run_local_problem_diff_eval.py | scripts/archive/2026-10/bench/run_local_problem_diff_eval.py | script (batch 2) | 2026-07-14 |
| scripts/bench/run_observation_cycle_01.py | scripts/archive/2026-10/bench/run_observation_cycle_01.py | script (batch 2) | 2026-07-14 |
| scripts/bench/run_observation_cycle_02.py | scripts/archive/2026-10/bench/run_observation_cycle_02.py | script (batch 2) | 2026-07-14 |
| scripts/bench/run_observation_cycle_03.py | scripts/archive/2026-10/bench/run_observation_cycle_03.py | script (batch 2) | 2026-07-14 |
| scripts/bench/run_r3_portfolio_bench.py | scripts/archive/2026-10/bench/run_r3_portfolio_bench.py | script (batch 2) | 2026-06-21 |
| scripts/bench/run_r6_shadow_bench.py | scripts/archive/2026-10/bench/run_r6_shadow_bench.py | script (batch 2) | 2026-06-21 |
| scripts/bench/run_u1_route_hardening.py | scripts/archive/2026-10/bench/run_u1_route_hardening.py | script (batch 2) | 2026-06-21 |
| scripts/bench/run_u2_task_expansion.py | scripts/archive/2026-10/bench/run_u2_task_expansion.py | script (batch 2) | 2026-06-21 |
| scripts/bench/run_u3_expanded_bench.py | scripts/archive/2026-10/bench/run_u3_expanded_bench.py | script (batch 2) | 2026-06-21 |
| scripts/bench/s2t_failure_taxonomy.py | scripts/archive/2026-10/bench/s2t_failure_taxonomy.py | script (batch 2) | 2026-07-14 |
| scripts/bench/t1_5_semantic_retry_astropy_13236.py | scripts/archive/2026-10/bench/t1_5_semantic_retry_astropy_13236.py | script (batch 2) | 2026-07-14 |
| scripts/bench/t1_8_rerun_astropy_12907.py | scripts/archive/2026-10/bench/t1_8_rerun_astropy_12907.py | script (batch 2) | 2026-07-14 |
| scripts/bench/teacher_student_gap_matrix.py | scripts/archive/2026-10/bench/teacher_student_gap_matrix.py | script (batch 2) | 2026-05-08 |
| scripts/bench/weak_model_closure_plan.py | scripts/archive/2026-10/bench/weak_model_closure_plan.py | script (batch 2) | 2026-05-07 |
| scripts/bench/weak_model_cost_truth.py | scripts/archive/2026-10/bench/weak_model_cost_truth.py | script (batch 2) | 2026-05-07 |
| scripts/bench/weak_model_long_loop.py | scripts/archive/2026-10/bench/weak_model_long_loop.py | script (batch 2) | 2026-05-07 |
| scripts/ops/build_heep_mat_b_blocked_mode_resolution.py | scripts/archive/2026-10/ops/build_heep_mat_b_blocked_mode_resolution.py | script (batch 2) | 2026-05-20 |
| scripts/ops/build_heep_mat_b_final_skill_decisions.py | scripts/archive/2026-10/ops/build_heep_mat_b_final_skill_decisions.py | script (batch 2) | 2026-05-20 |
| scripts/ops/build_heep_mat_b_live_report.py | scripts/archive/2026-10/ops/build_heep_mat_b_live_report.py | script (batch 2) | 2026-05-20 |
| scripts/ops/build_heep_mat_b_update_packets.py | scripts/archive/2026-10/ops/build_heep_mat_b_update_packets.py | script (batch 2) | 2026-05-20 |
| scripts/ops/build_heep_runtime_curation_status.py | scripts/archive/2026-10/ops/build_heep_runtime_curation_status.py | script (batch 2) | 2026-05-20 |
| scripts/ops/build_heep_runtime_default_apply_decision.py | scripts/archive/2026-10/ops/build_heep_runtime_default_apply_decision.py | script (batch 2) | 2026-05-20 |
| scripts/ops/build_publication_readiness_gate.py | scripts/archive/2026-10/ops/build_publication_readiness_gate.py | script (batch 2) | 2026-05-20 |
| scripts/ops/build_sf_current_skill_ssot.py | scripts/archive/2026-10/ops/build_sf_current_skill_ssot.py | script (batch 2) | 2026-05-20 |
| scripts/ops/build_sf_final_capability_skill_settlement.py | scripts/archive/2026-10/ops/build_sf_final_capability_skill_settlement.py | script (batch 2) | 2026-05-21 |
| scripts/ops/build_sf_final_compare_report.py | scripts/archive/2026-10/ops/build_sf_final_compare_report.py | script (batch 2) | 2026-05-21 |
| scripts/ops/build_sf_final_live_compare_matrix.py | scripts/archive/2026-10/ops/build_sf_final_live_compare_matrix.py | script (batch 2) | 2026-05-21 |
| scripts/ops/build_sf_final_live_compare_report.py | scripts/archive/2026-10/ops/build_sf_final_live_compare_report.py | script (batch 2) | 2026-05-21 |
| scripts/ops/build_sf_final_local_skill_compare.py | scripts/archive/2026-10/ops/build_sf_final_local_skill_compare.py | script (batch 2) | 2026-05-21 |
| scripts/ops/build_sf_final_runtime_apply.py | scripts/archive/2026-10/ops/build_sf_final_runtime_apply.py | script (batch 2) | 2026-05-22 |
| scripts/ops/build_sf_replacement_cleanliness_manifest.py | scripts/archive/2026-10/ops/build_sf_replacement_cleanliness_manifest.py | script (batch 2) | 2026-05-20 |
| scripts/ops/build_sf_systematic_current_overlay.py | scripts/archive/2026-10/ops/build_sf_systematic_current_overlay.py | script (batch 2) | 2026-05-20 |
| scripts/ops/build_zero_trust_v2_public_claim_gate_review.py | scripts/archive/2026-10/ops/build_zero_trust_v2_public_claim_gate_review.py | script (batch 2) | 2026-05-22 |
| scripts/ops/evaluate_github_skill_challengers.py | scripts/archive/2026-10/ops/evaluate_github_skill_challengers.py | script (batch 2) | 2026-05-20 |
| scripts/ops/finalize_heep_mat_b_holds.py | scripts/archive/2026-10/ops/finalize_heep_mat_b_holds.py | script (batch 2) | 2026-05-20 |
| scripts/ops/optimize_sf_primary_skill_descriptions.py | scripts/archive/2026-10/ops/optimize_sf_primary_skill_descriptions.py | script (batch 2) | 2026-05-20 |
| scripts/ops/run_heep_live_pilot.py | scripts/archive/2026-10/ops/run_heep_live_pilot.py | script (batch 2) | 2026-05-20 |
| scripts/ops/run_live_vertical_proof.py | scripts/archive/2026-10/ops/run_live_vertical_proof.py | script (batch 2) | 2026-07-25 |
| scripts/ops/weak_model_convergence.py | scripts/archive/2026-10/ops/weak_model_convergence.py | script (batch 2) | 2026-05-09 |
| scripts/ops/zero_trust_v2_report_dag.py | scripts/archive/2026-10/ops/zero_trust_v2_report_dag.py | script (batch 2) | 2026-05-22 |
| scripts/bench/eia_roi_wave2.py | scripts/archive/2026-10/bench/eia_roi_wave2.py | script (batch 2) | 2026-08-23 |
| scripts/ops/backfill_telemetry.py | scripts/archive/2026-10/ops/backfill_telemetry.py | script (batch 2) | 2026-05-27 |

### Batch-2 candidates dropped (kept in place)

| path | reason |
|---|---|
| scripts/ops/policy_override_lifecycle.py | test_policy_lane_integration.py also tests live check_policy_lane_gate.py (CI policy-lane-gate); impact-map policy rows |
| scripts/ops/check_policy_override_receipt.py | test_policy_lane_gate.py is run by .github/workflows/policy-lane-gate.yml and also covers live policy_lane_precommit/check_policy_lane_gate |
| scripts/bench/s2t_memory_sidecar_shadow.py | tests/gates/test_s2t_memory_sidecar_fixtures.py is a target of impact-map row nexus/infrastructure/state_json_store.py and of every plan |
| scripts/ops/nexus_self_hosted_mcp_http.py | its test file tests the live nexus.orchestrator.self_hosted_mcp_http module (shared test) |
| scripts/ops/lazy_executor_demo.py | tests/scenario/test_v25_scenarios.py shares it with live nexus.optimize modules |
| scripts/ops/test_repo.sh | 3 test files read it incl. live test_canonical_core_transport.py and localheal seam test |
| scripts/bench/freeze_public_manifest.py | its test is a named target of impact-map row nexus/research/sprint_service.py |
| scripts/ops/nexus_p110_launch_candidate_gate.py | its test is a named target of impact-map row nexus/research/sprint_service.py |
| scripts/bench/teacher_reference_gate.py | imported by nexus_p110_launch_candidate_gate.py, which stays |
| scripts/bench/check_post_wiring_regression_readiness.py | test_live_regression_entrypoints.py is shared with live run_c12481/run_c13453 regression scripts |
| scripts/scratch/phase13_closed_loop_test.py | tests/services/test_archived_legacy_engine_2026_10_13.py is shared (impact-map row nexus/evaluation/eval_harness.py; names live scripts) |
| scripts/bench/codex_dx_history.py | scripts/ops/pr_impact_gate.py:73-77 (gate code) maps configs/benchmarks/codex_dx_before_v1.json to tests/benchmark/test_codex_dx_history.py |
| scripts/ops/validate_codex_dx_failure_prevention.py | scripts/ops/pr_impact_gate.py:73 and tests/ops/test_pr_impact_gate.py:480 name tests/ops/test_codex_dx_failure_prevention.py |
| scripts/ops/repo_doctor.py | tests/ops/test_pr_impact_gate.py:1062 and test_codex_dx_failure_prevention.py:88 use tests/ops/test_repo_doctor.py as a real-file fixture reference |
