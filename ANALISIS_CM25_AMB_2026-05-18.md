# Análisis de Toma Ambiente Mono — `TEMPLATE_GRABACION_PIANO_amb_Mono.wav`
> Generado: 2026-05-18 | Micrófono: CM25 (cardioide SDC) — canal ambiente
> Posición: ambiente de sala (cardioide direccional). CH1 del template REAPER (RECINPUT 0).
> Misma sesión que ORTF M5 y XY — grabación simultánea.

---

## 1. Información del Archivo

| Campo | Valor | Observación |
|---|---|---|
| Ruta | `...\TEMPLATE_GRABACION_PIANO_amb_Mono.wav` | |
| Sample rate | 48 000 Hz | Nativo — sin conversión |
| Bit depth | PCM_24 | |
| Canales declarados | 2 | ⚠ Ver sección 1.1 |
| Duración | 140.00 s | Misma sesión que ORTF y XY |
| Tamaño | 38.45 MB | |
| DC offset | −0.0000077 | Despreciable — OK |
| Clipping | Ninguno | ✅ OK |

### 1.1 Archivo estéreo pero DUAL-MONO — hallazgo crítico

```
Correlación L-R : 1.000000  (idénticos al bit)
RMS diferencia  : −240.00 dBFS  (esencialmente cero digital)
```

**L y R son bit-idénticos.** El CM25 es un micrófono mono: REAPER exportó su canal único
a ambas pistas del WAV estéreo. Este archivo **no contiene información estéreo**.
En el template REAPER (RECINPUT 0 = CH1), la señal se rutea como mono expandido a estéreo.

> **Implicación para el pipeline:** cargar con `sf.read(always_2d=True)` y usar únicamente
> `y[:, 0]` para todos los análisis. Usar `librosa.to_mono()` es equivalente pero innecesario.
> En `pipeline_rectify.py` el procesamiento estéreo es redundante — la exportación final
> puede ser **mono** para este canal, ahorrando la mitad del espacio en disco.

---

## 2. Niveles Globales y Clasificación Dinámica

### 2.1 Niveles globales

| Métrica | Valor |
|---|---|
| Peak global | −24.82 dBFS |
| RMS global | −50.99 dBFS |
| Peak máximo por nota real | −24.82 dBFS |
| RMS sustain promedio (notas reales) | −57.50 dBFS |
| Déficit vs target mf (peak −6 dBFS) | **−18.8 dB** |
| Ganancia necesaria en preamp | **+19 dB** en Focusrite |

### 2.2 Análisis por nota

| # | t_inicio | Duración | f0 Hz | Nota | Peak | RMS_sus | Dyn | Flutter | Origen |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 0.376s | 20.9s | ? ¹ | ? | −30.2 | −56.0 | p | 9.0 dB | ORTF/XY coincide |
| 2 | 21.315s | 15.2s | — | — | −52.2 | −65.6 | p | 8.0 dB | **EXTRA CM25** |
| 3 | 36.483s | 14.7s | 49.6 | G1 | −24.8 | −51.9 | p | 19.7 dB | ORTF/XY coincide |
| 4 | 51.216s | 17.7s | 49.6 | G1 | −27.3 | −53.6 | p | 8.5 dB | ORTF/XY coincide |
| 5 | 68.869s | 13.9s | — | — | −49.8 | −64.2 | p | 10.9 dB | **EXTRA CM25** |
| 6 | 82.747s | 17.0s | 99.1 | G2 | −28.0 | −62.0 | p | 7.6 dB | ORTF/XY coincide |
| 7 | 99.728s | 12.8s | 197.1 | G3 | −26.8 | −58.4 | p | 11.6 dB | ORTF/XY coincide² |
| 8 | 112.552s | 9.3s | — | — | −52.6 | −65.3 | p | 7.6 dB | **EXTRA CM25** |
| 9 | 121.877s | 18.1s | 197.1 | G3 | −28.7 | −63.2 | p | 12.7 dB | ORTF/XY coincide |

