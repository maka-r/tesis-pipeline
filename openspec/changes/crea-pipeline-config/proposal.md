# Proposal: Centralizar todas las constantes en pipeline_config.py

## Intent

Eliminar la duplicación de ~50 constantes idénticas en 4 scripts, unificar 15 nombres divergentes para el mismo valor, y centralizar 11 rutas de archivos que comparten base. Una fuente única de verdad previene desvíos futuros (cambiar una constante en 1 archivo y olvidar los otros 3) y habilita agregar nuevas dinámicas (mp, mf, f, ff) con un solo punto de edición.

## Scope

### In Scope
- Crear `pipeline_config.py` con ~19 secciones (Audio I/O, Paths, Onset, RMS, Offset, Phase, Hum, Key Noise, Level Targets, Flutter, Pitch, Cleanup, Session Modifiers, Noise/Artifact, SNR, Cross-Session, Debug)
- Unificar 15 nombres divergentes a canónicos (e.g. `PITCH_WINDOW_S` sobre `PITCH_WINDOW_SECONDS`)
- Centralizar 11 rutas usando `BASE_SAMPLES_DIR` + subpaths computados
- Convertir targets de nivel en `LEVEL_TARGET` dict por dinámica (p/mp/mf/f/ff)
- Actualizar imports en piano_sampler.py, pipeline_compare.py, pipeline_rectify.py, pipeline_new_session_compare.py
- Renombrar referencias internas en cada script a los nombres canónicos

### Out of Scope
- `claude_exporter.py` — 0 constantes compartidas con los pipelines
- Funciones utilitarias, lógica computacional o types/hints
- Refactor de arquitectura interna (solo extracción de constantes)
- Agregar type hints a las constantes

## Capabilities

### New Capabilities
- `pipeline-config`: Contrato del módulo de configuración centralizada — secciones, nombres canónicos, rutas base, y política de importación

### Modified Capabilities
- None — refactor puro; ningún comportamiento existente cambia

## Approach

Crear `pipeline_config.py` como módulo de constantes puras (sin imports de los pipelines). Import explícito (`from pipeline_config import TARGET_SR, ...`) en cada script — prohibido `import *`. Migración en 6 fases secuenciales, cada fase es un PR orquestado (force-chained).

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `pipeline_config.py` | New | Módulo central con ~19 secciones |
| `piano_sampler.py` | Modified | Reemplazar CONFIGURATION block → imports |
| `pipeline_compare.py` | Modified | Reemplazar CONFIGURACION block → imports |
| `pipeline_rectify.py` | Modified | Reemplazar RUTAS + PARAMETROS → imports |
| `pipeline_new_session_compare.py` | Modified | Reemplazar RUTAS + PARAMETROS → imports |

## Migration Plan (6 Fases)

| Fase | Acción | Archivos tocados |
|------|--------|------------------|
| 1 | Crear `pipeline_config.py` con todas las constantes | `pipeline_config.py` (nuevo) |
| 2 | Actualizar `piano_sampler.py` | `piano_sampler.py` |
| 3 | Actualizar `pipeline_compare.py` | `pipeline_compare.py` |
| 4 | Actualizar `pipeline_rectify.py` | `pipeline_rectify.py` |
| 5 | Actualizar `pipeline_new_session_compare.py` | `pipeline_new_session_compare.py` |
| 6 | Renombrar 15 nombres divergentes a canónicos en todos los archivos | Todos |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| `import *` causa NameError por nombres divergentes | Alta | Usar imports explícitos; never `import *` |
| Ruta computada difiere de hardcode original | Media | Verificar cada path computado vs original antes de borrar hardcode |
| Constante compartida cambiada afecta 4 scripts | Baja | Es el objetivo — cambios coordinados en un solo PR |
| Import circular (config → pipeline → config) | Baja | Regla estricta: config es constantes puras, sin imports de pipeline modules |

## Rollback Plan

Revertir el commit que introduce `pipeline_config.py` + modifica los 4 scripts. No hay migración de datos ni dependencias externas. Cada script vuelve a sus bloques de constantes originales.

## Success Criteria

- [ ] `python piano_sampler.py` corre sin errores y produce output idéntico
- [ ] `python pipeline_compare.py` corre sin errores y produce output idéntico
- [ ] `python pipeline_rectify.py` corre sin errores y produce output idéntico
- [ ] `python pipeline_new_session_compare.py` corre sin errores y produce output idéntico
- [ ] Los 15 nombres divergentes están unificados en todos los archivos
- [ ] Ningún script usa `from pipeline_config import *`
