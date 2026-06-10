# Tasks: crea pipeline_config.py para centralizar todas las constantes

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~641 |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1: Phase 1+2 (~385) → PR 2: Phase 3+4+5 (~256) → PR 3: Phase 6 (verify) |
| Delivery strategy | force-chained |
| Chain strategy | feature-branch-chain |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Create config + migrate piano_sampler | PR 1 | ~385 lines; base = feature/tracker branch |
| 2 | Migrate compare + rectify + new_session | PR 2 | ~256 lines; base = PR 1 branch |
| 3 | Verify all scripts produce identical output | PR 3 | 0 code changes; base = PR 2 branch |

## Phase 1: Create pipeline_config.py

- [ ] 1.1 Audio I/O + Paths section (~30 lines) [REQ-CONFIG-001,002,003]
- [ ] 1.2 Onset + RMS + Offset section (~40 lines) [REQ-CONFIG-004,005,006]
- [ ] 1.3 Phase + Hum + KNR section (~30 lines) [REQ-CONFIG-007,008,009]
- [ ] 1.4 Level Targets + Flutter section (~25 lines) [REQ-CONFIG-010,011]
- [ ] 1.5 Pitch + Cleanup + Session Modifiers (~25 lines) [REQ-CONFIG-012,013,014]
- [ ] 1.6 Noise/Artifact + SNR + Cross-Session + Debug (~40 lines) [REQ-CONFIG-015-018]
- [ ] 1.7 Naming convention map + section headers (~20 lines) [REQ-CONFIG-019]
- [ ] 1.8 Module header + import policy comments (~10 lines) [REQ-CONFIG-020]

## Phase 2: Update piano_sampler.py

- [ ] 2.1 Replace CONFIGURATION block (L24-171) with explicit import (~5 add, ~148 del) [REQ-CONFIG-020]
- [ ] 2.2 Rename 11 divergent names (PITCH_WINDOW_SECONDS→S, FLUTTER_SUSTAIN_SKIP_MS→SKIP_MS, etc.) [REQ-CONFIG-019]
- [ ] 2.3 Remove now-redundant local constants (covered by 2.1)

## Phase 3: Update pipeline_compare.py

- [ ] 3.1 Replace CONFIGURACION block (L30-128) with explicit import (~3 add, ~99 del) [REQ-CONFIG-020]
- [ ] 3.2 Rename SESSION_A["folder"]→SESSION_A_DIR, OUTPUT_DIR→COMPARE_OUTPUT_DIR [REQ-CONFIG-003]
- [ ] 3.3 Remove redundant local constants

## Phase 4: Update pipeline_rectify.py

- [ ] 4.1 Replace RUTAS + PARAMETROS blocks (L42-114) with explicit import (~4 add, ~73 del) [REQ-CONFIG-020]
- [ ] 4.2 Rename LEVEL_TARGET_DB→LEVEL_TARGET["p"], SESSIONS→SESSION_A/B_DIR [REQ-CONFIG-003,019]
- [ ] 4.3 Remove redundant local constants

## Phase 5: Update pipeline_new_session_compare.py

- [ ] 5.1 Replace RUTAS + PARAMETROS blocks (L31-75) with explicit import (~4 add, ~45 del) [REQ-CONFIG-020]
- [ ] 5.2 Rename NOISE_TAIL_FRAC→TAIL_FRACTION, LEVEL_TARGET_P→LEVEL_TARGET["p"], HUM_FREQS→computed [REQ-CONFIG-003,019]
- [ ] 5.3 Remove redundant local constants

## Phase 6: Final Verification

- [ ] 6.1 Run each script and verify byte-identical output (SHA-256 WAVs, diff TXT) [All REQ-CONFIG]
- [ ] 6.2 Audit: no `from pipeline_config import *` exists in any file [REQ-CONFIG-020]
- [ ] 6.3 Verify all 15 name unifications complete across all 4 scripts [REQ-CONFIG-019]

## Requirements Coverage Map

| REQ-CONFIG | Phase(s) | Key verification |
|---|---|---|
| 001 | 1 | Pure constants module — inspect |
| 002 | 1 | Audio I/O values match originals exactly |
| 003 | 1, 3, 4, 5 | Computed paths match originals via os.path.normpath |
| 004, 005, 006 | 1 | Onset/RMS/Offset values preserved |
| 007, 008, 009 | 1 | Phase/Hum/KNR values preserved |
| 010, 011 | 1 | LEVEL_TARGET dict + Flutter thresholds |
| 012, 013, 014 | 1 | Pitch/Cleanup/Session values preserved |
| 015-018 | 1 | Noise/SNR/Cross-session/Debug values preserved |
| 019 | 1.7, 2.2, 3.2, 4.2, 5.2, 6.3 | 15 name unifications enforced |
| 020 | 1.8, 2.1, 3.1, 4.1, 5.1, 6.2 | Explicit imports only; no `import *` |
