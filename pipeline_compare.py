# -*- coding: utf-8 -*-
"""
pipeline_compare.py
-------------------
Pipeline de consistencia cruzada entre sesiones de muestreo de piano.

Compara todos los samples exportados de dos sesiones procesadas con
piano_sampler.py y detecta inconsistencias en:
  - Nivel dinamico (curva de velocidad a traves del teclado)
  - Flutter / fluctuacion de sustain (batimiento entre cuerdas)
  - Ruido de tecla (energia HF en el ataque)
  - Caracter espectral (desplazamiento de centroide ataque vs sustain)
  - Duracion de decay por registro
  - Solapamiento C4 (nota presente en ambas sesiones)

Genera:
  compare_report.txt      Tabla completa + flags de inconsistencia
  compare_overview.png    4 paneles: nivel / flutter / ruido tecla / duracion
  compare_C4_overlap.png  Comparacion directa del C4 de ambas sesiones
  compare_level_curve.png Curva de nivel vs MIDI con tendencia esperada
"""

import os
import re
import numpy as np
import scipy.signal
import librosa
import soundfile as sf

# =============================================================================
# CONFIGURACION
# =============================================================================

SESSION_A = {
    "label": "Sesion 01  (C1-C4)",
    "folder": r"D:\Sesiones y proyectos\SESION 29-8\Pruebas de rendimiento denoise\Output_Samples\p\piano-model_mt_2_piano",
}
SESSION_B = {
    "label": "Sesion 02  (B0, C4-C7)",
    "folder": r"D:\Sesiones y proyectos\SESION 29-8\Pruebas de rendimiento denoise\Output_Samples\p\proyecto-balance-tesis-002_piano-model_mt_2_piano",
}

OUTPUT_DIR = r"D:\Sesiones y proyectos\SESION 29-8\Pruebas de rendimiento denoise\Output_Samples\compare"
TARGET_SR  = 48000       # sample rate objetivo; archivos a distinto SR se resamplean al cargar

# =============================================================================
# METADATA DE SETUP DE MICROFONOS POR SESION
# Documenta el hardware para cuantificar diferencias timbricas entre sesiones.
# Hallazgo metodologico: sesiones p/ff usan par hibrido SDC+LDC (CM25+AT3035);
# nuevas dinamicas (mp, mf, f) usaran par matched SDC (Rode M5 ORTF).
# La diferencia timbrica es una variable controlada documentada en la tesis.
# =============================================================================

SESSION_METADATA = {
    "sesion_01": {
        "label":            SESSION_A["label"],
        "microfono_L":      "CM25",
        "microfono_R":      "AT3035",
        "tipo_par":         "hibrido_SDC_LDC",
        "EIN_promedio_dBA": 19.5,
        "posicion":         "no documentada",
        "folder":           SESSION_A["folder"],
    },
    "sesion_02": {
        "label":            SESSION_B["label"],
        "microfono_L":      "CM25",
        "microfono_R":      "AT3035",
        "tipo_par":         "hibrido_SDC_LDC",
        "EIN_promedio_dBA": 19.5,
        "posicion":         "no documentada",
        "folder":           SESSION_B["folder"],
    },
    "sesion_M5": {
        "label":            "Sesion M5 (futuras sesiones mp/mf/f)",
        "microfono_L":      "Rode_M5",
        "microfono_R":      "Rode_M5",
        "tipo_par":         "matched_SDC_ORTF",
        "EIN_promedio_dBA": 19.0,
        "posicion":         "ORTF 40-50cm sobre marco, apuntando cuerdas medias",
        "folder":           None,   # carpeta a asignar cuando existan grabaciones M5
    },
}


def parse_filename_modifiers(filename):
    """
    Detecta modificadores _UNA (una corda) y _SP (sin pedal) en un nombre de archivo.
    Retorna dict {'una_corda': bool, 'sin_pedal': bool}.
    """
    base = os.path.splitext(os.path.basename(filename))[0].upper()
    return {
        "una_corda": "_UNA" in base,
        "sin_pedal": "_SP"  in base,
    }


def get_session_metadata(folder):
    """Busca la metadata de setup de microfonos para una carpeta dada."""
    for meta in SESSION_METADATA.values():
        if meta.get("folder") == folder:
            return meta
    return None

# Parametros de analisis (deben coincidir con piano_sampler.py)
RMS_FRAME_LENGTH    = 2048
RMS_HOP_LENGTH      = 512
SAVGOL_WINDOW       = 51
SAVGOL_POLY         = 3

