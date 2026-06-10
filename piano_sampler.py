# -*- coding: utf-8 -*-
"""
piano_sampler.py
----------------
Pipeline local de segmentación de notas de piano para biblioteca de samples (Kontakt 7).

Flujo:
  load_audio → phase_correction → mono → onset detection → offset detection
  → pitch detection → label assignment → export → verify

Swappear INPUT_FILE en la sección CONFIGURATION para procesar distintas sesiones.
"""

import os
import gc
import re
import collections

import numpy as np
import scipy.signal
import librosa
import soundfile as sf

# =============================================================================
# CONFIGURATION
# =============================================================================

INPUT_FILE = r"C:\Users\Macarena\Downloads\output\proyecto-balance-tesis-002_piano-model_mt_2_piano.wav"
OUTPUT_DIR = r"D:\Sesiones y proyectos\SESION 29-8\Pruebas de rendimiento denoise\Output_Samples"
INTENSITY_LABEL = "p"

# Corrección de fase
PHASE_CORRECTION_ENABLED = True
PHASE_CORRECTION_PRIORITY_CHANNEL = "L"   # 'L' o 'R'
PHASE_N_FFT = 2048
PHASE_HOP_LENGTH = 512
PHASE_CHUNK_SECONDS = 30                  # procesar en chunks para evitar OOM

# Detección de onsets
ONSET_HOP_LENGTH = 128       # 2.7ms @ 48000 Hz
ONSET_DELTA = 0.10           # umbral ODF — subir elimina resonancias secundarias dentro del decay
ONSET_WAIT = 10              # frames mínimos entre onsets (~27ms con hop 128 @ 48000 Hz)
ONSET_HPF_HZ = 30            # corte del high-pass filter previo
ONSET_PREROLL_MS = 15        # ms de pre-roll; acotado por offset de nota anterior
MIN_INTER_ONSET_SECONDS = 4  # gap mínimo entre onsets válidos — onset más cercano que esto
                              # se considera resonancia secundaria y se descarta
ONSET_MIN_PEAK_DB = -30.0    # pico de ataque mínimo (dBFS) para aceptar un onset. Descarta
                              # falsos (resonancias/ruido) que preceden al ataque real y se lo
                              # "robarían" vía el filtro de gap. Notas mf reales pican -8..-12 dBFS;
                              # las resonancias simpáticas quedan < -35. None para desactivar.

# Detección de offsets (cola de resonancia)
MAX_TAIL_SECONDS = 35.0      # techo absoluto de búsqueda (fallback si no hay onset siguiente)
NOISE_FLOOR_MARGIN_DB = -2   # dB sobre el piso de ruido para declarar silencio
                              # negativo → el señal debe caer BAJO el piso estimado antes de marcar offset
                              # más bajo = colas más largas; subir si el final tarda demasiado
NOISE_FLOOR_PERCENTILE = 2   # percentil más bajo → estimador más conservador del piso real
MIN_FRAMES_BELOW = 25        # frames consecutivos bajo umbral (~267ms @ hop 512 @ 48000 Hz)
# Offset por decaimiento RELATIVO: la nota termina cuando su RMS cae este nivel bajo
# su propio pico, independiente del piso de ruido y del siguiente ataque. Resuelve las
# colas largas en tomas con pedal/ruido (donde el RMS no llega a tocar el piso).
# Convive con el criterio absoluto: gana el que dispare primero (umbral más alto).
OFFSET_REL_DECAY_ENABLED = True
OFFSET_REL_DECAY_DB      = -30.0   # dB bajo el pico de SUSTAIN (no el de ataque, ver SKIP)
OFFSET_PEAK_SKIP_MS      = 350     # ms de ataque a ignorar al medir el pico de referencia.
                                   # Mide sobre el sustain para no atar el umbral al transiente
                                   # del golpe (evita el corte prematuro de notas con ataque fuerte)
RMS_FRAME_LENGTH = 2048
RMS_HOP_LENGTH = 512
SAVGOL_WINDOW = 51           # debe ser impar; ventana grande → curva estable en decays lentos
SAVGOL_POLY = 3
MIN_TAIL_LOW_HZ = 4.0        # notas < 200 Hz
MIN_TAIL_MID_HZ = 2.0        # notas 200-500 Hz
MIN_TAIL_HIGH_HZ = 1.0       # notas > 500 Hz
ONSET_GUARD_SECONDS = 0.1    # margen antes del siguiente onset

# Filtro de hum (interferencia de red eléctrica) sobre la SEÑAL DE ANÁLISIS.
# Se aplica a y_mono antes de estimar piso, onsets, offset y pitch — NO al audio
# exportado (y_stereo queda intacto: el filtrado es no destructivo).
# Objetivo: bajar el piso de ruido para que detect_offset corte en el final
# musical real y no al nivel del hum, y evitar que pyin se enganche al hum/tonos
# de red en la cola. Notch angosto (Q alto) en armónicos de red para NO tocar las
# fundamentales del piano. HP subsónico suave bajo A0 (27.5 Hz) para rumble.
HUM_FILTER_ENABLED   = False  # OFF: baja el piso solo ~2 dB y NO mejora el offset
                              # (el corte lo limita el siguiente ataque, no el piso).
                              # Además, aplicado al análisis perjudica la detección de
                              # onsets. Reactivar solo si se aplica selectivamente.
HUM_BASE_HZ          = 50.0   # frecuencia de red (Argentina = 50 Hz; 60 en otras regiones)
HUM_N_HARMONICS      = 6      # 50, 100, 150, 200, 250, 300 Hz
HUM_Q                = 30.0   # Q alto = banda angosta (~±2 Hz); no toca fundamentales vecinas
HUM_SUBSONIC_HP_HZ   = 22.0   # HP suave bajo A0 (27.5 Hz); 0 para desactivar

# Reducción de ruido de mecanismo de tecla (key noise)
# El ruido de tecla ocupa 9-11 kHz, dura ~20-50ms desde el onset.
# Se aplica atenuación de high-shelf en esa ventana con rampa de salida gradual.
# Estándar en producción de sample libraries (Spitfire, EastWest, etc.)
KEY_NOISE_REDUCTION_ENABLED = True
KEY_NOISE_MIN_F0_HZ = 130.0      # C3 ≈ 130.8 Hz — aplicar solo a notas de este registro en adelante
KEY_NOISE_WINDOW_MS = 50         # ventana de ataque donde vive el ruido de tecla
KEY_NOISE_SHELF_HZ = 8000        # frecuencia de corte del high-shelf (9-11 kHz es el núcleo del ruido)
KEY_NOISE_ATTENUATION_DB = -15   # atenuación en dB sobre la banda de ruido de tecla

# Normalización de dinámica (gate de nivel estático)
# Aplica un único escalar de ganancia por nota — NO modifica el ADSR.
# Objetivo: homogeneizar la dinámica p entre registros con distinta velocity.
# TARGET_DB es el RMS de sustain objetivo para dinámica p (estándar profesional: -28 dBFS).
# MEASURE_START/END: ventana de sustain estabilizado a medir (ms desde onset).
# APPLY_BOOST: False → solo atenuación (nunca sube notas); evita amplificar piso de ruido.
DYNAMIC_NORM_ENABLED     = True
DYNAMIC_NORM_TARGET_DB   = -28.0  # dBFS RMS de sustain para dinámica p
DYNAMIC_NORM_MEASURE_START_MS = 200
DYNAMIC_NORM_MEASURE_END_MS   = 700
DYNAMIC_NORM_APPLY_BOOST = False  # solo reducir, nunca amplificar
DYNAMIC_NORM_TOLERANCE_DB = 1.5  # notas dentro de ±1.5 dB del target → gain=1.0

# Análisis de fluctuación de sustain (flutter)
FLUTTER_SUSTAIN_SKIP_MS  = 400   # ms de ataque a ignorar antes del análisis
FLUTTER_THRESHOLD_DB     = 2.5   # varianza pico-a-pico residual → flag de flutter
FLUTTER_RISE_DB          = 2.0   # re-emergencia: cuántos dB debe subir el RMS para
                                  # ser considerada reaparición del sustain

