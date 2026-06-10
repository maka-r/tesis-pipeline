# Design: pipeline_config.py — Centralized Constants Module

## Technical Approach

Pure constants module (`pipeline_config.py`) extracted from 4 pipeline scripts. ~70 shared constants organized in 19 sections matching pipeline data flow. Paths computed from `BASE_SAMPLES_DIR` via `os.path.join`. All 15 legacy name variants unified to canonical names. Level targets restructured as `dict` keyed by dynamic marking. Zero functions, zero classes, zero imports from pipeline modules.

## Architecture Decisions

| Decision | Choice | Alternatives | Rationale |
|----------|--------|-------------|-----------|
| Path model | `BASE_SAMPLES_DIR` + `os.path.join` computed paths | `pathlib.Path`, env vars | Matches existing `os.path.join` patterns in codebase; pure module-level computation, no runtime overhead |
| Level targets | `dict` keyed by dynamic (`p/mp/mf/f/ff`) | Per-var constants, Enum | Dict enables `LEVEL_TARGET[INTENSITY_LABEL]` in code, extensible to new dynamics without adding new vars |
| Import policy | Explicit `from pipeline_config import NAME` | `import *`, `import pipeline_config as cfg` | Per spec REQ-CONFIG-020; prevents NameError from unification renames, enables static analysis |
| Non-base paths | Stay as separate constants `INPUT_FILE`, `NEW_WAV_PATH` | Move under base | These paths are outside `BASE_SAMPLES_DIR` tree; forcing them under base is misleading |
| `SESSION_METADATA` | Stays in `pipeline_compare.py` | Move to config | Project-specific structured data, not shared constants; references paths that WILL come from config |

## Module Structure

```
pipeline_config.py          # Project root, alongside the 4 pipeline scripts
├── # -*- coding: utf-8 -*- (encoding header)
├── import os               # Single stdlib import for os.path.join
├── # ===== AUDIO I/O =====
├── # ===== PATHS =====
├── # ===== ONSET DETECTION =====
├── # ===== RMS / ENVELOPE =====
├── # ===== OFFSET DETECTION =====
├── # ===== PHASE CORRECTION =====
├── # ===== HUM FILTER =====
├── # ===== KEY NOISE REDUCTION =====
├── # ===== LEVEL TARGETS =====
├── # ===== FLUTTER DETECTION =====
├── # ===== FLUTTER SMOOTHING =====
├── # ===== PITCH DETECTION =====
├── # ===== EXPORT CLEANUP =====
├── # ===== SESSION MODIFIERS =====
├── # ===== NOISE / ARTIFACT DETECTION =====
├── # ===== SNR TIERS =====
├── # ===== CROSS-SESSION COMPARISON =====
└── # ===== DEBUG / LEGACY =====
```

## Section Constants

### Audio I/O
```python
TARGET_SR          = 48000
EXPORT_SUBTYPE     = "PCM_24"
AUDIO_FILE_EXT     = ".wav"     # canonical extension for all pipeline I/O
FADE_IN_MS         = 8           # cos fade-in on export (was EXPORT_FADEIN_MS)
```

### Paths
```python
import os

# Root for all session output — all derived paths below are computed from this
BASE_SAMPLES_DIR = r"D:\Sesiones y proyectos\SESION 29-8\Pruebas de rendimiento denoise\Output_Samples"

# Standalone paths (not under BASE_SAMPLES_DIR)
INPUT_FILE    = r"C:\Users\Macarena\Downloads\output\proyecto-balance-tesis-002_piano-model_mt_2_piano.wav"
NEW_WAV_PATH  = r"D:\Renders multipistas\Tesis\Crudos 15-5\TEMPLATE_GRABACION_PIANO_XY.wav"

# Computed subpaths
SESSION_A_DIR        = os.path.join(BASE_SAMPLES_DIR, "p", "piano-model_mt_2_piano")
SESSION_B_DIR        = os.path.join(BASE_SAMPLES_DIR, "p", "proyecto-balance-tesis-002_piano-model_mt_2_piano")
COMPARE_OUTPUT_DIR   = os.path.join(BASE_SAMPLES_DIR, "compare")
RECTIFY_OUTPUT_DIR   = os.path.join(BASE_SAMPLES_DIR, "p_rectificado_pip")
NEW_SESSION_OUT_DIR  = os.path.join(BASE_SAMPLES_DIR, "new_session_compare")
# NOTE: SPECTRAL_DIR is computed per-script: os.path.join(RECTIFY_OUTPUT_DIR, "_spectral")
```

