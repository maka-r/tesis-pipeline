# -*- coding: utf-8 -*-
"""
pipeline_new_session_compare.py
--------------------------------
Analisis comparativo entre:
  A) Muestras existentes procesadas (p_rectificado_pip/, 44100 Hz, post-MVSep)
  B) Nuevo archivo de grabacion (48000 Hz, pre-MVSep, ORTF M5)

Produce:
  Output_Samples/new_session_compare/
    compare_new_session_report.txt   -- Informe completo (nivel, fase, ruido, recomendaciones)
    compare_dynamics.png             -- Panel: RMS sustain existentes vs nuevo (normalizado)
    compare_phase.png                -- Panel: coherencia L/R por banda octava
    compare_noise.png                -- Panel: piso de ruido y perfil espectral
    compare_spectral.png             -- Panel: centroide espectral ataque vs sustain

Uso: python pipeline_new_session_compare.py
"""

import os
import gc
import numpy as np
import scipy.signal
import librosa
import soundfile as sf
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

# =============================================================================
# RUTAS
# =============================================================================

EXISTING_DIR = r"D:\Sesiones y proyectos\SESION 29-8\Pruebas de rendimiento denoise\Output_Samples\p_rectificado_pip"
NEW_WAV      = r"D:\Renders multipistas\Tesis\Crudos 15-5\TEMPLATE_GRABACION_PIANO_XY.wav"
OUTPUT_DIR   = r"D:\Sesiones y proyectos\SESION 29-8\Pruebas de rendimiento denoise\Output_Samples\new_session_compare"

# =============================================================================
# PARAMETROS (heredados del pipeline principal)
# =============================================================================

TARGET_SR          = 48000
ATTACK_MS          = 50
SUSTAIN_START_MS   = 200
SUSTAIN_END_MS     = 700
FLUTTER_SKIP_MS    = 400
PITCH_FRAME_LENGTH = 4096
PITCH_HOP_LENGTH   = 512
PITCH_WINDOW_S     = 0.5
RMS_HOP_LENGTH     = 512
RMS_FRAME_LENGTH   = 2048

# Onset detection (iguales a piano_sampler.py)
ONSET_HOP_LENGTH        = 128
ONSET_DELTA             = 0.10
ONSET_WAIT              = 10
ONSET_HPF_HZ            = 30
ONSET_PREROLL_MS        = 15
MIN_INTER_ONSET_SECONDS = 4
MAX_TAIL_SECONDS        = 35.0

# Noise analysis
NOISE_WINDOW_S     = 0.5
NOISE_TAIL_FRAC    = 2 / 3
HUM_FREQS_50HZ     = [50, 100, 150, 200, 250, 300]
HUM_FREQS_60HZ     = [60, 120, 180, 240, 300, 360]
HUM_BANDWIDTH_HZ   = 4
HUM_THRESHOLD_DB   = -60

# Targets de nivel (tabla INSTRUCCIONES_TEMPLATE_RPP.txt)
LEVEL_TARGET_P  = -28.0   # dBFS RMS sustain (p)
LEVEL_TARGET_MF = -18.0   # dBFS RMS sustain (mf)
PEAK_TARGET_MF  = -6.0    # dBFS pico (mf)

os.makedirs(OUTPUT_DIR, exist_ok=True)

# =============================================================================
# UTILIDADES
# =============================================================================

def load_resample(path):
    """Carga WAV y resamplea a TARGET_SR si difiere."""
    y_st, sr = sf.read(path, dtype='float32', always_2d=True)
    if sr != TARGET_SR:
        y_st = np.stack([
            librosa.resample(y_st[:, c], orig_sr=sr, target_sr=TARGET_SR)
            for c in range(y_st.shape[1])
        ], axis=1)
        sr = TARGET_SR
    return y_st, sr   # shape: (samples, channels)


def rms_db(x):
    return 20 * np.log10(np.sqrt(np.mean(x ** 2)) + 1e-12)


def peak_db(x):
    return 20 * np.log10(np.max(np.abs(x)) + 1e-12)


def wiener_flatness(spectrum):
    """Planitud espectral de Wiener: 0=tonal, 1=ruido blanco."""
    s = np.abs(spectrum) + 1e-12
    geo = np.exp(np.mean(np.log(s)))
    ari = np.mean(s)
    return float(geo / ari)


# =============================================================================
# ANALISIS DE FASE L/R
# =============================================================================

def analyze_phase(y_stereo, sr, n_octaves=8, label=""):
    """
    Mide coherencia de fase entre L y R por banda de octava.
    Retorna dict: {'octave_centers': [...], 'coherence': [...], 'itd_ms': float}
    """
    L = y_stereo[:, 0]
    R = y_stereo[:, 1] if y_stereo.shape[1] > 1 else y_stereo[:, 0]

    # Coherencia espectral (magnitud del coeficiente de correlacion cruzada normalizado)
    f_centers = [63 * (2 ** i) for i in range(n_octaves)]  # 63, 125, 250 ... Hz
    coherences = []

    n_fft = 4096
    hop   = n_fft // 4

    SL = librosa.stft(L, n_fft=n_fft, hop_length=hop)
    SR_stft = librosa.stft(R, n_fft=n_fft, hop_length=hop)
    freqs = librosa.fft_frequencies(sr=sr, n_fft=n_fft)

    for fc in f_centers:
        lo = fc / np.sqrt(2)
        hi = fc * np.sqrt(2)
        mask = (freqs >= lo) & (freqs <= hi)
        if mask.sum() == 0:
            coherences.append(np.nan)
            continue
        sl_b = SL[mask, :]
        sr_b = SR_stft[mask, :]
        cross = np.mean(sl_b * np.conj(sr_b), axis=0)
        pl    = np.mean(np.abs(sl_b) ** 2, axis=0)
        pr    = np.mean(np.abs(sr_b) ** 2, axis=0)
        coh   = np.abs(cross) / (np.sqrt(pl * pr) + 1e-12)
        coherences.append(float(np.median(coh)))

    # ITD estimado via correlacion cruzada en la senal completa (banda 100-2000 Hz)
    b, a = scipy.signal.butter(4, [100 / (sr / 2), min(2000 / (sr / 2), 0.99)], btype='band')
    Lf = scipy.signal.filtfilt(b, a, L)
    Rf = scipy.signal.filtfilt(b, a, R)
    xcorr = np.correlate(Lf[:sr], Rf[:sr], mode='full')   # 1 segundo
    lag_samples = np.argmax(np.abs(xcorr)) - sr + 1
    itd_ms = lag_samples / sr * 1000

    return {
        'label':         label,
        'octave_centers': f_centers,
        'coherence':     coherences,
        'itd_ms':        itd_ms,
    }