ATTACK_MS           = 50      # ventana de ataque para analisis espectral
SUSTAIN_START_MS    = 200     # inicio ventana de sustain (post-ataque)
SUSTAIN_END_MS      = 700     # fin ventana de sustain
FLUTTER_SKIP_MS     = 400     # ms a saltar antes del analisis de flutter
KEY_NOISE_SHELF_HZ  = 8000    # frecuencia de corte para energia HF

# Umbrales de inconsistencia
LEVEL_INCONSISTENCY_DB   = 4.0   # desviacion del nivel respecto a tendencia
FLUTTER_WARN_DB          = 5.0   # flutter moderado
FLUTTER_CRITICAL_DB      = 10.0  # flutter critico
REEMERGENCE_FLAG         = 1     # cualquier re-emergencia = flag
LEVEL_CROSS_SESSION_DB   = 3.0   # diferencia entre sesiones para la misma nota
HF_WARN_DB               = -42.0 # energia HF en ataque sobre este umbral = advertencia
DECAY_RATIO_TOLERANCE    = 0.35  # tolerancia en curva de decay esperada (fraccion)

PITCH_WINDOW_S      = 0.5
PITCH_FRAME_LENGTH  = 4096
PITCH_HOP_LENGTH    = 512


# =============================================================================
# EXTRACCION DE METRICAS POR NOTA
# =============================================================================

