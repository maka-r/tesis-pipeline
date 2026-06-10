# Análisis de Toma XY — `TEMPLATE_GRABACION_PIANO_XY.wav`
> Generado: 2026-05-18 | Pipeline: piano_sampler + pipeline_new_session_compare
> Posición de grabación: XY a **30 cm de las cuerdas**, apuntando al **Do central (C4)**,
> cerca de la cola del piano. Integrado como canal CH4+5 en el template REAPER.

---

## 1. Información del Archivo

| Campo | Valor |
|---|---|
| Ruta | `D:\Renders multipistas\Tesis\Crudos 15-5\TEMPLATE_GRABACION_PIANO_XY.wav` |
| Sample rate | 48 000 Hz (nativo — coincide con TARGET_SR del pipeline) |
| Bit depth | PCM_24 |
| Canales | 2 (estéreo L/R) |
| Duración | 140.00 s |
| Tamaño | 38.45 MB |
| DC offset | −0.000006 (despreciable — OK) |
| Clipping | **Ninguno** (0 muestras ≥ 0.9999 en ambos canales) |

---

## 2. Niveles Globales y Clasificación Dinámica

### 2.1 Resumen de niveles

| Métrica | Canal L | Canal R | Mono |
|---|---|---|---|
| Peak | −17.88 dBFS | −19.44 dBFS | −18.76 dBFS |
| RMS global | −47.12 dBFS | −47.31 dBFS | −47.52 dBFS |
| Balance L−R | | +1.27 dB (L más fuerte) | |

### 2.2 Análisis por nota

| # | t_inicio | Duración | f0 Hz | Nota | Peak L | Peak R | RMS_sus | Dyn_RMS | Dyn_pico | Flutter ptp |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 0.78s | 35.7s | 62.5 | **B1** ¹ | −24.4 | −26.3 | −56.7 | p | pp | 14.3 dB |
| 2 | 36.48s | 14.7s | 49.6 | G1 | −17.9 | −19.4 | −50.7 | p | pp | **23.0 dB** ⚠ |
| 3 | 51.20s | 31.6s | 49.6 | G1 | −20.0 | −21.6 | −56.6 | p | pp | 17.7 dB |
| 4 | 82.76s | 17.7s | 99.1 | G2 | −22.2 | −23.2 | −59.3 | p | pp | 11.9 dB |
| 5 | 100.42s | 21.4s | 197.1 | G3 | −22.7 | −21.4 | −66.3 | p | pp | 10.4 dB |
| 6 | 121.87s | 18.1s | 197.1 | G3 | −24.7 | −23.6 | −66.6 | p | pp | 11.0 dB |

