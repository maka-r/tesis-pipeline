# -*- coding: utf-8 -*-
"""
pipeline_rectify.py
-------------------
Rectificacion no destructiva de samples de piano basada en las metricas
del pipeline_compare.py.

CRITERIOS (orden de aplicacion):
  1. NIVEL           -- Ganancia estatica por nota (escalar unico, ADSR intacto)
                        Target: -28.0 dBFS RMS de sustain  (estandar dinamica p)
                        Para _UNA: LEVEL_MAX_BOOST ampliado a +12 dB.
  2. KNR_PLUS        -- Segundo paso de reduccion de ruido de tecla
                        Para _UNA: -8 dB (sordina atenua HF fisicamente).
                        Para notas normales: -10 dB adicional.
  3. SMOOTH_FLUTTER  -- Savitzky-Golay sobre envolvente RMS por banda STFT
                        Solo en sustain (post-ataque). Transicion 50ms.
                        Moderado (2.5-10 dB): smoothing leve (ventana 51)
                        Critico (>10 dB):     smoothing fuerte + REQUIERE_RX
                        NOTA: flutter es caracteristica del instrumento patrimonial
                        que NO puede afinarse. Se documenta como tal.
  4. TRIM_REEMERGENCIA -- Recorte + fade-out coseno de 800ms en punto de re-emergencia
  5. FLUTTER residual -- Documentado. Estrategia: pipeline -> REAPER -> iZotope RX
                         -> Kontakt Random Tune +/-5 cents.

Soporta modificadores de sesion: _UNA (una corda), _SP (sin pedal).

Genera en Output_Samples/p_rectificado_pip/:
  *.wav                    Muestras rectificadas
  _spectral/*.png          Espectrograma individual (5 paneles) por nota
  correction_log.txt       Tabla de correcciones aplicadas por nota
  noise_snr_report.txt     Piso de ruido 3 componentes, SNR y artefactos por nota
"""

import os
import gc
import numpy as np
import scipy.signal
from scipy.ndimage import uniform_filter1d
import librosa
import soundfile as sf

# =============================================================================
# RUTAS
# =============================================================================

SESSIONS = [
    r"D:\Sesiones y proyectos\SESION 29-8\Pruebas de rendimiento denoise\Output_Samples\p\piano-model_mt_2_piano",
    r"D:\Sesiones y proyectos\SESION 29-8\Pruebas de rendimiento denoise\Output_Samples\p\proyecto-balance-tesis-002_piano-model_mt_2_piano",
]

OUTPUT_DIR    = r"D:\Sesiones y proyectos\SESION 29-8\Pruebas de rendimiento denoise\Output_Samples\p_rectificado_pip"
SPECTRAL_DIR  = os.path.join(OUTPUT_DIR, "_spectral")
EXPORT_SUBTYPE = "PCM_24"
TARGET_SR      = 48000       # sample rate objetivo; archivos a distinto SR se resamplean al cargar

# =============================================================================
# PARAMETROS GENERALES
# =============================================================================

RMS_FRAME_LENGTH = 2048
RMS_HOP_LENGTH   = 512
SAVGOL_WINDOW    = 51
SAVGOL_POLY      = 3

ATTACK_MS        = 50
SUSTAIN_START_MS = 200
SUSTAIN_END_MS   = 700
FLUTTER_SKIP_MS  = 400

KEY_NOISE_SHELF_HZ      = 8000
KNR_PLUS_ATTENUATION_DB = -10    # dB adicional (encima de los -15 ya aplicados) — sesion normal
KNR_UNA_ATTENUATION_DB  = -8     # dB para notas _UNA (sordina atenua HF fisicamente)
KNR_PLUS_WINDOW_MS      = 50
KNR_HF_THRESHOLD_DB     = -38.0  # activar KNR_PLUS si HF_ataque > este valor

REEMERGENCE_RISE_DB     = 2.0
TRIM_FADEOUT_MS         = 800

# Nivel — parametros base y para _UNA
LEVEL_TARGET_DB     = -28.0
LEVEL_TOLERANCE     = 1.5
LEVEL_MAX_BOOST     = 8.0     # techo normal (notas con pedal)
LEVEL_MAX_BOOST_UNA = 12.0    # techo ampliado para una corda (_UNA)

# Flutter
FLUTTER_WARN_DB     = 5.0
FLUTTER_CRITICAL_DB = 10.0
FLUTTER_SMOOTH_WIN_LEVE    = 51   # ventana Savitzky-Golay: flutter moderado
FLUTTER_SMOOTH_WIN_CRITICO = 101  # ventana: flutter critico
FLUTTER_SMOOTH_RAMP_MS     = 50   # ms de transicion attack->sustain en smooth

PITCH_WINDOW_S      = 0.5
PITCH_FRAME_LENGTH  = 4096
PITCH_HOP_LENGTH    = 512

# ---------------------------------------------------------------------------
# Ruido residual y SNR
# ---------------------------------------------------------------------------
NOISE_WINDOW_S        = 0.5
NOISE_TAIL_FRACTION   = 2/3
NOISE_SP_FRACTION     = 0.15   # fraccion alternativa para notas _SP (sin pedal)
HUM_PEAK_RATIO        = 3.0
CLICK_ONSET_SKIP_MS   = 200
CLICK_THRESHOLD_FS    = 0.05
RUMBLE_HZ             = 20.0
RUMBLE_DB_THRESHOLD   = -40.0
DC_OFFSET_THRESHOLD   = 0.005
MVSEP_PEAK_DB         = 15.0

SNR_TIER_EXCELLENT    = 70.0
SNR_TIER_PROFESSIONAL = 60.0
SNR_TIER_CONSUMER     = 50.0
SNR_TIER_MARGINAL     = 40.0


# =============================================================================
# UTILIDADES DE MODIFICADORES
# =============================================================================

def parse_filename_modifiers(filename):
    """
    Detecta modificadores _UNA (una corda) y _SP (sin pedal) en el nombre de archivo.
    Retorna dict {'una_corda': bool, 'sin_pedal': bool}.
    """
    base = os.path.splitext(os.path.basename(filename))[0].upper()
    return {
        "una_corda": "_UNA" in base,
        "sin_pedal": "_SP"  in base,
    }


def get_effective_params(filename):
    """
    Retorna parametros adaptados al tipo de sesion segun los modificadores del archivo.
    """
    mods = parse_filename_modifiers(filename)
    return {
        "knr_plus_db":    KNR_UNA_ATTENUATION_DB if mods["una_corda"] else KNR_PLUS_ATTENUATION_DB,
        "level_max_boost": LEVEL_MAX_BOOST_UNA if mods["una_corda"] else LEVEL_MAX_BOOST,
        "noise_window_s": None,   # None = calcular dinamicamente para _SP, o NOISE_WINDOW_S fijo
        "una_corda":      mods["una_corda"],
        "sin_pedal":      mods["sin_pedal"],
    }


# =============================================================================
# SUAVIZADO DE FLUTTER DE SUSTAIN
# =============================================================================