def extract_metrics(wav_path):
    """
    Carga un WAV y extrae todas las metricas de calidad.

    Returns dict con:
        path, filename, midi, f0_hz, duration,
        rms_attack_db, rms_sustain_db,
        centroid_attack, centroid_sustain, centroid_delta,
        hf_energy_db,
        flutter_ptp_db, reemergence_count
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

    atk_end   = int(ATTACK_MS / 1000 * sr)
    sus_start = int(SUSTAIN_START_MS / 1000 * sr)
    sus_end   = int(SUSTAIN_END_MS   / 1000 * sr)
    fl_skip   = int(FLUTTER_SKIP_MS  / 1000 * sr)

    seg_atk = y[:atk_end]
    seg_sus = y[sus_start : min(sus_end, n)]

    # --- f0 ---
    f0_hz = None
    pw = int(PITCH_WINDOW_S * sr)
    if n >= PITCH_FRAME_LENGTH:
        try:
            f0_arr, vf, vp = librosa.pyin(
                y[:min(pw, n)], sr=sr,
                fmin=librosa.note_to_hz('A0'),
                fmax=librosa.note_to_hz('C8'),
                frame_length=PITCH_FRAME_LENGTH,
                hop_length=PITCH_HOP_LENGTH,
                fill_na=None,
            )
            valid = vf & ~np.isnan(f0_arr)
            if np.any(valid):
                f0_hz = float(np.average(f0_arr[valid], weights=vp[valid]))
        except Exception:
            pass

    midi = int(round(librosa.hz_to_midi(f0_hz))) if f0_hz else None

    # --- RMS ataque y sustain ---
    rms_atk = float(np.sqrt(np.mean(seg_atk ** 2))) if len(seg_atk) > 0 else 1e-9
    rms_sus = float(np.sqrt(np.mean(seg_sus ** 2))) if len(seg_sus) > 128 else 1e-9
    rms_atk_db = 20 * np.log10(max(rms_atk, 1e-9))
    rms_sus_db = 20 * np.log10(max(rms_sus, 1e-9))

    # --- Centroide espectral ataque y sustain ---
    def safe_centroid(seg):
        if len(seg) < 512:
            return None
        return float(np.mean(
            librosa.feature.spectral_centroid(y=seg, sr=sr, n_fft=1024, hop_length=256)
        ))

    sc_atk = safe_centroid(seg_atk)
    sc_sus = safe_centroid(seg_sus)
    centroid_delta = (sc_atk - sc_sus) if (sc_atk and sc_sus) else None

    # --- Energia HF en ataque (> KEY_NOISE_SHELF_HZ) ---
    hf_energy_db = None
    if len(seg_atk) >= 512:
        D_atk  = np.abs(librosa.stft(seg_atk, n_fft=1024, hop_length=256)) ** 2
        freqs  = librosa.fft_frequencies(sr=sr, n_fft=1024)
        s_bin  = int(np.searchsorted(freqs, KEY_NOISE_SHELF_HZ))
        e_tot  = float(np.sum(D_atk)) + 1e-12
        e_hf   = float(np.sum(D_atk[s_bin:, :]))
        hf_energy_db = 10 * np.log10(e_hf / e_tot + 1e-12)

    # --- Flutter (varianza del sustain tras FLUTTER_SKIP_MS) ---
    flutter_ptp_db   = 0.0
    reemergence_count = 0
    fl_seg = y[fl_skip:n]
    if len(fl_seg) > RMS_FRAME_LENGTH * 4:
        rms_fl = librosa.feature.rms(
            y=fl_seg, frame_length=RMS_FRAME_LENGTH, hop_length=RMS_HOP_LENGTH
        )[0]
        rms_fl = np.maximum(rms_fl, 1e-9)
        if len(rms_fl) >= SAVGOL_WINDOW:
            trend   = scipy.signal.savgol_filter(rms_fl, SAVGOL_WINDOW, SAVGOL_POLY)
            trend   = np.maximum(trend, 1e-9)
            res_db  = 20 * np.log10(rms_fl) - 20 * np.log10(trend)
            flutter_ptp_db = float(np.ptp(res_db))

            rms_db = 20 * np.log10(rms_fl)
            for k in range(2, len(rms_db)):
                if (rms_db[k-2] - rms_db[k-1]) > 1.0 and (rms_db[k] - rms_db[k-1]) > 2.0:
                    reemergence_count += 1

    return {
        "path":               wav_path,
        "filename":           os.path.basename(wav_path),
        "midi":               midi,
        "f0_hz":              f0_hz,
        "note_name":          librosa.hz_to_note(f0_hz) if f0_hz else "?",
        "duration":           n / sr,
        "rms_attack_db":      rms_atk_db,
        "rms_sustain_db":     rms_sus_db,
        "centroid_attack":    sc_atk,
        "centroid_sustain":   sc_sus,
        "centroid_delta":     centroid_delta,
        "hf_energy_db":       hf_energy_db,
        "flutter_ptp_db":     flutter_ptp_db,
        "reemergence_count":  reemergence_count,
        # Modificadores de nomenclatura y mic setup (se rellenan en load_session)
        "modifiers":          parse_filename_modifiers(os.path.basename(wav_path)),
        "mic_setup":          None,
    }


def load_session(session_dict):
    """Carga todos los WAVs de una sesion y extrae metricas."""
    folder = session_dict["folder"]
    wavs   = sorted(
        [f for f in os.listdir(folder) if f.endswith(".wav")],
        key=lambda f: (
            int(re.search(r'(\d+)', f).group(1)) if re.search(r'(\d+)', f) else 0,
            f
        )
    )
    mic_meta = get_session_metadata(folder)   # metadata de microfono para esta sesion
    notes = []
    for fname in wavs:
        path = os.path.join(folder, fname)
        print(f"  Analizando: {fname}")
        m = extract_metrics(path)
        m["session"]   = session_dict["label"]
        m["mic_setup"] = mic_meta              # adjuntar metadata de hardware
        notes.append(m)
    return notes


# =============================================================================
# ANALISIS DE INCONSISTENCIAS
# =============================================================================

def flag_note(note):
    """Genera lista de flags de inconsistencia para una nota."""
    flags = []

    # Flutter
    fp = note["flutter_ptp_db"]
    if fp >= FLUTTER_CRITICAL_DB:
        flags.append(f"FLUTTER_CRITICO ({fp:.1f}dB ptp)")
    elif fp >= FLUTTER_WARN_DB:
        flags.append(f"FLUTTER_MODERADO ({fp:.1f}dB ptp)")

    # Re-emergencia
    if note["reemergence_count"] >= REEMERGENCE_FLAG:
        flags.append(f"REEMERGENCIA x{note['reemergence_count']}")

    # Ruido de tecla
    hf = note.get("hf_energy_db")
    if hf is not None and hf > HF_WARN_DB:
        flags.append(f"KEY_NOISE_ALTO ({hf:.1f}dB HF)")

    # Centroide anomalo (sustain mas brillante que ataque — ocurre en notas muy agudas)
    cd = note.get("centroid_delta")
    if cd is not None and cd < -300:
        flags.append(f"CENTROIDE_INVERTIDO ({cd:+.0f}Hz)")

    return flags


def build_level_trend(notes_all):
    """
    Ajusta una recta de regresion lineal al RMS de sustain en funcion del MIDI
    para estimar la curva de nivel esperada. Retorna funcion predict(midi).
    """
    valid = [(n["midi"], n["rms_sustain_db"])
             for n in notes_all if n["midi"] is not None and n["rms_sustain_db"] > -80]
    if len(valid) < 3:
        return lambda m: -28.0
    midis = np.array([v[0] for v in valid])
    levels = np.array([v[1] for v in valid])
    coeffs = np.polyfit(midis, levels, 1)
    return np.poly1d(coeffs)


def cross_session_overlap(notes_a, notes_b):
    """
    Detecta notas presentes en ambas sesiones (mismo MIDI) y compara metricas.
    Retorna lista de dicts con la comparacion.
    """
    midi_a = {}
    for n in notes_a:
        if n["midi"] is not None:
            midi_a.setdefault(n["midi"], []).append(n)

    midi_b = {}
    for n in notes_b:
        if n["midi"] is not None:
            midi_b.setdefault(n["midi"], []).append(n)

    overlap = []
    for midi in sorted(set(midi_a) & set(midi_b)):
        group_a = midi_a[midi]
        group_b = midi_b[midi]
        avg = lambda lst, key: np.mean([x[key] for x in lst if x.get(key) is not None])

        diff_rms     = avg(group_b, "rms_sustain_db") - avg(group_a, "rms_sustain_db")
        diff_flutter = avg(group_b, "flutter_ptp_db") - avg(group_a, "flutter_ptp_db")
        diff_hf      = avg(group_b, "hf_energy_db")  - avg(group_a, "hf_energy_db")
        diff_dur     = avg(group_b, "duration")       - avg(group_a, "duration")

        flags = []
        if abs(diff_rms) > LEVEL_CROSS_SESSION_DB:
            flags.append(f"NIVEL_CROSS_SESSION {diff_rms:+.1f}dB")

        overlap.append({
            "midi": midi,
            "note": librosa.hz_to_note(librosa.midi_to_hz(midi)),
            "n_a":  len(group_a),
            "n_b":  len(group_b),
            "rms_sus_a":  avg(group_a, "rms_sustain_db"),
            "rms_sus_b":  avg(group_b, "rms_sustain_db"),
            "flutter_a":  avg(group_a, "flutter_ptp_db"),
            "flutter_b":  avg(group_b, "flutter_ptp_db"),
            "hf_a":       avg(group_a, "hf_energy_db"),
            "hf_b":       avg(group_b, "hf_energy_db"),
            "dur_a":      avg(group_a, "duration"),
            "dur_b":      avg(group_b, "duration"),
            "diff_rms_db":    diff_rms,
            "diff_flutter_db": diff_flutter,
            "diff_hf_db":     diff_hf,
            "diff_dur_s":     diff_dur,
            "flags":      flags,
        })
    return overlap


# =============================================================================
# REPORTE DE TEXTO
# =============================================================================

def write_report(notes_a, notes_b, overlap, trend_fn, out_dir):
    lines = [
        "PIPELINE DE INCONSISTENCIAS — Comparacion entre sesiones",
        "=" * 70,
        f"Sesion A: {SESSION_A['label']}  ({len(notes_a)} muestras)",
        f"Sesion B: {SESSION_B['label']}  ({len(notes_b)} muestras)",
        "",
    ]

    def section(title, notes, trend_fn):
        out = [f"{'=' * 70}", f"  {title}", f"{'=' * 70}", ""]
        hdr = f"{'Archivo':<24} {'MIDI':>4} {'Dur':>6} {'RMS_atk':>8} {'RMS_sus':>8} {'Trend':>7} {'Dev':>6} {'Flutter':>8} {'HF_atk':>7} {'Flags'}"
        out.append(hdr)
        out.append("-" * 110)
        for n in notes:
            midi = n["midi"] or 0
            trend_db = float(trend_fn(midi)) if midi else -28.0
            dev_db   = n["rms_sustain_db"] - trend_db
            flags    = flag_note(n)
            if abs(dev_db) > LEVEL_INCONSISTENCY_DB:
                flags.insert(0, f"NIVEL_FUERA_TENDENCIA ({dev_db:+.1f}dB)")
            flag_str = " | ".join(flags) if flags else "OK"
            out.append(
                f"{n['filename']:<24} {midi:>4} "
                f"{n['duration']:>6.1f}s "
                f"{n['rms_attack_db']:>7.1f} "
                f"{n['rms_sustain_db']:>7.1f} "
                f"{trend_db:>6.1f} "
                f"{dev_db:>+6.1f} "
                f"{n['flutter_ptp_db']:>7.1f} "
                f"{(n['hf_energy_db'] or 0):>6.1f}  "
                f"{flag_str}"
            )
        out.append("")
        return out

    lines += section(SESSION_A["label"], notes_a, trend_fn)
    lines += section(SESSION_B["label"], notes_b, trend_fn)

    lines += ["=" * 70, "  SOLAPAMIENTO ENTRE SESIONES (misma nota en A y B)", "=" * 70, ""]
    if not overlap:
        lines.append("  Ninguna nota en comun detectada.")
    else:
        for ov in overlap:
            lines += [
                f"  {ov['note']} (MIDI {ov['midi']})  —  "
                f"Sesion A: {ov['n_a']} take(s)    Sesion B: {ov['n_b']} take(s)",
                f"    RMS sustain   A={ov['rms_sus_a']:.1f} dBFS   B={ov['rms_sus_b']:.1f} dBFS   "
                f"diff={ov['diff_rms_db']:+.1f} dB",
                f"    Flutter ptp   A={ov['flutter_a']:.1f} dB     B={ov['flutter_b']:.1f} dB     "
                f"diff={ov['diff_flutter_db']:+.1f} dB",
                f"    HF ataque     A={ov['hf_a']:.1f} dB     B={ov['hf_b']:.1f} dB     "
                f"diff={ov['diff_hf_db']:+.1f} dB",
                f"    Duracion      A={ov['dur_a']:.1f}s          B={ov['dur_b']:.1f}s          "
                f"diff={ov['diff_dur_s']:+.1f}s",
                f"    FLAGS: {' | '.join(ov['flags']) if ov['flags'] else 'OK'}",
                "",
            ]

    # Resumen ejecutivo de inconsistencias
    all_notes = notes_a + notes_b
    critical  = [n for n in all_notes if n["flutter_ptp_db"] >= FLUTTER_CRITICAL_DB]
    warn      = [n for n in all_notes if FLUTTER_WARN_DB <= n["flutter_ptp_db"] < FLUTTER_CRITICAL_DB]
    reemerg   = [n for n in all_notes if n["reemergence_count"] >= REEMERGENCE_FLAG]
    hf_warn   = [n for n in all_notes if (n.get("hf_energy_db") or -99) > HF_WARN_DB]

    lines += [
        "=" * 70, "  RESUMEN EJECUTIVO", "=" * 70, "",
        f"  Flutter critico  (>={FLUTTER_CRITICAL_DB}dB):  "
        f"{len(critical)} nota(s): {', '.join(n['filename'] for n in critical)}",
        f"  Flutter moderado ({FLUTTER_WARN_DB}-{FLUTTER_CRITICAL_DB}dB): "
        f"{len(warn)} nota(s): {', '.join(n['filename'] for n in warn)}",
        f"  Re-emergencia de sustain:         "
        f"{len(reemerg)} nota(s): {', '.join(n['filename'] for n in reemerg)}",
        f"  Ruido de tecla alto (>{HF_WARN_DB}dB):   "
        f"{len(hf_warn)} nota(s): {', '.join(n['filename'] for n in hf_warn)}",
        "",
        "  PRIORIDADES DE ACCION:",
        "  1. Re-afinacion del piano en registros con flutter critico",
        "     antes de la proxima sesion de grabacion.",
        "  2. Re-grabacion de notas con re-emergencia de sustain",
        "     (inspeccionar visualmente el PNG de sustain en _spectral/).",
        "  3. Verificar nivel dinamico de C6 y C7 (sesion 02) —",
        "     niveles entre -35 y -49 dBFS no corresponden a dinamica p.",
        "  4. C4 aparece en ambas sesiones con diferencia de nivel y flutter;",
        "     seleccionar la mejor version para la biblioteca o re-grabar.",
    ]

    # Seccion de metadata de setup de microfonos
    lines += [
        "",
        "=" * 70,
        "  METADATA DE SETUP DE MICROFONOS",
        "=" * 70,
        "",
        "  NOTA METODOLOGICA: Las sesiones p/ff existentes (01 y 02) fueron grabadas",
        "  con par hibrido SDC+LDC (CM25 + AT3035). Las nuevas dinamicas (mp, mf, f)",
        "  se grabaran con par matched SDC (Rode M5 en configuracion ORTF).",
        "  La diferencia timbrica es una variable controlada documentada, no un error.",
        "  pipeline_compare.py la cuantifica como evidencia de mejora metodologica.",
        "",
    ]
    for key, meta in SESSION_METADATA.items():
        if meta.get("folder") is None and key == "sesion_M5":
            lines.append(f"  [{key.upper()}] {meta['label']}  (pendiente de grabacion)")
        else:
            lines.append(f"  [{key.upper()}] {meta['label']}")
        lines += [
            f"    Mic L         : {meta['microfono_L']}",
            f"    Mic R         : {meta['microfono_R']}",
            f"    Tipo par      : {meta['tipo_par']}",
            f"    EIN promedio  : {meta['EIN_promedio_dBA']} dBA",
            f"    Posicion      : {meta['posicion']}",
            "",
        ]

    lines += [
        "  Setup futuro (M5 ORTF):",
        "  - Par matched SDC (misma capsula, mismo EIN) elimina asimetria timbrica L/R.",
        "  - ORTF (110°, 17cm) provee imagen estereo natural con buena suma mono.",
        "  - EIN 19 dBA es 0.5 dBA mejor que el promedio del par CM25+AT3035.",
        "  - Para C6-C7 reducir distancia M5 a 30-35cm para mejorar SNR.",
        "  - C2 par (XY dentro del piano) como fuente secundaria de mayor nivel directo.",
    ]

    path = os.path.join(out_dir, "compare_report.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"  Reporte escrito: {path}")


# =============================================================================
# VISUALIZACIONES
# =============================================================================

def plot_overview(notes_a, notes_b, trend_fn, out_dir):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    all_notes = notes_a + notes_b
    valid = [n for n in all_notes if n["midi"] is not None]
    midi_range = np.arange(
        min(n["midi"] for n in valid) - 1,
        max(n["midi"] for n in valid) + 2
    )

    colors = {SESSION_A["label"]: "#4C9BE8", SESSION_B["label"]: "#E8824C"}
    markers = {SESSION_A["label"]: "o", SESSION_B["label"]: "s"}

    fig, axes = plt.subplots(4, 1, figsize=(16, 18))
    fig.suptitle("Comparacion de Sesiones — Inconsistencias de Calidad", fontsize=13, fontweight="bold")

    # --- Panel 1: Nivel dinamico (RMS sustain) ---
    ax = axes[0]
    for session_label, notes in [(SESSION_A["label"], notes_a), (SESSION_B["label"], notes_b)]:
        for n in notes:
            if n["midi"] is None:
                continue
            dev = n["rms_sustain_db"] - float(trend_fn(n["midi"]))
            ec  = "red" if abs(dev) > LEVEL_INCONSISTENCY_DB else colors[session_label]
            ax.scatter(n["midi"], n["rms_sustain_db"],
                       color=colors[session_label], edgecolors=ec,
                       marker=markers[session_label], s=80, linewidths=1.5,
                       label=session_label, zorder=3)
    ax.plot(midi_range, [float(trend_fn(m)) for m in midi_range],
            color="gray", ls="--", lw=1.2, label="Tendencia lineal")
    ax.axhspan(-28 - LEVEL_INCONSISTENCY_DB, -28 + LEVEL_INCONSISTENCY_DB,
               alpha=0.08, color="green", label=f"Zona p ±{LEVEL_INCONSISTENCY_DB}dB")
    ax.set_ylabel("RMS sustain (dBFS)")
    ax.set_title("Nivel dinamico por nota  [puntos rojos = fuera de tendencia]", fontsize=9)
    ax.grid(alpha=0.3)
    # Eliminar duplicados en leyenda
    handles, labels = ax.get_legend_handles_labels()
    seen = {}
    for h, l in zip(handles, labels):
        seen.setdefault(l, h)
    ax.legend(seen.values(), seen.keys(), fontsize=7, loc="lower left")

    # --- Panel 2: Flutter ptp ---
    ax = axes[1]
    for session_label, notes in [(SESSION_A["label"], notes_a), (SESSION_B["label"], notes_b)]:
        for n in notes:
            if n["midi"] is None:
                continue
            color = ("red" if n["flutter_ptp_db"] >= FLUTTER_CRITICAL_DB
                     else "orange" if n["flutter_ptp_db"] >= FLUTTER_WARN_DB
                     else colors[session_label])
            ax.bar(n["midi"] + (0.3 if session_label == SESSION_B["label"] else -0.3),
                   n["flutter_ptp_db"], width=0.55,
                   color=color, alpha=0.85, label=session_label)
    ax.axhline(FLUTTER_CRITICAL_DB, color="red",    ls="--", lw=1, label=f"Critico {FLUTTER_CRITICAL_DB}dB")
    ax.axhline(FLUTTER_WARN_DB,     color="orange",  ls="--", lw=1, label=f"Moderado {FLUTTER_WARN_DB}dB")
    ax.set_ylabel("Flutter ptp (dB)")
    ax.set_title("Flutter de sustain  [rojo=critico / naranja=moderado]", fontsize=9)
    ax.grid(alpha=0.3, axis="y")
    handles, labels = ax.get_legend_handles_labels()
    seen = {}
    for h, l in zip(handles, labels):
        seen.setdefault(l, h)
    ax.legend(seen.values(), seen.keys(), fontsize=7)

    # --- Panel 3: Energia HF en ataque (ruido de tecla) ---
    ax = axes[2]
    for session_label, notes in [(SESSION_A["label"], notes_a), (SESSION_B["label"], notes_b)]:
        for n in notes:
            if n["midi"] is None or n.get("hf_energy_db") is None:
                continue
            color = ("red" if n["hf_energy_db"] > HF_WARN_DB
                     else colors[session_label])
            ax.scatter(n["midi"], n["hf_energy_db"],
                       color=color, marker=markers[session_label], s=80, zorder=3,
                       label=session_label)
    ax.axhline(HF_WARN_DB, color="red", ls="--", lw=1, label=f"Umbral key noise {HF_WARN_DB}dB")
    ax.set_ylabel("Energia >8kHz ataque (dB relativo)")
    ax.set_title("Ruido de tecla por registro  [rojo = key noise elevado]", fontsize=9)
    ax.grid(alpha=0.3)
    handles, labels = ax.get_legend_handles_labels()
    seen = {}
    for h, l in zip(handles, labels):
        seen.setdefault(l, h)
    ax.legend(seen.values(), seen.keys(), fontsize=7)

    # --- Panel 4: Duracion (decay) ---
    ax = axes[3]
    for session_label, notes in [(SESSION_A["label"], notes_a), (SESSION_B["label"], notes_b)]:
        midis = [n["midi"] for n in notes if n["midi"] is not None]
        durs  = [n["duration"] for n in notes if n["midi"] is not None]
        ax.scatter(midis, durs, color=colors[session_label],
                   marker=markers[session_label], s=80,
                   label=session_label, zorder=3)
    # Curva de decay teorica (exponencial inversa aproximada para piano)
    midi_th = np.linspace(min(n["midi"] for n in valid), max(n["midi"] for n in valid), 100)
    # Aproximacion: decay ~ 35 * exp(-0.045 * (midi - 24)) + 4
    decay_th = 35 * np.exp(-0.045 * (midi_th - 24)) + 4
    ax.plot(midi_th, decay_th, color="gray", ls="--", lw=1.2, label="Decay teorico piano")
    ax.set_xlabel("Nota MIDI")
    ax.set_ylabel("Duracion (s)")
    ax.set_title("Duracion de decay por registro  [esperado: mas largo en notas graves]", fontsize=9)
    ax.grid(alpha=0.3)
    handles, labels = ax.get_legend_handles_labels()
    seen = {}
    for h, l in zip(handles, labels):
        seen.setdefault(l, h)
    ax.legend(seen.values(), seen.keys(), fontsize=7)

    # Eje X comun: etiquetas de notas MIDI
    tick_midis = sorted(set(n["midi"] for n in valid if n["midi"] is not None))
    tick_labels = [librosa.hz_to_note(librosa.midi_to_hz(m)) for m in tick_midis]
    for ax in axes:
        ax.set_xticks(tick_midis)
        ax.set_xticklabels(tick_labels, fontsize=8, rotation=45)

    plt.tight_layout(rect=[0, 0, 1, 0.97])
    path = os.path.join(out_dir, "compare_overview.png")
    plt.savefig(path, dpi=120)
    plt.close(fig)
    print(f"  Overview guardado: {path}")


def plot_c4_overlap(notes_a, notes_b, out_dir):
    """Comparacion directa del C4 entre ambas sesiones."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    C4_MIDI = 60
    group_a = [n for n in notes_a if n["midi"] == C4_MIDI]
    group_b = [n for n in notes_b if n["midi"] == C4_MIDI]

    if not group_a or not group_b:
        print("  [!] C4 no encontrado en alguna sesion — omitiendo compare_C4_overlap.png")
        return

    metrics = ["rms_attack_db", "rms_sustain_db", "centroid_delta", "hf_energy_db", "flutter_ptp_db", "duration"]
    metric_labels = ["RMS ataque\n(dBFS)", "RMS sustain\n(dBFS)", "Centroide delta\n(Hz)", "HF >8kHz\n(dB rel)", "Flutter ptp\n(dB)", "Duracion\n(s)"]

    fig, axes = plt.subplots(2, 3, figsize=(14, 8))
    fig.suptitle("C4 — Comparacion directa entre Sesion A y Sesion B", fontsize=12, fontweight="bold")
    axes = axes.flatten()

    colors_a = ["#4C9BE8"] * len(group_a)
    colors_b = ["#E8824C"] * len(group_b)

    for i, (metric, label) in enumerate(zip(metrics, metric_labels)):
        ax = axes[i]
        vals_a = [n.get(metric) for n in group_a if n.get(metric) is not None]
        vals_b = [n.get(metric) for n in group_b if n.get(metric) is not None]

        x_a = np.arange(len(vals_a))
        x_b = np.arange(len(vals_b)) + len(vals_a) + 0.5

        ax.bar(x_a, vals_a, color="#4C9BE8", alpha=0.85,
               label=SESSION_A["label"])
        ax.bar(x_b, vals_b, color="#E8824C", alpha=0.85,
               label=SESSION_B["label"])

        tick_pos = list(x_a) + list(x_b)
        tick_lbl = [f"A_RR{j+1}" for j in range(len(vals_a))] + \
                   [f"B_{j+1}" for j in range(len(vals_b))]
        ax.set_xticks(tick_pos)
        ax.set_xticklabels(tick_lbl, fontsize=7)
        ax.set_title(label, fontsize=8)
        ax.grid(alpha=0.3, axis="y")
        if i == 0:
            ax.legend(fontsize=7)

    plt.tight_layout()
    path = os.path.join(out_dir, "compare_C4_overlap.png")
    plt.savefig(path, dpi=120)
    plt.close(fig)
    print(f"  C4 overlap guardado: {path}")