**Path translation table:**

| Original hardcoded path | Script | Computed from base |
|---|---|---|
| `OUTPUT_DIR` = `BASE_SAMPLES_DIR` | piano_sampler | `BASE_SAMPLES_DIR` |
| `SESSION_A["folder"]` = `{BASE}\p\piano-model_mt_2_piano` | pipeline_compare | `SESSION_A_DIR` |
| `SESSION_B["folder"]` = `{BASE}\p\proyecto-balance-tesis-002...` | pipeline_compare | `SESSION_B_DIR` |
| `OUTPUT_DIR` = `{BASE}\compare` | pipeline_compare | `COMPARE_OUTPUT_DIR` |
| `SESSIONS[0]` = `{BASE}\p\piano-model_mt_2_piano` | pipeline_rectify | `SESSION_A_DIR` |
| `SESSIONS[1]` = `{BASE}\p\proyecto-balance-tesis-002...` | pipeline_rectify | `SESSION_B_DIR` |
| `OUTPUT_DIR` = `{BASE}\p_rectificado_pip` | pipeline_rectify | `RECTIFY_OUTPUT_DIR` |
| `SPECTRAL_DIR` = `OUTPUT_DIR + "\_spectral"` | pipeline_rectify | `RECTIFY_OUTPUT_DIR` (computed in script) |
| `EXISTING_DIR` = `{BASE}\p_rectificado_pip` | new_session_compare | `RECTIFY_OUTPUT_DIR` |
| `OUTPUT_DIR` = `{BASE}\new_session_compare` | new_session_compare | `NEW_SESSION_OUT_DIR` |

### Onset Detection
```python
ONSET_HOP_LENGTH       = 128
ONSET_DELTA            = 0.10
ONSET_WAIT             = 10
ONSET_HPF_HZ           = 30
ONSET_PREROLL_MS       = 15
MIN_INTER_ONSET_SECONDS = 4
ONSET_MIN_PEAK_DB      = -30.0
ONSET_GUARD_SECONDS    = 0.1
```

### RMS / Envelope
```python
RMS_FRAME_LENGTH = 2048
RMS_HOP_LENGTH   = 512
SAVGOL_WINDOW    = 51       # must be odd
SAVGOL_POLY      = 3
```

### Offset Detection
```python
MAX_TAIL_SECONDS       = 35.0
NOISE_FLOOR_MARGIN_DB  = -2
NOISE_FLOOR_PERCENTILE = 2
MIN_FRAMES_BELOW       = 25
OFFSET_REL_DECAY_ENABLED = True
OFFSET_REL_DECAY_DB    = -30.0
OFFSET_PEAK_SKIP_MS    = 350
MIN_TAIL_LOW_HZ        = 4.0    # notes < 200 Hz
MIN_TAIL_MID_HZ        = 2.0    # notes 200-500 Hz
MIN_TAIL_HIGH_HZ       = 1.0    # notes > 500 Hz
```

### Phase Correction
```python
PHASE_CORRECTION_ENABLED = True
PHASE_CORRECTION_PRIORITY_CHANNEL = "L"
PHASE_N_FFT            = 2048
PHASE_HOP_LENGTH       = 512
PHASE_CHUNK_SECONDS    = 30
```

### Hum Filter
```python
HUM_FILTER_ENABLED   = False
HUM_BASE_HZ          = 50.0
HUM_N_HARMONICS      = 6
HUM_Q                = 30.0
HUM_SUBSONIC_HP_HZ   = 22.0
```

### Key Noise Reduction
```python
KEY_NOISE_REDUCTION_ENABLED = True
KEY_NOISE_MIN_F0_HZ     = 130.0
KEY_NOISE_WINDOW_MS     = 50
KEY_NOISE_SHELF_HZ      = 8000
KEY_NOISE_ATTENUATION_DB = -15
KNR_UNA_ATTENUATION_DB  = -8
KNR_PLUS_ATTENUATION_DB = -10
KNR_PLUS_WINDOW_MS      = 50
KNR_HF_THRESHOLD_DB     = -38.0
```