# Fade-in coseno en exportación (elimina clics de cuantización sin tocar el onset)
EXPORT_FADEIN_MS = 8

# Limpieza final del audio EXPORTADO (no destructiva — solo sobre el WAV de salida,
# la señal de análisis no se toca). Basado en la caracterización de ruido de 29-5:
#   LPF   → elimina tonos ultrasónicos 21-23 kHz (interferencia digital fuera de banda útil)
#   Notch → tonos fijos audibles detectados (8.3 kHz). Lista vacía [] desactiva los notches.
CLEANUP_FILTER_ENABLED = True
CLEANUP_LPF_HZ         = 20000.0   # corte del low-pass; None o 0 para desactivar
CLEANUP_NOTCH_HZ       = [8300.0]  # tonos fijos a eliminar (Hz)
CLEANUP_NOTCH_Q        = 30.0      # Q de los notch (alto = banda angosta, no toca el brillo)

# Detección de pitch
PITCH_WINDOW_SECONDS = 0.5
PITCH_FRAME_LENGTH = 4096
PITCH_HOP_LENGTH = 512

# Exportación
EXPORT_SUBTYPE = "PCM_24"    # 24-bit para Kontakt
TARGET_SR      = 48000       # sample rate objetivo; archivos a distinto SR se resamplean al cargar
DEBUG_VISUALIZE = False      # True → genera PNGs por nota (requiere matplotlib)

# =============================================================================
# MODIFICADORES DE SESION — controlan nomenclatura y parametros adaptativos
# Convencion: {Nota}_{Oct}_{Din}[_UNA][_SP][_RR{N}].wav
# =============================================================================

# Lista de modificadores activos para esta ejecucion.
# Ejemplos: []  ->  grabacion normal con pedal (por defecto)
#           ['UNA']       ->  sesion con sordina (una corda)
#           ['SP']        ->  sesion sin pedal de sustain
#           ['UNA', 'SP'] ->  sordina Y sin pedal
SESSION_MODIFIERS = []

# Parametros para una corda (_UNA):
# La sordina ya atenua fisicamente el HF; KNR mas suave evita sobre-procesamiento.
# El nivel es inherentemente mas bajo, por lo que se permite mayor boost.
KNR_UNA_ATTENUATION_DB  = -8     # dB (vs -15 normal)
LEVEL_MAX_BOOST_UNA_DB  = 12.0   # dB maximo de boost (vs +8 normal)

# Parametros para sin pedal (_SP):
# El decay es mas corto — la ventana de busqueda de silencio se escala
# como fraccion de la duracion total de la nota en lugar de usar 500 ms fijo.
NOISE_WINDOW_SP_FRACTION = 0.15  # 15% de la duracion de la nota

# Nota sobre flutter: el instrumento es un piano patrimonial que NO puede afinarse.
# El flutter documentado (beating entre cuerdas) es una CARACTERISTICA DEL INSTRUMENTO,
# no un artefacto de captura. Se documenta pero no se corrige en este pipeline.
# Estrategia gradual: pipeline -> REAPER -> iZotope RX -> Kontakt Random Tune +/-5 cents.

# =============================================================================
# AUDIO LOADING
# =============================================================================

def load_audio(filepath):
    """Carga estereo y resamplea a TARGET_SR si el archivo tiene un SR distinto."""
    print(f"Cargando: {filepath}")
    y, sr = librosa.load(filepath, sr=None, mono=False)
    if y.ndim == 1:
        y = np.stack([y, y])
    if sr != TARGET_SR:
        print(f"  Remuestreando {sr} Hz -> {TARGET_SR} Hz ...")
        y = np.stack([
            librosa.resample(y[c], orig_sr=sr, target_sr=TARGET_SR)
            for c in range(y.shape[0])
        ])
        sr = TARGET_SR
    print(f"  Shape: {y.shape}  SR: {sr} Hz  Duracion: {y.shape[1]/sr:.2f}s")
    return y, sr


# =============================================================================
# PHASE CORRECTION
# =============================================================================

def apply_phase_correction(y_stereo, sr,
                            priority_channel=PHASE_CORRECTION_PRIORITY_CHANNEL,
                            n_fft=PHASE_N_FFT,
                            hop_length=PHASE_HOP_LENGTH,
                            chunk_seconds=PHASE_CHUNK_SECONDS):
    """
    Alinea la fase del canal no-prioritario respecto al canal prioritario
    usando STFT, procesando en chunks para evitar OOM en archivos largos.
    """
    print(f"Aplicando corrección de fase (canal prioritario: {priority_channel})...")
    total_samples = y_stereo.shape[1]
    samples_per_chunk = int(sr * chunk_seconds)
    output = np.empty_like(y_stereo)

    # Calcular diferencia de fase del audio completo una sola vez
    stft_L_full = librosa.stft(y_stereo[0], n_fft=n_fft, hop_length=hop_length)
    stft_R_full = librosa.stft(y_stereo[1], n_fft=n_fft, hop_length=hop_length)
    phase_diff_full = np.angle(stft_L_full) - np.angle(stft_R_full)
    del stft_L_full, stft_R_full
    gc.collect()

    current_frame = 0

    for start in range(0, total_samples, samples_per_chunk):
        end = min(start + samples_per_chunk, total_samples)
        chunk_len = end - start
        chunk = y_stereo[:, start:end]

        stft_L = librosa.stft(chunk[0], n_fft=n_fft, hop_length=hop_length)
        stft_R = librosa.stft(chunk[1], n_fft=n_fft, hop_length=hop_length)
        n_frames = stft_L.shape[1]

        # Extraer slice de la diferencia de fase correspondiente a este chunk
        phase_slice = phase_diff_full[:, current_frame : current_frame + n_frames]
        if phase_slice.shape[1] != n_frames:
            phase_slice = librosa.util.fix_length(phase_slice, size=n_frames, axis=1)

        if priority_channel == "L":
            stft_R_corr = np.abs(stft_R) * np.exp(1j * (np.angle(stft_R) + phase_slice))
            y_L = librosa.istft(stft_L, hop_length=hop_length, length=chunk_len)
            y_R = librosa.istft(stft_R_corr, hop_length=hop_length, length=chunk_len)
        else:
            stft_L_corr = np.abs(stft_L) * np.exp(1j * (np.angle(stft_L) - phase_slice))
            y_L = librosa.istft(stft_L_corr, hop_length=hop_length, length=chunk_len)
            y_R = librosa.istft(stft_R, hop_length=hop_length, length=chunk_len)

        output[0, start:end] = y_L
        output[1, start:end] = y_R
        current_frame += n_frames

        del stft_L, stft_R, y_L, y_R
        gc.collect()

        pct = 100 * end / total_samples
        print(f"  Fase: {end/sr:.1f}s / {total_samples/sr:.1f}s ({pct:.0f}%)")

    del phase_diff_full
    gc.collect()
    print("  Corrección de fase completada.")
    return output


# =============================================================================
# MONO CONVERSION
# =============================================================================

def to_mono(y_stereo):
    """Promedio de canales sin modificar el array estéreo original."""
    return librosa.to_mono(y_stereo)


def apply_hum_filter(y_mono, sr,
                     base_hz=HUM_BASE_HZ, n_harmonics=HUM_N_HARMONICS,
                     q=HUM_Q, subsonic_hp_hz=HUM_SUBSONIC_HP_HZ):
    """
    Filtra la interferencia de red eléctrica de la SEÑAL DE ANÁLISIS.

    HP subsónico suave (bajo A0) + notch angosto en cada armónico de red.
    El Q alto mantiene la banda en ~±2 Hz para no tocar las fundamentales
    del piano vecinas. Devuelve una copia filtrada; no modifica el original.

    Pensado SOLO para la señal de análisis (piso de ruido, onset, offset,
    pitch). El audio exportado usa y_stereo sin filtrar — no destructivo.
    """
    out = y_mono.astype(np.float64, copy=True)
    if subsonic_hp_hz and subsonic_hp_hz > 0:
        sos = scipy.signal.butter(2, subsonic_hp_hz, btype='high', fs=sr, output='sos')
        out = scipy.signal.sosfiltfilt(sos, out)
    for k in range(1, n_harmonics + 1):
        f0 = base_hz * k
        if f0 >= sr / 2:
            break
        b, a = scipy.signal.iirnotch(f0, q, fs=sr)
        out = scipy.signal.filtfilt(b, a, out)
    return out.astype(np.float32)