> ¹ Nota 1 — f0 no detectado por `pyin`: el nivel es −30.2 dBFS, bajo para estimación
> robusta de fundamental. Probable C#1/B0 por analogía con ORTF/XY.
>
> ² Nota 7 — el CM25 detecta el onset a 99.728s vs ORTF/XY en 100.424s (696 ms antes).
> El CM25 capta una excitación de sala previa al ataque directo — el pedal de sustain o la
> preparación del pianista resonando en el espacio antes de llegar al campo cercano.

### 2.3 Dinámica real vs intención

```
Target mf: peak = −6.0 dBFS
Mejor peak medido: −24.82 dBFS
Déficit: −18.8 dB → dinámica real grabada = pp/p

Dinámica real: pp/p  (NO mf como se intentó)
Ganancia necesaria para re-grabar a mf: +19 dB en el preamp Focusrite.
```

---

## 3. Eventos Extra — Exclusivos del CM25 Ambiente

El CM25, por su posición de campo lejano, captura **3 eventos acústicos** que los
micrófonos de campo cercano (XY y ORTF) no detectaron:

### Extra 1 — t = 21.32–36.48 s (15.2 s)

| Métrica | Valor |
|---|---|
| Peak | −52.2 dBFS |
| RMS | −65.2 dBFS |
| f0 | No detectado |
| RMS std (estacionariedad) | 1.9 dB → **estacionario** |
| Picos espectrales dominantes | 70.3, 82.0, 58.6, 117.2, 46.9 Hz |