### Level Targets
```python
LEVEL_TARGET = {
    "p":  -28.0,
    "mp": -22.0,
    "mf": -18.0,
    "f":  -14.0,
    "ff": -10.0,
}
LEVEL_TARGET_DEFAULT = "p"     # default dynamic when none specified
LEVEL_TOLERANCE      = 1.5     # dB — notes within ±tolerance → no gain
LEVEL_MAX_BOOST      = 8.0     # dB — ceiling for normal notes
LEVEL_MAX_BOOST_UNA  = 12.0    # dB — ceiling for una corda (_UNA)
LEVEL_APPLY_BOOST    = False   # False → attenuate only, never amplify
DYNAMIC_NORM_ENABLED = True
```

**Reference pattern**: Each script that normalizes level accesses via `LEVEL_TARGET["p"]` (or `LEVEL_TARGET[INTENSITY_LABEL]`).

### Flutter Detection
```python
FLUTTER_THRESHOLD_DB = 2.5     # ptp variance → flutter flag
FLUTTER_WARN_DB      = 5.0     # moderate flutter threshold
FLUTTER_CRITICAL_DB  = 10.0    # critical — requires RX
FLUTTER_SKIP_MS      = 400     # ms of attack to skip before analysis
REEMERGENCE_RISE_DB  = 2.0     # dB rise to count as re-emergence
```

### Flutter Smoothing
```python
FLUTTER_SMOOTH_WIN_LEVE    = 51    # Savgol window: moderate flutter
FLUTTER_SMOOTH_WIN_CRITICO = 101   # Savgol window: critical flutter
FLUTTER_SMOOTH_RAMP_MS     = 50    # attack→sustain transition ramp
TRIM_FADEOUT_MS            = 800   # cos fade-out for re-emergence trim
```

### Pitch Detection
```python
PITCH_WINDOW_S     = 0.5
PITCH_FRAME_LENGTH = 4096
PITCH_HOP_LENGTH   = 512
```

### Export Cleanup
```python
CLEANUP_FILTER_ENABLED = True
CLEANUP_LPF_HZ         = 20000.0
CLEANUP_NOTCH_HZ       = [8300.0]
CLEANUP_NOTCH_Q        = 30.0
```

### Session Modifiers
```python
SESSION_MODIFIERS = []    # [] = normal, ["UNA"] = una corda, ["SP"] = no pedal
```

### Noise / Artifact Detection
```python
NOISE_WINDOW_S       = 0.5
NOISE_TAIL_FRACTION  = 2/3
NOISE_SP_FRACTION    = 0.15    # for _SP (sin pedal) — fraction of note duration
RMS_FLOOR            = 1e-9    # epsilon for log-safe RMS
HUM_PEAK_RATIO       = 3.0
HUM_BANDWIDTH_HZ     = 4
HUM_THRESHOLD_DB     = -60
CLICK_ONSET_SKIP_MS  = 200
CLICK_THRESHOLD_FS   = 0.05
RUMBLE_HZ            = 20.0
RUMBLE_DB_THRESHOLD  = -40.0
DC_OFFSET_THRESHOLD  = 0.005
MVSEP_PEAK_DB        = 15.0
```

### SNR Tiers
```python
SNR_TIER_EXCELLENT    = 70.0
SNR_TIER_PROFESSIONAL = 60.0
SNR_TIER_CONSUMER     = 50.0
SNR_TIER_MARGINAL     = 40.0
```

### Cross-Session Comparison
```python
LEVEL_INCONSISTENCY_DB = 4.0
LEVEL_CROSS_SESSION_DB = 3.0
HF_WARN_DB             = -42.0
DECAY_RATIO_TOLERANCE  = 0.35
REEMERGENCE_FLAG       = 1
```

### Debug / Legacy
```python
DEBUG_VISUALIZE = False
LEGACY_SR       = 44100    # original SR of existing MVSep samples
```

## Name Unification Mapping