# =============================================================================
# ONSET DETECTION
# =============================================================================

def detect_onsets(y_mono, sr):
    """
    Detecta onsets tuneados para piano percusivo.
    Aplica HPF previo para eliminar rumble de baja frecuencia.
    Retorna array de índices de sample.
    """
    print("Detectando onsets...")
    sos = scipy.signal.butter(4, ONSET_HPF_HZ, btype='high', fs=sr, output='sos')
    y_hpf = scipy.signal.sosfiltfilt(sos, y_mono)

    onset_samples = librosa.onset.onset_detect(
        y=y_hpf,
        sr=sr,
        units='samples',
        hop_length=ONSET_HOP_LENGTH,
        backtrack=True,
        pre_max=3,
        post_max=3,
        pre_avg=5,
        post_avg=5,
        delta=ONSET_DELTA,
        wait=ONSET_WAIT,
    )
    print(f"  {len(onset_samples)} onsets brutos detectados.")

    if len(onset_samples) == 0:
        return onset_samples

    # Filtro de NIVEL: descarta onsets cuyo pico de ataque sea muy bajo (resonancias,
    # ruido). Va ANTES del filtro de gap para que un falso débil no "robe" el lugar de un
    # ataque real cercano (que el gap descartaría por proximidad al falso).
    if ONSET_MIN_PEAK_DB is not None:
        win = int(0.12 * sr)  # 120 ms post-onset para medir el pico del ataque
        strong = []
        for s in onset_samples:
            seg = y_mono[s : min(s + win, len(y_mono))]
            peak_db = 20 * np.log10(max(float(np.max(np.abs(seg))) if len(seg) else 0.0, 1e-9))
            if peak_db >= ONSET_MIN_PEAK_DB:
                strong.append(s)
            else:
                print(f"  [!] Onset espurio descartado en {s/sr:.2f}s (pico {peak_db:.1f} dBFS < {ONSET_MIN_PEAK_DB})")
        onset_samples = np.array(strong, dtype=int)
        print(f"  {len(onset_samples)} onsets tras filtro de nivel.")
        if len(onset_samples) == 0:
            return onset_samples

    # Filtrar onsets demasiado cercanos al anterior (resonancias secundarias en el decay)
    min_gap = int(MIN_INTER_ONSET_SECONDS * sr)
    filtered = [onset_samples[0]]
    for s in onset_samples[1:]:
        if s - filtered[-1] >= min_gap:
            filtered.append(s)
        else:
            print(f"  [!] Onset descartado en {s/sr:.2f}s (gap {(s - filtered[-1])/sr:.2f}s < {MIN_INTER_ONSET_SECONDS}s)")
    onset_samples = np.array(filtered, dtype=int)
    print(f"  {len(onset_samples)} onsets tras filtro de gap minimo.")
    return onset_samples


# =============================================================================
# NOISE FLOOR ESTIMATION
# =============================================================================

def estimate_noise_floor(y_mono, sr):
    """
    Estima el piso de ruido absoluto del archivo completo.

    Calcula el RMS de frames cortos en todo el audio y usa el percentil 5
    como estimador del piso — selecciona naturalmente los momentos más
    silenciosos (entre notas, al final de los decays) sin necesitar anotar
    regiones de silencio manualmente.

    Returns
    -------
    float : RMS del piso de ruido (escala lineal, 0-1)
    """
    rms_frames = librosa.feature.rms(
        y=y_mono,
        frame_length=RMS_FRAME_LENGTH,
        hop_length=RMS_HOP_LENGTH,
    )[0]
    noise_floor = float(np.percentile(rms_frames, NOISE_FLOOR_PERCENTILE))
    noise_db = 20 * np.log10(max(noise_floor, 1e-9))
    threshold_db = noise_db + NOISE_FLOOR_MARGIN_DB
    print(f"  Piso de ruido estimado: {noise_db:.1f} dBFS  |  umbral de offset: {threshold_db:.1f} dBFS")
    return noise_floor


# =============================================================================
# OFFSET DETECTION
# =============================================================================

def detect_offset(y_mono, sr, onset_sample, next_onset_sample, noise_floor_rms):
    """
    Detecta el offset (final de la resonancia) de una nota.

    Criterio: el RMS suavizado cae y se mantiene por debajo de
    (noise_floor_rms × 10^(NOISE_FLOOR_MARGIN_DB/20)) durante
    MIN_FRAMES_BELOW frames consecutivos.

    La ventana de búsqueda se extiende hasta el siguiente onset
    (con margen de guardia) o MAX_TAIL_SECONDS, lo que sea menor.
    Esto permite capturar decays de 20-30 segundos en notas graves.

    Parameters
    ----------
    next_onset_sample : int or None
        Sample del onset siguiente. Si None (última nota), usa MAX_TAIL_SECONDS.
    noise_floor_rms : float
        RMS del piso de ruido del archivo completo.

    Returns
    -------
    int : índice de sample del offset
    """
    total_samples = len(y_mono)
    guard = int(ONSET_GUARD_SECONDS * sr)

    # Ventana de búsqueda: hasta el siguiente onset (con guardia) o techo absoluto
    if next_onset_sample is not None:
        search_end = min(next_onset_sample - guard, total_samples)
    else:
        search_end = min(onset_sample + int(MAX_TAIL_SECONDS * sr), total_samples)

    # Garantizar al menos un frame de RMS
    if search_end <= onset_sample + RMS_FRAME_LENGTH:
        return search_end

    segment = y_mono[onset_sample:search_end]

    # RMS envelope con ventana larga para suavizar decays lentos
    rms = librosa.feature.rms(
        y=segment,
        frame_length=RMS_FRAME_LENGTH,
        hop_length=RMS_HOP_LENGTH,
    )[0]

    if len(rms) < SAVGOL_WINDOW:
        return search_end

    rms_smooth = scipy.signal.savgol_filter(rms, SAVGOL_WINDOW, SAVGOL_POLY)
    rms_smooth = np.maximum(rms_smooth, 0)  # eliminar valores negativos por Savitzky-Golay

    # Umbral absoluto: piso de ruido + margen en dB
    threshold_abs = noise_floor_rms * (10 ** (NOISE_FLOOR_MARGIN_DB / 20))

    # Umbral relativo: pico propio de la nota - OFFSET_REL_DECAY_DB.
    # Gana el más alto → el criterio que corte antes. En tomas con pedal/ruido el
    # RMS no llega al piso, pero sí cae N dB bajo su pico → el relativo dispara.
    if OFFSET_REL_DECAY_ENABLED:
        # Pico de referencia sobre el SUSTAIN (ignora el transiente de ataque) para que
        # el umbral no quede atado al golpe inicial y no corte prematuro la cola.
        skip = int((OFFSET_PEAK_SKIP_MS / 1000 * sr) / RMS_HOP_LENGTH)
        sustain = rms_smooth[skip:] if len(rms_smooth) > skip + 5 else rms_smooth
        peak_rms = float(np.max(sustain))
        threshold_rel = peak_rms * (10 ** (OFFSET_REL_DECAY_DB / 20))
        threshold = max(threshold_abs, threshold_rel)
    else:
        threshold = threshold_abs

    # Buscar primer frame donde el RMS cae bajo el umbral y permanece MIN_FRAMES_BELOW
    offset_frame = len(rms_smooth) - 1  # default: fin de la ventana
    for i in range(len(rms_smooth) - MIN_FRAMES_BELOW):
        if np.all(rms_smooth[i : i + MIN_FRAMES_BELOW] < threshold):
            offset_frame = i
            break

    offset_sample = onset_sample + int(librosa.frames_to_samples(offset_frame, hop_length=RMS_HOP_LENGTH))
    return min(offset_sample, total_samples)


