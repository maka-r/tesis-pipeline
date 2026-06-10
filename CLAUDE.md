# CLAUDE.md — Piano Sample Library Pipeline

> Memoria persistente del proyecto. Actualizar al final de cada sesión de trabajo.

---

## 1. Propósito del proyecto

Construcción de una **biblioteca de samples de piano profesional para Kontakt 7** como parte de una tesis de ingeniería de audio. El flujo toma grabaciones reales de piano (audio mezclado), las separa con el modelo neuronal **MVSep**, y aplica un pipeline de análisis y rectificación no destructiva para producir muestras listas para implementación en un sampler.

**Problema que resuelve:** Las grabaciones multi-sesión presentan inconsistencias de nivel, ruido de mecanismo de tecla (key noise), flutter de sustain por cuerdas desafinadas, re-emergencias de sustain y diferencias de dinámica entre sesiones. El pipeline detecta, documenta y corrige todo esto de forma auditable y no destructiva.

---

## 2. Stack tecnológico

| Componente | Detalle |
|---|---|
| Lenguaje | Python 3.x (Windows, cp1252 console) |
| Audio I/O | `soundfile` (lectura/escritura WAV, PCM_24) |
| DSP / análisis | `librosa` (STFT, pyin, RMS, onset detection) |
| Matemática | `numpy`, `scipy.signal` (Savitzky-Golay, filtros), `scipy.ndimage` |
| Visualización | `matplotlib` (espectrogramas PNG, backend Agg) |
| Separación de fuentes | **MVSep** (modelo externo, genera stems WAV) |
| Sampler destino | **Native Instruments Kontakt 7** |
| Formato de exportación | WAV 24-bit estéreo, 44.1 kHz (o SR original) |

---

## 3. Estructura del proyecto

```
SESION 29-8/Pruebas de rendimiento denoise/
│
├── CLAUDE.md                        ← este archivo (memoria del proyecto)
│
├── piano_sampler.py                 ← PIPELINE PRINCIPAL
│   Detecta onsets, aplica KNR, normalización dinámica,
│   analiza flutter/re-emergencia y exporta WAVs por nota.
│   INPUT: archivo WAV separado por MVSep (stem de piano)
│   OUTPUT: Output_Samples/p/<nombre_modelo>/
│
├── pipeline_compare.py              ← COMPARACIÓN ENTRE SESIONES
│   Carga todos los WAVs de dos sesiones, extrae métricas
│   (f0, RMS, HF, flutter, re-emergencia), detecta overlaps,
│   construye curva de tendencia de nivel y genera reportes.
│   OUTPUT: Output_Samples/compare/
│
├── pipeline_rectify.py              ← RECTIFICACIÓN NO DESTRUCTIVA
│   Lee los WAVs de ambas sesiones, aplica correcciones
│   (gain estático, KNR+, trim re-emergencia), genera
│   espectrogramas 5-panel y reportes de ruido/SNR/artefactos.
│   OUTPUT: Output_Samples/p_rectificado_pip/
│
├── Output_Samples/
│   ├── p/
│   │   ├── piano-model_mt_2_piano/          ← Sesión 01 (9 WAVs: C1–C4)
│   │   │   └── _spectral/                   ← PNGs de análisis espectral
│   │   └── proyecto-balance-tesis-002_piano-model_mt_2_piano/  ← Sesión 02 (12 WAVs: B0, C4–C7)
│   │       └── _spectral/
│   ├── compare/                             ← Reportes cross-sesión + PNGs
│   └── p_rectificado_pip/                   ← 21 WAVs rectificados (SALIDA FINAL)
│       ├── _spectral/                       ← 21 PNGs espectrogramas 5-panel
│       ├── correction_log.txt               ← Tabla de correcciones por nota
│       └── noise_snr_report.txt             ← Piso de ruido, SNR y artefactos
│
├── Media/                           ← Archivos de audio fuente originales
└── Backups/                         ← Backups de scripts anteriores
```

---

## 4. Estado actual

### ✅ Completado

| Módulo | Descripción |
|---|---|
| `piano_sampler.py` | Detección de onsets, KNR (−15 dB > 8 kHz para f0 ≥ 130 Hz), normalización dinámica no destructiva a −28 dBFS, análisis de flutter/re-emergencia, reporte espectral por nota. Procesadas Sesión 01 y Sesión 02. |
| `pipeline_compare.py` | Comparación cross-sesión completa. Genera `compare_report.txt` + 3 PNGs. Detectado NIVEL_CROSS_SESSION de −5.4 dB en C4 (Sesión A = mp, Sesión B = p correcta). |
| `pipeline_rectify.py` | Rectificación no destructiva de 21 muestras. Gain estático, KNR+, trim re-emergencia + cosine fade. **Nueva extensión:** análisis de piso de ruido, SNR con tiers de calidad, planitud espectral (artefacto MVSep), detección de hum y artefactos de forma de onda. Espectrogramas ampliados a 5 paneles. Genera `noise_snr_report.txt`. |

### 🔄 En construcción ahora mismo