| Legacy name | Canonical name | Files affected |
|---|---|---|
| `PITCH_WINDOW_SECONDS` (piano_sampler) | `PITCH_WINDOW_S` | piano_sampler |
| `FLUTTER_SUSTAIN_SKIP_MS` (piano_sampler) | `FLUTTER_SKIP_MS` | piano_sampler |
| `DYNAMIC_NORM_TARGET_DB` (piano_sampler) | `LEVEL_TARGET["p"]` | piano_sampler, rectify, new_session |
| `DYNAMIC_NORM_TOLERANCE_DB` (piano_sampler) | `LEVEL_TOLERANCE` | piano_sampler, rectify |
| `FLUTTER_RISE_DB` (piano_sampler) | `REEMERGENCE_RISE_DB` | piano_sampler, rectify |
| `NOISE_TAIL_FRAC` (new_session) | `NOISE_TAIL_FRACTION` | new_session, rectify |
| `NOISE_WINDOW_SP_FRACTION` (piano_sampler) | `NOISE_SP_FRACTION` | piano_sampler, rectify |
| `DYNAMIC_NORM_MEASURE_START_MS` (piano_sampler) | `SUSTAIN_START_MS` | piano_sampler, compare, rectify, new_session |
| `DYNAMIC_NORM_MEASURE_END_MS` (piano_sampler) | `SUSTAIN_END_MS` | piano_sampler, compare, rectify, new_session |
| `LEVEL_MAX_BOOST_UNA_DB` (piano_sampler) | `LEVEL_MAX_BOOST_UNA` | piano_sampler, rectify |
| `DYNAMIC_NORM_APPLY_BOOST` (piano_sampler) | `LEVEL_APPLY_BOOST` | piano_sampler |
| `LEVEL_TARGET_DB` (rectify) | `LEVEL_TARGET["p"]` | rectify |
| `LEVEL_TARGET_P` (new_session) | `LEVEL_TARGET["p"]` | new_session |
| `LEVEL_TARGET_MF` (new_session) | `LEVEL_TARGET["mf"]` | new_session |
| `EXPORT_FADEIN_MS` (piano_sampler) | `FADE_IN_MS` | piano_sampler |
| `HUM_FREQS_50HZ` / `HUM_FREQS_60HZ` (new_session) | computed from `HUM_BASE_HZ` + `HUM_N_HARMONICS` | new_session |

## Import Design Per Script

### piano_sampler.py
```python
from pipeline_config import (
    TARGET_SR, EXPORT_SUBTYPE, FADE_IN_MS, AUDIO_FILE_EXT,
    INPUT_FILE, BASE_SAMPLES_DIR,
    PHASE_CORRECTION_ENABLED, PHASE_CORRECTION_PRIORITY_CHANNEL, PHASE_N_FFT,
    PHASE_HOP_LENGTH, PHASE_CHUNK_SECONDS,
    ONSET_HOP_LENGTH, ONSET_DELTA, ONSET_WAIT, ONSET_HPF_HZ, ONSET_PREROLL_MS,
    MIN_INTER_ONSET_SECONDS, ONSET_MIN_PEAK_DB, ONSET_GUARD_SECONDS,
    RMS_FRAME_LENGTH, RMS_HOP_LENGTH, SAVGOL_WINDOW, SAVGOL_POLY,
    MAX_TAIL_SECONDS, NOISE_FLOOR_MARGIN_DB, NOISE_FLOOR_PERCENTILE,
    MIN_FRAMES_BELOW, OFFSET_REL_DECAY_ENABLED, OFFSET_REL_DECAY_DB,
    OFFSET_PEAK_SKIP_MS, MIN_TAIL_LOW_HZ, MIN_TAIL_MID_HZ, MIN_TAIL_HIGH_HZ,
    HUM_FILTER_ENABLED, HUM_BASE_HZ, HUM_N_HARMONICS, HUM_Q, HUM_SUBSONIC_HP_HZ,
    KEY_NOISE_REDUCTION_ENABLED, KEY_NOISE_MIN_F0_HZ, KEY_NOISE_WINDOW_MS,
    KEY_NOISE_SHELF_HZ, KEY_NOISE_ATTENUATION_DB, KNR_UNA_ATTENUATION_DB,
    LEVEL_TARGET, LEVEL_TOLERANCE, LEVEL_MAX_BOOST, LEVEL_APPLY_BOOST,
    DYNAMIC_NORM_ENABLED,
    FLUTTER_THRESHOLD_DB, FLUTTER_SKIP_MS, REEMERGENCE_RISE_DB,
    PITCH_WINDOW_S, PITCH_FRAME_LENGTH,
    CLEANUP_FILTER_ENABLED, CLEANUP_LPF_HZ, CLEANUP_NOTCH_HZ, CLEANUP_NOTCH_Q,
    SESSION_MODIFIERS, NOISE_SP_FRACTION, DEBUG_VISUALIZE,
    SUSTAIN_START_MS, SUSTAIN_END_MS, RMS_FLOOR,
)  # ~50 imports
```