def apply_register_minimum(onset_sample, offset_sample, f0_hz, sr, total_samples):
    """
    Garantiza una cola mínima según el registro de la nota.
    Aplicado DESPUÉS de detect_offset y detect_pitch.
    """
    if f0_hz is None or f0_hz <= 0:
        min_tail = MIN_TAIL_MID_HZ
    elif f0_hz < 200:
        min_tail = MIN_TAIL_LOW_HZ
    elif f0_hz <= 500:
        min_tail = MIN_TAIL_MID_HZ
    else:
        min_tail = MIN_TAIL_HIGH_HZ

    min_offset = onset_sample + int(min_tail * sr)
    return min(max(offset_sample, min_offset), total_samples)


# =============================================================================
# DYNAMIC NORMALIZATION
# =============================================================================

def normalize_to_piano_dynamic(y_mono, sr, notes):
    """
    Calcula un escalar de ganancia estático por nota para homogeneizar
    la dinámica p entre registros con distinta velocity de interpretación.

    Mide el RMS en la ventana de sustain estabilizado (post-ataque) de
    cada nota y calcula cuánto debe moverse para alcanzar DYNAMIC_NORM_TARGET_DB.

    Principio: un único multiplicador por nota — sin ataque, sin sustain,
    sin release modificados. El shape del ADSR queda intacto.

    Almacena `note["dyn_gain"]` y `note["dyn_gain_db"]` en cada nota.

    Returns
    -------
    notes : list con campo "dyn_gain" actualizado
    """
    start_s = int(DYNAMIC_NORM_MEASURE_START_MS / 1000 * sr)
    end_s   = int(DYNAMIC_NORM_MEASURE_END_MS   / 1000 * sr)
    target_rms = 10 ** (DYNAMIC_NORM_TARGET_DB / 20)

    print(f"  Target dinamica p: {DYNAMIC_NORM_TARGET_DB:.1f} dBFS  "
          f"(ventana medicion: {DYNAMIC_NORM_MEASURE_START_MS}-{DYNAMIC_NORM_MEASURE_END_MS}ms)")

    for i, note in enumerate(notes):
        start = note["onset"] + start_s
        end   = min(note["onset"] + end_s, note["offset"])

        if end <= start + 512:
            note["dyn_gain"]    = 1.0
            note["dyn_gain_db"] = 0.0
            continue

        rms = float(np.sqrt(np.mean(y_mono[start:end] ** 2)))
        if rms < 1e-9:
            note["dyn_gain"]    = 1.0
            note["dyn_gain_db"] = 0.0
            continue

        current_db = 20 * np.log10(rms)
        diff_db    = DYNAMIC_NORM_TARGET_DB - current_db  # positivo = nota muy quieta

        # Dentro de tolerancia → no tocar
        if abs(diff_db) <= DYNAMIC_NORM_TOLERANCE_DB:
            note["dyn_gain"]    = 1.0
            note["dyn_gain_db"] = 0.0
            tag = "dentro tolerancia"
        elif diff_db > 0 and not DYNAMIC_NORM_APPLY_BOOST:
            # Nota más quieta que el target Y boost desactivado
            note["dyn_gain"]    = 1.0
            note["dyn_gain_db"] = 0.0
            tag = "no boost (desactivado)"
        else:
            gain    = target_rms / rms
            gain_db = 20 * np.log10(gain)
            note["dyn_gain"]    = float(gain)
            note["dyn_gain_db"] = float(gain_db)
            direction = "atenuacion" if gain_db < 0 else "amplificacion"
            tag = f"{direction} {gain_db:+.2f} dB"

        note_name = librosa.hz_to_note(note["f0"]) if note.get("f0") else "?"
        print(f"  Nota {i+1:2d} ({note_name}): sustain RMS {current_db:.1f} dBFS  >>  {tag}")

    return notes


# =============================================================================
# KEY NOISE REDUCTION
# =============================================================================

def apply_key_noise_reduction(segment_stereo, sr, f0_hz, attenuation_db=None):
    """
    Atenúa el ruido de mecanismo de tecla en la ventana de ataque.

    Estándar en producción de sample libraries: el ruido de tecla ocupa
    9-11 kHz y dura 20-50ms desde el onset. Se aplica atenuación de
    high-shelf SOLO sobre los primeros KEY_NOISE_WINDOW_MS ms usando
    STFT frame-a-frame, con rampa de salida gradual (sin corte abrupto).

    Referencia: forum consensus en Gearspace / Sound on Sound.
    Solo se aplica cuando f0_hz >= KEY_NOISE_MIN_F0_HZ (C3 en adelante).

    attenuation_db : float, opcional
        Anulacion personalizada. Si None, usa KEY_NOISE_ATTENUATION_DB.
        Para notas _UNA pasar KNR_UNA_ATTENUATION_DB (-8 dB) porque la
        sordina ya atenua el HF fisicamente.

    Returns
    -------
    np.ndarray : segmento estéreo (2, N) con ruido de tecla atenuado
    """
    if not KEY_NOISE_REDUCTION_ENABLED:
        return segment_stereo
    if f0_hz is None or f0_hz < KEY_NOISE_MIN_F0_HZ:
        return segment_stereo

    if attenuation_db is None:
        attenuation_db = KEY_NOISE_ATTENUATION_DB

    n_fft = 2048
    hop = 512
    window_samples = int(KEY_NOISE_WINDOW_MS / 1000 * sr)
    window_frames = max(1, int(np.ceil(window_samples / hop)))

    freqs = np.fft.rfftfreq(n_fft, d=1.0 / sr)
    shelf_bin = int(np.searchsorted(freqs, KEY_NOISE_SHELF_HZ))
    gain_floor = 10 ** (attenuation_db / 20)

    result = np.empty_like(segment_stereo)
    for ch in range(2):
        stft = librosa.stft(segment_stereo[ch], n_fft=n_fft, hop_length=hop)
        n_frames = stft.shape[1]
        for fi in range(min(window_frames, n_frames)):
            # Rampa: máxima atenuación en frame 0, atenuación cero en window_frames
            alpha = fi / window_frames          # 0.0 → 1.0
            frame_gain = gain_floor + alpha * (1.0 - gain_floor)
            stft[shelf_bin:, fi] *= frame_gain
        result[ch] = librosa.istft(stft, hop_length=hop, length=segment_stereo.shape[1])

    return result


# =============================================================================
# SPECTRAL ANALYSIS
# =============================================================================

