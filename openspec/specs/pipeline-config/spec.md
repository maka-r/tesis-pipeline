# pipeline-config Specification

## Purpose

Single source of truth for all shared constants, file paths, and level targets used across `piano_sampler.py`, `pipeline_compare.py`, `pipeline_rectify.py`, and `pipeline_new_session_compare.py`. Pure constants module — no functions, classes, or imports from pipeline modules.

## Requirements

| ID | Title | Description | Verification |
|----|-------|-------------|-------------|
| REQ-CONFIG-001 | Module structure | Pure Python constants only. UPPER_CASE naming. No `import` from pipeline modules. No functions/classes. | Inspection |
| REQ-CONFIG-002 | Audio I/O | `TARGET_SR=48000`, `AUDIO_FILE_EXTENSION=".wav"`, `EXPORT_SUBTYPE="PCM_24"` | Comparison |
| REQ-CONFIG-003 | Path configuration | `BASE_SAMPLES_DIR` as root with computed subpaths for each session/output dir. MUST match current 11 hardcoded paths exactly. | Comparison |
| REQ-CONFIG-004 | Onset detection | `ONSET_HOP_LENGTH=128`, `ONSET_DELTA=0.10`, `ONSET_WAIT=10`, `ONSET_HPF_HZ=30`, `ONSET_PREROLL_MS=15`, `MIN_INTER_ONSET_SECONDS=4`, `ONSET_MIN_PEAK_DB=-30.0`, `ONSET_GUARD_SECONDS=0.1` | Comparison |
| REQ-CONFIG-005 | RMS analysis | `RMS_FRAME_LENGTH=2048`, `RMS_HOP_LENGTH=512` | Comparison |
| REQ-CONFIG-006 | Offset detection | `MAX_TAIL_SECONDS=35.0`, `NOISE_FLOOR_MARGIN_DB=-2`, `NOISE_FLOOR_PERCENTILE=2`, `MIN_FRAMES_BELOW=25`, `OFFSET_REL_DECAY_ENABLED=True`, `OFFSET_REL_DECAY_DB=-30.0`, `OFFSET_PEAK_SKIP_MS=350` | Comparison |
| REQ-CONFIG-007 | Phase correction | `PHASE_CORRECTION_ENABLED=True`, `PHASE_N_FFT=2048`, `PHASE_HOP_LENGTH=512`, `PHASE_CHUNK_SECONDS=30` | Comparison |
| REQ-CONFIG-008 | Hum filter | `HUM_FILTER_ENABLED=False`, `HUM_BASE_HZ=50.0`, `HUM_N_HARMONICS=6`, `HUM_Q=30.0`, `HUM_SUBSONIC_HP_HZ=22.0` | Comparison |
| REQ-CONFIG-009 | Key noise reduction | `KEY_NOISE_REDUCTION_ENABLED=True`, `KEY_NOISE_MIN_F0_HZ=130.0`, `KEY_NOISE_WINDOW_MS=50`, `KEY_NOISE_SHELF_HZ=8000`, `KEY_NOISE_ATTENUATION_DB=-15`, `KNR_UNA_ATTENUATION_DB=-8` | Comparison |
| REQ-CONFIG-010 | Level targets | `LEVEL_TARGET = {"p": -28.0, "mp": -22.0, "mf": -18.0, "f": -14.0, "ff": -10.0}`. Plus `LEVEL_TOLERANCE=1.5`, `LEVEL_MAX_BOOST=8.0`, `LEVEL_MAX_BOOST_UNA=12.0`, `LEVEL_APPLY_BOOST=False` | Comparison |
| REQ-CONFIG-011 | Flutter detection | `FLUTTER_THRESHOLD_DB=2.5`, `FLUTTER_WARN_DB=5.0`, `FLUTTER_CRITICAL_DB=10.0`, `FLUTTER_SKIP_MS=400`, `REEMERGENCE_RISE_DB=2.0` | Comparison |
| REQ-CONFIG-012 | Flutter smoothing | `FLUTTER_SMOOTH_WIN_LEVE=51`, `FLUTTER_SMOOTH_WIN_CRITICO=101`, `FLUTTER_SMOOTH_RAMP_MS=50`, `TRIM_FADEOUT_MS=800` | Comparison |
| REQ-CONFIG-013 | Pitch detection | `PITCH_WINDOW_S=0.5`, `PITCH_FRAME_LENGTH=4096`, `PITCH_HOP_LENGTH=512` | Comparison |
| REQ-CONFIG-014 | Export cleanup | `CLEANUP_FILTER_ENABLED=True`, `CLEANUP_LPF_HZ=20000.0`, `CLEANUP_NOTCH_HZ=[8300.0]`, `CLEANUP_NOTCH_Q=30.0`, `FADE_IN_MS=8` | Comparison |
| REQ-CONFIG-015 | Session modifiers | `SESSION_MODIFIERS=[]`, `LEGACY_SR=44100` | Inspection |
| REQ-CONFIG-016 | Noise/artifact detection | `NOISE_WINDOW_S=0.5`, `NOISE_TAIL_FRACTION=2/3`, `NOISE_SP_FRACTION=0.15`, `RMS_FLOOR=1e-9`, `MAX_NOISE_DB=-60` | Comparison |
| REQ-CONFIG-017 | SNR tiers | `SNR_TIER_EXCELLENT=70.0`, `SNR_TIER_PROFESSIONAL=60.0`, `SNR_TIER_CONSUMER=50.0`, `SNR_TIER_MARGINAL=40.0` | Comparison |
| REQ-CONFIG-018 | Cross-session comparison | `LEVEL_INCONSISTENCY_DB=4.0`, `LEVEL_CROSS_SESSION_DB=3.0`, `HF_WARN_DB=-42.0`, `DECAY_RATIO_TOLERANCE=0.35`, `REEMERGENCE_FLAG=1` | Comparison |
| REQ-CONFIG-019 | Naming convention | All 15 name unifications mapped (see below). Legacy names MUST NOT appear in config. | Inspection |
| REQ-CONFIG-020 | Import policy | Explicit `from pipeline_config import <NAME>` only. No `import *`. Each script imports exactly the constants it uses. | Inspection |