### pipeline_compare.py
```python
from pipeline_config import (
    TARGET_SR,
    SESSION_A_DIR, SESSION_B_DIR, COMPARE_OUTPUT_DIR,
    RMS_FRAME_LENGTH, RMS_HOP_LENGTH, SAVGOL_WINDOW, SAVGOL_POLY,
    KEY_NOISE_SHELF_HZ,
    LEVEL_INCONSISTENCY_DB, LEVEL_CROSS_SESSION_DB,
    FLUTTER_WARN_DB, FLUTTER_CRITICAL_DB, REEMERGENCE_FLAG,
    HF_WARN_DB, DECAY_RATIO_TOLERANCE,
    PITCH_WINDOW_S, PITCH_FRAME_LENGTH, PITCH_HOP_LENGTH,
    ATTACK_MS, SUSTAIN_START_MS, SUSTAIN_END_MS, FLUTTER_SKIP_MS,
)  # ~20 imports
```

### pipeline_rectify.py
```python
from pipeline_config import (
    TARGET_SR, EXPORT_SUBTYPE,
    SESSION_A_DIR, SESSION_B_DIR, RECTIFY_OUTPUT_DIR,
    RMS_FRAME_LENGTH, RMS_HOP_LENGTH, SAVGOL_WINDOW, SAVGOL_POLY,
    ATTACK_MS, SUSTAIN_START_MS, SUSTAIN_END_MS, FLUTTER_SKIP_MS,
    KEY_NOISE_SHELF_HZ, KNR_PLUS_ATTENUATION_DB, KNR_UNA_ATTENUATION_DB,
    KNR_PLUS_WINDOW_MS, KNR_HF_THRESHOLD_DB,
    LEVEL_TARGET, LEVEL_TOLERANCE, LEVEL_MAX_BOOST, LEVEL_MAX_BOOST_UNA,
    FLUTTER_WARN_DB, FLUTTER_CRITICAL_DB,
    FLUTTER_SMOOTH_WIN_LEVE, FLUTTER_SMOOTH_WIN_CRITICO, FLUTTER_SMOOTH_RAMP_MS,
    TRIM_FADEOUT_MS, REEMERGENCE_RISE_DB,
    PITCH_WINDOW_S, PITCH_FRAME_LENGTH, PITCH_HOP_LENGTH,
    NOISE_WINDOW_S, NOISE_TAIL_FRACTION, NOISE_SP_FRACTION, RMS_FLOOR,
    HUM_PEAK_RATIO, CLICK_ONSET_SKIP_MS, CLICK_THRESHOLD_FS,
    RUMBLE_HZ, RUMBLE_DB_THRESHOLD, DC_OFFSET_THRESHOLD, MVSEP_PEAK_DB,
    SNR_TIER_EXCELLENT, SNR_TIER_PROFESSIONAL, SNR_TIER_CONSUMER, SNR_TIER_MARGINAL,
)  # ~35 imports
```

### pipeline_new_session_compare.py
```python
from pipeline_config import (
    TARGET_SR, LEGACY_SR,
    RECTIFY_OUTPUT_DIR, NEW_WAV_PATH, NEW_SESSION_OUT_DIR,
    ATTACK_MS, SUSTAIN_START_MS, SUSTAIN_END_MS, FLUTTER_SKIP_MS,
    PITCH_FRAME_LENGTH, PITCH_HOP_LENGTH, PITCH_WINDOW_S,
    RMS_HOP_LENGTH, RMS_FRAME_LENGTH,
    ONSET_HOP_LENGTH, ONSET_DELTA, ONSET_WAIT, ONSET_HPF_HZ,
    ONSET_PREROLL_MS, MIN_INTER_ONSET_SECONDS, MAX_TAIL_SECONDS,
    NOISE_WINDOW_S, NOISE_TAIL_FRACTION, RMS_FLOOR,
    HUM_BASE_HZ, HUM_N_HARMONICS, HUM_BANDWIDTH_HZ, HUM_THRESHOLD_DB,
    LEVEL_TARGET,
)  # ~25 imports
```

## Change Impact Per Script