- **Ejecución pendiente** de `pipeline_rectify.py` con el nuevo módulo de ruido/SNR para obtener `noise_snr_report.txt` con métricas reales de las 21 muestras.

### ⏳ Pendiente

1. **Re-grabación obligatoria:**
   - `C_7_p_RR1/RR2/RR3` — nivel 14–21 dB por debajo del target p; boost capped en +8 dB. Requiere mayor velocity en la próxima sesión.
   - `C_6_p_RR1` — necesita +8.6 dB (apenas sobre el techo). Candidato a re-grabar.
2. **Re-afinación del piano** — flutter crítico (>10 dB ptp) en C2_RR1, C4 x3, C5 x4, C7 x3. Prioridad antes de la próxima sesión de grabación.
3. **Edición manual en REAPER** — re-emergencias de sustain en C_1_p y C_4_p_RR1 para control fino del punto de corte.
4. **Implementación en Kontakt 7** — mapeo de key ranges, round robins, velocity layers, curvas de dinámica y noise gate de grupo.
5. **Grabación de dinámicas adicionales** — actualmente solo existe la capa `p`. Faltan al menos `mp`, `mf`, `f`.

---

## 5. Decisiones clave

### Arquitectura del pipeline

- **No-destructivo:** todas las correcciones son escalares aplicados en memoria; los WAVs originales de `Output_Samples/p/` nunca se modifican.
- **Orden de corrección fijo:** Gain → KNR+ → Trim_reemergencia. El orden importa porque el gain amplifica también el HF antes del segundo KNR.
- **Separación de responsabilidades:** `piano_sampler.py` hace la extracción por nota; `pipeline_compare.py` hace el QC cross-sesión; `pipeline_rectify.py` hace la corrección y el reporte final.

### Parámetros críticos

| Parámetro | Valor | Razón |
|---|---|---|
| `LEVEL_TARGET_DB` | −28.0 dBFS | Estándar RMS de sustain para dinámica `p` en librerías profesionales |
| `LEVEL_MAX_BOOST` | +8.0 dB | Techo para evitar amplificación de ruido inaceptable |
| `KNR shelf` | 8000 Hz, −15 dB | Rango de ruido de mecanismo de tecla (9–11 kHz); con ramp lineal para evitar artefactos |
| `KNR mínimo f0` | 130 Hz (C3) | Por debajo de C3, los armónicos graves enmascaran el key noise; aplicar KNR introduce coloración sin beneficio |
| `FLUTTER threshold` | ptp > 2.5 dB = warn, > 10 dB = crítico | Basado en percepción de inestabilidad de pitch en escucha crítica |
| `NOISE_WINDOW_S` | 500 ms | Ventana mínima estadísticamente representativa para el piso de ruido |
| `SNR tiers` | Excelente ≥ 70 dB, Prof ≥ 60 dB, Consumer ≥ 50 dB | Referencia VSL/Spitfire tier para librerías de piano |
| `MVSEP_PEAK_DB` | 15 dB sobre baseline | Umbral para detección de ruido musical estructurado post-separación |

### Convenciones de nomenclatura de WAVs

```
{Nota}_{Octava}_{Dinámica}[_RR{N}].wav
Ejemplo: C_4_p_RR2.wav  →  Do4, dinámica piano, Round Robin 2
         B_0_p.wav       →  Si0, dinámica piano (única toma)
```

### Detección de onset

- `ONSET_DELTA = 0.10` (aumentado de 0.06 para evitar falsos positivos en resonancias)
- `MIN_INTER_ONSET_SECONDS = 4` — filtra onsets secundarios por resonancia simpática
- `ONSET_PREROLL_MS = 15` — conserva el pre-ataque del sonido real

---

## 6. Comandos esenciales

```bash
# Instalar dependencias
pip install librosa soundfile numpy scipy matplotlib

# Pipeline 1: Extraer y procesar notas de una sesión
# Editar INPUT_FILE en piano_sampler.py antes de ejecutar
python piano_sampler.py

# Pipeline 2: Comparación cross-sesión
python pipeline_compare.py
# Salida: Output_Samples/compare/compare_report.txt + PNGs

# Pipeline 3: Rectificación + análisis de ruido/SNR (PIPELINE FINAL)
python pipeline_rectify.py
# Salida: Output_Samples/p_rectificado_pip/*.wav
#         Output_Samples/p_rectificado_pip/_spectral/*.png
#         Output_Samples/p_rectificado_pip/correction_log.txt
#         Output_Samples/p_rectificado_pip/noise_snr_report.txt
```

---

## 7. Contexto de sesión

### Resumen de esta sesión

1. **Extensión de `pipeline_rectify.py`** con tres nuevos módulos de análisis:
   - `analyze_noise_profile()` — localiza el segmento más silencioso (último tercio de la nota, ventana de 500 ms) y mide: RMS del piso de ruido (dBFS), planitud espectral de Wiener (0=tonal/MVSep artifact, 1=ruido blanco), hum a armónicos de 50/60 Hz, picos de ruido musical MVSep (bins > 15 dB sobre baseline local).
   - `compute_snr_quality()` — SNR = RMS_ataque − piso_ruido, clasifica en tiers VSL/Spitfire.
   - `detect_waveform_artifacts()` — DC offset, clipping, clicks incidentales post-onset, rumble sub-20 Hz.