**Diagnóstico:** resonancias simpáticas del instrumento excitadas por la primera nota.
Los picos de 58.6 Hz (≈ Bb1), 70.3 Hz (≈ C#2), 82.0 Hz (≈ E2) corresponden a cuerdas
que continúan vibrando simpáticamente mientras la primera nota decae.
No es una nota intencional ni ruido eléctrico — es la **cola de resonancia del piano** en sala.

### Extra 2 — t = 68.87–82.75 s (13.9 s)

| Métrica | Valor |
|---|---|
| Peak | −49.8 dBFS |
| RMS | −63.8 dBFS |
| f0 | No detectado |
| RMS std | 1.7 dB → **estacionario** |
| Picos espectrales | 199.2, 82.0, 93.8, 128.9, 246.1 Hz |

**Diagnóstico:** igual que Extra 1 — cola de resonancia de la nota G1 (f0 = 49.6 Hz).
El pico dominante a 199.2 Hz es el 4° armónico de G1 (4 × 49.6 = 198.4 Hz). La sala
mantiene estas frecuencias audibles mucho más tiempo que en campo cercano.

### Extra 3 — t = 112.55–121.88 s (9.3 s)

| Métrica | Valor |
|---|---|
| Peak | −52.6 dBFS |
| RMS | −65.3 dBFS |
| f0 | No detectado (infrasónico) |
| RMS std | 1.8 dB → **estacionario** |
| Picos espectrales | **11.7, 23.4, 35.2, 46.9, 93.8 Hz** |

**Diagnóstico:** eventos infrasónicos / modos de sala excitados por las notas graves
previas. Los picos en 11.7 Hz, 23.4 Hz y 35.2 Hz son **infrasónicos o modos de sala**
(debajo del rango audible del piano). Posibles fuentes:
- Modos resonantes de la habitación (dimensiones típicas de sala generan modos en 10–40 Hz)
- Vibración mecánica del cuerpo del piano transmitida al piso
- Movimiento de aire del pedal de sustain

> **Relevancia para pipeline:** los 3 eventos extra deben ser **excluidos del procesamiento**
> de `piano_sampler.py`. El onset detector los captura solo en el CM25 ambiente,
> no en los micrófonos de referencia. Filtrarlos cruzando onsets con la lista de ORTF/XY.

---

## 4. Análisis de Ruido y Piso de Ruido

### 4.1 Métricas clave

| Métrica | Valor | Interpretación |
|---|---|---|
| Piso de ruido (RMS mín 500ms) | **−67.44 dBFS** | El más alto de los tres canales |
| Wiener flatness | **0.4113** | Semi-blanco — el más natural del conjunto |
| Rumble LF (<20 Hz) relativo | **+3.9 dB** | 🔴 CRÍTICO: sub-sónicos más fuertes que la señal promedio |
| Hum eléctrico | **Ninguno** | ✅ Toma de tierra correcta |

### 4.2 Distribución espectral (durante nota G1, t = 36.5–40 s)

| Banda | Energía relativa al promedio de bin |
|---|---|
| LF < 200 Hz | **+28.7 dB** (dominante, pero menos que XY +36.2 dB) |
| MF 200 Hz – 4 kHz | **+13.6 dB** (mejor presencia MF del conjunto) |
| HF > 4 kHz | **−96.2 dB** (prácticamente ausente) |

### 4.3 Rumble LF — hallazgo crítico

```
Energía sub-20 Hz: +3.9 dB SOBRE la energía media de bin

Esto significa que el rango infrasónico (<20 Hz) tiene MÁS energía
por bin que el promedio del espectro entero. Es el peor resultado
de los tres canales (XY = −14.6 dB relativo).
```

**Origen probable:** el CM25 en posición de campo lejano capta vibración mecánica
del piso/sala, ventilación, y mecánica del piano transmitida por el suelo con mayor
eficiencia que los micrófonos de campo cercano (que están más alejados del piso).

**Acción obligatoria antes del pipeline:** filtro pasa-altos en REAPER:
- Mínimo: HP 80 Hz (Butterworth 4° orden) — elimina rumble sin afectar el piano
- Recomendado: HP 120 Hz para este canal ambiente (el piano en sala no tiene
  componentes útiles por debajo del C1 = 32.7 Hz, y a 120 Hz el rumble de sala
  ya no es audible en el contexto del sample)

### 4.4 Wiener flatness — gradiente de distancia documentado

| Canal | Flatness | Interpretación |
|---|---|---|
| XY (30 cm cuerdas) | 0.0033 | Casi puramente tonal — resonancias simpáticas de cuerdas |
| ORTF M5 (40–50 cm marco) | 0.2145 | Semi-tonal — mezcla simpáticas + sala |
| **CM25 (ambiente sala)** | **0.4113** | Semi-blanco — mezcla sala difusa + resonancias lejanas |

**Este gradiente es un hallazgo de tesis.** La flatness de Wiener crece monotónicamente
con la distancia de captura, documentando la transición del campo cercano (dominado por
resonancias de cuerdas tonales) al campo difuso de sala (ruido más blanco/natural).
Citable directamente en la sección de Resultados.

---

## 5. Flutter de Sustain

| Nota | Flutter ptp | Estado pipeline |
|---|---|---|
| G1 (nota 3, t=36.5s) | **19.7 dB** | 🔴 FLUTTER_CRITICO_RX |
| G3 (nota 9) | 12.7 dB | 🔴 FLUTTER_CRITICO_RX |
| G3 (nota 7) | 11.6 dB | 🔴 FLUTTER_CRITICO_RX |
| Extra 2 | 10.9 dB | (no es nota real) |
| G2 (nota 6) | 7.6 dB | ⚠ FLUTTER_SUAVIZADO |
| G1 (nota 4) | 8.5 dB | ⚠ FLUTTER_SUAVIZADO |
| Nota 1 | 9.0 dB | ⚠ FLUTTER_SUAVIZADO |

El flutter es menor que en la toma XY (CM25 promedio ~10.9 dB vs XY 14.4 dB).
La distancia de captura promedia las fluctuaciones de RMS de cuerdas individuales.

---

## 6. Comparación Completa — Tres Tomas de la Misma Sesión

| Métrica | XY (30 cm) | ORTF M5 (40–50 cm) | CM25 amb (sala) |
|---|---|---|---|
| **Peak máximo** | −17.88 dBFS | −29.37 dBFS | −24.82 dBFS |
| **Déficit vs mf** | −11.9 dB | −26.4 dB | −18.8 dB |
| **Gain necesario** | **+12 dB** | **+26 dB** | **+19 dB** |
| **Tipo de archivo** | Estéreo real | Estéreo real | Dual-mono |
| **Notas detectadas** | 6 | 6 | 9 (3 fantasma) |
| **Piso de ruido** | −70.71 dBFS | −77.30 dBFS | −67.44 dBFS |
| **Wiener flatness** | 0.0033 | 0.2145 | 0.4113 |
| **Rumble LF** | −14.6 dB rel | N/M | **+3.9 dB rel** 🔴 |
| **HF >4 kHz** | −104.8 dB rel | — | −96.2 dB rel |
| **MF 200–4 kHz** | +8.8 dB rel | — | **+13.6 dB rel** ✅ |
| **Hum eléctrico** | No† | Ninguno | Ninguno |
| **Flutter prom.** | 14.4 dB ptp | 36.3 dB ptp | ~10.9 dB ptp |
| **ITD** | 0.104 ms | −0.271 ms | N/A (mono) |
| **Corr. L-R** | 0.864 | — | **1.000** (dual-mono) |

> † El "hum" del XY fue identificado como armónicos simpáticos de G1, no eléctrico.

### 6.1 Rol de cada toma en la arquitectura del sampler

| Canal | Función en Kontakt | Fortaleza | Limitación |
|---|---|---|---|
| XY (30 cm) | Cuerpo y presencia directa | Mejor nivel, mayor coherencia MF | Sin HF, alta tonal noise |
| ORTF M5 (40–50 cm) | Imagen estéreo, espacialidad | Imagen natural, algo de HF | Nivel muy bajo, menor coherencia MF |
| CM25 amb | Reverb de sala, calidez LF | Mejor balance MF relativo | Dual-mono, rumble severo, fantasmas |

La combinación de los tres captura las tres dimensiones del piano:
presencia directa (XY) + imagen (ORTF) + sala/reverb (CM25).
Esta estrategia multimicrofónica es metodológicamente válida para la tesis.

---

## 7. Acciones Recomendadas

### 7.1 Antes de re-grabar

- [ ] **Subir ganancia preamp +19 dB** en Focusrite Control 2 para el CM25
- [ ] **Aplicar HP 120 Hz** en REAPER antes del render a 140s (eliminar rumble infrasónico)
- [ ] **Verificar posición del CM25:** para captura de ambiente de sala pura, asegurarse
      de que el micrófono NO esté sobre una superficie reflectante o acoplado al piso

### 7.2 Pipeline — parámetros específicos CM25 ambiente

```python
# piano_sampler.py — sesión CM25 ambiente
SESSION_MODIFIERS = []          # sin modificadores
INTENSITY_LABEL   = 'mf'       # una vez corregido el nivel
TARGET_SR         = 48000      # nativo — sin conversión

# CRÍTICO: filtrar onsets cruzando con lista de ORTF/XY antes de segmentar
# Los 3 onsets extra (t≈21.3, 68.9, 112.6s) son resonancias de sala, no notas.
# Agregar lista de exclusión por tiempo:
ONSET_EXCLUSION_S = [21.315, 68.869, 112.552]  # ±2s de tolerancia
```

```python
# pipeline_rectify.py — precauciones CM25
# 1. El archivo tiene L=R: procesar solo canal 0, exportar como mono
# 2. HP filter previo OBLIGATORIO: Butterworth 4° orden, fc = 120 Hz
# 3. KNR: aplicar normalmente (key noise sigue siendo relevante en ambiente)
# 4. smooth_flutter_sustain: G1 nota 3 = FLUTTER_CRITICO_RX (sg_win=101)
# 5. Noise: flatness 0.4113 → ruido semi-blanco = más tratable con RX Spectral
#    (a diferencia del ruido tonal MVSep que requiere De-flutter)
```

### 7.3 Oportunidad: el ruido del CM25 es más tratable

```
Flatness 0.4113 = más parecido a ruido blanco → iZotope RX Spectral DeNoise
Flatness 0.0033 (XY) = tonal = solo De-flutter funciona

Esto significa que el CM25 ambiente, pese a tener el piso más alto (-67.44 dBFS),
puede ser el canal con MEJOR SNR perceptivo post-reducción porque el ruido de sala
responde bien a reducción broadband, a diferencia del ruido tonal MVSep.
```

---

## 8. Relevancia para la Tesis

### 8.1 El gradiente de flatness como dato medible de distancia acústica

Los tres valores de Wiener flatness (0.003 → 0.214 → 0.411) son directamente citables
como evidencia cuantitativa de que **la distancia de captura determina el carácter
espectral del piso de ruido**, progresando del campo cercano dominado por resonancias
tonales hacia el campo difuso de sala con ruido más distribuido.

### 8.2 Los tres eventos fantasma documentan el instrumento

Los onsets extra (t=21.3, 68.9, 112.5s) capturados exclusivamente por el CM25
demuestran que el piano patrimonial genera resonancias simpáticas sostenidas de **15+ s**
que son audibles en sala pero imperceptibles en campo cercano. Este hallazgo:
- Documenta el comportamiento acústico del instrumento en contexto de sala
- Justifica el uso de noise gate en Kontakt 7 (las resonancias de sala entre notas
  serían audibles en el sampler sin gate)
- Es citable como evidencia del tiempo de reverberación natural del instrumento

### 8.3 El dual-mono confirma limitación de diseño de grabación

Haber exportado el CM25 como WAV estéreo con L=R duplicado es ineficiente pero no
dañino para el pipeline. Sin embargo, **confirma que la sesión no contempló captura
de ambiente estéreo real** (ej. par de micrófonos de apoyo en sala). Para sesiones
futuras, considerar un segundo canal de ambiente (CM25 + AT3035 en configuración de
sala, o el propio CM25 + room reverb en REAPER) para proporcionar dimensión espacial
al canal ambiente del sampler.

---

## 9. Resumen Ejecutivo

| Parámetro | Resultado | Acción |
|---|---|---|
| SR | 48 000 Hz nativo | ✅ Sin conversión |
| Dual-mono (L=R) | Confirmado | ⚠ Exportar como mono en pipeline |
| Clipping | Ninguno | ✅ OK |
| Nivel vs mf target | **−18.8 dB déficit** | 🔴 +19 dB en preamp Focusrite |
| Dinámica real | **pp/p** (no mf) | 🔴 Re-grabar |
| Eventos fantasma | **3 detectados** | ⚠ Excluir por lista de tiempo |
| Piso de ruido | −67.44 dBFS | 🔴 Mayor del conjunto |
| Wiener flatness | **0.4113** | ✅ Más tratable con RX Spectral |
| Rumble LF <20 Hz | **+3.9 dB relativo** | 🔴 HP 120 Hz obligatorio pre-pipeline |
| HF >4 kHz | −96.2 dB (ausente) | ⚠ Canal de sala: esperado |
| MF 200–4 kHz | **+13.6 dB rel** | ✅ Mejor del conjunto |
| Hum eléctrico | Ninguno | ✅ OK |
| Flutter G1 | **19.7 dB ptp** | 🔴 FLUTTER_CRITICO_RX |
| Gradiente flatness | Documenta distancia acústica | ✅ Citable en tesis |

**Acción prioritaria:** HP 120 Hz + re-grabar con +19 dB de ganancia.
El canal CM25 ambiente tiene el ruido más tratable del conjunto pero requiere
corrección de rumble severo antes de cualquier procesamiento.

---

*Análisis generado con el pipeline: `piano_sampler.py` + criterios de `pipeline_new_session_compare.py`*
*Herramientas: librosa (STFT, pyin, onset), soundfile, numpy, scipy.signal*
*Fecha: 2026-05-18 | Sesión: grabación multipista — perspectiva CM25 ambiente*