def smooth_flutter_sustain(segment_stereo, sr, flutter_ptp_db):
    """
    Suaviza la envolvente de amplitud del sustain usando Savitzky-Golay
    sobre la envolvente RMS por banda STFT.

    IMPORTANTE: Solo actua sobre el sustain (posterior al ataque ATTACK_MS).
    El ataque queda intacto. Transicion de FLUTTER_SMOOTH_RAMP_MS con ramp lineal.

    Estrategia segun severidad:
      flutter < FLUTTER_WARN_DB      -> sin accion
      FLUTTER_WARN_DB <= f < CRITICAL -> smoothing leve  (sg_win=51)  + no flag
      flutter >= FLUTTER_CRITICAL_DB  -> smoothing fuerte (sg_win=101) + REQUIERE_RX

    El flutter es una caracteristica del instrumento patrimonial (no afinable).
    Este suavizado es un paliativo en el pipeline; la correccion definitiva
    requiere iZotope RX (flutter critico) o Kontakt Random Tune +/-5 cents.

    Returns
    -------
    (segment_stereo_out, requiere_rx)
      segment_stereo_out : np.ndarray (2, N)
      requiere_rx        : bool — True si flutter > FLUTTER_CRITICAL_DB
    """
    if flutter_ptp_db < FLUTTER_WARN_DB:
        return segment_stereo, False

    requiere_rx = (flutter_ptp_db >= FLUTTER_CRITICAL_DB)
    sg_window   = FLUTTER_SMOOTH_WIN_CRITICO if requiere_rx else FLUTTER_SMOOTH_WIN_LEVE

    attack_samples = int(ATTACK_MS / 1000 * sr)
    ramp_samples   = int(FLUTTER_SMOOTH_RAMP_MS / 1000 * sr)
    n = segment_stereo.shape[1]

    if n <= attack_samples + sg_window * 2:
        return segment_stereo, requiere_rx  # nota demasiado corta para suavizar

    result = segment_stereo.copy()
    n_fft  = 1024
    hop    = 256

    for ch in range(2):
        y_atk = segment_stereo[ch, :attack_samples]
        y_sus = segment_stereo[ch, attack_samples:].copy()
        sus_len = len(y_sus)

        if sus_len < n_fft:
            continue

        # STFT del segmento de sustain
        S        = librosa.stft(y_sus, n_fft=n_fft, hop_length=hop)
        n_frames = S.shape[1]

        if n_frames < sg_window:
            continue

        # Asegurar sg_window impar y no mayor que n_frames
        sg_win = min(sg_window, n_frames if n_frames % 2 == 1 else n_frames - 1)
        sg_win = sg_win if sg_win % 2 == 1 else sg_win - 1
        if sg_win < 5:
            continue

        # Savitzky-Golay sobre la magnitud de cada banda a lo largo del tiempo
        magnitudes = np.abs(S)   # (bins, frames)
        smoothed   = np.apply_along_axis(
            lambda row: scipy.signal.savgol_filter(row, sg_win, SAVGOL_POLY),
            axis=1, arr=magnitudes
        )
        smoothed = np.maximum(smoothed, 1e-12)

        # Ratio de ganancia: corrige la modulacion de amplitud sin afectar la fase
        gain_ratio = smoothed / (magnitudes + 1e-12)
        # Clip: solo atenuar batimiento, no amplificar mas de 1.3x
        gain_ratio = np.clip(gain_ratio, 0.2, 1.3)

        S_smooth     = S * gain_ratio
        y_sus_smooth = librosa.istft(S_smooth, hop_length=hop, length=sus_len)

        # Ramp lineal de transicion: blending attack_end -> sustain_smooth
        if ramp_samples > 0 and ramp_samples < sus_len:
            ramp = np.linspace(0.0, 1.0, ramp_samples)
            y_sus_smooth[:ramp_samples] = (y_sus[:ramp_samples] * (1.0 - ramp) +
                                           y_sus_smooth[:ramp_samples] * ramp)

        result[ch, attack_samples:] = y_sus_smooth

    return result, requiere_rx


# =============================================================================
# ANALISIS DE RUIDO RESIDUAL (3 COMPONENTES)
# =============================================================================