2. **Espectrogramas ampliados a 5 paneles** — panel 5 nuevo: espectro del piso de ruido con baseline suavizado, marcas de hum y métricas de flatness/picos MVSep en el título.
3. **Nuevo reporte `noise_snr_report.txt`** — tabla comparativa de todas las notas, identificación de la nota con mejor SNR, ranking completo, análisis MVSep por nota, abordajes específicos por tipo de artefacto.

### Hallazgos clave del pipeline anterior (sin noise analysis aún ejecutado)

| Problema | Notas afectadas | Acción pipeline |
|---|---|---|
| Flutter crítico (>10 dB ptp) | C2_RR1, C4_RR1/RR2/RR3, C4, C5 x4, C7 x3 | Documentado; requiere re-afinación del piano |
| Nivel insuficiente (capped) | C6_RR1, C7 x3 | Boost +8 dB aplicado; flaggeado REQUIERE_REGRABACION |
| Re-emergencia de sustain | C1, C4_RR1, C7_RR2 | Trim + cosine fade-out aplicado |
| Cross-session level C4 | C4 Sesión A vs Sesión B | −5.4 dB de diferencia; Sesión A corregida (atenuada) |
| Key noise (HF > −38 dB) | C3 x3, C4 x3, C5 x3, C6 x2, B0 | KNR+ aplicado (−10 dB adicional sobre shelf 8 kHz) |
| Centroide invertido C7 | C7 x3 | Indica f0 fundamental débil; ruido domina en ataque |

### Próximos pasos concretos

```
[ ] 1. Ejecutar python pipeline_rectify.py (versión nueva con noise analysis)
        → Leer noise_snr_report.txt para identificar:
           a) La nota con mejor SNR de toda la sesión
           b) Si hay hum eléctrico en alguna nota
           c) Artefactos incidentales específicos a tratar en REAPER

[ ] 2. REAPER — edición manual:
        → Abrir C_1_p.wav y C_4_p_RR1.wav; ajustar punto de trim de re-emergencia
        → Si hay clicks detectados: localizar con forma de onda, aplicar crossfade 2–5 ms
        → Si hay DC offset: agregar filtro HP 5 Hz

[ ] 3. Nueva sesión de grabación:
        → Re-afinar el piano antes (prioridad absoluta — afecta 11 notas)
        → Re-grabar C7 x3 con velocity notablemente mayor
        → Re-grabar C6_RR1 (candidato opcional)
        → Grabar capas dinámicas adicionales: mp, mf, f (un set de tomas por nota)

[ ] 4. Correr pipeline completo sobre las nuevas grabaciones:
        piano_sampler.py → pipeline_compare.py → pipeline_rectify.py

[ ] 5. Implementación en Kontakt 7:
        → Mapear Output_Samples/p_rectificado_pip/*.wav a key ranges
        → Configurar round robins (RR1/RR2/RR3 por nota)
        → Noise gate de grupo para cortar cola de ruido MVSep
        → Velocity layers cuando existan múltiples dinámicas
        → Random tune ±3–5 cents por voz para dispersar flutter residual
```

### Flujo recomendado: Limpieza → Separación → Implementación

```
GRABACION
  └─► Grabación en DAW (REAPER) — una nota por take, pedal de sustain largo
      Formato: WAV 24-bit, 44.1 kHz, estéreo

LIMPIEZA (pre-separación)
  └─► Escucha crítica en REAPER: eliminar takes con ruido externo, clipping,
      pedal mal capturado. Exportar audio mezclado por dinámica.

SEPARACIÓN
  └─► MVSep: correr modelo sobre cada archivo exportado
      Obtener stem de piano (piano_only.wav)
      Verificar que no haya bleed de otras fuentes

PROCESAMIENTO POR NOTA (piano_sampler.py)
  └─► Detecta onsets → Segmenta notas → Aplica KNR → Normaliza dinámica
      → Exporta WAVs nombrados con convención {Nota}_{Oct}_{Din}[_RR{N}].wav

QC CROSS-SESIÓN (pipeline_compare.py)
  └─► Compara todas las sesiones de la misma dinámica
      → Detecta diferencias de nivel, flutter, HF entre sesiones
      → Genera compare_report.txt con flags de acción

RECTIFICACIÓN (pipeline_rectify.py)
  └─► Corrige inconsistencias no destructivamente
      → Genera WAVs finales + espectrogramas + correction_log + noise_snr_report
      → Identifica qué notas requieren re-grabación

EDICIÓN MANUAL (REAPER, solo si hay artefactos detectados)
  └─► Clicks, DC offset, re-emergencias que requieran ajuste fino

IMPLEMENTACIÓN (Kontakt 7)
  └─► Importar WAVs de p_rectificado_pip/
      → Mapear zonas, round robins, velocity layers
      → Noise gate, random tune, curvas de dinámica
```

---

*Última actualización: Sesión del 2026-05-06*