> ¹ **Advertencia f0 nota 1:** el modelo `pyin` detecta 62.5 Hz (B1) en vez de ~34 Hz (C#1).
> Esta misma nota en la toma ORTF fue detectada a 33.9 Hz. La discrepancia indica que
> `pyin` está capturando el **segundo armónico** en lugar del fundamental, posiblemente
> porque la posición XY (a 30 cm sobre las cuerdas) tiene menos energía sub-grave que la
> posición ORTF (40–50 cm sobre el marco). Verificar f0 real en REAPER con un analizador espectral.

### 2.3 Clasificación dinámica y déficit vs target mf

```
Target mf → Peak: −6.0 dBFS | RMS sustain: −18.0 dBFS

Mejor peak medido  : −17.88 dBFS (nota 2, G1)
Déficit pico vs mf : −11.9 dB  →  se necesitan  +12 dB en el preamp Focusrite
Déficit RMS vs mf  : −32.7 dB  (nivel de sustain pp/p, no mf)

Dinámica real grabada : entre pp y p  (NO mf como se intentó)
```

> La toma XY tiene **+11.5 dB más de nivel que la toma ORTF** de la misma sesión (ORTF peak
> promedio: −32.4 dBFS). Esto es esperable por la menor distancia (30 cm vs 40–50 cm),
> pero ambas tomas siguen siendo insuficientes para mf. El Focusrite necesita +12 dB más de ganancia.

---

## 3. Análisis de Fase y Estéreo

### 3.1 Coherencia por banda de octava

| Banda | Coherencia | Estado |
|---|---|---|
| 31 – 63 Hz | **0.979** | ✅ Excelente |
| 63 – 126 Hz | **0.894** | ✅ OK |
| 126 – 252 Hz | **0.907** | ✅ OK |
| 252 – 504 Hz | **0.946** | ✅ Excelente |
| 504 – 1008 Hz | **0.902** | ✅ Excelente |
| 1008 – 2016 Hz | **0.941** | ✅ Excelente |
| 2016 – 4032 Hz | **0.901** | ✅ Excelente |
| 4032 – 8064 Hz | **0.098** | 🔴 CRÍTICO — borde del contenido útil |
| 8064 – 16128 Hz | **0.026** | 🔴 CRÍTICO — sin contenido HF útil |

### 3.2 ITD y correlación global

| Métrica | Valor | Referencia |
|---|---|---|
| ITD estimado (XY) | **+0.104 ms** | Teórico XY coincidente: 0 ms ✅ |
| Correlación L−R global | **0.864** | Típico XY90: 0.65–0.80 (levemente alto) |
| Balance L−R (RMS) | **+0.19 dB** | Esencialmente equilibrado ✅ |

### 3.3 Interpretación de la coherencia

**LF/MF (31 Hz – 4 kHz) — Excelente:**
La configuración XY coincidente produce coherencia alta y uniforme en todo el espectro
medio. Es significativamente mejor que la toma ORTF en la misma sesión:

| Banda | XY (esta toma) | ORTF M5 (sesión anterior) |
|---|---|---|
| 63 Hz | 0.979 | 0.870 |
| 1 kHz | 0.941 | 0.248 |
| 2 kHz | 0.901 | 0.156 |
| 4 kHz | 0.098 | 0.233 |
| 8 kHz | 0.026 | — |

El XY es inherentemente más mono-compatible. **Ventaja para Kontakt:** el instrumento
virtualizará mejor sin cancelaciones de fase al sumar canales en mono.

**HF (> 4 kHz) — Sin señal útil (0.046):**
La caída extrema NO es un defecto de coherencia de fase; es consecuencia directa de que
no hay energía HF capturada (ver sección 4). Con SNR tan bajo en HF, la coherencia mide
esencialmente ruido incoherente. **No hay información estéreo aprovechable por encima de 4 kHz.**

**Correlación global 0.866:**
Levemente por encima del rango típico XY90 (0.65–0.80). Puede indicar:
- Ángulo entre cápsulas efectivo menor a 90° (cápsulas demasiado juntas o convergentes)
- O imagen estéreo más estrecha de lo esperado por la posición a 30 cm

---

## 4. Análisis de Ruido y Piso de Ruido

### 4.1 Métricas de ruido

| Métrica | Valor | Interpretación |
|---|---|---|
| Piso de ruido (RMS mín 500ms) | **−70.71 dBFS** | Más alto que toma ORTF (−77.3 dBFS) |
| Flatness de Wiener | **0.0033** | Extremadamente tonal (pre-MVSep) |
| Rumble LF (<20 Hz) relativo | **−14.6 dB** | Significativo — se recomienda HP filter |

### 4.2 Distribución espectral

| Banda | Energía relativa al promedio de bin |
|---|---|
| LF < 200 Hz | **+36.2 dB** (dominante absoluto) |
| MF 200 Hz – 4 kHz | **+8.8 dB** |
| HF > 4 kHz | **−104.8 dB** (esencialmente cero) |

> La ausencia de HF útil (−104 dB relativo) es el hallazgo más importante de esta toma.
> A 30 cm sobre las cuerdas apuntando al Do central, la tabla armónica actúa como un
> filtro pasa-bajos natural: la madera absorbe y dispersa las frecuencias por encima de
> ~4 kHz antes de que lleguen al micrófono. Esto confirma que el XY en esta posición captura
> fundamentalmente el **cuerpo de la nota** (LF/MF), no el ataque ni el brillo (HF).

### 4.3 Hum detectado: piano sympathetic — NO hum eléctrico

El algoritmo de detección marcó: `[50, 60, 100, 120, 150, 250, 300 Hz]`

**Diagnóstico:** esto NO es hum eléctrico. Son **resonancias simpáticas del piano**.

| "Hum" detectado | Armónico real de G1 (f0 ≈ 49.6 Hz) |
|---|---|
| 50 Hz | G1 fundamental (49.6 Hz) |
| 100 Hz | 2° armónico G1 (99.2 Hz) |
| 150 Hz | 3° armónico G1 (148.8 Hz) |
| 250 Hz | 5° armónico G1 (248.0 Hz) |
| 300 Hz | 6° armónico G1 (297.6 Hz) |

La cuerda de G1 sigue resonando simpáticamente durante la cola de la grabación.
El 60 Hz detectado puede corresponder a B1 (62.5 Hz) o a hum de red de 60 Hz —
**verificar con grabación de silencio** (amortiguadores presionados, sin tocar).
La flatness de 0.0033 confirma que el piso de ruido es casi enteramente tonal
(resonancias de cuerdas), no ruido eléctrico blanco.

> **Implicación para tesis:** el piano patrimonial genera un piso de ruido tonal propio
> incluso en la cola de las notas, independientemente de la captura electrónica.
> Esta es otra manifestación de la variable controlada del instrumento.

---

## 5. Flutter de Sustain

| Nota | Flutter ptp | Estado pipeline |
|---|---|---|
| G1 (nota 2) | **23.0 dB** | 🔴 FLUTTER_CRITICO_RX (> 10 dB) |
| G1 (nota 3) | **17.7 dB** | 🔴 FLUTTER_CRITICO_RX |
| B1 (nota 1) | 14.3 dB | 🔴 FLUTTER_CRITICO_RX |
| G2 (nota 4) | 11.9 dB | 🔴 FLUTTER_CRITICO_RX |
| G3 (nota 6) | 11.0 dB | 🔴 FLUTTER_CRITICO_RX |
| G3 (nota 5) | 10.4 dB | 🔴 FLUTTER_CRITICO_RX |

**Las 6 notas superan el umbral crítico (> 10 dB ptp).** El flutter es más pronunciado
en G1 (cuerdas simpáticas de mayor longitud a 30 cm) que en G3. La proximidad extrema
amplifica las fluctuaciones de RMS por la modulación física de las cuerdas cercanas.

---

## 6. Comparación con Toma ORTF (Misma Sesión)

Los onsets de ambas tomas son **virtualmente idénticos** (diferencia < 30 ms):

| # | t ORTF | t XY | Diferencia |
|---|---|---|---|
| 1 | 0.79s | 0.78s | 10 ms |
| 2 | 36.50s | 36.48s | 20 ms |
| 3 | 51.22s | 51.20s | 20 ms |
| 4 | 82.77s | 82.76s | 10 ms |
| 5 | 100.43s | 100.42s | 10 ms |
| 6 | 121.89s | 121.87s | 20 ms |

**Conclusión:** son grabaciones simultáneas o de la misma toma. Constituyen dos perspectivas
complementarias del mismo evento acústico. Esto es importante para la tesis.

### 6.1 Tabla comparativa

| Métrica | XY (30 cm, cuerdas) | ORTF M5 (40–50 cm, marco) |
|---|---|---|
| Peak mejor | −17.88 dBFS | −29.37 dBFS |
| Déficit vs mf | **−11.9 dB** | −26.4 dB |
| Gain necesario | **+12 dB** | +26 dB |
| Coherencia LF (63 Hz) | **0.979** | 0.870 |
| Coherencia MF (1–4 kHz) | **0.883–0.913** | 0.156–0.248 |
| Coherencia HF (>4 kHz) | 0.046 | 0.233 |
| ITD | **+0.104 ms** | −0.271 ms |
| Correlación L-R | 0.866 | — |
| Piso de ruido | −70.71 dBFS | −77.3 dBFS |
| Flatness Wiener | **0.0033** | 0.2145 |
| Contenido HF | **Ausente** (−104 dB rel) | Presente pero débil |
| Flutter promedio | 14.4 dB | 36.3 dB |

### 6.2 Rol de cada perspectiva en el sampler

| Posición | Fortaleza | Limitación | Uso en Kontakt |
|---|---|---|---|
| **XY 30 cm** | Nivel (+11.5 dB), coherencia MF, mono-compatible | Sin HF, ruido de mecanismo | Cuerpo y calidez LF/MF |
| **ORTF 40–50 cm** | Imagen estéreo, algo de HF, menor ruido de mecanismo | Nivel bajo, menor coherencia MF | Espacialidad y ambiente |

La combinación de ambas perspectivas en el template REAPER (XY como referencia de cuerpo,
ORTF para espacialidad) es metodológicamente correcta. El pipeline procesará cada par por separado.

---

## 7. Acciones Recomendadas

### 7.1 Antes de re-grabar

- [ ] **Subir ganancia preamp ≈ +12 dB** en Focusrite Control 2 para alcanzar peak mf de −6 dBFS
- [ ] **Verificar ángulo XY:** la correlación 0.866 sugiere ángulo efectivo < 90°.
      Para XY90 con picos a 90°: verificar que las cápsulas estén exactamente enfrentadas en cruz
- [ ] **Test de silencio:** grabar 10 s con amortiguadores presionados (todos los pedales abajo)
      para distinguir hum eléctrico de resonancias simpáticas en la banda 50–60 Hz
- [ ] **Considerar subir posición:** la ausencia de HF indica que 30 cm desde las cuerdas
      es demasiado cercano para capturar el brillo del piano. Probar 50–70 cm para obtener balance
      LF/MF/HF más natural y reducir el rumble mecánico

### 7.2 Pipeline — parámetros para esta toma

```python
# piano_sampler.py — sesión XY
SESSION_MODIFIERS = []          # sin modificadores (grabación normal)
INTENSITY_LABEL   = 'mf'       # dinámica objetivo (una vez corregido el nivel)
TARGET_SR         = 48000      # nativo — sin resampleo

# Parámetros diferenciados por posición XY cercana:
# KNR: aplicar desde C3 en adelante (igual que pipeline estándar)
#   PERO: verificar si el proximity noise necesita shelf más bajo (ej. -20 dB)
#   porque a 30 cm el key noise se capta más fuerte

# Rumble: aplicar HP 80 Hz (más agresivo que el HP 20 Hz estándar)
#   Razón: -14.6 dB relativo en <20 Hz indica ruido mecánico de mecanismo de tecla
```

### 7.3 Pipeline — precauciones post-MVSep

```
1. PISO DE RUIDO más alto (-70.71 dBFS pre-MVSep vs -77.3 dBFS ORTF)
   → Después de MVSep esperado bajar ~14 dB, igual que ORTF
   → Monitor flatness post-MVSep: si sube de 0.08, aplicar smooth_flutter_sustain() con sg_win=101

2. HF AUSENTE por encima de 4 kHz
   → NO aplicar KNR encima de 8 kHz (no hay señal que proteger)
   → El espectrograma 5-panel de pipeline_rectify.py confirmará la distribución

3. FLUTTER CRÍTICO en TODAS las notas (10.4–23.0 dB ptp)
   → smooth_flutter_sustain() se activará en modo sg_win=101 para todas
   → Las 6 notas quedarán marcadas FLUTTER_CRITICO_RX → iZotope RX Elements post-pipeline

4. RESONANCIAS SIMPÁTICAS en cola (flatness 0.0033 pre-MVSep)
   → El modelo MVSep NO separa estas resonancias: son piano
   → Documentar en tesis: el piso tonal del XY es más bajo (más armónico) que el ORTF
      porque el XY captura directamente la tabla armónica

5. NOTE 1 — f0 VERIFICAR:
   → pyin detectó B1 (62.5 Hz); ORTF detectó C#1 (33.9 Hz) en la misma nota
   → Verificar en REAPER con analizador espectral cuál es el f0 real
   → Si es C#1 (~34 Hz), el pipeline asignará KNR incorrecto (C3=130 Hz mínimo)
```

---

## 8. Relevancia para la Tesis

### Variable controlada: posición de micrófonos

Esta toma agrega una **tercera perspectiva de captura** al diseño experimental:

| Perspectiva | Micrófonos | Posición | Captura principal |
|---|---|---|---|
| A (sesiones existentes) | CM25 + AT3035 | Posición no documentada | Referencia legacy capa p |
| B (sesiones futuras) | Rode M5 ORTF | 40–50 cm sobre marco | Espacialidad + imagen estéreo |
| C (esta toma) | XY (tipo a confirmar) | 30 cm sobre cuerdas | Cuerpo LF/MF + presencia directa |

Las tres perspectivas constituyen un **análisis multimicrofónico** documentable en la tesis
como variable de diseño, no como error de setup.

### Hallazgo de tesis: piso de ruido tonal en posición de campo cercano

La flatness de Wiener de 0.0033 (pre-MVSep) en la posición XY vs 0.2145 (pre-MVSep) en ORTF
demuestra que **la distancia de grabación determina el carácter del piso de ruido**:
- Campo cercano (30 cm): ruido dominado por resonancias de cuerdas → tonal, alto SNR tímbrico
- Campo medio (40–50 cm): ruido de sala + cuerdas → más mixto, menos tonal

Este dato es directamente citable en la sección de Métodos de la tesis como justificación
de la elección de posición de micrófono por dinámica.

### Limitación documentada: ausencia de HF en posición XY

La caída a −104 dB relativo en HF > 4 kHz implica que esta toma **no es autosuficiente**
como fuente principal de samples: requiere la combinación con la toma ORTF para completar
el espectro. Esta limitación debe documentarse como decisión de diseño en la tesis
(multi-mic blending) y como variable de implementación en Kontakt 7 (mix entre capas).

---

## 9. Resumen Ejecutivo

| Parámetro | Resultado | Acción |
|---|---|---|
| SR | 48 000 Hz nativo | ✅ Sin conversión |
| Clipping | Ninguno | ✅ OK |
| Nivel vs mf target | **−11.9 dB déficit** | 🔴 +12 dB en preamp antes de re-grabar |
| Dinámica real | **pp/p** (no mf) | 🔴 Re-grabar con más ganancia |
| f0 nota 1 | B1 (62.5 Hz) — posible alias | ⚠ Verificar en REAPER |
| Coherencia LF–MF | **0.846–0.979** | ✅ Excelente |
| Coherencia HF | **0.046** (>4 kHz) | ⚠ Sin HF útil — documentar |
| ITD | 0.104 ms | ✅ Correcto para XY |
| Correlación L-R | 0.866 | ⚠ Verificar ángulo ≥ 90° |
| Piso de ruido | −70.71 dBFS | ⚠ Más alto que ORTF |
| Flatness | 0.0033 | ⚠ Resonancias simpáticas (no hum) |
| Flutter | **10.4–23.0 dB ptp** | 🔴 FLUTTER_CRITICO_RX — todas las notas |
| Rumble LF | −14.6 dB relativo | ⚠ HP 80 Hz al procesar |
| HF energy | −104 dB relativo | 🔴 Posición demasiado cercana — subir a 50–70 cm |
| Hum 50/60 Hz | Resonancias G1 (no eléctrico) | ⚠ Confirmar con test de silencio |

**Acción prioritaria:** Re-grabar con +12 dB más de ganancia en el preamp.
La toma actual documenta la configuración del sistema y es válida para análisis de tesis,
pero no es apta como muestra final de mf para la biblioteca Kontakt.

---

*Análisis generado con el pipeline: `piano_sampler.py` + `pipeline_new_session_compare.py`*
*Herramientas: librosa (STFT, pyin, onset), soundfile, numpy, scipy.signal*
*Fecha: 2026-05-18 | Sesión: grabación multipista AB — perspectiva XY*
