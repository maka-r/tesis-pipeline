# Exploration: Centralized Configuration (`pipeline_config.py`)

> **Phase**: SDD Explore  
> **Change**: crea pipeline_config.py para centralizar todas las constantes  
> **Date**: 2026-06-05  
> **Status**: Completed  

---

## 1. Current State

Five Python files each define their own set of constants at module level (import-level). ~50 constants are **duplicated with identical name+value** across 2–4 files. ~15 more have **same value but different names** between files. All file system paths are hardcoded per-script with no central reference.

### Files Analyzed

| File | Lines | Constants |
|------|-------|-----------|
| `piano_sampler.py` | ~1365 | ~55 constants (CONFIGURATION section) |
| `pipeline_compare.py` | 792 | ~25 constants (CONFIGURACION section) |
| `pipeline_rectify.py` | 1314 | ~50 constants (RUTAS + PARAMETROS GENERALES sections) |
| `pipeline_new_session_compare.py` | 852 | ~30 constants (RUTAS + PARAMETROS sections) |
| `claude_exporter.py` | 91 | 3 sets (TEXT_EXTENSIONS, IGNORE_DIRS, IGNORE_FILES) — independent |
| `contexto.md` | 1052 | Documents config values (reference source of truth) |

---

## 2. Comparison Matrix (Select Key Entries)

### 2a. Truly Shared Constants (identical name + value across ≥2 files)

| Constant | Value | piano_sampler | pipeline_compare | pipeline_rectify | new_session_compare |
|----------|-------|:---:|:---:|:---:|:---:|
| `TARGET_SR` | 48000 | ✅ | ✅ | ✅ | ✅ |
| `RMS_FRAME_LENGTH` | 2048 | ✅ | ✅ | ✅ | ✅ |
| `RMS_HOP_LENGTH` | 512 | ✅ | ✅ | ✅ | ✅ |
| `SAVGOL_WINDOW` | 51 | ✅ | ✅ | ✅ | — |
| `SAVGOL_POLY` | 3 | ✅ | ✅ | ✅ | — |
| `PITCH_FRAME_LENGTH` | 4096 | ✅ | ✅ | ✅ | ✅ |
| `PITCH_HOP_LENGTH` | 512 | ✅ | ✅ | ✅ | ✅ |
| `EXPORT_SUBTYPE` | "PCM_24" | ✅ | — | ✅ | — |
| `ONSET_HOP_LENGTH` | 128 | ✅ | — | — | ✅ |
| `ONSET_DELTA` | 0.10 | ✅ | — | — | ✅ |
| `ONSET_WAIT` | 10 | ✅ | — | — | ✅ |
| `ONSET_HPF_HZ` | 30 | ✅ | — | — | ✅ |
| `ONSET_PREROLL_MS` | 15 | ✅ | — | — | ✅ |
| `MIN_INTER_ONSET_SECONDS` | 4 | ✅ | — | — | ✅ |
| `MAX_TAIL_SECONDS` | 35.0 | ✅ | — | — | ✅ |
| `KEY_NOISE_SHELF_HZ` | 8000 | ✅ | ✅ | ✅ | — |
| `KNR_UNA_ATTENUATION_DB` | -8 | ✅ | — | ✅ | — |
| `NOISE_WINDOW_S` | 0.5 | — | — | ✅ | ✅ |
| `NOISE_TAIL_FRACTION` / `NOISE_TAIL_FRAC` | 2/3 | — | — | ✅ | ✅ |
| `FLUTTER_WARN_DB` | 5.0 | — | ✅ | ✅ | — |
| `FLUTTER_CRITICAL_DB` | 10.0 | — | ✅ | ✅ | — |
| `NOISE_SP_FRACTION` | 0.15 | ✅ | — | ✅ | — |
| `PITCH_WINDOW_S` / `PITCH_WINDOW_SECONDS` | 0.5 | ✅ | ✅ | ✅ | ✅ |
| `KEY_NOISE_WINDOW_MS` | 50 | ✅ | — | ✅ | — |
| `REEMERGENCE_RISE_DB` / `FLUTTER_RISE_DB` | 2.0 | ✅ | — | ✅ | — |