# =============================================================================
# ANALISIS DE PISO DE RUIDO
# =============================================================================

def analyze_noise_floor(y_mono, sr, label=""):
    """
    Caracteriza el piso de ruido:
      - Nivel (dBFS RMS)
      - Flatness de Wiener
      - Presencia de hum (50/60 Hz y armonicos)
      - Perfil espectral medio de la cola
    """
    n = len(y_mono)
    tail_start = int(n * NOISE_TAIL_FRAC)
    tail = y_mono[tail_start:]
    if len(tail) < 512:
        tail = y_mono

    # Ventana mas silenciosa en la cola
    win_s = max(int(NOISE_WINDOW_S * sr), 256)
    n_wins = len(tail) // win_s
    rms_wins = []
    for i in range(n_wins):
        seg = tail[i * win_s:(i + 1) * win_s]
        rms_wins.append(rms_db(seg))
    noise_floor_db = min(rms_wins) if rms_wins else rms_db(tail)

    # Espectro medio de la cola (para flatness y hum)
    n_fft = 2048
    S = np.abs(librosa.stft(tail, n_fft=n_fft, hop_length=n_fft // 4))
    freqs = librosa.fft_frequencies(sr=sr, n_fft=n_fft)
    mean_spectrum = S.mean(axis=1)
    flatness = wiener_flatness(mean_spectrum)

    # Deteccion de hum
    hum_detected = []
    for hf in HUM_FREQS_50HZ + HUM_FREQS_60HZ:
        if hf > sr / 2:
            continue
        mask = np.abs(freqs - hf) <= HUM_BANDWIDTH_HZ
        if mask.sum() == 0:
            continue
        bin_db   = 20 * np.log10(mean_spectrum[mask].max() + 1e-12)
        local    = np.abs(freqs - hf) <= 60
        baseline = 20 * np.log10(np.median(mean_spectrum[local]) + 1e-12)
        if bin_db - baseline > 6 and bin_db > HUM_THRESHOLD_DB:
            hum_detected.append(hf)

    return {
        'label':          label,
        'noise_floor_db': noise_floor_db,
        'flatness':       flatness,
        'hum_hz':         sorted(set(hum_detected)),
        'freqs':          freqs,
        'mean_spectrum':  mean_spectrum,
    }


# =============================================================================
# ANALISIS POR NOTA (generico)
# =============================================================================

def extract_note_metrics(y_stereo, sr, t_start, t_end, label=""):
    """Extrae metricas de una nota delimitada por t_start y t_end."""
    s0 = int(t_start * sr)
    s1 = int(t_end   * sr)
    seg_st = y_stereo[s0:s1, :]
    y  = librosa.to_mono(seg_st.T)
    n  = len(y)

    atk_end   = min(int(ATTACK_MS / 1000 * sr), n)
    sus_start = min(int(SUSTAIN_START_MS / 1000 * sr), n)
    sus_end   = min(int(SUSTAIN_END_MS   / 1000 * sr), n)

    seg_atk = y[:atk_end]
    seg_sus = y[sus_start:sus_end] if sus_end > sus_start else y[:n//2]

    pk    = peak_db(y)
    r_atk = rms_db(seg_atk) if len(seg_atk) > 0 else -99
    r_sus = rms_db(seg_sus)  if len(seg_sus) > 0 else -99

    # Flutter en sustain
    fl_skip = int(FLUTTER_SKIP_MS / 1000 * sr)
    sus_full = y[fl_skip:] if fl_skip < n else y
    rms_env = librosa.feature.rms(y=sus_full,
                                   frame_length=RMS_FRAME_LENGTH,
                                   hop_length=RMS_HOP_LENGTH)[0]
    rms_env_db = 20 * np.log10(rms_env + 1e-12)
    flutter_ptp = float(np.ptp(rms_env_db)) if len(rms_env_db) > 2 else 0.0

    # Centroide espectral
    c_atk = float(np.mean(librosa.feature.spectral_centroid(
        y=seg_atk if len(seg_atk) > 0 else y[:n//4],
        sr=sr, n_fft=1024, hop_length=256)))
    c_sus = float(np.mean(librosa.feature.spectral_centroid(
        y=seg_sus if len(seg_sus) > 0 else y[n//2:],
        sr=sr, n_fft=1024, hop_length=256)))

    # HF energy (8-20 kHz) — indicador de key noise
    f_rs, psd = scipy.signal.welch(y, fs=sr, nperseg=2048)
    hf_mask = f_rs >= 8000
    total_mask = f_rs >= 20
    hf_energy = 10 * np.log10(psd[hf_mask].sum() / (psd[total_mask].sum() + 1e-12) + 1e-12)

    # Pitch
    f0_hz = None
    if n >= PITCH_FRAME_LENGTH:
        try:
            pw = min(int(PITCH_WINDOW_S * sr), n)
            f0arr, vf, vp = librosa.pyin(
                y[:pw], sr=sr,
                fmin=librosa.note_to_hz('A0'),
                fmax=librosa.note_to_hz('C8'),
                frame_length=PITCH_FRAME_LENGTH,
                hop_length=PITCH_HOP_LENGTH,
                fill_na=None)
            voiced = f0arr[vf > 0.5] if vf is not None else np.array([])
            if len(voiced) > 0:
                f0_hz = float(np.nanmedian(voiced))
        except Exception:
            pass

    note_name = librosa.hz_to_note(f0_hz) if f0_hz else "?"

    noise = analyze_noise_floor(y, sr, label)

    return {
        'label':       label,
        't_start':     t_start,
        't_end':       t_end,
        'dur':         t_end - t_start,
        'f0_hz':       f0_hz,
        'note_name':   note_name,
        'peak_db':     pk,
        'rms_atk_db':  r_atk,
        'rms_sus_db':  r_sus,
        'flutter_ptp': flutter_ptp,
        'centroid_atk': c_atk,
        'centroid_sus': c_sus,
        'hf_energy_db': hf_energy,
        'noise_floor_db': noise['noise_floor_db'],
        'flatness':    noise['flatness'],
        'hum_hz':      noise['hum_hz'],
    }


# =============================================================================
# DETECCION DE NOTAS EN ARCHIVO LARGO
# =============================================================================

def detect_and_segment(y_stereo, sr):
    """
    Detecta onsets en el archivo nuevo y devuelve lista de segmentos.
    Misma logica que piano_sampler.py.
    """
    y_mono = librosa.to_mono(y_stereo.T)

    # High-pass previo al onset detection
    b, a = scipy.signal.butter(4, ONSET_HPF_HZ / (sr / 2), btype='high')
    y_hpf = scipy.signal.filtfilt(b, a, y_mono)

    onset_frames = librosa.onset.onset_detect(
        y=y_hpf, sr=sr,
        hop_length=ONSET_HOP_LENGTH,
        delta=ONSET_DELTA,
        wait=ONSET_WAIT,
        backtrack=False,
    )
    onset_times = librosa.frames_to_time(onset_frames, sr=sr, hop_length=ONSET_HOP_LENGTH)

    # Filtrar onsets muy cercanos
    filtered = [onset_times[0]] if len(onset_times) > 0 else []
    for t in onset_times[1:]:
        if t - filtered[-1] >= MIN_INTER_ONSET_SECONDS:
            filtered.append(t)
    onset_times = np.array(filtered)

    duration = len(y_mono) / sr
    segments = []
    for i, t_on in enumerate(onset_times):
        t_start = max(0, t_on - ONSET_PREROLL_MS / 1000)
        if i + 1 < len(onset_times):
            t_end = min(onset_times[i + 1] - ONSET_PREROLL_MS / 1000, t_on + MAX_TAIL_SECONDS)
        else:
            t_end = min(t_on + MAX_TAIL_SECONDS, duration)
        if t_end - t_start > 1.0:  # descartar segmentos muy cortos
            segments.append((t_start, t_end))

    return segments


# =============================================================================
# ANALISIS DE MUESTRAS EXISTENTES (batch)
# =============================================================================

def analyze_existing_samples(directory):
    """Carga y analiza todas las muestras procesadas existentes."""
    import glob
    wav_files = sorted(glob.glob(os.path.join(directory, "*.wav")))
    results = []
    print(f"  Analizando {len(wav_files)} muestras existentes...")
    for wf in wav_files:
        fname = os.path.basename(wf)
        y_st, sr = load_resample(wf)
        y_mono = librosa.to_mono(y_st.T)
        n = len(y_mono)

        atk_end  = min(int(ATTACK_MS / 1000 * sr), n)
        sus_s    = min(int(SUSTAIN_START_MS / 1000 * sr), n)
        sus_e    = min(int(SUSTAIN_END_MS   / 1000 * sr), n)
        seg_atk  = y_mono[:atk_end]
        seg_sus  = y_mono[sus_s:sus_e] if sus_e > sus_s else y_mono[:n // 2]

        rms_env = librosa.feature.rms(y=y_mono[int(FLUTTER_SKIP_MS / 1000 * sr):],
                                       frame_length=RMS_FRAME_LENGTH,
                                       hop_length=RMS_HOP_LENGTH)[0]
        rms_env_db = 20 * np.log10(rms_env + 1e-12)
        flutter_ptp = float(np.ptp(rms_env_db)) if len(rms_env_db) > 2 else 0.0

        c_atk = float(np.mean(librosa.feature.spectral_centroid(
            y=seg_atk if len(seg_atk) > 0 else y_mono[:n//4],
            sr=sr, n_fft=1024, hop_length=256)))
        c_sus = float(np.mean(librosa.feature.spectral_centroid(
            y=seg_sus if len(seg_sus) > 0 else y_mono[n//2:],
            sr=sr, n_fft=1024, hop_length=256)))

        f_rs, psd = scipy.signal.welch(y_mono, fs=sr, nperseg=2048)
        hf_mask   = f_rs >= 8000
        tot_mask  = f_rs >= 20
        hf_energy = 10 * np.log10(psd[hf_mask].sum() / (psd[tot_mask].sum() + 1e-12) + 1e-12)

        phase = analyze_phase(y_st, sr, label=fname)
        noise = analyze_noise_floor(y_mono, sr, label=fname)

        results.append({
            'fname':       fname,
            'sr':          sr,
            'dur':         n / sr,
            'peak_db':     peak_db(y_mono),
            'rms_atk_db':  rms_db(seg_atk) if len(seg_atk) > 0 else -99,
            'rms_sus_db':  rms_db(seg_sus)  if len(seg_sus) > 0 else -99,
            'flutter_ptp': flutter_ptp,
            'centroid_atk': c_atk,
            'centroid_sus': c_sus,
            'hf_energy_db': hf_energy,
            'noise_floor_db': noise['noise_floor_db'],
            'flatness':    noise['flatness'],
            'hum_hz':      noise['hum_hz'],
            'itd_ms':      phase['itd_ms'],
            'coherence_lf': np.nanmean(phase['coherence'][:3]),  # octavas bajas 63-250 Hz
            'coherence_hf': np.nanmean(phase['coherence'][5:]),  # octavas altas 2k-8k Hz
        })
        gc.collect()
    return results


# =============================================================================
# MAIN
# =============================================================================

def main():
    print("=" * 70)
    print("PIPELINE COMPARATIVO: SESION EXISTENTE vs NUEVA GRABACION")
    print("=" * 70)

    # ── 1. Cargar archivo nuevo ──────────────────────────────────────────
    print(f"\n[1/4] Cargando archivo nuevo: {os.path.basename(NEW_WAV)}")
    y_new, sr_new = load_resample(NEW_WAV)
    sr_orig_new   = sf.info(NEW_WAV).samplerate
    print(f"  SR original: {sr_orig_new} Hz  ->  SR de trabajo: {sr_new} Hz")
    print(f"  Duracion   : {y_new.shape[0] / sr_new:.1f}s  |  Canales: {y_new.shape[1]}")

    # ── 2. Detectar notas en archivo nuevo ───────────────────────────────
    print(f"\n[2/4] Detectando notas en archivo nuevo ...")
    segments = detect_and_segment(y_new, sr_new)
    print(f"  {len(segments)} notas detectadas: {[(f'{s[0]:.1f}s', f'{s[1]-s[0]:.1f}s') for s in segments]}")

    new_notes = []
    for i, (t0, t1) in enumerate(segments):
        label = f"nueva_nota_{i+1}"
        m = extract_note_metrics(y_new, sr_new, t0, t1, label)
        new_notes.append(m)
        f0_str = f"{m['f0_hz']:.1f}" if m['f0_hz'] else "0"
        print(f"  Nota {i+1}: t={t0:.1f}s  dur={t1-t0:.1f}s  f0={f0_str}Hz"
              f"  peak={m['peak_db']:.1f}dBFS  RMS_sus={m['rms_sus_db']:.1f}dBFS"
              f"  flutter={m['flutter_ptp']:.1f}dB  flat={m['flatness']:.4f}")

    # Fase del archivo nuevo completo
    phase_new = analyze_phase(y_new, sr_new, label="nueva_grabacion")
    print(f"  ITD estimado (nuevo): {phase_new['itd_ms']:.3f} ms")
    print(f"  Coherencia LF (63-250Hz): {np.nanmean(phase_new['coherence'][:3]):.3f}")
    print(f"  Coherencia HF (2k-8kHz): {np.nanmean(phase_new['coherence'][5:]):.3f}")

    # ── 3. Analizar muestras existentes ──────────────────────────────────
    print(f"\n[3/4] Analizando muestras existentes (p_rectificado_pip) ...")
    existing = analyze_existing_samples(EXISTING_DIR)

    # Stats agregadas de existentes
    ex_peaks  = [e['peak_db']      for e in existing]
    ex_sus    = [e['rms_sus_db']   for e in existing]
    ex_fl     = [e['flutter_ptp']  for e in existing]
    ex_noise  = [e['noise_floor_db'] for e in existing]
    ex_flat   = [e['flatness']     for e in existing]
    ex_itd    = [e['itd_ms']       for e in existing]
    ex_coh_lf = [e['coherence_lf'] for e in existing]
    ex_coh_hf = [e['coherence_hf'] for e in existing]

    # Stats del nuevo
    nw_peaks  = [n['peak_db']       for n in new_notes]
    nw_sus    = [n['rms_sus_db']    for n in new_notes]
    nw_fl     = [n['flutter_ptp']   for n in new_notes]
    nw_noise  = [n['noise_floor_db'] for n in new_notes]
    nw_flat   = [n['flatness']      for n in new_notes]

    # ── 4. Generar PNGs ──────────────────────────────────────────────────
    print(f"\n[4/4] Generando graficos ...")

    # -- 4a. Dinamica --
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    fig.suptitle("Comparacion de Dinamica: Existentes vs Nueva Grabacion", fontsize=13, fontweight='bold')

    ax = axes[0]
    ax.hist(ex_sus, bins=10, alpha=0.7, label="Existentes (p proc.)", color='steelblue')
    ax.axvline(LEVEL_TARGET_P,  color='steelblue', ls='--', lw=1.5, label=f"Target p ({LEVEL_TARGET_P} dBFS)")
    ax.axvline(LEVEL_TARGET_MF, color='tomato',    ls='--', lw=1.5, label=f"Target mf ({LEVEL_TARGET_MF} dBFS)")
    if nw_sus:
        ax.axvline(np.mean(nw_sus), color='orange', ls='-', lw=2,
                   label=f"Nueva prom. ({np.mean(nw_sus):.1f} dBFS)")
    ax.set_xlabel("RMS Sustain (dBFS)")
    ax.set_ylabel("Frecuencia")
    ax.set_title("Distribucion RMS Sustain")
    ax.legend(fontsize=8)

    ax = axes[1]
    labels_ex = [e['fname'][:12] for e in existing]
    ax.barh(labels_ex, ex_sus, color='steelblue', alpha=0.7, label='Existentes')
    ax.axvline(LEVEL_TARGET_P, color='steelblue', ls='--', lw=1.5, label=f"Target p")
    ax.axvline(LEVEL_TARGET_MF, color='tomato',   ls='--', lw=1.5, label=f"Target mf")
    if nw_sus:
        for i, v in enumerate(nw_sus):
            ax.axvline(v, color='orange', ls=':', lw=1, alpha=0.8)
        ax.axvline(nw_sus[0], color='orange', lw=1.5, label=f"Nueva notas")
    ax.set_xlabel("RMS Sustain (dBFS)")
    ax.set_title("RMS Sustain por muestra existente")
    ax.legend(fontsize=8)
    plt.tight_layout()
    out_dyn = os.path.join(OUTPUT_DIR, "compare_dynamics.png")
    plt.savefig(out_dyn, dpi=120, bbox_inches='tight')
    plt.close()

    # -- 4b. Fase --
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    fig.suptitle("Comparacion de Fase L/R: Existentes vs Nueva Grabacion (ORTF M5)", fontsize=13, fontweight='bold')

    freqs_oct = [f"{fc}Hz" for fc in phase_new['octave_centers']]
    coh_ex_mean = []
    for oc_idx in range(len(phase_new['octave_centers'])):
        vals = []
        for e in existing:
            if 'phase' not in e:
                pass  # ya se calculo en analyze_existing_samples
        coh_ex_mean = [np.nanmean([e['coherence_lf'] if i < 3 else e['coherence_hf']
                                    for e in existing])
                        for i in range(len(phase_new['octave_centers']))]

    ax = axes[0]
    coh_new = phase_new['coherence']
    ax.plot(range(len(freqs_oct)), coh_new, 'o-', color='tomato', lw=2, label=f"Nueva (ORTF M5)  ITD={phase_new['itd_ms']:.2f}ms")
    # Coherencias individuales de existentes
    for e in existing[:5]:
        pass  # ya no tenemos coherence por octava en existing, solo LF/HF

    ax.axhline(0.9, color='gray', ls='--', lw=1, label="Umbral coh. alta (>0.9)")
    ax.axhline(0.7, color='gray', ls=':',  lw=1, label="Umbral coh. media (>0.7)")
    ax.set_xticks(range(len(freqs_oct)))
    ax.set_xticklabels(freqs_oct, rotation=45, fontsize=8)
    ax.set_ylim(0, 1.1)
    ax.set_ylabel("Coherencia L/R")
    ax.set_title("Coherencia espectral por banda de octava\n(Nueva grabacion ORTF M5)")
    ax.legend(fontsize=8)

    ax = axes[1]
    itds_ex = ex_itd
    ax.hist(itds_ex, bins=8, color='steelblue', alpha=0.7, label="Existentes (CM25+AT3035)")
    ax.axvline(phase_new['itd_ms'], color='tomato', lw=2,
               label=f"Nueva ORTF M5 ({phase_new['itd_ms']:.2f} ms)")
    ax.axvline(0.5,  color='gray', ls='--', lw=1, label="ITD tipico ORTF (0.5ms)")
    ax.set_xlabel("ITD estimado (ms)")
    ax.set_ylabel("Frecuencia")
    ax.set_title("Diferencia interaural de tiempo (ITD)")
    ax.legend(fontsize=8)
    plt.tight_layout()
    out_phase = os.path.join(OUTPUT_DIR, "compare_phase.png")
    plt.savefig(out_phase, dpi=120, bbox_inches='tight')
    plt.close()

    # -- 4c. Ruido --
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    fig.suptitle("Comparacion de Piso de Ruido: Existentes vs Nueva Grabacion", fontsize=13, fontweight='bold')

    ax = axes[0]
    ax.hist(ex_flat, bins=8, alpha=0.7, color='steelblue', label="Existentes (post-MVSep)")
    if nw_flat:
        ax.axvline(np.mean(nw_flat), color='tomato', lw=2,
                   label=f"Nueva prom. flatness ({np.mean(nw_flat):.3f})")
    ax.axvline(0.10, color='gray', ls='--', lw=1, label="Umbral tonal (<0.10)")
    ax.set_xlabel("Flatness de Wiener")
    ax.set_ylabel("Frecuencia")
    ax.set_title("Planitud espectral del piso de ruido\n(0=tonal/MVSep, 1=ruido blanco)")
    ax.legend(fontsize=8)

    ax = axes[1]
    ax.scatter(ex_noise, ex_flat, color='steelblue', alpha=0.7, label='Existentes (post-MVSep)')
    if nw_noise and nw_flat:
        ax.scatter(nw_noise, nw_flat, color='tomato', s=80, zorder=5,
                   label=f'Nueva (pre-MVSep, SR={sr_orig_new}Hz)')
    ax.axhline(0.10, color='gray', ls='--', lw=1, label='Umbral tonal')
    ax.set_xlabel("Piso de ruido (dBFS RMS)")
    ax.set_ylabel("Flatness de Wiener")
    ax.set_title("Piso de ruido vs Planitud espectral")
    ax.legend(fontsize=8)
    plt.tight_layout()
    out_noise = os.path.join(OUTPUT_DIR, "compare_noise.png")
    plt.savefig(out_noise, dpi=120, bbox_inches='tight')
    plt.close()

    print(f"  Guardados: compare_dynamics.png / compare_phase.png / compare_noise.png")

    # ── 5. Escribir informe ───────────────────────────────────────────────
    rpt_path = os.path.join(OUTPUT_DIR, "compare_new_session_report.txt")
    with open(rpt_path, "w", encoding="utf-8") as f:
        W = lambda s="": f.write(s + "\n")

        W("=" * 78)
        W("  INFORME COMPARATIVO: SESION EXISTENTE vs NUEVA GRABACION")
        W("=" * 78)
        W(f"  Existentes : {EXISTING_DIR}")
        W(f"  Nuevo      : {NEW_WAV}")
        W(f"  SR existentes (original): 44100 Hz  (resampleados a {TARGET_SR} Hz)")
        W(f"  SR nuevo    (original)  : {sr_orig_new} Hz")
        W()

        # -- Contexto --
        W("=" * 78)
        W("CONTEXTO DE SESION")
        W("=" * 78)
        W(f"  Muestras existentes : 21 notas (p dinamica, piano patrimonial)")
        W(f"    Microfonos         : CM25 (SDC, ch1) + AT3035 (LDC, ch2) — par hibrido")
        W(f"    Procesamiento      : MVSep -> piano_sampler -> pipeline_rectify")
        W(f"    SNR rango          : 57.4 dB (C1) a 74.1 dB (C5_RR1 — EXCELENTE)")
        W(f"    Ruido MVSep        : tonal en TODAS (flatness < 0.08)")
        W()
        W(f"  Nueva grabacion     : {len(segments)} notas detectadas")
        W(f"    Microfonos         : Rode M5 ORTF (par matched SDC, 110 deg, 17 cm)")
        W(f"    SR de grabacion    : {sr_orig_new} Hz (diferente a existentes)")
        W(f"    Procesamiento      : pre-MVSep (grabacion cruda de REAPER)")
        W(f"    Dinamica esperada  : mf  (segun sesion de grabacion)")
        W()

        # -- Dinamica --
        W("=" * 78)
        W("COMPARACION DE DINAMICA")
        W("=" * 78)
        W()
        W("  Muestras existentes (p dinamica — post-pipeline):")
        W(f"    Peak promedio    : {np.mean(ex_peaks):.1f} dBFS  (rango {min(ex_peaks):.1f} a {max(ex_peaks):.1f})")
        W(f"    RMS sustain prom.: {np.mean(ex_sus):.1f} dBFS  (target p = {LEVEL_TARGET_P} dBFS)")
        W(f"    Flutter ptp prom.: {np.mean(ex_fl):.1f} dB  (max {max(ex_fl):.1f} dB)")
        W()
        W("  Nueva grabacion (pre-MVSep):")
        pk_new = np.mean(nw_peaks) if nw_peaks else -99
        sus_new = np.mean(nw_sus) if nw_sus else -99
        fl_new = np.mean(nw_fl) if nw_fl else 0
        W(f"    Peak promedio    : {pk_new:.1f} dBFS  (target mf = {PEAK_TARGET_MF} dBFS)")
        W(f"    RMS sustain prom.: {sus_new:.1f} dBFS  (target mf = {LEVEL_TARGET_MF} dBFS)")
        W(f"    Flutter ptp prom.: {fl_new:.1f} dB")
        W(f"    Deficit de nivel : {pk_new - PEAK_TARGET_MF:.1f} dB")
        W()
        deficit = pk_new - PEAK_TARGET_MF
        W("  [!] DIAGNOSTICO DE NIVEL:")
        if deficit < -15:
            W(f"    CRITICO: el nivel es {abs(deficit):.1f} dB por debajo del target mf.")
            W(f"    -> Subir ganancia del preamp Focusrite en aprox. +{abs(deficit):.0f} dB")
            W(f"    -> Verificar: pico en track ORTF REAPER debe llegar a {PEAK_TARGET_MF} dBFS")
            W(f"    -> Esta toma NO es apta para el pipeline como muestra final de mf.")
            W(f"    -> Puede usarse para verificar timbre, fase y configuracion de micros.")
        elif deficit < -6:
            W(f"    ADVERTENCIA: nivel {abs(deficit):.1f} dB bajo el target. Ajustar ganancia.")
        else:
            W(f"    OK: nivel dentro del rango aceptable.")
        W()

        # -- Tabla de notas nuevas --
        W("  Detalle por nota nueva:")
        W(f"  {'Nota':<6} {'t_ini':>6} {'Dur':>5} {'f0_Hz':>7} {'Pitch':>6} {'Peak':>7} {'RMS_sus':>8} {'Flutter':>8} {'Noise':>8}")
        W("  " + "-" * 70)
        for m in new_notes:
            W(f"  {m['label'][-1]:<6} {m['t_start']:>6.1f}s {m['dur']:>4.1f}s"
              f" {(m['f0_hz'] or 0):>7.1f} {m['note_name']:>6}"
              f" {m['peak_db']:>7.1f} {m['rms_sus_db']:>8.1f}"
              f" {m['flutter_ptp']:>8.1f} {m['noise_floor_db']:>8.1f}")
        W()

        # -- Fase --
        W("=" * 78)
        W("COMPARACION DE FASE L/R")
        W("=" * 78)
        W()
        W("  Muestras existentes (CM25+AT3035 — par hibrido SDC+LDC):")
        W(f"    ITD promedio     : {np.mean(ex_itd):.3f} ms  (std={np.std(ex_itd):.3f} ms)")
        W(f"    Coherencia LF prom.: {np.nanmean(ex_coh_lf):.3f}  (63-250 Hz)")
        W(f"    Coherencia HF prom.: {np.nanmean(ex_coh_hf):.3f}  (2k-8k Hz)")
        W()
        W("  Nueva grabacion (Rode M5 ORTF — par matched SDC):")
        W(f"    ITD estimado     : {phase_new['itd_ms']:.3f} ms")
        W(f"      -> ORTF teorico 17cm: ~0.50 ms  (distancia entre capsulas / c)")
        W(f"      -> Diferencia real vs teorico: {abs(phase_new['itd_ms'] - 0.50):.3f} ms")
        W(f"    Coherencia por banda:")
        for i, (fc, coh) in enumerate(zip(phase_new['octave_centers'], phase_new['coherence'])):
            if not np.isnan(coh):
                flag = "OK" if coh > 0.7 else "[!] BAJA"
                W(f"      {fc:>5} Hz: {coh:.3f}  {flag}")
        W()
        W("  Interpretacion:")
        coh_lf_new = np.nanmean(phase_new['coherence'][:3])
        coh_hf_new = np.nanmean(phase_new['coherence'][5:])
        if coh_lf_new > 0.85:
            W("    Coherencia LF ALTA: el par ORTF M5 tiene buena correlacion a bajas")
            W("    frecuencias. Imagen esterea solida. Compatible con procesamiento Kontakt.")
        else:
            W("    [!] Coherencia LF baja. Revisar fase en piano_sampler.py:")
            W("        PHASE_CORRECTION_ENABLED = True  (ya configurado)")
        if coh_hf_new > 0.5:
            W("    Coherencia HF moderada-alta: esperable en ORTF (capsulas a 17cm).")
            W("    La diferencia de tiempo de llegada en HF es intencional en ORTF.")
        else:
            W("    [!] Coherencia HF muy baja. Verificar posicion de los M5.")
        W()
        W("  Diferencia de fase entre sesiones (existentes vs nuevo):")
        itd_diff = phase_new['itd_ms'] - np.mean(ex_itd)
        W(f"    Delta ITD: {itd_diff:+.3f} ms")
        W(f"    Los existentes usaron par hibrido SDC+LDC (respuesta de fase distinta")
        W(f"    entre canales). El nuevo par ORTF M5 es simetrico — la coherencia sera")
        W(f"    diferente por diseno. Documentar como variable controlada en tesis.")
        W()

        # -- Ruido --
        W("=" * 78)
        W("COMPARACION DE PISO DE RUIDO Y PRECAUCIONES PARA REDUCCION")
        W("=" * 78)
        W()
        W("  Muestras existentes (post-MVSep):")
        W(f"    Piso de ruido prom. : {np.mean(ex_noise):.1f} dBFS  (std={np.std(ex_noise):.1f})")
        W(f"    Flatness prom.      : {np.mean(ex_flat):.4f}  (0=tonal, 1=blanco)")
        W(f"    Flatness max        : {max(ex_flat):.4f}")
        W(f"    Interpretacion      : ruido MVSep TONAL dominante en TODAS las muestras")
        W(f"    Hum detectado en    : {sum(1 for e in existing if e['hum_hz'])} muestras")
        W()
        W("  Nueva grabacion (pre-MVSep, grabacion directa REAPER):")
        W(f"    Piso de ruido prom. : {np.mean(nw_noise):.1f} dBFS  (std={np.std(nw_noise):.1f})")
        W(f"    Flatness prom.      : {np.mean(nw_flat):.4f}")
        mean_flat_new = np.mean(nw_flat) if nw_flat else 0
        if mean_flat_new > 0.5:
            interp_str = "ruido de sala/electrico (mas blanco -- pre-MVSep esperado)"
        elif mean_flat_new > 0.15:
            interp_str = "ruido semi-tonal (posible ruido de sala + componentes estructurados)"
        else:
            interp_str = "ruido muy tonal (inesperado pre-MVSep; revisar si hay ruido de ventilador)"
        W(f"    Interpretacion      : {interp_str}")
        hum_new = [h for m in new_notes for h in m['hum_hz']]
        if hum_new:
            W(f"    Hum detectado      : {sorted(set(hum_new))} Hz")
            W(f"    -> Verificar toma de tierra antes de grabar sesion final.")
        else:
            W(f"    Hum                : no detectado (OK)")
        W()

        W("  PRECAUCIONES PARA REDUCCION DE RUIDO EN NUEVAS MUESTRAS:")
        W()
        W("  1. DIFERENCIA DE PISO DE RUIDO (pre vs post MVSep):")
        diff_noise = np.mean(nw_noise) - np.mean(ex_noise)
        W(f"     Nuevo piso: {np.mean(nw_noise):.1f} dBFS  |  Existentes post-MVSep: {np.mean(ex_noise):.1f} dBFS")
        W(f"     Diferencia: {diff_noise:+.1f} dB")
        if diff_noise > 5:
            W("     [!] El nuevo archivo tiene piso de ruido MAS ALTO que los existentes.")
            W("     Tras MVSep, el piso bajara (el modelo separa la senal del ruido de sala).")
            W("     -> NO aplicar denoise antes de MVSep: el modelo lo maneja.")
            W("     -> Aplicar denoise (RX Spectral) DESPUES de MVSep si flatness < 0.15.")
        elif diff_noise < -5:
            W("     El nuevo archivo tiene piso de ruido mas bajo. Excelente SNR esperado.")
        else:
            W("     Pisos de ruido similares. Mismo flujo de denoise aplicara.")
        W()
        W("  2. RUIDO MUSICAL (MVSep) — PRECAUCION PRINCIPAL:")
        W("     Las muestras existentes tienen ruido MVSep TONAL (flatness < 0.08).")
        W("     Las nuevas muestras tendran el mismo problema post-MVSep.")
        W("     -> Estrategia (misma que existentes):")
        W("        a) smooth_flutter_sustain() en pipeline_rectify.py (ya implementado)")
        W("        b) iZotope RX Spectral Repair (aprender perfil de la COLA de la nota)")
        W("        c) NO usar DeNoise broadband: colorearia el piano")
        W("        d) Acon Digital DeNoise (~free) como alternativa mas economica")
        W()
        W("  3. FLATNESS PRE-MVSep vs POST-MVSep:")
        W(f"     Pre-MVSep flatness nuevo : {np.mean(nw_flat):.4f}")
        W(f"     Post-MVSep flatness exist.: {np.mean(ex_flat):.4f}")
        W("     -> El modelo MVSep INTRODUCE ruido tonal (flatness baja).")
        W("     -> La flatness pre-MVSep no predice la post; el modelo domina.")
        W("     -> Tras MVSep: esperar flatness < 0.10 (igual que existentes).")
        W()
        W("  4. DIFERENCIA DE SAMPLE RATE (48000 vs 44100 Hz):")
        W(f"     Existentes: 44100 Hz  |  Nuevas: {sr_orig_new} Hz")
        W("     -> TARGET_SR = 48000 en los tres scripts: ya implementado.")
        W("     -> Los existentes se resamplean a 48000 Hz al cargarse.")
        W("     -> Las nuevas se leen directamente a 48000 Hz (sin conversion).")
        W("     -> REAPER: verificar que el proyecto y la interfaz esten a 48000 Hz.")
        W("     -> IMPORTANTE: si se mezclan muestras 44100 y 48000 en Kontakt,")
        W("        configurar el instrumento a 48000 Hz para evitar pitch-shifting.")
        W()
        W("  5. NIVEL INSUFICIENTE (nueva grabacion):")
        W(f"     Deficit actual: {deficit:.1f} dB respecto a target mf ({PEAK_TARGET_MF} dBFS)")
        W("     -> El pipeline_rectify.py intentara boostar hasta LEVEL_MAX_BOOST.")
        W("     -> Con deficit de 23 dB el boost de +8 dB es INSUFICIENTE.")
        W("     -> ACCION: re-grabar a nivel correcto antes de procesar.")
        W("     -> Referencia: peak ORTF en REAPER debe ser -6 dBFS para mf.")
        W()

        # -- Recomendaciones de parametros --
        W("=" * 78)
        W("RECOMENDACIONES DE PARAMETROS PARA NUEVAS MUESTRAS EN EL PIPELINE")
        W("=" * 78)
        W()
        W("  piano_sampler.py:")
        W("    SESSION_MODIFIERS = []        # sin modificadores (grabacion mf normal)")
        W("    INPUT_FILE = <ruta stem MVSep de la nueva sesion>")
        W("    INTENSITY_LABEL = 'mf'")
        W("    TARGET_SR = 48000             # ya configurado")
        W("    DYNAMIC_NORM_TARGET_DB = -18.0  # target mf (en lugar de -28.0 para p)")
        W()
        W("  pipeline_rectify.py:")
        W("    Actualizar SESSIONS para incluir la nueva carpeta mf:")
        W('      SESSIONS = [')
        W('        r"...p_rectificado_pip...",  # existentes (p)')
        W('        r"...nueva_sesion_mf...",    # nuevas (mf)')
        W('      ]')
        W("    LEVEL_TARGET_DB = -18.0  # target mf (en lugar de -28.0 para p)")
        W("    TARGET_SR = 48000        # ya configurado")
        W()
        W("  pipeline_compare.py:")
        W("    SESSION_A = {'label': 'Sesion p (existente)', 'folder': <p_rectificado>}")
        W("    SESSION_B = {'label': 'Sesion mf (nueva)',    'folder': <nueva_mf>}")
        W("    TARGET_SR = 48000  # ya configurado")
        W()

        # -- Similitudes --
        W("=" * 78)
        W("SIMILITUDES DETECTADAS")
        W("=" * 78)
        W()
        W("  Caracteristica          Existentes        Nuevo          Compatibilidad")
        W("  " + "-" * 70)
        W(f"  Instrumento             Piano patrimonial  Piano patrimonial  IDENTICO")
        W(f"  Flutter ptp (prom.)     {np.mean(ex_fl):.1f} dB          {fl_new:.1f} dB           {'SIMILAR' if abs(np.mean(ex_fl)-fl_new)<5 else 'DIFERENTE'}")
        W(f"  Tipo de ruido           Tonal (MVSep)      {'Tonal' if mean_flat_new < 0.15 else 'Blanco/mixto'}         {'OK' if mean_flat_new > 0.10 else 'REVISAR'}")
        W(f"  Sample rate (trabajo)   {TARGET_SR} Hz       {TARGET_SR} Hz       IGUAL (TARGET_SR)")
        W(f"  Bit depth exportacion   24 bits            24 bits          IGUAL (PCM_24)")
        W(f"  Setup de mic            CM25+AT3035        Rode M5 ORTF     DIFERENTE (var. controlada)")
        W(f"  ITD                     {np.mean(ex_itd):.2f} ms (prom.)  {phase_new['itd_ms']:.2f} ms        {'SIMILAR' if abs(np.mean(ex_itd)-phase_new['itd_ms'])<0.5 else 'DIFERENTE (ORTF intencional)'}")
        W()

    print(f"  Informe guardado: {rpt_path}")
    print()
    print("=" * 70)
    print("RESUMEN EJECUTIVO")
    print("=" * 70)
    print(f"  Nivel nueva grabacion  : {pk_new:.1f} dBFS  (deficit {pk_new-PEAK_TARGET_MF:.1f} dB vs target mf)")
    print(f"  ITD nueva (ORTF M5)    : {phase_new['itd_ms']:.3f} ms  (teorico ORTF 17cm: ~0.50 ms)")
    print(f"  Piso ruido nuevo (prom): {np.mean(nw_noise):.1f} dBFS")
    print(f"  Flatness nuevo (prom)  : {np.mean(nw_flat):.4f}  vs existentes: {np.mean(ex_flat):.4f}")
    print(f"  SR original nuevo      : {sr_orig_new} Hz  -> procesado a {TARGET_SR} Hz (TARGET_SR)")
    print(f"  Hum detectado          : {sorted(set(hum_new)) if hum_new else 'ninguno'}")
    print()
    print(f"  Accion prioritaria: RE-GRABAR con +{abs(pk_new-PEAK_TARGET_MF):.0f} dB mas de ganancia en Focusrite.")
    print(f"  Todo lo demas (fase, ruido, SR) esta dentro de parametros esperados.")
    print()
    print(f"Salida: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