## Naming Convention Map

| Old name (source) | Old name (others) | Canonical name |
|---|---|---|
| `PITCH_WINDOW_SECONDS` (piano_sampler) | `PITCH_WINDOW_S` (3 files) | `PITCH_WINDOW_S` |
| `FLUTTER_SUSTAIN_SKIP_MS` (piano_sampler) | `FLUTTER_SKIP_MS` (3 files) | `FLUTTER_SKIP_MS` |
| `DYNAMIC_NORM_TARGET_DB` (piano_sampler) | `LEVEL_TARGET_DB` (rectify), `LEVEL_TARGET_P` (new_session) | `LEVEL_TARGET` dict |
| `DYNAMIC_NORM_TOLERANCE_DB` (piano_sampler) | `LEVEL_TOLERANCE` (rectify) | `LEVEL_TOLERANCE` |
| `FLUTTER_RISE_DB` (piano_sampler) | `REEMERGENCE_RISE_DB` (rectify) | `REEMERGENCE_RISE_DB` |
| `NOISE_TAIL_FRACTION` (rectify) | `NOISE_TAIL_FRAC` (new_session) | `NOISE_TAIL_FRACTION` |
| `NOISE_WINDOW_SP_FRACTION` (piano_sampler) | `NOISE_SP_FRACTION` (rectify) | `NOISE_SP_FRACTION` |
| `DYNAMIC_NORM_MEASURE_START_MS` (piano_sampler) | `SUSTAIN_START_MS` (3 files) | `SUSTAIN_START_MS` |
| `DYNAMIC_NORM_MEASURE_END_MS` (piano_sampler) | `SUSTAIN_END_MS` (3 files) | `SUSTAIN_END_MS` |
| `LEVEL_MAX_BOOST_UNA_DB` (piano_sampler) | `LEVEL_MAX_BOOST_UNA` (rectify) | `LEVEL_MAX_BOOST_UNA` |
| `ATTACK_MS` (hardcoded 50ms in func) | `ATTACK_MS` (3 files as constant) | `ATTACK_MS` |
| `HUM_FREQS_50HZ` / `HUM_FREQS_60HZ` (new_session) | `HUM_BASE_HZ` + `HUM_N_HARMONICS` (piano_sampler) | `HUM_BASE_HZ` + `HUM_N_HARMONICS` (computed) |
| `LEVEL_TARGET_DB` (rectify) | `LEVEL_TARGET_P` (new_session) | `LEVEL_TARGET["p"]` |
| `DYNAMIC_NORM_APPLY_BOOST` (piano_sampler) | — | `LEVEL_APPLY_BOOST` |
| `SAVGOL_POLY` (3 files) | `SAVGOL_POLYORDER` (—) | `SAVGOL_POLY` |

## Scenarios

### Scenario 1: Single script updated to use config
- **GIVEN** `pipeline_config.py` exists with all constants
- **WHEN** `piano_sampler.py` replaces its CONFIGURATION block with `from pipeline_config import TARGET_SR, ...` and internal references are updated to canonical names
- **THEN** `python piano_sampler.py` runs without errors and produces byte-identical WAV output for the same input file

### Scenario 2: All 4 scripts updated — full pipeline run
- **GIVEN** `pipeline_config.py` exists with all constants
- **WHEN** all 4 scripts are updated to import from config and internal names are canonicalized
- **THEN** `pipeline_compare.py`, `pipeline_rectify.py`, and `pipeline_new_session_compare.py` each run without errors
- **AND** the full pipeline (`piano_sampler` → `pipeline_rectify` → `pipeline_compare`) produces output identical to a run without the config module

### Scenario 3: LEVEL_TARGET dict used in normalization
- **GIVEN** `LEVEL_TARGET = {"p": -28.0, "mp": -22.0, "mf": -18.0, "f": -14.0, "ff": -10.0}`
- **WHEN** `piano_sampler.py` reads `LEVEL_TARGET["p"]` for dynamic normalization instead of `DYNAMIC_NORM_TARGET_DB`
- **THEN** the gain value applied to each note is identical to the original hardcoded `-28.0 dBFS` target