### 2b. Same Value, Different Name (rename candidates)

| Concept | piano_sampler name | Other files name | Common value |
|---------|-------------------|-----------------|:---:|
| Pitch window | `PITCH_WINDOW_SECONDS` | `PITCH_WINDOW_S` | 0.5 |
| Flutter skip | `FLUTTER_SUSTAIN_SKIP_MS` | `FLUTTER_SKIP_MS` | 400 |
| Level target p | `DYNAMIC_NORM_TARGET_DB` | `LEVEL_TARGET_DB` (rectify), `LEVEL_TARGET_P` (new_session) | -28.0 |
| Level tolerance | `DYNAMIC_NORM_TOLERANCE_DB` | `LEVEL_TOLERANCE` | 1.5 |
| Rise threshold | `FLUTTER_RISE_DB` | `REEMERGENCE_RISE_DB` | 2.0 |
| Tail fraction | _(inferred)_ | `NOISE_TAIL_FRACTION` / `NOISE_TAIL_FRAC` | 2/3 |
| SP fraction | `NOISE_WINDOW_SP_FRACTION` | `NOISE_SP_FRACTION` | 0.15 |
| Sustain start | `DYNAMIC_NORM_MEASURE_START_MS` | `SUSTAIN_START_MS` (3 files) | 200 |
| Sustain end | `DYNAMIC_NORM_MEASURE_END_MS` | `SUSTAIN_END_MS` (3 files) | 700 |
| Attack window | _(hardcoded 50ms in funcs)_ | `ATTACK_MS` (3 files) | 50 |
| Boost max | `LEVEL_MAX_BOOST_UNA_DB` | `LEVEL_MAX_BOOST_UNA` | 12.0 |
| Hum freqs | `HUM_N_HARMONICS * BASE_HZ` | `HUM_FREQS_50HZ` / `HUM_FREQS_60HZ` | — |

### 2c. Constants Unique to One File

| File | Unique constants |
|------|-----------------|
| **piano_sampler** | `PHASE_CORRECTION_ENABLED`, `PHASE_CORRECTION_PRIORITY_CHANNEL`, `PHASE_N_FFT`, `PHASE_HOP_LENGTH`, `PHASE_CHUNK_SECONDS`, `ONSET_MIN_PEAK_DB`, `NOISE_FLOOR_PERCENTILE`, `MIN_FRAMES_BELOW`, `OFFSET_REL_DECAY_ENABLED`, `OFFSET_REL_DECAY_DB`, `OFFSET_PEAK_SKIP_MS`, `MIN_TAIL_LOW/MID/HIGH_HZ`, `HUM_FILTER_ENABLED`, `HUM_BASE_HZ`, `HUM_N_HARMONICS`, `HUM_Q`, `HUM_SUBSONIC_HP_HZ`, `KEY_NOISE_REDUCTION_ENABLED`, `KEY_NOISE_MIN_F0_HZ`, `DYNAMIC_NORM_ENABLED`, `DYNAMIC_NORM_APPLY_BOOST`, `FLUTTER_THRESHOLD_DB`, `CLEANUP_FILTER_ENABLED`, `CLEANUP_LPF_HZ`, `CLEANUP_NOTCH_HZ/Q`, `EXPORT_FADEIN_MS`, `DEBUG_VISUALIZE`, `ONSET_GUARD_SECONDS`, `SESSION_MODIFIERS`, `INTENSITY_LABEL` |
| **pipeline_rectify** | `KNR_PLUS_ATTENUATION_DB`, `KNR_PLUS_WINDOW_MS`, `KNR_HF_THRESHOLD_DB`, `TRIM_FADEOUT_MS`, `FLUTTER_SMOOTH_WIN_LEVE`, `FLUTTER_SMOOTH_WIN_CRITICO`, `FLUTTER_SMOOTH_RAMP_MS`, `CLICK_ONSET_SKIP_MS`, `CLICK_THRESHOLD_FS`, `RUMBLE_HZ`, `RUMBLE_DB_THRESHOLD`, `DC_OFFSET_THRESHOLD`, `MVSEP_PEAK_DB`, `SNR_TIER_*` |
| **pipeline_compare** | `LEVEL_INCONSISTENCY_DB`, `LEVEL_CROSS_SESSION_DB`, `HF_WARN_DB`, `DECAY_RATIO_TOLERANCE`, `SESSION_METADATA`, session labels |
| **new_session_compare** | `HUM_FREQS_50HZ`, `HUM_FREQS_60HZ`, `HUM_BANDWIDTH_HZ`, `HUM_THRESHOLD_DB`, `LEVEL_TARGET_MF`, `PEAK_TARGET_MF` |
| **claude_exporter** | `TEXT_EXTENSIONS`, `IGNORE_DIRS`, `IGNORE_FILES` — fully independent, no overlap |