def analyze_noise_profile(y, sr, flutter_ptp_db=0.0, sin_pedal=False):
    """
    Localiza el segmento mas silencioso en el ultimo tercio de la nota y
    caracteriza el perfil de ruido residual en tres componentes:

      1. Piso electronico   -- RMS minimo absoluto del segmento mas silencioso
                               (ruido de microfono + previo + conversion AD)
      2. Flutter de cuerdas -- Varianza de la envolvente RMS en sustain
                               (caracteristica del instrumento patrimonial)
      3. Ruido ambiental    -- Diferencia entre el RMS mediano y el minimo
                               en la cola de la nota (sala, HVAC, etc.)

    Para notas _SP (sin pedal) la ventana se calcula como fraccion de la
    duracion total (NOISE_SP_FRACTION) en lugar de NOISE_WINDOW_S fijo.

    Retorna dict con todos los campos necesarios para SNR y el reporte.
    """
    n = len(y)
    # Ventana: fija para notas con pedal, proporcional para _SP
    if sin_pedal:
        win_samples = max(int(NOISE_SP_FRACTION * n), 64)
    else:
        win_samples = max(int(NOISE_WINDOW_S * sr), 64)

    tail_start = int(NOISE_TAIL_FRACTION * n)
    if n - tail_start < win_samples:
        tail_start = max(0, n - win_samples * 2)

    y_tail = y[tail_start:]

    # --- Componente 1: Piso electronico (ventana mas silenciosa) ---
    best_rms   = np.inf
    best_start = 0
    hop = max(1, win_samples // 4)
    pos = 0
    while pos + win_samples <= len(y_tail):
        chunk = y_tail[pos : pos + win_samples]
        rms   = float(np.sqrt(np.mean(chunk ** 2)))
        if rms < best_rms:
            best_rms   = rms
            best_start = pos
        pos += hop

    noise_seg    = y_tail[best_start : best_start + win_samples]
    if len(noise_seg) < 32:
        noise_seg = y_tail if len(y_tail) >= 32 else y[-min(512, n):]

    elec_rms    = float(np.sqrt(np.mean(noise_seg ** 2))) if len(noise_seg) > 0 else 1e-9
    elec_rms_db = 20 * np.log10(max(elec_rms, 1e-9))

    # --- Componente 2: Flutter de cuerdas ---
    # Estimado como la contribucion de amplitud modulada encima del piso.
    # Relacion: flutter_ptp_db mide el rango pico a pico de la varianza residual.
    # La contribucion RMS aproximada es piso + flutter_ptp/2 (promedio de la modulacion).
    flutter_contribution_db = elec_rms_db + flutter_ptp_db / 2.0

    # --- Componente 3: Ruido ambiental de sala ---
    # Medido como el RMS mediano del tail vs el minimo (diferencia = aporte de sala)
    mid_rms_db = -999.0
    if len(y_tail) >= win_samples * 2:
        # Calcular RMS en ventanas del tail y tomar la mediana
        rms_windows = []
        pos2 = 0
        while pos2 + win_samples <= len(y_tail):
            chunk = y_tail[pos2 : pos2 + win_samples]
            rms_windows.append(float(np.sqrt(np.mean(chunk ** 2))))
            pos2 += win_samples
        if rms_windows:
            mid_rms     = float(np.median(rms_windows))
            mid_rms_db  = 20 * np.log10(max(mid_rms, 1e-9))

    room_contribution_db = max(0.0, mid_rms_db - elec_rms_db) if mid_rms_db > -990 else 0.0

    # --- FFT para analisis espectral ---
    seg_len = len(noise_seg)
    n_fft   = 2 ** int(np.floor(np.log2(max(seg_len, 64))))
    n_fft   = min(n_fft, 2048)
    fft_in  = (noise_seg[:n_fft] if seg_len >= n_fft
               else np.pad(noise_seg, (0, n_fft - seg_len)))
    spec    = np.abs(np.fft.rfft(fft_in, n=n_fft)) ** 2
    freqs_n = np.fft.rfftfreq(n_fft, d=1.0 / sr)

    # Planitud espectral de Wiener (0=tonal/MVSep, 1=ruido blanco)
    spec_safe = np.maximum(spec, 1e-12)
    geo_mean  = np.exp(np.mean(np.log(spec_safe)))
    ari_mean  = float(np.mean(spec_safe))
    flatness  = float(geo_mean / (ari_mean + 1e-12))

    # Hum: picos en armonicos de 50/60 Hz
    freq_res     = sr / n_fft
    hum_detected = []
    for base_hz in (50, 60):
        for k in range(1, 6):
            hf = base_hz * k
            if hf >= sr / 2:
                break
            bin_idx    = int(round(hf / freq_res))
            if bin_idx >= len(spec):
                break
            lo         = max(0, bin_idx - 5)
            hi         = min(len(spec), bin_idx + 6)
            local_mean = float(np.mean(spec[lo:hi])) + 1e-12
            if spec[bin_idx] > HUM_PEAK_RATIO * local_mean:
                hum_detected.append(hf)

    # Picos de ruido musical MVSep
    mvsep_peaks = 0
    if len(spec) >= 20:
        baseline    = uniform_filter1d(spec.astype(float), size=20)
        spec_db     = 10 * np.log10(spec     + 1e-12)
        base_db     = 10 * np.log10(baseline + 1e-12)
        mvsep_peaks = int(np.sum((spec_db - base_db) > MVSEP_PEAK_DB))

    return {
        # Componente 1: electronico
        "noise_rms_db":          elec_rms_db,
        "noise_seg":             noise_seg,
        "noise_freqs":           freqs_n,
        "noise_spec":            spec,
        # Componente 2: flutter de cuerdas
        "flutter_contribution_db": flutter_contribution_db,
        # Componente 3: ambiental
        "room_contribution_db":  room_contribution_db,
        # Analisis espectral del piso
        "flatness":              flatness,
        "hum_detected":          hum_detected,
        "mvsep_peaks":           mvsep_peaks,
        "tail_start_s":          (tail_start + best_start) / sr,
    }


def compute_snr_quality(rms_atk_db, noise_rms_db):
    """Calcula SNR y clasifica segun estandares de libreria profesional."""
    snr = float(rms_atk_db - noise_rms_db)
    if snr >= SNR_TIER_EXCELLENT:
        tier = f"EXCELENTE (>={SNR_TIER_EXCELLENT:.0f}dB - tier VSL/Spitfire)"
    elif snr >= SNR_TIER_PROFESSIONAL:
        tier = f"PROFESIONAL (>={SNR_TIER_PROFESSIONAL:.0f}dB)"
    elif snr >= SNR_TIER_CONSUMER:
        tier = f"CONSUMER (>={SNR_TIER_CONSUMER:.0f}dB)"
    elif snr >= SNR_TIER_MARGINAL:
        tier = f"MARGINAL (>={SNR_TIER_MARGINAL:.0f}dB)"
    else:
        tier = f"INACEPTABLE (<{SNR_TIER_MARGINAL:.0f}dB)"
    return {"snr_db": snr, "tier": tier}


def detect_waveform_artifacts(y, sr):
    """Detecta DC offset, clipping, clicks incidentales y rumble sub-20 Hz."""
    artifacts = []

    dc = float(np.mean(y))
    if abs(dc) > DC_OFFSET_THRESHOLD:
        artifacts.append(f"DC_OFFSET (media={dc:+.5f} FS)")

    clipped = int(np.sum(np.abs(y) >= 0.999))
    if clipped > 0:
        peak = float(np.max(np.abs(y)))
        artifacts.append(f"CLIPPING ({clipped} muestra(s), pico={peak:.5f})")

    skip_s = int(CLICK_ONSET_SKIP_MS / 1000 * sr)
    y_post = y[skip_s:] if len(y) > skip_s + 2 else y
    if len(y_post) > 1:
        diff_y     = np.abs(np.diff(y_post))
        click_mask = diff_y > CLICK_THRESHOLD_FS
        n_clicks   = int(np.sum(click_mask))
        if n_clicks > 0:
            first_idx    = int(np.argmax(click_mask))
            first_time_s = (skip_s + first_idx) / sr
            artifacts.append(
                f"CLICKS_INCIDENTALES ({n_clicks} transiente(s) post-onset, "
                f"primero en t={first_time_s:.2f}s)"
            )

    if len(y) >= 4096:
        n_fft     = 4096
        spec      = np.abs(np.fft.rfft(y[:n_fft], n=n_fft)) ** 2
        freqs     = np.fft.rfftfreq(n_fft, d=1.0 / sr)
        e_rumble  = float(np.sum(spec[freqs < RUMBLE_HZ]))
        e_total   = float(np.sum(spec)) + 1e-12
        rumble_db = 10 * np.log10(e_rumble / e_total + 1e-12)
        if rumble_db > RUMBLE_DB_THRESHOLD:
            artifacts.append(
                f"RUMBLE_LF (energia <{RUMBLE_HZ:.0f}Hz = {rumble_db:.1f}dB relativo al total)"
            )

    return artifacts


# =============================================================================
# ANALISIS POR NOTA
# =============================================================================

def analyze_note(wav_path):
    """
    Carga WAV y extrae todas las metricas necesarias para decidir correcciones.
    Detecta modificadores _UNA / _SP y ajusta parametros de analisis.
    """
    y_stereo, sr = sf.read(wav_path, dtype='float32', always_2d=True)
    if sr != TARGET_SR:
        y_stereo = np.stack([
            librosa.resample(y_stereo[:, c], orig_sr=sr, target_sr=TARGET_SR)
            for c in range(y_stereo.shape[1])
        ], axis=1)
        sr = TARGET_SR
    y = librosa.to_mono(y_stereo.T)
    n = len(y)

    params    = get_effective_params(os.path.basename(wav_path))
    sin_pedal = params["sin_pedal"]

    atk_end   = int(ATTACK_MS        / 1000 * sr)
    sus_start = int(SUSTAIN_START_MS / 1000 * sr)
    sus_end   = int(SUSTAIN_END_MS   / 1000 * sr)
    fl_skip   = int(FLUTTER_SKIP_MS  / 1000 * sr)

    seg_atk = y[:atk_end]
    seg_sus = y[sus_start : min(sus_end, n)]

    # f0
    f0_hz = None
    if n >= PITCH_FRAME_LENGTH:
        try:
            f0arr, vf, vp = librosa.pyin(
                y[:min(int(PITCH_WINDOW_S * sr), n)], sr=sr,
                fmin=librosa.note_to_hz('A0'), fmax=librosa.note_to_hz('C8'),
                frame_length=PITCH_FRAME_LENGTH, hop_length=PITCH_HOP_LENGTH,
                fill_na=None,
            )
            valid = vf & ~np.isnan(f0arr)
            if np.any(valid):
                f0_hz = float(np.average(f0arr[valid], weights=vp[valid]))
        except Exception:
            pass

    midi = int(round(librosa.hz_to_midi(f0_hz))) if f0_hz else None

    rms_atk    = float(np.sqrt(np.mean(seg_atk ** 2))) if len(seg_atk) > 0 else 1e-9
    rms_sus    = float(np.sqrt(np.mean(seg_sus ** 2))) if len(seg_sus) > 128 else 1e-9
    rms_atk_db = 20 * np.log10(max(rms_atk, 1e-9))
    rms_sus_db = 20 * np.log10(max(rms_sus, 1e-9))

    # HF energy en ataque
    hf_db = None
    if len(seg_atk) >= 512:
        D     = np.abs(librosa.stft(seg_atk, n_fft=1024, hop_length=256)) ** 2
        freqs = librosa.fft_frequencies(sr=sr, n_fft=1024)
        sb    = int(np.searchsorted(freqs, KEY_NOISE_SHELF_HZ))
        e_tot = float(np.sum(D)) + 1e-12
        e_hf  = float(np.sum(D[sb:, :]))
        hf_db = 10 * np.log10(e_hf / e_tot + 1e-12)

    # Flutter y re-emergencia
    flutter_ptp        = 0.0
    reemergence_count  = 0
    reemergence_sample = None
    fl_seg = y[fl_skip:n]

    if len(fl_seg) > RMS_FRAME_LENGTH * 4:
        rms_fl = librosa.feature.rms(
            y=fl_seg, frame_length=RMS_FRAME_LENGTH, hop_length=RMS_HOP_LENGTH
        )[0]
        rms_fl = np.maximum(rms_fl, 1e-9)
        if len(rms_fl) >= SAVGOL_WINDOW:
            trend      = scipy.signal.savgol_filter(rms_fl, SAVGOL_WINDOW, SAVGOL_POLY)
            trend      = np.maximum(trend, 1e-9)
            res_db     = 20 * np.log10(rms_fl) - 20 * np.log10(trend)
            flutter_ptp = float(np.ptp(res_db))

        rms_db = 20 * np.log10(rms_fl)
        for k in range(2, len(rms_db)):
            drop = rms_db[k-2] - rms_db[k-1]
            rise = rms_db[k]   - rms_db[k-1]
            if drop > 1.0 and rise > REEMERGENCE_RISE_DB:
                reemergence_count += 1
                if reemergence_sample is None:
                    frame_in_seg = k - 1
                    reemergence_sample = fl_skip + int(
                        librosa.frames_to_samples(frame_in_seg, hop_length=RMS_HOP_LENGTH)
                    )

    # Ruido 3 componentes, SNR y artefactos
    noise_p   = analyze_noise_profile(y, sr, flutter_ptp_db=flutter_ptp, sin_pedal=sin_pedal)
    snr_r     = compute_snr_quality(rms_atk_db, noise_p["noise_rms_db"])
    artifacts = detect_waveform_artifacts(y, sr)

    return {
        "path":               wav_path,
        "filename":           os.path.basename(wav_path),
        "sr":                 sr,
        "n_samples":          n,
        "f0_hz":              f0_hz,
        "midi":               midi,
        "note_name":          librosa.hz_to_note(f0_hz) if f0_hz else "?",
        "duration":           n / sr,
        # Nivel
        "rms_atk_db":         rms_atk_db,
        "rms_sus_db":         rms_sus_db,
        "hf_energy_db":       hf_db,
        # Dinamica de sustain
        "flutter_ptp_db":     flutter_ptp,
        "reemergence_count":  reemergence_count,
        "reemergence_sample": reemergence_sample,
        # Ruido — 3 componentes
        "noise_rms_db":          noise_p["noise_rms_db"],
        "flutter_contribution_db": noise_p["flutter_contribution_db"],
        "room_contribution_db":  noise_p["room_contribution_db"],
        "noise_seg":             noise_p["noise_seg"],
        "noise_freqs":           noise_p["noise_freqs"],
        "noise_spec":            noise_p["noise_spec"],
        "noise_flatness":        noise_p["flatness"],
        "hum_detected":          noise_p["hum_detected"],
        "mvsep_peaks":           noise_p["mvsep_peaks"],
        "noise_tail_s":          noise_p["tail_start_s"],
        # SNR
        "snr_db":             snr_r["snr_db"],
        "snr_tier":           snr_r["tier"],
        # Artefactos
        "artifacts":          artifacts,
        # Modificadores activos
        "una_corda":          parse_filename_modifiers(os.path.basename(wav_path))["una_corda"],
        "sin_pedal":          parse_filename_modifiers(os.path.basename(wav_path))["sin_pedal"],
        # Params efectivos para correccion
        "_params":            params,
    }


# =============================================================================
# DECISION DE CORRECCIONES
# =============================================================================

def decide_corrections(note):
    """
    Decide que correcciones aplicar a cada nota.
    Usa parametros adaptativos segun modificadores _UNA / _SP del archivo.
    """
    params        = note["_params"]
    max_boost     = params["level_max_boost"]
    knr_plus_db   = params["knr_plus_db"]
    is_una        = params["una_corda"]

    corr = {
        "gain_db":              0.0,
        "gain_capped":          False,
        "knr_plus":             False,
        "knr_plus_db":          knr_plus_db,
        "smooth_flutter":       False,
        "smooth_requiere_rx":   False,
        "trim_reemergencia":    False,
        "trim_sample":          None,
        "alternatives":         [],
        "status":               "OK",
        "flags_residuales":     [],
    }

    # --- NIVEL ---
    diff = LEVEL_TARGET_DB - note["rms_sus_db"]
    if abs(diff) > LEVEL_TOLERANCE:
        if diff > 0:
            if diff > max_boost:
                corr["gain_db"]     = max_boost
                corr["gain_capped"] = True
                corr["status"]      = "REQUIERE_REGRABACION"
                corr["alternatives"].append(
                    f"Nivel insuficiente: necesita +{diff:.1f}dB pero techo es +{max_boost:.0f}dB"
                    f"{'(_UNA ampliado)' if is_una else ''}. "
                    f"Opciones: (A) re-grabar con mayor velocity; "
                    f"(B) ajustar curva velocidad en Kontakt. "
                    f"Se aplico boost maximo de +{max_boost:.0f}dB."
                )
            else:
                corr["gain_db"] = diff
        else:
            corr["gain_db"] = diff

    # --- KNR ADICIONAL ---
    hf = note.get("hf_energy_db")
    if hf is not None and hf > KNR_HF_THRESHOLD_DB and note["f0_hz"] and note["f0_hz"] >= 130.0:
        corr["knr_plus"] = True
        if is_una:
            corr["flags_residuales"].append(f"KNR_UNA ({knr_plus_db:+.0f}dB - sordina reduce HF)")

    # --- SUAVIZADO DE FLUTTER ---
    fp = note["flutter_ptp_db"]
    if fp >= FLUTTER_WARN_DB:
        corr["smooth_flutter"] = True
        if fp >= FLUTTER_CRITICAL_DB:
            corr["smooth_requiere_rx"] = True
            corr["flags_residuales"].append(f"FLUTTER_CRITICO ({fp:.1f}dB ptp) — REQUIERE_RX")
            corr["alternatives"].append(
                f"Flutter critico ({fp:.1f}dB ptp): instrumento patrimonial no afinable. "
                f"Pipeline aplica smoothing espectral (paliatvo). "
                f"Solucion definitiva: iZotope RX Elements De-flutter + "
                f"Kontakt Random Tune +/-5 cents."
            )
            if corr["status"] == "OK":
                corr["status"] = "FLUTTER_CRITICO_RX"
        else:
            corr["flags_residuales"].append(f"FLUTTER_MODERADO ({fp:.1f}dB ptp)")
            if corr["status"] == "OK":
                corr["status"] = "FLUTTER_SUAVIZADO"

    # --- TRIM REEMERGENCIA ---
    if note["reemergence_count"] > 0 and note["reemergence_sample"] is not None:
        corr["trim_reemergencia"] = True
        corr["trim_sample"]       = note["reemergence_sample"]
        corr["alternatives"].append(
            f"Re-emergencia detectada en {note['reemergence_sample']/note['sr']:.1f}s. "
            f"Se recorta + fade-out coseno de {TRIM_FADEOUT_MS}ms. "
            f"Alternativa: edicion manual en REAPER para control fino del punto de corte."
        )

    return corr


# =============================================================================
# APLICACION DE CORRECCIONES
# =============================================================================

def apply_knr_plus(segment_stereo, sr, f0_hz, knr_db):
    """Segundo paso de KNR: knr_db dB sobre KEY_NOISE_SHELF_HZ."""
    n_fft       = 2048
    hop         = 512
    win_samples = int(KNR_PLUS_WINDOW_MS / 1000 * sr)
    win_frames  = max(1, int(np.ceil(win_samples / hop)))
    freqs       = np.fft.rfftfreq(n_fft, d=1.0 / sr)
    shelf_bin   = int(np.searchsorted(freqs, KEY_NOISE_SHELF_HZ))
    gain_floor  = 10 ** (knr_db / 20)

    result = np.empty_like(segment_stereo)
    for ch in range(2):
        stft = librosa.stft(segment_stereo[ch], n_fft=n_fft, hop_length=hop)
        n_fr = stft.shape[1]
        for fi in range(min(win_frames, n_fr)):
            alpha = fi / win_frames
            stft[shelf_bin:, fi] *= gain_floor + alpha * (1.0 - gain_floor)
        result[ch] = librosa.istft(stft, hop_length=hop, length=segment_stereo.shape[1])
    return result


def apply_trim_reemergencia(segment_stereo, trim_sample, sr):
    """Recorta en trim_sample y aplica fade-out coseno de TRIM_FADEOUT_MS ms."""
    fadeout_samples = int(TRIM_FADEOUT_MS / 1000 * sr)
    cut_point  = min(trim_sample, segment_stereo.shape[1])
    start_fade = max(0, cut_point - fadeout_samples)
    out        = segment_stereo[:, :cut_point].copy()
    ramp_len   = cut_point - start_fade
    if ramp_len > 0:
        t    = np.linspace(0.0, np.pi / 2, ramp_len)
        ramp = np.cos(t)
        out[:, start_fade:cut_point] *= ramp
    return out


def rectify_note(note, corr, y_stereo_full):
    """
    Aplica las correcciones decididas al segmento estereo.
    Orden: Gain -> KNR+ -> Smooth_flutter -> Trim_reemergencia.
    Retorna array estereo rectificado (2, N).
    """
    seg = y_stereo_full.copy()

    # 1. Ganancia estatica (preserva ADSR)
    if corr["gain_db"] != 0.0:
        seg *= 10 ** (corr["gain_db"] / 20)

    # 2. KNR adicional (con dB adaptativo segun _UNA)
    if corr["knr_plus"]:
        seg = apply_knr_plus(seg, note["sr"], note["f0_hz"], corr["knr_plus_db"])

    # 3. Suavizado de flutter (solo sustain, ataque intacto)
    if corr["smooth_flutter"]:
        seg, _ = smooth_flutter_sustain(seg, note["sr"], note["flutter_ptp_db"])

    # 4. Trim re-emergencia
    if corr["trim_reemergencia"] and corr["trim_sample"] is not None:
        seg = apply_trim_reemergencia(seg, corr["trim_sample"], note["sr"])

    return seg


# =============================================================================
# ANALISIS ESPECTRAL INDIVIDUAL (5 paneles)
# =============================================================================

def generate_spectral_png(y_stereo_rect, note, corr, out_dir, sr):
    """Genera PNG espectral de 5 paneles para la nota rectificada."""
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except ImportError:
        return

    y = librosa.to_mono(y_stereo_rect)
    n = len(y)

    atk_end = int(ATTACK_MS       / 1000 * sr)
    fl_skip = int(FLUTTER_SKIP_MS / 1000 * sr)
    seg_fl  = y[fl_skip:n] if n > fl_skip + RMS_FRAME_LENGTH * 4 else y

    D_full = librosa.amplitude_to_db(np.abs(librosa.stft(y, n_fft=2048, hop_length=512)), ref=np.max)
    t_full = librosa.frames_to_time(np.arange(D_full.shape[1]), sr=sr, hop_length=512)

    zoom_samples = int(0.2 * sr)
    seg_zoom = y[:min(zoom_samples, n)]
    D_zoom   = librosa.amplitude_to_db(np.abs(librosa.stft(seg_zoom, n_fft=1024, hop_length=128)), ref=np.max)
    t_zoom   = librosa.frames_to_time(np.arange(D_zoom.shape[1]), sr=sr, hop_length=128)

    rms_env = librosa.feature.rms(y=y, frame_length=RMS_FRAME_LENGTH, hop_length=RMS_HOP_LENGTH)[0]
    t_rms   = librosa.frames_to_time(np.arange(len(rms_env)), sr=sr, hop_length=RMS_HOP_LENGTH)
    rms_env = np.maximum(rms_env, 1e-9)

    rms_fl_arr  = None
    trend_db    = None
    flutter_ptp = 0.0
    if len(seg_fl) > RMS_FRAME_LENGTH * 4:
        rms_fl_arr = librosa.feature.rms(y=seg_fl, frame_length=RMS_FRAME_LENGTH, hop_length=RMS_HOP_LENGTH)[0]
        rms_fl_arr = np.maximum(rms_fl_arr, 1e-9)
        if len(rms_fl_arr) >= SAVGOL_WINDOW:
            tr          = scipy.signal.savgol_filter(rms_fl_arr, SAVGOL_WINDOW, SAVGOL_POLY)
            tr          = np.maximum(tr, 1e-9)
            res         = 20 * np.log10(rms_fl_arr) - 20 * np.log10(tr)
            flutter_ptp = float(np.ptp(res))
            trend_db    = 20 * np.log10(tr)

    corrections_str = []
    if corr["gain_db"] != 0.0:
        corrections_str.append(f"Gain {corr['gain_db']:+.1f}dB{'(cap)' if corr['gain_capped'] else ''}")
    if corr["knr_plus"]:
        corrections_str.append(f"KNR+{abs(corr['knr_plus_db']):.0f}dB")
    if corr["smooth_flutter"]:
        rx_tag = "+REQUIERE_RX" if corr["smooth_requiere_rx"] else ""
        corrections_str.append(f"FlutterSmooth{rx_tag}")
    if corr["trim_reemergencia"]:
        t_trim = corr["trim_sample"] / sr if corr["trim_sample"] else 0
        corrections_str.append(f"Trim@{t_trim:.1f}s")
    corr_label  = "  |  ".join(corrections_str) if corrections_str else "SIN CORRECCION"
    flags_label = "  ".join(corr["flags_residuales"]) if corr["flags_residuales"] else ""

    snr_db   = note.get("snr_db",      0.0)
    snr_tier = note.get("snr_tier",    "?")
    noise_db = note.get("noise_rms_db", -999.0)
    f0_val   = note.get("f0_hz",        0.0) or 0.0
    mod_tags = ("_UNA" if note.get("una_corda") else "") + ("_SP" if note.get("sin_pedal") else "")

    fig, axes = plt.subplots(5, 1, figsize=(14, 17), sharex=False)
    suptitle = (
        f"{note['filename']}  [{note['note_name']}  {f0_val:.1f}Hz]{mod_tags}  Estado: {corr['status']}\n"
        f"Correcciones: {corr_label}  {flags_label}\n"
        f"SNR: {snr_db:.1f}dB ({snr_tier.split('(')[0].strip()})  |  "
        f"Piso elec: {noise_db:.1f}dBFS  |  "
        f"Sala: +{note.get('room_contribution_db', 0):.1f}dB  |  "
        f"Flatness: {note.get('noise_flatness', 0):.4f}  |  "
        f"Picos MVSep: {note.get('mvsep_peaks', 0)}"
    )
    fig.suptitle(suptitle, fontsize=8, fontweight="bold")

    # Panel 1: espectrograma completo
    librosa.display.specshow(D_full, sr=sr, hop_length=512, x_coords=t_full,
                             x_axis='time', y_axis='log', ax=axes[0], cmap='magma')
    axes[0].set_title("Espectrograma completo (dB, log)", fontsize=8)
    axes[0].axhline(KEY_NOISE_SHELF_HZ, color='cyan', lw=0.7, ls='--', label='8kHz (KNR shelf)')
    axes[0].legend(fontsize=7, loc='upper right')

    # Panel 2: zoom ataque 0-200ms
    librosa.display.specshow(D_zoom, sr=sr, hop_length=128, x_coords=t_zoom,
                             x_axis='time', y_axis='log', ax=axes[1], cmap='magma')
    axes[1].set_title("Zoom ataque 0-200ms", fontsize=8)
    axes[1].axvline(ATTACK_MS / 1000, color='lime', lw=0.8, ls='--',
                    label=f'{ATTACK_MS}ms key noise window')
    axes[1].axhline(KEY_NOISE_SHELF_HZ, color='cyan', lw=0.7, ls='--')
    axes[1].legend(fontsize=7, loc='upper right')

    # Panel 3: waveform + RMS
    t_wave = np.arange(n) / sr
    axes[2].plot(t_wave, y, lw=0.25, color='steelblue', alpha=0.6, label='waveform')
    axes[2].plot(t_rms, rms_env, lw=1.5, color='orange', label='RMS')
    if corr["trim_reemergencia"] and corr["trim_sample"]:
        t_t = corr["trim_sample"] / sr
        axes[2].axvline(t_t, color='red', lw=1.2, ls='--', label=f'Trim @{t_t:.1f}s')
    noise_ts = note.get("noise_tail_s")
    if noise_ts:
        axes[2].axvline(noise_ts, color='gray', lw=0.8, ls=':', label=f'Ruido @{noise_ts:.1f}s')
    axes[2].set_ylabel("Amplitud")
    axes[2].set_title(
        f"Waveform  |  RMS sustain: {note['rms_sus_db']:.1f}dBFS  |  "
        f"Gain: {corr['gain_db']:+.1f}dB", fontsize=8
    )
    axes[2].legend(fontsize=7, loc='upper right')

    # Panel 4: flutter con tendencia Savgol
    if rms_fl_arr is not None and trend_db is not None:
        t_fl      = (librosa.frames_to_time(np.arange(len(rms_fl_arr)), sr=sr, hop_length=RMS_HOP_LENGTH)
                     + FLUTTER_SKIP_MS / 1000)
        rms_fl_db = 20 * np.log10(rms_fl_arr)
        axes[3].plot(t_fl, rms_fl_db, lw=0.9, color='steelblue', alpha=0.7, label='RMS (dB)')
        axes[3].plot(t_fl, trend_db,  lw=1.5, color='orange',               label='Tendencia Savgol')
        axes[3].fill_between(t_fl, rms_fl_db, trend_db,
                             where=(rms_fl_db > trend_db + 1.0),
                             color='red', alpha=0.25, label='Flutter')
        color_f = ('red'    if flutter_ptp >= FLUTTER_CRITICAL_DB else
                   'orange' if flutter_ptp >= FLUTTER_WARN_DB     else 'green')
        smooth_tag = " [SUAVIZADO]" if corr["smooth_flutter"] else ""
        axes[3].set_title(
            f"Sustain RMS  |  Flutter ptp: {flutter_ptp:.1f}dB{smooth_tag}  "
            f"|  Re-emergencias: {note['reemergence_count']}", fontsize=8, color=color_f
        )
        axes[3].set_ylabel("dBFS")
        axes[3].set_xlabel("Tiempo (s)")
        axes[3].legend(fontsize=7, loc='upper right')
    else:
        axes[3].set_visible(False)

    # Panel 5: espectro del piso de ruido con 3 componentes
    noise_freqs = note.get("noise_freqs")
    noise_spec  = note.get("noise_spec")
    if noise_freqs is not None and noise_spec is not None and len(noise_freqs) > 1:
        spec_db = 10 * np.log10(noise_spec + 1e-12)
        axes[4].plot(noise_freqs, spec_db, lw=0.7, color='mediumseagreen', alpha=0.85,
                     label='Espectro piso de ruido')
        if len(noise_spec) >= 20:
            baseline = uniform_filter1d(noise_spec.astype(float), size=20)
            base_db  = 10 * np.log10(baseline + 1e-12)
            axes[4].plot(noise_freqs, base_db, lw=1.2, color='orange', ls='--',
                         label='Baseline suavizado')
        for hf in note.get("hum_detected", []):
            axes[4].axvline(hf, color='red', lw=0.8, ls=':', alpha=0.7, label=f'Hum {hf}Hz')
        axes[4].set_xlim(0, min(sr / 2, 22050))
        axes[4].set_xlabel("Frecuencia (Hz)")
        axes[4].set_ylabel("Potencia (dB)")
        hums     = note.get("hum_detected", [])
        hum_str  = f"Hum: {hums}Hz" if hums else "Sin hum"
        room_db  = note.get("room_contribution_db", 0.0)
        axes[4].set_title(
            f"Piso de ruido — 3 componentes  |  "
            f"Elec={noise_db:.1f}dBFS  Sala=+{room_db:.1f}dB  Flutter_est=+{note.get('flutter_ptp_db', 0)/2:.1f}dB  |  "
            f"Flat={note.get('noise_flatness', 0):.4f}  MVSep={note.get('mvsep_peaks', 0)}  {hum_str}",
            fontsize=7
        )
        axes[4].legend(fontsize=7, loc='upper right')
    else:
        axes[4].set_visible(False)

    plt.tight_layout(rect=[0, 0, 1, 0.93])
    out_path = os.path.join(out_dir, note["filename"].replace(".wav", "_rectificado.png"))
    plt.savefig(out_path, dpi=110)
    plt.close(fig)


# =============================================================================
# LOG DE CORRECCIONES
# =============================================================================

def write_correction_log(results, out_dir):
    lines = [
        "LOG DE RECTIFICACION -- pipeline_rectify.py",
        "=" * 80,
        f"Target nivel p    : {LEVEL_TARGET_DB} dBFS  |  Tolerancia: +/-{LEVEL_TOLERANCE}dB",
        f"Boost max normal  : +{LEVEL_MAX_BOOST}dB  |  Boost max _UNA: +{LEVEL_MAX_BOOST_UNA}dB",
        f"KNR Plus normal   : {abs(KNR_PLUS_ATTENUATION_DB)}dB adicional si HF > {KNR_HF_THRESHOLD_DB}dB",
        f"KNR Plus _UNA     : {abs(KNR_UNA_ATTENUATION_DB)}dB (sordina atenua HF fisicamente)",
        f"Smooth flutter    : Savitzky-Golay sobre RMS por banda STFT (solo sustain)",
        f"Trim reemergencia : fade-out coseno de {TRIM_FADEOUT_MS}ms",
        f"Instrumento       : Piano patrimonial NO afinable. Flutter = caracter. del instr.",
        "=" * 80, "",
        f"{'Archivo':<26} {'Nota':>5} {'RMS':>7} {'Gain':>7} {'KNR+':>5} {'Smooth':>7} {'Trim':>7} {'Estado':<22} {'Flags'}",
        "-" * 130,
    ]

    status_counts = {}
    for r in results:
        n, c   = r["note"], r["corr"]
        knr_s  = f"{abs(c['knr_plus_db']):.0f}dB" if c["knr_plus"] else "-"
        trim_s = (f"@{c['trim_sample']/n['sr']:.1f}s"
                  if c["trim_reemergencia"] and c["trim_sample"] else "-")
        smooth_s = "RX" if c.get("smooth_requiere_rx") else ("Si" if c.get("smooth_flutter") else "-")
        flags  = " | ".join(c["flags_residuales"]) if c["flags_residuales"] else "OK"
        gain_s = f"{c['gain_db']:+.2f}{'(c)' if c['gain_capped'] else ''}"
        mod_s  = ("_UNA" if n.get("una_corda") else "") + ("_SP" if n.get("sin_pedal") else "")
        lines.append(
            f"{n['filename']:<26} {n['note_name']:>5} "
            f"{n['rms_sus_db']:>6.1f} "
            f"{gain_s:>7}  "
            f"{knr_s:>5}  {smooth_s:>7}  {trim_s:>7}  "
            f"{c['status']:<22} {flags}{mod_s}"
        )
        status_counts[c["status"]] = status_counts.get(c["status"], 0) + 1

    lines += ["", "=" * 80, "RESUMEN DE ESTADOS:", ""]
    for status, cnt in sorted(status_counts.items()):
        lines.append(f"  {status:<30} {cnt} nota(s)")

    lines += ["", "=" * 80, "ALTERNATIVAS DETALLADAS POR NOTA:", ""]
    for r in results:
        n, c = r["note"], r["corr"]
        if c["alternatives"]:
            lines.append(f"  {n['filename']} ({n['note_name']}):")
            for alt in c["alternatives"]:
                for line in alt.split(". "):
                    if line.strip():
                        lines.append(f"    - {line.strip()}")
            lines.append("")

    lines += [
        "=" * 80,
        "ESTRATEGIA DE CORRECCION DE FLUTTER (instrumento patrimonial no afinable):",
        "",
        "  El flutter no puede corregirse no-destructivamente de forma completa.",
        "  El pipeline aplica suavizado espectral como paliativo. Estrategia gradual:",
        "  1. pipeline_rectify.py: smooth_flutter_sustain() — Savitzky-Golay por banda",
        "     STFT. Atenua la modulacion de amplitud sin afectar el pitch ni el ataque.",
        "  2. REAPER: ReaTune / ReaPitch para flutter moderado (2.5-10 dB ptp).",
        "  3. iZotope RX Elements (~USD 100): De-flutter para flutter critico (>10 dB ptp).",
        "     Notas candidatas: C2_RR1, C4 x3, C5 x4, C7 x3.",
        "  4. Kontakt 7: Random Tune +/-5 cents por voz — dispersa el patron de",
        "     batimiento entre voice instances. Documentado como decision de diseno",
        "     que reproduce el comportamiento acustico del instrumento patrimonial.",
        "",
        "NOTAS SOBRE NIVEL INSUFICIENTE (C7):",
        "  Los tres RR de C7 requieren boost de +14 a +21 dB. Techo de +8dB insuficiente.",
        "  Causa raiz: velocity insuficiente del pianista en registro agudo.",
        "  El nuevo setup M5 mejora SNR pero no resuelve el problema de velocity.",
        "  Opciones: (1) Re-grabar con mayor velocity. (2) Capa 'pp' en Kontakt.",
    ]

    path = os.path.join(out_dir, "correction_log.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"  Log escrito: {path}")


# =============================================================================
# INFORME DE RUIDO / SNR / ARTEFACTOS (3 COMPONENTES)
# =============================================================================

def write_noise_snr_report(results, out_dir):
    """
    Genera noise_snr_report.txt con analisis de piso de ruido en 3 componentes,
    ranking SNR, analisis MVSep, hum y artefactos incidentales.
    """
    snr_ranked = sorted(results, key=lambda r: r["note"].get("snr_db", -999), reverse=True)

    lines = [
        "INFORME DE RUIDO RESIDUAL Y SNR -- pipeline_rectify.py",
        "=" * 80,
        "METODOLOGIA — Descomposicion en 3 componentes de ruido:",
        "  1. Piso electronico : RMS del segmento mas silencioso (mic + previo + AD)",
        "  2. Flutter cuerdas  : Contribucion estimada del beating entre cuerdas",
        "                        (caracteristica del instrumento patrimonial no afinable)",
        "  3. Ruido ambiental  : Diferencia entre RMS mediano y minimo de la cola",
        "                        (sala, HVAC, ambiente de grabacion)",
        f"Tiers SNR: Excel>={SNR_TIER_EXCELLENT:.0f}dB | Prof>={SNR_TIER_PROFESSIONAL:.0f}dB | "
        f"Consumer>={SNR_TIER_CONSUMER:.0f}dB | Marginal>={SNR_TIER_MARGINAL:.0f}dB",
        "=" * 80, "",
        f"{'Archivo':<26} {'Nota':>5} {'Elec_dBFS':>10} {'Sala+dB':>8} {'Flutt+dB':>9} "
        f"{'SNR_dB':>7} {'Flat':>6} {'MVSep':>6}  Tier",
        "-" * 100,
    ]

    for r in results:
        n          = r["note"]
        elec_db    = n.get("noise_rms_db",          -999.0)
        room_db    = n.get("room_contribution_db",   0.0)
        flutt_db   = n.get("flutter_ptp_db",         0.0) / 2.0
        snr_db     = n.get("snr_db",                 0.0)
        flatness   = n.get("noise_flatness",          0.0)
        mvsep_p    = n.get("mvsep_peaks",             0)
        tier_short = n.get("snr_tier", "?").split("(")[0].strip()
        mod_s      = ("_UNA" if n.get("una_corda") else "") + ("_SP" if n.get("sin_pedal") else "")
        lines.append(
            f"{n['filename']:<26} {n['note_name']:>5} "
            f"{elec_db:>10.1f} "
            f"{room_db:>8.1f} "
            f"{flutt_db:>9.1f} "
            f"{snr_db:>7.1f} "
            f"{flatness:>6.4f} "
            f"{mvsep_p:>6}  "
            f"{tier_short}{mod_s}"
        )

    # Nota con mejor SNR
    best_r    = snr_ranked[0]["note"] if snr_ranked else None
    best_snr  = best_r.get("snr_db",       0.0)  if best_r else 0.0
    best_tier = best_r.get("snr_tier",      "?")  if best_r else "?"
    best_elec = best_r.get("noise_rms_db", -999.) if best_r else -999.0

    lines += [
        "",
        "=" * 80,
        "NOTA CON MEJOR SNR (referencia de calidad):",
        "",
        f"  Archivo    : {best_r['filename'] if best_r else 'N/A'}",
        f"  Nota       : {best_r['note_name'] if best_r else 'N/A'}",
        f"  SNR        : {best_snr:.1f} dB",
        f"  Piso elec. : {best_elec:.1f} dBFS",
        f"  Tier       : {best_tier}",
        "",
        "  Referencia para futuras sesiones con nuevo setup M5 ORTF:",
        "  El SNR del set actual (CM25+AT3035, par hibrido SDC+LDC) servira",
        "  como baseline. El nuevo par matched M5 (EIN 19 dBA, matched SDC)",
        "  deberia mejorar flatness espectral y reducir ruido tonal de MVSep.",
    ]

    if best_snr >= SNR_TIER_EXCELLENT:
        lines += [
            f"  >> SNR >= {SNR_TIER_EXCELLENT:.0f}dB: EXCELENTE (tier VSL/Spitfire).",
            "     Comparable a librerias de referencia. No requiere tratamiento adicional.",
        ]
    elif best_snr >= SNR_TIER_PROFESSIONAL:
        lines += [
            f"  >> SNR >= {SNR_TIER_PROFESSIONAL:.0f}dB: PROFESIONAL. Aceptable para produccion.",
            "     Opcional: noise gate suave post-release en Kontakt.",
        ]
    else:
        lines += [
            f"  >> SNR < {SNR_TIER_PROFESSIONAL:.0f}dB: Evaluar mejora de cadena de captura.",
            "     Nuevo setup M5 deberia subir el SNR del set completo.",
        ]

    lines += ["", "  Ranking SNR (mayor a menor):"]
    for i, r in enumerate(snr_ranked, 1):
        n = r["note"]
        lines.append(
            f"  {i:>2}. {n['filename']:<26} {n['note_name']:>5}  "
            f"SNR={n.get('snr_db', 0):.1f}dB  Elec={n.get('noise_rms_db', -999):.1f}dBFS  "
            f"{n.get('snr_tier', '?').split('(')[0].strip()}"
        )

    # Analisis de 3 componentes
    lines += [
        "",
        "=" * 80,
        "ANALISIS DE 3 COMPONENTES DE RUIDO:",
        "",
        "  Componente 1 — Piso electronico:",
        "    Ruido de captura (mic + previo + conversion). Valor tipico set actual: ~-93 dBFS.",
        "    Con nuevo setup M5 (EIN 19 dBA, Focusrite 18i20 122dB DR) se espera mejora",
        "    de 0.5-2 dBA respecto al par CM25+AT3035.",
        "",
        "  Componente 2 — Flutter de cuerdas (instrumento patrimonial):",
        "    NO es un artefacto de captura. Es el beating entre cuerdas desafinadas",
        "    del instrumento institucional que NO puede afinarse.",
        "    La estimacion (flutter_ptp/2) es aproximada; iZotope RX De-flutter",
        "    puede medir y corregir este componente con mayor precision.",
        "    NOTAS CRITICAS: C2_RR1, C4 x3, C5 x4, C7 x3 (>10 dB ptp).",
        "",
        "  Componente 3 — Ruido ambiental de sala:",
        "    Diferencia entre RMS mediano y minimo de la cola de la nota.",
        "    Valor 0 dB = sala muy silenciosa o nota sin cola util.",
        "    El CM25 usado como microfono de sala (1-1.5m, lateral) en el nuevo",
        "    setup provee referencia independiente del piso ambiental.",
        "",
        f"  {'Archivo':<26} {'Elec_dBFS':>10} {'Sala+dB':>8} {'Flutt_est+dB':>13}  Planitud_MVSep",
        "  " + "-" * 75,
    ]

    for r in results:
        n        = r["note"]
        elec_db  = n.get("noise_rms_db",         -999.0)
        room_db  = n.get("room_contribution_db",  0.0)
        flutt_db = n.get("flutter_ptp_db",        0.0) / 2.0
        flat     = n.get("noise_flatness",         0.0)
        if flat < 0.05:
            flat_interp = "Muy tonal (MVSep dominante)"
        elif flat < 0.15:
            flat_interp = "Algo tonal"
        elif flat < 0.40:
            flat_interp = "Mixto (sala+MVSep)"
        else:
            flat_interp = "Plano (sala/previo)"
        lines.append(
            f"  {n['filename']:<26} {elec_db:>10.1f} {room_db:>8.1f} {flutt_db:>13.1f}  {flat_interp}"
        )

    # Hum
    hum_notes = [(r["note"]["filename"], r["note"].get("hum_detected", []))
                 for r in results if r["note"].get("hum_detected")]
    if hum_notes:
        lines += [
            "", "=" * 80,
            "HUM DETECTADO EN COLA DE NOTA:",
            "  ATENCION: Frecuencias 250/300 Hz pueden ser parciales residuales del piano",
            "  (inarmónicidad natural de cuerdas graves) y NO hum electrico.",
            "  Verificar en espectrograma si la energia es estacionaria (hum real)",
            "  o decae con la nota (parcial residual -> NO aplicar notch).", "",
        ]
        for fname, hums in hum_notes:
            lines.append(f"  {fname:<28}  Frecuencias: {hums} Hz")
        lines += [
            "",
            "  Si se confirma hum electrico:",
            "  1. Verificar toma de tierra de la interfaz Focusrite 18i20 y del previo.",
            "  2. ReaEQ: notch de alta Q (Q=20-30) en cada frecuencia detectada.",
            "  3. iZotope RX Hum Removal: extrae fundamental + armonicos automaticamente.",
        ]

    # Artefactos incidentales
    artifact_notes = [(r["note"], r["note"].get("artifacts", []))
                      for r in results if r["note"].get("artifacts")]
    lines += ["", "=" * 80, "ARTEFACTOS INCIDENTALES EN FORMA DE ONDA:", ""]
    if artifact_notes:
        for n, arts in artifact_notes:
            lines.append(f"  {n['filename']} ({n['note_name']}):")
            for art in arts:
                lines.append(f"    [!] {art}")
                if "DC_OFFSET" in art:
                    lines += [
                        "        Abordaje: HP a 5 Hz en REAPER (ReaEQ shelving).",
                        "        Alternativa: 'Remove DC Offset' en el render del item.",
                    ]
                elif "CLIPPING" in art:
                    lines += [
                        "        Abordaje: re-grabar. Clipping es irrecuperable.",
                        "        Reducir ganancia del previo o activar Clip Safe en 18i20.",
                    ]
                elif "CLICKS_INCIDENTALES" in art:
                    lines += [
                        "        Abordaje: edicion manual en REAPER (crossfade 2-5ms).",
                        "        Herramienta alternativa: iZotope RX De-click.",
                    ]
                elif "RUMBLE_LF" in art:
                    lines += [
                        "        Abordaje: HP a 20 Hz (24 dB/oct) en REAPER o Kontakt Group Insert.",
                        "        No afecta contenido musical (f0 minimo del set >30 Hz).",
                    ]
            lines.append("")
    else:
        lines.append("  No se detectaron artefactos incidentales.")

    lines += [
        "", "=" * 80,
        "IMPACTO DEL NUEVO SETUP M5 EN EL PIPELINE:",
        "",
        "  Las nuevas grabaciones con Rode M5 (ORTF, matched SDC) produciran archivos",
        "  con distinto timbre respecto a las sesiones p/ff existentes (par hibrido).",
        "  Estrategia documentada en tesis:",
        "  - NO intentar igualar color timbrico entre setups.",
        "  - Usar pipeline_compare.py con SESSION_METADATA para cuantificar la diferencia",
        "    espectral como resultado medible de la investigacion.",
        "  - El cambio de setup esta justificado por mejora en SNR, matched imaging",
        "    y eliminacion de la asimetria timbrica L/R (CM25 SDC + AT3035 LDC).",
        "",
        "  Parametros a ajustar para nuevas sesiones _UNA (una corda):",
        f"  - KNR: {abs(KNR_UNA_ATTENUATION_DB)} dB (vs {abs(KNR_PLUS_ATTENUATION_DB)} dB normal) — sordina atenua HF fisicamente.",
        f"  - LEVEL_MAX_BOOST: +{LEVEL_MAX_BOOST_UNA} dB (vs +{LEVEL_MAX_BOOST} dB normal) — nivel inherentemente menor.",
        f"  - NOISE_WINDOW: {NOISE_SP_FRACTION*100:.0f}% de duracion para _SP (sin pedal).",
    ]

    path = os.path.join(out_dir, "noise_snr_report.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"  Informe SNR/ruido: {path}")


# =============================================================================
# MAIN
# =============================================================================

def main():
    os.makedirs(OUTPUT_DIR,   exist_ok=True)
    os.makedirs(SPECTRAL_DIR, exist_ok=True)

    print(f"\n{'='*65}")
    print(f"PIPELINE RECTIFICACION NO DESTRUCTIVA")
    print(f"{'='*65}\n")
    print(f"Salida: {OUTPUT_DIR}\n")

    all_wavs = []
    for session_folder in SESSIONS:
        for fname in sorted(os.listdir(session_folder)):
            if fname.endswith(".wav"):
                all_wavs.append(os.path.join(session_folder, fname))

    print(f"Total de muestras a procesar: {len(all_wavs)}\n")
    results = []

    for wav_path in all_wavs:
        fname = os.path.basename(wav_path)
        print(f"  [{fname}]")

        # 1. Analizar
        note = analyze_note(wav_path)
        mods = ("_UNA" if note.get("una_corda") else "") + ("_SP" if note.get("sin_pedal") else "")
        print(f"    f0={note['f0_hz']:.1f}Hz ({note['note_name']}){mods}  "
              f"RMS_sus={note['rms_sus_db']:.1f}dBFS  "
              f"Flutter={note['flutter_ptp_db']:.1f}dB  "
              f"Reemerg={note['reemergence_count']}")
        print(f"    SNR={note['snr_db']:.1f}dB ({note['snr_tier'].split('(')[0].strip()})  "
              f"Elec={note['noise_rms_db']:.1f}dBFS  "
              f"Sala=+{note['room_contribution_db']:.1f}dB  "
              f"Flat={note['noise_flatness']:.4f}  "
              f"MVSep={note['mvsep_peaks']}")
        if note["artifacts"]:
            print(f"    [!] Artefactos: {' | '.join(note['artifacts'])}")
        if note["hum_detected"]:
            print(f"    [!] Hum/parcial en: {note['hum_detected']} Hz")

        # 2. Decidir correcciones
        corr = decide_corrections(note)
        tags = []
        if corr["gain_db"] != 0.0:
            tags.append(f"Gain{corr['gain_db']:+.1f}dB{'(cap)' if corr['gain_capped'] else ''}")
        if corr["knr_plus"]:
            tags.append(f"KNR+{abs(corr['knr_plus_db']):.0f}dB")
        if corr["smooth_flutter"]:
            tags.append("FlutterSmooth" + ("+RX" if corr["smooth_requiere_rx"] else ""))
        if corr["trim_reemergencia"]:
            tags.append(f"Trim@{corr['trim_sample']/note['sr']:.1f}s")
        if not tags:
            tags.append("SIN_CORRECCION")
        print(f"    Correcciones: {', '.join(tags)}  Estado: {corr['status']}")

        # 3. Cargar estereo completo
        y_stereo_raw, sr = sf.read(wav_path, dtype='float32', always_2d=True)
        if sr != TARGET_SR:
            y_stereo_raw = np.stack([
                librosa.resample(y_stereo_raw[:, c], orig_sr=sr, target_sr=TARGET_SR)
                for c in range(y_stereo_raw.shape[1])
            ], axis=1)
            sr = TARGET_SR
        y_stereo = y_stereo_raw.T  # (2, N)
        note["sr"] = sr

        # 4. Aplicar correcciones
        y_rect = rectify_note(note, corr, y_stereo)

        # 5. Exportar WAV
        out_wav = os.path.join(OUTPUT_DIR, fname)
        sf.write(out_wav, y_rect.T, sr, subtype=EXPORT_SUBTYPE)

        # 6. PNG espectral (5 paneles)
        generate_spectral_png(y_rect, note, corr, SPECTRAL_DIR, sr)

        results.append({"note": note, "corr": corr})
        del y_stereo, y_stereo_raw, y_rect
        gc.collect()

    # 7. Reportes
    print("\nGenerando log de correcciones...")
    write_correction_log(results, OUTPUT_DIR)

    print("Generando informe de ruido y SNR...")
    write_noise_snr_report(results, OUTPUT_DIR)

    # 8. Resumen en consola
    print(f"\n{'='*65}")
    print(f"Rectificacion completada: {len(results)} muestras procesadas.")
    print(f"WAVs            : {OUTPUT_DIR}")
    print(f"Espectrogramas  : {SPECTRAL_DIR}")
    print(f"Log             : {os.path.join(OUTPUT_DIR, 'correction_log.txt')}")
    print(f"Informe SNR     : {os.path.join(OUTPUT_DIR, 'noise_snr_report.txt')}")

    ok        = sum(1 for r in results if r["corr"]["status"] == "OK")
    suavizado = sum(1 for r in results if "FLUTTER_SUAVIZADO" in r["corr"]["status"])
    rx_flag   = sum(1 for r in results if r["corr"].get("smooth_requiere_rx"))
    regrabar  = sum(1 for r in results if r["corr"]["status"] == "REQUIERE_REGRABACION")
    print(f"\n  Sin correccion         : {ok}")
    print(f"  Flutter suavizado      : {suavizado}")
    print(f"  Flutter critico (RX)   : {rx_flag}")
    print(f"  Requieren re-grabacion : {regrabar}")

    if results:
        best  = max(results, key=lambda r: r["note"].get("snr_db", -999))
        worst = min(results, key=lambda r: r["note"].get("snr_db",  999))
        print(f"\n  Mejor SNR  : {best['note']['filename']:30s} "
              f"{best['note'].get('snr_db', 0):.1f}dB")
        print(f"  Peor SNR   : {worst['note']['filename']:30s} "
              f"{worst['note'].get('snr_db', 0):.1f}dB")


if __name__ == "__main__":
    main()