### piano_sampler.py
- **Remove**: `CONFIGURATION` block (lines 24–171, ~148 lines)
- **Add**: `from pipeline_config import ...` (~5 lines)
- **Modify**: Internal references to renamed constants:
  - `PITCH_WINDOW_SECONDS` → `PITCH_WINDOW_S` (lines 885, 135)
  - `FLUTTER_SUSTAIN_SKIP_MS` → `FLUTTER_SKIP_MS` (lines 685, 789)
  - `DYNAMIC_NORM_TARGET_DB` → `LEVEL_TARGET["p"]` or `LEVEL_TARGET[INTENSITY_LABEL]` (lines 497, 510, 512, 531)
  - `DYNAMIC_NORM_TOLERANCE_DB` → `LEVEL_TOLERANCE` (lines 534)
  - `DYNAMIC_NORM_MEASURE_START_MS` → `SUSTAIN_START_MS` (lines 508, 513)
  - `DYNAMIC_NORM_MEASURE_END_MS` → `SUSTAIN_END_MS` (lines 509, 513)
  - `DYNAMIC_NORM_APPLY_BOOST` → `LEVEL_APPLY_BOOST` (line 538)
  - `FLUTTER_RISE_DB` → `REEMERGENCE_RISE_DB` (line 709)
  - `NOISE_WINDOW_SP_FRACTION` → `NOISE_SP_FRACTION` (line 165)
  - `LEVEL_MAX_BOOST_UNA_DB` → `LEVEL_MAX_BOOST_UNA` (line 160)
  - `EXPORT_FADEIN_MS` → `FADE_IN_MS` (lines 1084, 123)
- **Estimated change**: −148, +5, ~11 renames = ~−132 net lines

### pipeline_compare.py
- **Remove**: `CONFIGURACION` block (lines 30–128, ~99 lines)
- **Add**: `from pipeline_config import ...` (~3 lines)
- **Modify**: `SESSION_A`/`SESSION_B`/`OUTPUT_DIR` use config paths; all remaining config vars removed
- **Estimated change**: −99, +3 = ~−96 net lines

### pipeline_rectify.py
- **Remove**: `RUTAS` + `PARAMETROS GENERALES` blocks (lines 42–114, ~73 lines)
- **Add**: `from pipeline_config import ...` (~4 lines)
- **Modify**: `SESSIONS` list, `OUTPUT_DIR`, `LEVEL_TARGET_DB` → `LEVEL_TARGET["p"]`
- **Estimated change**: −73, +4, ~5 renames = ~−64 net lines

### pipeline_new_session_compare.py
- **Remove**: `RUTAS` + `PARAMETROS` blocks (lines 31–75, ~45 lines)
- **Add**: `from pipeline_config import ...` (~4 lines)
- **Modify**: `EXISTING_DIR`, `NEW_WAV`, `OUTPUT_DIR`, `LEVEL_TARGET_P` → `LEVEL_TARGET["p"]`, `NOISE_TAIL_FRAC` → `NOISE_TAIL_FRACTION`, hum freqs computed
- **Estimated change**: −45, +4, ~6 renames = ~−35 net lines

**Total estimated: ~−327 net lines** (all reduction is elimination of duplicate config blocks)

## Verification Strategy

| Script | What to verify | Method | Pass criterion |
|---|---|---|---|
| `piano_sampler.py` | Same WAV output for same input | SHA-256 hash of each output WAV | All hashes identical pre/post |
| `pipeline_compare.py` | Same report text | File diff `compare_report.txt` | 0 differences |
| `pipeline_rectify.py` | Same rectified WAV + same logs | SHA-256 of WAVs + diff of TXT logs | All WAV hashes identical, 0 log diff |
| `new_session_compare.py` | Same report + same PNGs | File diff TXT + pixel-compare PNGs | 0 TXT diff, PNGs identical |

**"Identical output"** means: given the same input files, the post-refactor script produces byte-identical WAV files and character-identical TXT/PNG outputs. No spectral or approximate comparison needed — this is a pure constants extraction with zero algorithmic changes.

**Execution sequence per script** (run with existing input files):
1. `git stash` existing changes → run original → save outputs to `ref/` dir
2. `git stash pop` → run modified → save outputs to `new/` dir
3. Diff `ref/` vs `new/` for each output file

**Rollback guard**: If any output differs, the change must NOT be merged. The config path computation is the highest-risk area.

## Open Questions

- [ ] `INTENSITY_LABEL = "p"` stays in piano_sampler.py as per-run config, or moves to pipeline_config as a default?
  → **Decision**: Stay in piano_sampler.py. It's a per-invocation parameter, not a shared constant.

## Risks

| Risk | Mitigation |
|------|------------|
| Computed path differs from hardcoded original | Compare each computed path via `os.path.normpath` equality before deleting hardcodes |
| Import misses a constant that script uses | Each script's import list audited against `grep` of constant usage in that file |
| `HUM_FREQS_50HZ` removal in new_session_compare breaks hum detection | Add `HUM_FREQS_50HZ` and `HUM_FREQS_60HZ` as computed lists in the script (not config) to preserve existing behavior |