### 2d. Hardcoded Paths (11 total)

All paths reference the same base directory tree:
```
D:\Sesiones y proyectos\SESION 29-8\Pruebas de rendimiento denoise\Output_Samples\
```

| Variable | File | Full path |
|----------|------|-----------|
| `INPUT_FILE` | piano_sampler | `C:\Users\Macarena\Downloads\output\proyecto-balance-tesis-002_piano-model_mt_2_piano.wav` |
| `OUTPUT_DIR` | piano_sampler | `…\Output_Samples` |
| `SESSION_A["folder"]` | pipeline_compare | `…\Output_Samples\p\piano-model_mt_2_piano` |
| `SESSION_B["folder"]` | pipeline_compare | `…\Output_Samples\p\proyecto-balance-tesis-002_piano-model_mt_2_piano` |
| `OUTPUT_DIR` | pipeline_compare | `…\Output_Samples\compare` |
| `SESSIONS[0]` | pipeline_rectify | `…\Output_Samples\p\piano-model_mt_2_piano` |
| `SESSIONS[1]` | pipeline_rectify | `…\Output_Samples\p\proyecto-balance-tesis-002_piano-model_mt_2_piano` |
| `OUTPUT_DIR` | pipeline_rectify | `…\Output_Samples\p_rectificado_pip` |
| `SPECTRAL_DIR` | pipeline_rectify | `…\Output_Samples\p_rectificado_pip\_spectral` |
| `EXISTING_DIR` | new_session_compare | `…\Output_Samples\p_rectificado_pip` |
| `NEW_WAV` | new_session_compare | `D:\Renders multipistas\Tesis\Crudos 15-5\TEMPLATE_GRABACION_PIANO_XY.wav` |
| `OUTPUT_DIR` | new_session_compare | `…\Output_Samples\new_session_compare` |

---

## 3. Key Findings

### 3.1 No Name-Clash Bugs Found
All constants with the same name across files have identical values. No `RMS_FRAME_LENGTH=2048` in one file and `RMS_FRAME_LENGTH=4096` in another. The duplication is consistent — but still fragile.

### 3.2 15 Name Mismatches Need Unification
Same values, different names. E.g., `PITCH_WINDOW_SECONDS` vs `PITCH_WINDOW_S`. After import `from pipeline_config import *` these would conflict unless unified.

### 3.3 Level Targets Need a Structure
`DYNAMIC_NORM_TARGET_DB=-28.0`, `LEVEL_TARGET_DB=-28.0`, `LEVEL_TARGET_P=-28.0` all mean the same thing. `contexto.md` documents targets per dynamic:
- p = -28.0, mp = -22.0, mf = -18.0, f = -14.0, ff = -10.0 dBFS
→ Should be a dict: `LEVEL_TARGET = {"p": -28.0, "mp": -22.0, "mf": -18.0, "f": -14.0, "ff": -10.0}`

### 3.4 `claude_exporter.py` Is Independent
It has zero shared constants with the main pipeline. Should NOT be imported from `pipeline_config.py` — or at most just the shared IGNORE_DIRS list.

### 3.5 Paths Should Use a `BASE_DIR` + Relative Subpaths
11 hardcoded paths all compose from the same base. Introducing `BASE_SAMPLES_DIR` and computed subpaths eliminates duplication and makes adding new sessions trivial.

