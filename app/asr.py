"""
Speech recognition via faster-whisper with automatic gender detection.
"""
import os
import platform
import wave
from typing import Callable, Optional

import numpy as np


# ---------------------------------------------------------------------------
# PyAV 19 compatibility shim
# ---------------------------------------------------------------------------
try:
    import av as _av
    _av_major = int(_av.__version__.split(".")[0])
    if _av_major >= 19:
        _orig_av_open = _av.open
        def _patched_av_open(*args, **kwargs):
            kwargs.pop("metadata_errors", None)
            return _orig_av_open(*args, **kwargs)
        _av.open = _patched_av_open
except Exception:
    pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _is_apple_silicon() -> bool:
    return (platform.system() == "Darwin" and platform.machine() in ("arm64", "aarch64"))


def _mps_available() -> bool:
    try:
        import ctranslate2
        if hasattr(ctranslate2, "get_mps_device_count"):
            return ctranslate2.get_mps_device_count() > 0
    except Exception:
        pass
    return False


def _resolve_device(device: str) -> tuple[str, str]:
    if device == "auto":
        if _is_apple_silicon() and _mps_available():
            return "mps", "float16"
        try:
            import torch
            if torch.cuda.is_available():
                return "cuda", "float16"
        except Exception:
            pass
        return "cpu", "int8"
    if device == "mps":
        return ("mps", "float16") if _mps_available() else ("cpu", "int8")
    if device == "cuda":
        return "cuda", "float16"
    return "cpu", "int8"


def _configure_ct2_logging(verbose: bool):
    try:
        import ctranslate2
        ctranslate2.set_log_level(1 if verbose else -1)
    except Exception:
        pass


def _detect_gender(audio_path: str, start_ms: int, end_ms: int) -> str:
    """
    Reads the audio segment, splits into small chunks, and estimates the
    dominant pitch (F0) to determine Male vs Female.
    """
    try:
        with wave.open(audio_path, 'rb') as wf:
            sr = wf.getframerate()
            n_frames = wf.getnframes()

            start_frame = int(start_ms / 1000.0 * sr)
            end_frame = int(end_ms / 1000.0 * sr)

            if end_frame > n_frames:
                end_frame = n_frames
            if start_frame >= end_frame:
                return "Unknown"

            wf.setpos(start_frame)
            frames = wf.readframes(end_frame - start_frame)

            # Audio must be 16-bit PCM for np.frombuffer
            audio_data = np.frombuffer(frames, dtype=np.int16)
    except Exception:
        return "Unknown"

    if len(audio_data) < sr * 0.1:  # Too short to analyze
        return "Unknown"

    # Split into 50ms chunks to find pitch over time (ignoring silence)
    chunk_size = int(sr * 0.05)
    pitches = []

    for i in range(0, len(audio_data) - chunk_size, chunk_size):
        chunk = audio_data[i:i+chunk_size]

        # Skip silent or very quiet chunks (RMS threshold)
        if np.sqrt(np.mean(chunk.astype(float)**2)) < 500:
            continue

        # Apply Hanning window to reduce spectral leakage
        window = np.hanning(len(chunk))
        fft = np.fft.rfft(chunk * window)
        freqs = np.fft.rfftfreq(len(chunk), 1.0 / sr)

        # Limit to human voice range (60 Hz - 350 Hz)
        mask = (freqs >= 60) & (freqs <= 350)
        if not np.any(mask):
            continue

        mag = np.abs(fft[mask])
        freqs_masked = freqs[mask]

        if len(mag) > 0:
            pitches.append(freqs_masked[np.argmax(mag)])

    if not pitches:
        return "Unknown"

    median_pitch = np.median(pitches)

    # 165 Hz is the standard threshold between male and female
    if median_pitch > 165:
        return "Female"
    else:
        return "Male"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def transcribe(
    audio_path: str,
    model_size: str = "large-v3",
    device: str = "auto",
    language: Optional[str] = None,
    progress: Optional[Callable[[str], None]] = None,
    progress_percent: Optional[Callable[[int], None]] = None,
    verbose_ct2: bool = False,
) -> dict:
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise RuntimeError("faster-whisper is not installed. Run: pip install faster-whisper")

    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    _configure_ct2_logging(verbose=verbose_ct2)
    dev, compute_type = _resolve_device(device)

    if progress:
        progress(f"Loading Whisper model '{model_size}' on {dev} …")
    model = WhisperModel(model_size, device=dev, compute_type=compute_type)

    if progress:
        progress(f"Transcribing audio (device={dev}) …")
    if progress_percent:
        progress_percent(0)

    segments_iter, info = model.transcribe(
        audio_path,
        beam_size=5,
        language=language or None,
        vad_filter=True,
        word_timestamps=False,
    )

    total_duration = float(info.duration) if info.duration else 0.0
    results = []
    last_pct = 0

    for seg in segments_iter:
        text = seg.text.strip()
        if text:
            results.append({
                "start_ms": int(seg.start * 1000),
                "end_ms": int(seg.end * 1000),
                "text": text,
            })
        if progress_percent and total_duration > 0:
            pct = min(99, int(seg.end / total_duration * 100))
            if pct > last_pct:
                progress_percent(pct)
                last_pct = pct

    # ---- Auto Detect Gender for each segment ----
    if progress:
        progress("Analyzing voice pitch for speaker gender …")
    for i, r in enumerate(results):
        r["gender"] = _detect_gender(audio_path, r["start_ms"], r["end_ms"])
        if progress_percent and len(results) > 0:
            # Update progress bar for gender analysis (99% -> 100%)
            progress_percent(99 + int((i + 1) / len(results) * 1))

    if progress_percent:
        progress_percent(100)

    if progress:
        progress(f"Transcription complete: {len(results)} segments (language={info.language})")

    return {
        "language": info.language,
        "language_probability": float(info.language_probability),
        "segments": results,
        "device": dev,
        "compute_type": compute_type,
    }