def plot_level_curve(notes_a, notes_b, trend_fn, out_dir):
    """Curva de nivel dinamico a traves del teclado con banda de tolerancia."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    all_valid = [n for n in notes_a + notes_b if n["midi"] is not None]
    midi_range = np.linspace(
        min(n["midi"] for n in all_valid) - 2,
        max(n["midi"] for n in all_valid) + 2, 200
    )
    trend_vals = [float(trend_fn(m)) for m in midi_range]

    fig, ax = plt.subplots(figsize=(15, 6))
    ax.fill_between(midi_range,
                    [v - LEVEL_INCONSISTENCY_DB for v in trend_vals],
                    [v + LEVEL_INCONSISTENCY_DB for v in trend_vals],
                    alpha=0.12, color="green", label=f"Banda tolerancia ±{LEVEL_INCONSISTENCY_DB}dB")
    ax.plot(midi_range, trend_vals, color="gray", ls="--", lw=1.5, label="Tendencia global")

    colors = {SESSION_A["label"]: "#4C9BE8", SESSION_B["label"]: "#E8824C"}
    markers = {SESSION_A["label"]: "o", SESSION_B["label"]: "s"}

    for session_label, notes in [(SESSION_A["label"], notes_a), (SESSION_B["label"], notes_b)]:
        for n in notes:
            if n["midi"] is None:
                continue
            dev = n["rms_sustain_db"] - float(trend_fn(n["midi"]))
            ec  = "red" if abs(dev) > LEVEL_INCONSISTENCY_DB else "none"
            ax.scatter(n["midi"], n["rms_sustain_db"],
                       color=colors[session_label],
                       edgecolors=ec, linewidths=2,
                       marker=markers[session_label], s=120, zorder=5,
                       label=session_label)
            ax.annotate(n["filename"].replace(".wav", ""),
                        (n["midi"], n["rms_sustain_db"]),
                        textcoords="offset points", xytext=(4, 4),
                        fontsize=6, color="black", alpha=0.7)

    tick_midis = sorted(set(n["midi"] for n in all_valid))
    tick_labels = [librosa.hz_to_note(librosa.midi_to_hz(m)) for m in tick_midis]
    ax.set_xticks(tick_midis)
    ax.set_xticklabels(tick_labels, fontsize=8, rotation=45)
    ax.set_xlabel("Nota")
    ax.set_ylabel("RMS sustain (dBFS)")
    ax.set_title("Curva de nivel dinamico p — ambas sesiones\n"
                 "[circulo rojo = fuera de tolerancia | azul = Sesion A | naranja = Sesion B]",
                 fontsize=10)
    ax.grid(alpha=0.3)
    handles, labels = ax.get_legend_handles_labels()
    seen = {}
    for h, l in zip(handles, labels):
        seen.setdefault(l, h)
    ax.legend(seen.values(), seen.keys(), fontsize=8)

    plt.tight_layout()
    path = os.path.join(out_dir, "compare_level_curve.png")
    plt.savefig(path, dpi=130)
    plt.close(fig)
    print(f"  Curva de nivel guardada: {path}")


# =============================================================================
# MAIN
# =============================================================================

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"PIPELINE DE COMPARACION DE SESIONES")
    print(f"{'='*60}\n")

    print(f"[A] Cargando {SESSION_A['label']}...")
    notes_a = load_session(SESSION_A)

    print(f"\n[B] Cargando {SESSION_B['label']}...")
    notes_b = load_session(SESSION_B)

    all_notes = notes_a + notes_b

    print("\nCalculando tendencia de nivel dinamico...")
    trend_fn = build_level_trend(all_notes)

    print("Detectando solapamientos entre sesiones...")
    overlap = cross_session_overlap(notes_a, notes_b)

    print("\nGenerando reporte de texto...")
    write_report(notes_a, notes_b, overlap, trend_fn, OUTPUT_DIR)

    print("Generando visualizaciones...")
    plot_overview(notes_a, notes_b, trend_fn, OUTPUT_DIR)
    plot_c4_overlap(notes_a, notes_b, OUTPUT_DIR)
    plot_level_curve(notes_a, notes_b, trend_fn, OUTPUT_DIR)

    print(f"\n[OK] Pipeline de comparacion completado.")
    print(f"     Resultados en: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