---

## 4. Proposed Structure for `pipeline_config.py`

```
pipeline_config.py
├── ## 1. Audio I/O Defaults
│   └── TARGET_SR, EXPORT_SUBTYPE, EXPORT_FADEIN_MS
├── ## 2. Paths (Base + Composition)
│   ├── BASE_SAMPLES_DIR (the long common prefix)
│   ├── INPUT_FILE, OUTPUT_DIR (per session — override here)
│   └── computed: SESSION[x], SPECTRAL_DIR, compare, new_session_compare
├── ## 3. Onset Detection
│   └── ONSET_*, MIN_INTER_ONSET_SECONDS, ONSET_MIN_PEAK_DB, ONSET_GUARD_SECONDS
├── ## 4. RMS / Envelope Analysis
│   └── RMS_FRAME_LENGTH, RMS_HOP_LENGTH, SAVGOL_*
├── ## 5. Offset Detection
│   └── MAX_TAIL_SECONDS, NOISE_FLOOR_*, OFFSET_*, MIN_FRAMES_BELOW
├── ## 6. Register-Based Minimum Tails
│   └── MIN_TAIL_{LOW,MID,HIGH}_HZ
├── ## 7. Phase Correction
│   └── PHASE_*
├── ## 8. Hum Filter
│   └── HUM_*
├── ## 9. Key Noise Reduction
│   └── KEY_NOISE_*, KNR_*
├── ## 10. Dynamic Normalization (Level Targets)
│   ├── LEVEL_TARGET dict per dynamic
│   ├── LEVEL_TOLERANCE, LEVEL_MAX_BOOST
│   └── DYNAMIC_NORM_ENABLED, APPLY_BOOST
├── ## 11. Attack / Sustain Analysis Windows
│   └── ATTACK_MS, SUSTAIN_START/END_MS, FLUTTER_SKIP_MS
├── ## 12. Flutter Analysis & Smoothing
│   └── FLUTTER_*, TRIM_FADEOUT_MS
├── ## 13. Pitch Detection
│   └── PITCH_*
├── ## 14. Export Cleanup
│   └── CLEANUP_*
├── ## 15. Session Modifiers
│   └── SESSION_MODIFIERS, *_UNA overrides
├── ## 16. Noise Floor & Artifact Detection
│   └── NOISE_*, HUM_FREQS_*, CLICK_*, RUMBLE_*, DC_*, MVSEP_*
├── ## 17. SNR Tiers
│   └── SNR_TIER_*
├── ## 18. Cross-Session Comparison
│   └── LEVEL_INCONSISTENCY_DB, LEVEL_CROSS_SESSION_DB, HF_WARN_DB, ...
└── ## 19. Debug
    └── DEBUG_VISUALIZE
```

### Import Strategy Recommendation

Replace the individual `CONFIGURATION` / `CONFIGURACION` / `RUTAS` + `PARAMETROS` sections in each file with:

```python
from pipeline_config import *   # or selective imports
```

**Warning**: Because of the 15 name-mismatches, a blunt `from pipeline_config import *` will cause NameError in scripts that currently use the "wrong" local name. Each script's internal references must be updated to use the canonical name.

---

## 5. Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| `from pipeline_config import *` breaks existing names | 🔴 High | Rename all conflicting local vars in each .py to match canonical names |
| File path re-composition gives wrong path | 🟠 Medium | Test each computed path before removing old hardcoded ones |
| Changing a shared constant affects 4 scripts at once | 🟡 Low | That's the point — but requires coordinated changes |
| `claude_exporter.py` imports config it doesn't need | 🟢 Low | Keep it separate or use a small subset |
| Recursive import if config uses functions from scripts | 🔴 High | Config must be pure constants — no runtime deps on the pipeline modules |

---

## 6. Ready for Proposal?

**Yes.** The analysis is complete. The extraction is well-defined: ~30 truly shared constants, ~15 name unifications, ~11 paths to parameterize. The structure is clear and the risks are manageable.

Next step: **SDD Propose** — formalize scope, approach (extract all vs staggered), and commit strategy.