def generate_spectral_report(y_stereo, sr, notes, output_folder):
    """
    Genera un espectrograma PNG por nota y un informe TXT con análisis
    espectral de la ventana de ataque (primer 50ms) vs sustain (100-600ms).

    Para cada nota reporta:
    - Centroide espectral (Hz) en ataque vs sustain
    - Energía relativa sobre 8 kHz en ataque (indicador de ruido de tecla)
    - RMS total del ataque
    - Si aplica reducción de ruido de tecla
    """
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except ImportError:
        print("  [!] matplotlib no disponible — omitiendo análisis espectral")
        return

    report_dir = os.path.join(output_folder, "_spectral")
    os.makedirs(report_dir, exist_ok=True)
    report_lines = ["ANALISIS ESPECTRAL — piano_sampler.py", "=" * 60, ""]

    y_mono = librosa.to_mono(y_stereo)

    attack_ms = 50
    sustain_start_ms = 100
    sustain_end_ms = 600
    attack_samples = int(attack_ms / 1000 * sr)
    sus_start = int(sustain_start_ms / 1000 * sr)
    sus_end = int(sustain_end_ms / 1000 * sr)

    for i, note in enumerate(notes):
        if not note.get("f0") or not note.get("filename"):
            continue

        onset = note["onset"]
        offset = note["offset"]
        f0 = note["f0"]
        label = note.get("filename", f"nota_{i+1}")
        apply_knr = KEY_NOISE_REDUCTION_ENABLED and (f0 >= KEY_NOISE_MIN_F0_HZ)

        seg = y_mono[onset:offset]
        seg_attack = y_mono[onset : onset + attack_samples]
        seg_sustain = y_mono[onset + sus_start : onset + sus_end]
        if len(seg_sustain) < 512:
            seg_sustain = seg_attack

        # --- Centroide espectral ---
        sc_attack = float(np.mean(
            librosa.feature.spectral_centroid(y=seg_attack, sr=sr, n_fft=1024, hop_length=256)
        ))
        sc_sustain = float(np.mean(
            librosa.feature.spectral_centroid(y=seg_sustain, sr=sr, n_fft=1024, hop_length=256)
        ))

        # --- Energía sobre 8 kHz en el ataque (indicador de ruido de tecla) ---
        D_attack = np.abs(librosa.stft(seg_attack, n_fft=1024, hop_length=256)) ** 2
        freqs = librosa.fft_frequencies(sr=sr, n_fft=1024)
        shelf_bin = int(np.searchsorted(freqs, KEY_NOISE_SHELF_HZ))
        energy_total = np.sum(D_attack) + 1e-12
        energy_hf = np.sum(D_attack[shelf_bin:, :])
        hf_ratio_db = 10 * np.log10(energy_hf / energy_total + 1e-12)

        # --- RMS del ataque ---
        rms_attack_db = 20 * np.log10(float(np.sqrt(np.mean(seg_attack ** 2))) + 1e-9)

        # --- Análisis de flutter / fluctuación de sustain ---
        flutter_skip = int(FLUTTER_SUSTAIN_SKIP_MS / 1000 * sr)
        flutter_start = onset + flutter_skip
        flutter_seg = y_mono[flutter_start:offset]
        flutter_tag = ""
        flutter_ptp_db = 0.0
        reemergence_count = 0

        if len(flutter_seg) > RMS_FRAME_LENGTH * 4:
            rms_fl = librosa.feature.rms(
                y=flutter_seg, frame_length=RMS_FRAME_LENGTH, hop_length=RMS_HOP_LENGTH
            )[0]
            rms_fl = np.maximum(rms_fl, 1e-9)
            if len(rms_fl) >= SAVGOL_WINDOW:
                trend = scipy.signal.savgol_filter(rms_fl, SAVGOL_WINDOW, SAVGOL_POLY)
                trend = np.maximum(trend, 1e-9)
                residual_db = 20 * np.log10(rms_fl) - 20 * np.log10(trend)
                flutter_ptp_db = float(np.ptp(residual_db))

                # Detectar re-emergencias: el RMS SUBE más de FLUTTER_RISE_DB
                # después de haber bajado — indica que el sonido "reaparece"
                rms_db = 20 * np.log10(rms_fl)
                for k in range(2, len(rms_db)):
                    drop   = rms_db[k-2] - rms_db[k-1]   # bajó antes
                    rise   = rms_db[k]   - rms_db[k-1]   # sube ahora
                    if drop > 1.0 and rise > FLUTTER_RISE_DB:
                        reemergence_count += 1

                if flutter_ptp_db > FLUTTER_THRESHOLD_DB:
                    flutter_tag = f"[FLUTTER {flutter_ptp_db:.1f}dB ptp]"
                if reemergence_count > 0:
                    flutter_tag += f" [REEMERGENCIA x{reemergence_count}]"

        # --- Gain dinámico aplicado ---
        dyn_gain_db = note.get("dyn_gain_db", 0.0)
        dyn_tag = f"  Gain dinamico    : {dyn_gain_db:+.2f} dB" if dyn_gain_db != 0.0 else \
                  f"  Gain dinamico    : 0.00 dB (sin correccion)"

        note_name = librosa.hz_to_note(f0)
        knr_tag = "[KEY NOISE REDUCTION APLICADO]" if apply_knr else ""
        report_lines += [
            f"Nota {i+1:2d}: {label}  f0={f0:.1f} Hz ({note_name})  {knr_tag}  {flutter_tag}",
            f"  Dur total        : {(offset-onset)/sr:.2f}s",
            f"  Centroide ataque : {sc_attack:.0f} Hz",
            f"  Centroide sustain: {sc_sustain:.0f} Hz",
            f"  Diferencia       : {sc_attack - sc_sustain:+.0f} Hz (positivo = mas brillante en ataque)",
            f"  Energia >8kHz    : {hf_ratio_db:.1f} dB relativo al total del ataque",
            f"  RMS ataque       : {rms_attack_db:.1f} dBFS",
            dyn_tag,
            f"  Flutter ptp      : {flutter_ptp_db:.1f} dB  |  Re-emergencias: {reemergence_count}",
            "",
        ]

        # --- Espectrograma PNG ---
        fig, axes = plt.subplots(4, 1, figsize=(14, 12), sharex=False)
        title_str = f"{label}  |  f0={f0:.1f} Hz ({note_name})  {knr_tag}"
        if flutter_tag:
            title_str += f"  {flutter_tag}"
        fig.suptitle(title_str, fontsize=10)

        # Espectrograma completo de la nota
        D_full = librosa.amplitude_to_db(
            np.abs(librosa.stft(seg, n_fft=2048, hop_length=512)), ref=np.max
        )
        times_full = librosa.frames_to_time(np.arange(D_full.shape[1]), sr=sr, hop_length=512)
        librosa.display.specshow(D_full, sr=sr, hop_length=512, x_coords=times_full,
                                  x_axis='time', y_axis='log', ax=axes[0], cmap='magma')
        axes[0].set_title("Espectrograma completo (dB, eje Y log)", fontsize=9)
        axes[0].axhline(KEY_NOISE_SHELF_HZ, color='cyan', lw=0.8, ls='--',
                         label=f'{KEY_NOISE_SHELF_HZ//1000}kHz (corte key noise)')
        axes[0].legend(fontsize=7, loc='upper right')

        # Zoom ventana de ataque (primeros 200ms)
        zoom_samples = int(0.2 * sr)
        seg_zoom = seg[:zoom_samples] if len(seg) >= zoom_samples else seg
        D_zoom = librosa.amplitude_to_db(
            np.abs(librosa.stft(seg_zoom, n_fft=1024, hop_length=128)), ref=np.max
        )
        times_zoom = librosa.frames_to_time(np.arange(D_zoom.shape[1]), sr=sr, hop_length=128)
        librosa.display.specshow(D_zoom, sr=sr, hop_length=128, x_coords=times_zoom,
                                  x_axis='time', y_axis='log', ax=axes[1], cmap='magma')
        axes[1].set_title(f"Zoom ataque 0-200ms  |  Centroide: {sc_attack:.0f}Hz  |  HF>8kHz: {hf_ratio_db:.1f}dB", fontsize=9)
        axes[1].axvline(attack_ms / 1000, color='lime', lw=0.8, ls='--', label=f'{attack_ms}ms key noise window')
        axes[1].axhline(KEY_NOISE_SHELF_HZ, color='cyan', lw=0.8, ls='--')
        axes[1].legend(fontsize=7, loc='upper right')

        # Waveform + RMS
        t_wave = np.arange(len(seg)) / sr
        rms_env = librosa.feature.rms(y=seg, frame_length=RMS_FRAME_LENGTH, hop_length=RMS_HOP_LENGTH)[0]
        t_rms = librosa.frames_to_time(np.arange(len(rms_env)), sr=sr, hop_length=RMS_HOP_LENGTH)
        axes[2].plot(t_wave, seg, lw=0.3, color='steelblue', alpha=0.7, label='waveform')
        axes[2].plot(t_rms, rms_env, lw=1.5, color='orange', label='RMS envelope')
        axes[2].set_xlabel("Tiempo (s)")
        axes[2].set_ylabel("Amplitud")
        axes[2].legend(fontsize=7, loc='upper right')
        axes[2].set_title(f"Forma de onda  |  RMS ataque: {rms_attack_db:.1f} dBFS  "
                          f"|  Gain dinamico: {dyn_gain_db:+.2f} dB", fontsize=9)

        # Panel 4: RMS sustain con tendencia y residual — análisis de flutter
        if len(flutter_seg) > RMS_FRAME_LENGTH * 4:
            rms_fl_plot = librosa.feature.rms(
                y=flutter_seg, frame_length=RMS_FRAME_LENGTH, hop_length=RMS_HOP_LENGTH
            )[0]
            rms_fl_plot = np.maximum(rms_fl_plot, 1e-9)
            t_fl = librosa.frames_to_time(np.arange(len(rms_fl_plot)), sr=sr, hop_length=RMS_HOP_LENGTH)
            t_fl += FLUTTER_SUSTAIN_SKIP_MS / 1000  # offset al tiempo real dentro de la nota

            rms_fl_db = 20 * np.log10(rms_fl_plot)
            if len(rms_fl_plot) >= SAVGOL_WINDOW:
                trend_plot = scipy.signal.savgol_filter(rms_fl_plot, SAVGOL_WINDOW, SAVGOL_POLY)
                trend_plot = np.maximum(trend_plot, 1e-9)
                trend_db   = 20 * np.log10(trend_plot)
            else:
                trend_db = rms_fl_db

            axes[3].plot(t_fl, rms_fl_db,  lw=0.9, color='steelblue', alpha=0.7, label='RMS (dB)')
            axes[3].plot(t_fl, trend_db,   lw=1.5, color='orange', label='Tendencia Savgol')
            axes[3].fill_between(t_fl, rms_fl_db, trend_db,
                                  where=(rms_fl_db > trend_db + FLUTTER_THRESHOLD_DB / 2),
                                  color='red', alpha=0.3, label=f'Flutter >{FLUTTER_THRESHOLD_DB/2:.1f}dB')
            axes[3].set_ylabel("dBFS")
            axes[3].set_xlabel("Tiempo (s)")
            axes[3].legend(fontsize=7, loc='upper right')
            axes[3].set_title(
                f"Sustain RMS  |  Flutter ptp: {flutter_ptp_db:.1f} dB  |  "
                f"Re-emergencias: {reemergence_count}", fontsize=9
            )
        else:
            axes[3].set_visible(False)

        plt.tight_layout()
        png_name = label.replace('.wav', '_spectral.png')
        plt.savefig(os.path.join(report_dir, png_name), dpi=110)
        plt.close(fig)

    # --- Informe de texto ---
    # --- Sección de flutter summary ---
    flutter_notes = [n for n in notes if n.get("filename") and n.get("f0")]
    flutter_summary = []
    for n in flutter_notes:
        fname = n.get("filename", "")
        # Recoger datos del análisis almacenados en el loop anterior
        # (los datos ya están en el reporte de texto; aquí solo agregamos el resumen)

    report_lines += [
        "=" * 60,
        "INTERPRETACION — Octavas 3 y 4:",
        "",
        "El ruido de tecla (key mechanism noise) se manifiesta como:",
        "  - Centroide espectral en ataque significativamente mayor",
        "    que en sustain (diferencia positiva > 500 Hz)",
        "  - Energia en banda >8kHz elevada en el ataque (> -20 dB relativo)",
        "  - RMS de ataque desproporcionadamente alto respecto al sustain",
        "",
        "En octavas 3/4 la nota fundamental (130-260 Hz) ya no enmascara",
        "el ruido de mecanismo en 9-11 kHz — mientras que en C1/C2",
        "la energia de los armonicos graves domina y enmascara el click.",
        "",
        f"Umbral aplicado: notas con f0 >= {KEY_NOISE_MIN_F0_HZ} Hz",
        f"Atenuacion: {KEY_NOISE_ATTENUATION_DB} dB sobre {KEY_NOISE_SHELF_HZ} Hz en los primeros {KEY_NOISE_WINDOW_MS}ms",
        "",
        "=" * 60,
        "INTERPRETACION — Flutter / Fluctuacion de sustain:",
        "",
        "FLUTTER (varianza alta): batimiento entre cuerdas ligeramente desafinadas.",
        "  Causa: cada tecla del piano tiene 2-3 cuerdas. Si estan ligeramente",
        "  desafinadas entre si, la interferencia de fase genera amplitud modulada.",
        "  Solucion: re-afinacion del piano en esas notas. El beating leve es",
        "  natural y puede ser deseable; beating severo (>6 dB ptp) puede ser",
        "  perceptible como inestabilidad de pitch en la biblioteca.",
        "",
        "REEMERGENCIA: el RMS sube abruptamente despues de haber decaido.",
        "  Causas posibles:",
        "    a) Resonancia simpatica de otra cuerda (uso del pedal de sustain)",
        "    b) Modo de sala que re-excita la frecuencia de la nota",
        "    c) Ruido externo captado durante el decay",
        "  Solucion recomendada: recorte manual del segmento en REAPER antes",
        "  del punto de re-emergencia, o re-grabacion de la nota.",
        "",
        f"Umbral flutter: ptp > {FLUTTER_THRESHOLD_DB} dB",
        f"Umbral re-emergencia: rise > {FLUTTER_RISE_DB} dB",
    ]

    with open(os.path.join(report_dir, "spectral_report.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))

    print(f"  Analisis espectral guardado en: {report_dir}")
    del y_mono


# =============================================================================
# PITCH DETECTION
# =============================================================================

def detect_pitch(y_mono, sr, onset_sample):
    """
    Detecta la frecuencia fundamental usando pyin sobre los primeros
    PITCH_WINDOW_SECONDS del onset.

    Returns float (Hz) o None si no se puede determinar.
    """
    window_samples = int(PITCH_WINDOW_SECONDS * sr)
    segment = y_mono[onset_sample : onset_sample + window_samples]

    if len(segment) < PITCH_FRAME_LENGTH:
        return None

    try:
        f0, voiced_flag, voiced_probs = librosa.pyin(
            y=segment,
            sr=sr,
            fmin=librosa.note_to_hz('A0'),
            fmax=librosa.note_to_hz('C8'),
            frame_length=PITCH_FRAME_LENGTH,
            hop_length=PITCH_HOP_LENGTH,
            fill_na=None,
        )
    except Exception:
        return None

    valid = voiced_flag & ~np.isnan(f0)
    if not np.any(valid):
        return None

    return float(np.average(f0[valid], weights=voiced_probs[valid]))


# =============================================================================
# NOTE BUILDING
# =============================================================================
# ZERO-CROSSING ALIGNMENT
# =============================================================================

# =============================================================================

def build_note_segments(y_mono, sr, onset_samples, noise_floor_rms):
    """
    Para cada onset, detecta offset y pitch.
    Aplica pre-roll antes del onset detectado para capturar el inicio
    del transiente en notas de alta velocity, acotado por el offset
    de la nota anterior para no capturar su decay.
    Retorna lista de dicts con claves: onset, offset, f0.
    """
    print(f"Construyendo segmentos para {len(onset_samples)} notas...")
    total_samples = len(y_mono)
    preroll_samples = int(ONSET_PREROLL_MS / 1000 * sr)
    notes = []
    prev_offset = 0  # offset de la nota anterior como límite inferior del pre-roll

    for idx, onset in enumerate(onset_samples):
        next_onset = int(onset_samples[idx + 1]) if idx + 1 < len(onset_samples) else None

        # Pre-roll: retroceder hasta ONSET_PREROLL_MS ms antes del onset,
        # sin solapar con el decay de la nota anterior
        onset_export = max(prev_offset, onset - preroll_samples)

        offset_raw = detect_offset(y_mono, sr, onset, next_onset, noise_floor_rms)
        f0 = detect_pitch(y_mono, sr, onset)
        offset = apply_register_minimum(onset, offset_raw, f0, sr, total_samples)

        dur = (offset - onset_export) / sr
        preroll_ms = (onset - onset_export) / sr * 1000
        note_name = librosa.hz_to_note(f0) if f0 else "?"
        print(f"  Nota {idx+1:2d}: onset={onset_export/sr:6.2f}s (preroll {preroll_ms:.1f}ms)  "
              f"offset={offset/sr:6.2f}s  dur={dur:.2f}s  pitch={note_name}")

        notes.append({"onset": int(onset_export), "offset": int(offset), "f0": f0})
        prev_offset = offset

    return notes


# =============================================================================
# LABEL ASSIGNMENT
# =============================================================================

# Mapeo de notas a sharp equivalente (enharmonic normalization)
_FLAT_TO_SHARP = {
    "Db": "Cs", "Eb": "Ds", "Fb": "E",
    "Gb": "Fs", "Ab": "Gs", "Bb": "As", "Cb": "B",
}

# Caracteres especiales de librosa → notación ASCII
_UNICODE_NORMALIZE = str.maketrans({"♯": "#", "♭": "b"})


def parse_filename_modifiers(filename):
    """
    Detecta modificadores _UNA y _SP en un nombre de archivo WAV.
    Retorna dict {'una_corda': bool, 'sin_pedal': bool}.
    """
    base = os.path.splitext(os.path.basename(filename))[0].upper()
    return {
        "una_corda": "_UNA" in base,
        "sin_pedal": "_SP"  in base,
    }


def _hz_to_label(f0_hz, intensity, modifiers=None):
    """
    Convierte Hz a etiqueta 'Note_Octave_intensity[_UNA][_SP]' en formato ASCII.
    Soporta modificadores de sesion: _UNA (una corda / sordina), _SP (sin pedal).
    """
    if f0_hz is None or f0_hz <= 0:
        return None
    note_str = librosa.hz_to_note(f0_hz, cents=False)
    note_str = note_str.translate(_UNICODE_NORMALIZE)

    match = re.match(r"([A-G][b#]?)(-?[0-9]+)", note_str)
    if not match:
        return None

    note_raw = match.group(1)   # e.g. 'C#', 'Db', 'G'
    octave = match.group(2).lstrip("-") or "0"

    # Normalizar a sharp, formato ASCII: C# → Cs, Db → Cs
    if note_raw in _FLAT_TO_SHARP:
        note_clean = _FLAT_TO_SHARP[note_raw]
    else:
        note_clean = note_raw.replace("#", "s")

    mod_str = ""
    if modifiers:
        mods_up = [m.upper() for m in modifiers]
        if "UNA" in mods_up:
            mod_str += "_UNA"
        if "SP" in mods_up:
            mod_str += "_SP"

    return f"{note_clean}_{octave}_{intensity}{mod_str}"


def assign_labels(notes, intensity, modifiers=None):
    """
    Asigna etiquetas de nombre de archivo a cada nota.
    Notas con el mismo pitch reciben sufijo _RR1, _RR2, etc.
    Incluye modificadores _UNA / _SP en el nombre base segun SESSION_MODIFIERS.
    """
    # Primera pasada: asignar etiqueta base (con modificadores)
    for note in notes:
        note["label"] = _hz_to_label(note["f0"], intensity, modifiers)

    # Segunda pasada: agregar sufijos RR si hay repeticiones
    counts = collections.Counter(n["label"] for n in notes if n["label"])
    rr_counter = collections.defaultdict(int)

    for note in notes:
        lbl = note["label"]
        if lbl is None:
            note["filename"] = None
            continue
        if counts[lbl] > 1:
            rr_counter[lbl] += 1
            note["filename"] = f"{lbl}_RR{rr_counter[lbl]}.wav"
        else:
            note["filename"] = f"{lbl}.wav"

    return notes


# =============================================================================
# EXPORT
# =============================================================================

def apply_export_cleanup(segment_stereo, sr,
                         lpf_hz=None, notch_hz=None, notch_q=None):
    """
    Limpieza final no destructiva del audio a exportar:
      - LPF para eliminar tonos ultrasónicos / interferencia digital sobre ~20 kHz.
      - Notch(es) angostos en tonos fijos audibles (p.ej. 8.3 kHz).

    Se aplica por canal al segmento estéreo, con filtrado de fase cero (filtfilt)
    para no desplazar el transiente. No afecta la señal de análisis.
    """
    lpf_hz   = CLEANUP_LPF_HZ   if lpf_hz   is None else lpf_hz
    notch_hz = CLEANUP_NOTCH_HZ if notch_hz is None else notch_hz
    notch_q  = CLEANUP_NOTCH_Q  if notch_q  is None else notch_q

    out = segment_stereo.astype(np.float64, copy=True)
    if lpf_hz and lpf_hz < sr / 2:
        sos = scipy.signal.butter(8, lpf_hz, btype='low', fs=sr, output='sos')
        for ch in range(out.shape[0]):
            out[ch] = scipy.signal.sosfiltfilt(sos, out[ch])
    if notch_hz:
        for f0 in notch_hz:
            if 0 < f0 < sr / 2:
                b, a = scipy.signal.iirnotch(f0, notch_q, fs=sr)
                for ch in range(out.shape[0]):
                    out[ch] = scipy.signal.filtfilt(b, a, out[ch])
    return out.astype(np.float32)


def _apply_fadein(segment, sr):
    """
    Fade-in con curva coseno (igual potencia) de EXPORT_FADEIN_MS ms.

    La curva coseno es el estándar en sample libraries: sube más
    despacio que el lineal al principio (elimina el clic/pop de
    cuantización) y llega a ganancia plena sin escalón.
    """
    fade_samples = int(EXPORT_FADEIN_MS / 1000 * sr)
    fade_samples = min(fade_samples, segment.shape[1])
    if fade_samples <= 0:
        return segment
    # Curva coseno: 0 → 1 con forma suave
    t = np.linspace(0.0, np.pi / 2, fade_samples)
    ramp = np.sin(t)           # sin(0→π/2) = curva coseno de subida
    out = segment.copy()
    out[:, :fade_samples] *= ramp
    return out


def export_notes(y_stereo, sr, notes, output_folder, modifiers=None):
    """
    Exporta cada nota como WAV estéreo 24-bit con key noise reduction y fade-in.

    modifiers : list, opcional
        Lista de modificadores activos ('UNA', 'SP').
        Ajusta KNR y mensajes de log segun el tipo de sesion.
    """
    os.makedirs(output_folder, exist_ok=True)
    exported = 0
    skipped = 0
    knr_applied = 0

    # Determinar parametros segun modificadores activos
    is_una = bool(modifiers and "UNA" in [m.upper() for m in modifiers])
    is_sp  = bool(modifiers and "SP"  in [m.upper() for m in modifiers])
    knr_db = KNR_UNA_ATTENUATION_DB if is_una else KEY_NOISE_ATTENUATION_DB

    if is_una:
        print(f"  Modo UNA CORDA: KNR reducido a {knr_db}dB (sordina atenua HF fisicamente)")
    if is_sp:
        print(f"  Modo SIN PEDAL: decay mas corto, ventana de ruido reducida")

    for note in notes:
        if note["filename"] is None:
            skipped += 1
            continue

        onset, offset = note["onset"], note["offset"]
        if offset <= onset:
            skipped += 1
            continue

        segment = y_stereo[:, onset:offset].copy()   # (2, N)

        # 1. Normalización dinámica (gain estático — preserva ADSR)
        dyn_gain = note.get("dyn_gain", 1.0)
        if dyn_gain != 1.0:
            segment *= dyn_gain

        # 2. Reducción de ruido de tecla (C3 en adelante)
        #    Para _UNA: atenuacion reducida porque la sordina ya atenua HF fisicamente.
        f0 = note.get("f0")
        if KEY_NOISE_REDUCTION_ENABLED and f0 and f0 >= KEY_NOISE_MIN_F0_HZ:
            segment = apply_key_noise_reduction(segment, sr, f0, attenuation_db=knr_db)
            knr_applied += 1

        # 3. Limpieza final (LPF ultrasónicos + notch tonos fijos)
        if CLEANUP_FILTER_ENABLED:
            segment = apply_export_cleanup(segment, sr)

        # 4. Fade-in coseno
        segment = _apply_fadein(segment, sr)
        out_path = os.path.join(output_folder, note["filename"])
        sf.write(out_path, segment.T, sr, subtype=EXPORT_SUBTYPE)
        exported += 1

    print(f"  Exportadas: {exported}  KNR aplicado: {knr_applied} ({knr_db:+.0f}dB)  Saltadas: {skipped}")
    return exported


# =============================================================================
# VERIFICATION
# =============================================================================

def verify_outputs(output_folder, sr, notes):
    """Reporte de sanidad post-exportación."""
    print("\n--- VERIFICACIÓN ---")
    files = [f for f in os.listdir(output_folder) if f.endswith(".wav")]
    print(f"Archivos exportados: {len(files)}")

    issues = []
    durations = []

    for fname in files:
        path = os.path.join(output_folder, fname)
        info = sf.info(path)
        dur = info.duration
        durations.append(dur)

        if dur < 0.1:
            issues.append(f"MUY CORTO ({dur:.3f}s): {fname}")
        if dur > MAX_TAIL_SECONDS + 0.5:
            issues.append(f"MUY LARGO ({dur:.2f}s): {fname}")

        y_check, _ = sf.read(path, dtype='float32')
        peak = np.max(np.abs(y_check))
        if peak > 1.0:
            issues.append(f"CLIPPING ({peak:.3f}): {fname}")
        if peak < 10 ** (-40 / 20):
            issues.append(f"CASI SILENCIOSO ({peak:.6f}): {fname}")

    if durations:
        print(f"Duración min: {min(durations):.2f}s  max: {max(durations):.2f}s  media: {np.mean(durations):.2f}s")

    # Rango cromático capturado
    midi_notes = set()
    for n in notes:
        if n.get("f0") and n["f0"] > 0:
            midi_notes.add(int(round(librosa.hz_to_midi(n["f0"]))))
    if midi_notes:
        print(f"Rango MIDI capturado: {min(midi_notes)} – {max(midi_notes)}  ({len(midi_notes)} alturas únicas)")

    if issues:
        print(f"\n[!] {len(issues)} advertencia(s):")
        for issue in issues:
            print(f"  {issue}")
    else:
        print("[OK] Sin advertencias.")


# =============================================================================
# DEBUG VISUALIZATION
# =============================================================================

def visualize_note(y_mono, sr, note, output_folder, noise_floor_rms):
    """Genera PNG con waveform, RMS envelope, umbral de ruido y marcador de offset."""
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        return

    onset, offset = note["onset"], note["offset"]
    segment = y_mono[onset:offset]

    rms = librosa.feature.rms(y=segment, frame_length=RMS_FRAME_LENGTH, hop_length=RMS_HOP_LENGTH)[0]
    rms_smooth = scipy.signal.savgol_filter(rms, SAVGOL_WINDOW, SAVGOL_POLY) if len(rms) >= SAVGOL_WINDOW else rms
    rms_smooth = np.maximum(rms_smooth, 0)

    times_wave = np.arange(len(segment)) / sr
    times_rms = librosa.frames_to_time(np.arange(len(rms_smooth)), sr=sr, hop_length=RMS_HOP_LENGTH)
    threshold = noise_floor_rms * (10 ** (NOISE_FLOOR_MARGIN_DB / 20))

    fig, axes = plt.subplots(2, 1, figsize=(14, 6), sharex=True)
    axes[0].plot(times_wave, segment, lw=0.4, color='steelblue')
    axes[0].axvline((offset - onset) / sr, color='red', lw=1.5, label='offset')
    axes[0].set_ylabel("Amplitud")
    axes[0].legend(fontsize=8)
    title = f"{note.get('filename', 'nota')}"
    if note['f0']:
        title += f"  f0={note['f0']:.1f} Hz"
    axes[0].set_title(title)

    axes[1].plot(times_rms, rms_smooth, color='orange', lw=1.2, label='RMS suavizado')
    axes[1].axhline(threshold, color='red', ls='--', lw=1,
                    label=f'umbral (+{NOISE_FLOOR_MARGIN_DB}dB sobre piso)')
    axes[1].axvline((offset - onset) / sr, color='red', lw=1.5)
    axes[1].set_ylabel("RMS")
    axes[1].set_xlabel("Tiempo (s)")
    axes[1].legend(fontsize=8)

    plt.tight_layout()
    png_name = (note.get('filename') or 'nota').replace('.wav', '.png')
    plt.savefig(os.path.join(output_folder, png_name), dpi=100)
    plt.close(fig)


# =============================================================================
# MAIN
# =============================================================================

def main():
    input_file = INPUT_FILE
    if not os.path.exists(input_file):
        print(f"[ERROR] No se encontro el archivo: {input_file}")
        return

    # Carpeta de salida derivada del nombre del archivo de entrada
    stem = os.path.splitext(os.path.basename(input_file))[0]
    output_folder = os.path.join(OUTPUT_DIR, INTENSITY_LABEL, stem)
    print(f"Salida: {output_folder}")

    # 1. Cargar
    y_stereo, sr = load_audio(input_file)

    # 2. Corrección de fase
    if PHASE_CORRECTION_ENABLED:
        y_stereo = apply_phase_correction(y_stereo, sr)

    # 3. Mono para análisis
    y_mono = to_mono(y_stereo)

    # 3b. Filtro de hum sobre la señal de análisis (no afecta el audio exportado)
    if HUM_FILTER_ENABLED:
        print("Aplicando filtro de hum a la señal de análisis (notch red + HP subsónico)...")
        y_mono = apply_hum_filter(y_mono, sr)

    # 4. Piso de ruido (antes de onsets para que el print quede ordenado)
    print("Estimando piso de ruido...")
    noise_floor_rms = estimate_noise_floor(y_mono, sr)

    # 5. Onsets
    onset_samples = detect_onsets(y_mono, sr)
    if len(onset_samples) == 0:
        print("[ERROR] No se detectaron onsets. Revisa ONSET_DELTA o el archivo de entrada.")
        return

    # 6. Segmentos (offset + pitch por nota)
    notes = build_note_segments(y_mono, sr, onset_samples, noise_floor_rms)

    # 7. Etiquetas y nombres de archivo (con modificadores _UNA / _SP si aplica)
    notes = assign_labels(notes, INTENSITY_LABEL, SESSION_MODIFIERS)

    # 8. Normalización de dinámica p (gain estático por nota)
    if DYNAMIC_NORM_ENABLED:
        print("Normalizando dinámica p...")
        notes = normalize_to_piano_dynamic(y_mono, sr, notes)

    # 9. Análisis espectral (todas las notas, PNGs + reporte TXT)
    print("Generando análisis espectral...")
    generate_spectral_report(y_stereo, sr, notes, output_folder)

    # 10. Visualización debug (opcional)
    if DEBUG_VISUALIZE:
        debug_folder = os.path.join(output_folder, "_debug")
        os.makedirs(debug_folder, exist_ok=True)
        print("Generando visualizaciones debug...")
        for note in notes:
            visualize_note(y_mono, sr, note, debug_folder, noise_floor_rms)

    # Liberar mono antes de exportar (ya no se necesita)
    del y_mono
    gc.collect()

    # 11. Exportar (gain dyn + key noise reduction + fade-in)
    if SESSION_MODIFIERS:
        print(f"Exportando WAVs [modificadores: {SESSION_MODIFIERS}] a: {output_folder}")
    else:
        print(f"Exportando WAVs a: {output_folder}")
    export_notes(y_stereo, sr, notes, output_folder, SESSION_MODIFIERS)

    del y_stereo
    gc.collect()

    # 12. Verificar
    verify_outputs(output_folder, sr, notes)

    print(f"\n[OK] Pipeline completado. Samples en: {output_folder}")


if __name__ == "__main__":
    main()
