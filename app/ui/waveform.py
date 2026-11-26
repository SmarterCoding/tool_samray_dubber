import os
import wave
import numpy as np
import math

def generate_waveform(path: str, bars: int = 120) -> list[float]:
    """Extract waveform peaks using native numpy (super fast) or fallback."""
    if not path or not os.path.exists(path):
        return [0.35 + 0.65 * abs(math.sin(i * 0.37)) for i in range(bars)]

    try:
        # For WAV files, read directly with 'wave' and 'numpy' (milliseconds)
        if path.lower().endswith('.wav'):
            with wave.open(path, 'rb') as wf:
                n_frames = wf.getnframes()
                frames = wf.readframes(n_frames)
                dtype = np.int16 if wf.getsampwidth() == 2 else np.int32
                samples = np.frombuffer(frames, dtype=dtype)
        else:
            # Fallback to pydub for mp3 (slower, but only used on first load)
            from pydub import AudioSegment
            audio = AudioSegment.from_file(path)
            samples = np.array(audio.get_array_of_samples())

        if len(samples) == 0:
            return []

        chunk_size = max(1, len(samples) // bars)
        peaks = []
        for i in range(0, len(samples), chunk_size):
            chunk = samples[i:i+chunk_size]
            if len(chunk) > 0:
                peaks.append(np.max(np.abs(chunk)))

        mx = max(peaks) if peaks else 1
        return [float(p) / mx for p in peaks[:bars]]
    except Exception:
        return [0.35 + 0.65 * abs(math.sin(i * 0.37)) for i in range(bars)]