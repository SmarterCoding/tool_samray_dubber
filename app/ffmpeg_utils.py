import functools
import json
import os
import subprocess
import shutil
import sys
import wave
from typing import Optional


# =========================================================
# FFMPEG BINARIES
# =========================================================

def _is_executable(path: str) -> bool:
    if not path or not os.path.isfile(path):
        return False
    # Windows does not use POSIX execute permission bits for .exe files.
    if os.name == "nt":
        return path.lower().endswith((".exe", ".bat", ".cmd"))
    return os.access(path, os.X_OK)


def _project_root() -> str:
    """Find the application root from this module's location."""
    here = os.path.abspath(os.path.dirname(__file__))
    candidates = [here, os.path.dirname(here), os.path.dirname(os.path.dirname(here))]
    for candidate in candidates:
        if os.path.isdir(os.path.join(candidate, "vendor", "ffmpeg")):
            return candidate
    # Typical layout: project/app/utils/ffmpeg_utils.py
    return os.path.dirname(os.path.dirname(here))


def _binary_names(name: str):
    return [name + ".exe", name] if os.name == "nt" else [name]


def _bundled_binary(name: str) -> Optional[str]:
    """Find FFmpeg bundled under vendor/ffmpeg or in a PyInstaller build."""
    roots = [os.path.join(_project_root(), "vendor", "ffmpeg")]
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        roots.extend([os.path.join(meipass, "bin"), meipass,
                      os.path.join(meipass, "vendor", "ffmpeg")])
    roots.append(os.path.join(os.path.dirname(sys.executable), "bin"))
    for root in roots:
        for filename in _binary_names(name):
            candidate = os.path.join(root, filename)
            if _is_executable(candidate):
                return candidate
    return None

def _homebrew_full_binary(name: str) -> Optional[str]:
    """Find the Homebrew ffmpeg-full formula before falling back to PATH."""
    for prefix in ("/opt/homebrew", "/usr/local"):
        for filename in _binary_names(name):
            candidate = os.path.join(prefix, "opt", "ffmpeg-full", "bin", filename)
            if _is_executable(candidate):
                return candidate
    return None

def _resolve_binary(name: str, env_var: str) -> str:
    override = os.environ.get(env_var) or os.environ.get(f"{name.upper()}_BIN")
    if override:
        return override
    bundled = _bundled_binary(name)
    if bundled:
        return bundled
    full = _homebrew_full_binary(name)
    if full:
        return full
    found = shutil.which(name)
    if found:
        return found
    if os.name == "nt":
        found = shutil.which(name + ".exe")
        if found:
            return found
    return name + (".exe" if os.name == "nt" else "")


def ffmpeg_bin() -> str:
    return _resolve_binary("ffmpeg", "SAMRAY_FFMPEG")


def ffprobe_bin() -> str:
    return _resolve_binary("ffprobe", "SAMRAY_FFPROBE")

def install_ffmpeg() -> tuple[bool, str]:
    """Install a feature-rich FFmpeg using the host package manager.

    macOS: Homebrew ffmpeg-full (includes libass/subtitles support).
    Windows: Gyan FFmpeg shared build through winget.
    Debian/Ubuntu: distro FFmpeg package through apt.

    Call this only after the user chooses an Install FFmpeg action because
    it changes the machine and may request administrator permission.
    """
    system = sys.platform
    if system == "darwin":
        brew = shutil.which("brew")
        if not brew:
            return False, "Homebrew is not installed. Install Homebrew first: https://brew.sh/"
        command = [brew, "install", "ffmpeg-full"]
    elif system == "win32":
        winget = shutil.which("winget")
        if not winget:
            return False, "winget was not found. Install App Installer or install FFmpeg manually."
        command = [winget, "install", "--id", "Gyan.FFmpeg.Shared", "--exact",
                   "--accept-package-agreements", "--accept-source-agreements"]
    elif system.startswith("linux"):
        apt = shutil.which("apt-get")
        if not apt:
            return False, "This Linux system does not provide apt-get. Install FFmpeg with your distribution package manager."
        if hasattr(os, "geteuid") and os.geteuid() != 0:
            return False, "Run: sudo apt-get update && sudo apt-get install -y ffmpeg"
        command = [apt, "update"]
        try:
            update = subprocess.run(command, capture_output=True, text=True)
            if update.returncode != 0:
                return False, update.stderr or update.stdout
        except OSError as exc:
            return False, str(exc)
        command = [apt, "install", "-y", "ffmpeg"]
    else:
        return False, f"Automatic FFmpeg installation is not supported on {system}."

    try:
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            return False, (result.stderr or result.stdout or "FFmpeg installation failed.")[-5000:]
        _available_filters.cache_clear()
        ok, report = check_ffmpeg()
        if not ok:
            return False, "FFmpeg was installed but validation failed:\n" + report
        return True, report
    except OSError as exc:
        return False, f"Could not start installer: {exc}"


def check_ffmpeg() -> tuple[bool, str]:
    """Validate both binaries and report important exporter capabilities."""
    lines = []
    for label, binary in (("FFmpeg", ffmpeg_bin()), ("FFprobe", ffprobe_bin())):
        try:
            result = subprocess.run([binary, "-version"], capture_output=True,
                                    text=True, timeout=15)
            if result.returncode != 0:
                lines.append(f"{label}: FAILED ({binary})\n{result.stderr[-1000:]}")
                return False, "\n".join(lines)
            version_line = (result.stdout or result.stderr).splitlines()[0]
            lines.append(f"{label}: {version_line}\nPath: {binary}")
        except (OSError, subprocess.TimeoutExpired) as exc:
            lines.append(f"{label}: NOT FOUND ({binary}) - {exc}")
            return False, "\n".join(lines)
    filters = _available_filters(ffmpeg_bin())
    encoders = _available_encoders(ffmpeg_bin())
    lines.append("Subtitle burn-in filter: " + ("YES" if "subtitles" in filters else "NO"))
    lines.append("H.264 encoder libx264: " + ("YES" if "libx264" in encoders else "NO"))
    lines.append("AAC encoder: " + ("YES" if "aac" in encoders else "NO"))
    return True, "\n".join(lines)

# =========================================================
# PROCESS HELPERS
# =========================================================

def run(
    cmd: list[str],
    cwd: Optional[str] = None,
    timeout: Optional[int] = 120
) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, timeout=timeout
    )


# =========================================================
# FFMPEG CAPABILITIES
# =========================================================

@functools.lru_cache(maxsize=16)
def _available_filters(binary: str) -> frozenset[str]:
    """Return the filter names supported by an FFmpeg binary."""

    try:
        result = run([binary, "-hide_banner", "-filters"])
    except OSError:
        return frozenset()

    if result.returncode != 0:
        return frozenset()

    names = set()

    for line in result.stdout.splitlines():

        if line.startswith("Filters:"):
            continue

        parts = line.split()

        # Format: " TSC name  in->out  description"
        if len(parts) >= 2:
            names.add(parts[1])

    return frozenset(names)

@functools.lru_cache(maxsize=16)
def _available_encoders(binary: str) -> frozenset[str]:
    try:
        result = run([binary, "-hide_banner", "-encoders"])
    except (OSError, subprocess.TimeoutExpired):
        return frozenset()
    if result.returncode != 0:
        return frozenset()
    names = set()
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and len(parts[0]) >= 6 and parts[0][0] in ("V", "A", "S", "."):
            names.add(parts[1])
    return frozenset(names)


def has_filter(name: str) -> bool:
    """Check whether the selected FFmpeg build has a filter."""

    return name in _available_filters(ffmpeg_bin())


def subtitle_filter_error() -> str:
    """Explain how to fix a missing libass/subtitles filter."""

    binary = ffmpeg_bin()

    return (
        "This FFmpeg build cannot burn subtitles because the "
        "\"subtitles\" filter is missing.\n\n"
        "The filter requires an FFmpeg build compiled with libass.\n\n"
        f"FFmpeg in use:\n  {binary}\n\n"
        "macOS fix:\n"
        "  brew install ffmpeg-full\n\n"
        "SAMRAY DUBBER PRO automatically prefers ffmpeg-full when it "
        "is installed. You can also choose an explicit binary:\n"
        "  SAMRAY_FFMPEG=/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg\n"
        "  SAMRAY_FFPROBE=/opt/homebrew/opt/ffmpeg-full/bin/ffprobe\n\n"
        "To export without burned-in subtitles, uncheck "
        "\"Burn subtitles into video\"."
    )


def ensure_output_dir(path: str):
    """Create parent directory for output files."""

    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)


# =========================================================
# FFMPEG FILTER ESCAPING
# =========================================================

def escape_filter_path(path: str) -> str:
    """Escape a filename for the FFmpeg filtergraph parser."""
    path = os.path.abspath(path)
    return (path.replace("\\", "\\\\")
                .replace(":", "\\:")
                .replace("'", "\\'")
                .replace(",", "\\,")
                .replace("[", "\\[")
                .replace("]", "\\]"))


def escape_filter_text(value: str) -> str:
    """Escape a value embedded inside a single-quoted filter option."""
    return str(value).replace("\\", "\\\\").replace("'", "\\'")


def build_subtitle_filter(
    srt_path: str,
    font_name: str = "Khmer OS",
    font_size: int = 20
) -> str:
    if not os.path.isfile(srt_path):
        raise FileNotFoundError(f"Subtitle file not found: {srt_path}")
    if not has_filter("subtitles"):
        raise RuntimeError(subtitle_filter_error())

    escaped_path = escape_filter_path(srt_path)
    escaped_font = escape_filter_text(font_name)
    # force_style is quoted as one filter option; its commas must remain
    # ordinary commas because they separate ASS style properties.
    style = (
        f"FontName={escaped_font},FontSize={max(1, int(font_size))},"
        "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
        "BackColour=&H80000000,Outline=1,Shadow=1"
    )
    return f"subtitles='{escaped_path}':force_style='{style}'"


# =========================================================
# VIDEO DURATION
# =========================================================

def probe_media(path: str) -> dict:
    if not os.path.isfile(path):
        return {}
    cmd = [ffprobe_bin(), "-v", "error", "-show_streams", "-show_format",
           "-of", "json", path]
    try:
        result = run(cmd, timeout=30)
        if result.returncode != 0:
            return {}
        return json.loads(result.stdout or "{}")
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return {}


def has_audio_stream(path: str) -> bool:
    data = probe_media(path)
    return any(stream.get("codec_type") == "audio" for stream in data.get("streams", []))


def get_duration_ms(path: str) -> int:
    data = probe_media(path)
    try:
        duration = float(data.get("format", {}).get("duration", 0))
        if duration <= 0:
            durations = [float(s.get("duration", 0)) for s in data.get("streams", [])]
            duration = max(durations or [0])
        return max(0, int(duration * 1000))
    except (TypeError, ValueError):
        return 0


# =========================================================
# AUDIO EXTRACTION
# =========================================================

def extract_audio(
    video_path: str,
    out_wav: str,
    sample_rate: int = 16000
) -> bool:

    ensure_output_dir(out_wav)

    cmd = [
        ffmpeg_bin(),
        "-y",
        "-i", video_path,
        "-vn",
        "-ac", "1",
        "-ar", str(sample_rate),
        "-c:a", "pcm_s16le",
        out_wav
    ]

    return run(cmd).returncode == 0


def extract_audio_mp3(
    video_path: str,
    out_mp3: str
) -> bool:

    ensure_output_dir(out_mp3)

    cmd = [
        ffmpeg_bin(),
        "-y",
        "-i", video_path,
        "-vn",
        "-c:a", "libmp3lame",
        "-q:a", "2",
        out_mp3
    ]

    return run(cmd).returncode == 0


def convert_to_mp3(
    src: str,
    dst: str
) -> bool:

    ensure_output_dir(dst)

    cmd = [
        ffmpeg_bin(),
        "-y",
        "-i", src,
        "-c:a", "libmp3lame",
        "-q:a", "2",
        dst
    ]

    return run(cmd).returncode == 0


def convert_to_wav(
    src: str,
    dst: str,
    sample_rate: int = 44100
) -> bool:

    ensure_output_dir(dst)

    cmd = [
        ffmpeg_bin(),
        "-y",
        "-i", src,
        "-ac", "1",
        "-ar", str(sample_rate),
        "-c:a", "pcm_s16le",
        dst
    ]

    return run(cmd).returncode == 0


# =========================================================
# SRT SUBTITLE HELPERS
# =========================================================

def srt_time(ms: int) -> str:

    ms = max(0, int(ms))

    h = ms // 3600000
    m = (ms % 3600000) // 60000
    s = (ms % 60000) // 1000
    ms_rem = ms % 1000

    return (
        f"{h:02d}:"
        f"{m:02d}:"
        f"{s:02d},"
        f"{ms_rem:03d}"
    )


def write_srt(subtitles, path: str):
    """Write subtitles to UTF-8 SRT file."""

    ensure_output_dir(path)

    with open(path, "w", encoding="utf-8-sig") as f:

        for i, sub in enumerate(subtitles, 1):

            start = srt_time(sub.start_ms)
            end = srt_time(sub.end_ms)

            text = str(sub.text).strip()

            f.write(
                f"{i}\n"
                f"{start} --> {end}\n"
                f"{text}\n\n"
            )


# =========================================================
# AUDIO CONCATENATION WITH TIMING
# =========================================================

def concat_audio_with_timing(
    segments: list[tuple[str, int, int]],
    total_ms: int,
    out_wav: str,
    sample_rate: int = 44100,
    progress_callback=None
) -> bool:
    """Place TTS segments at timeline times and mix them into one WAV."""
    valid = []
    for path, start_ms, end_ms in segments:
        if not os.path.isfile(path):
            print(f"Audio segment not found: {path}")
            return False
        start_ms = max(0, int(start_ms))
        end_ms = int(end_ms)
        if end_ms <= start_ms:
            end_ms = start_ms + max(1, get_duration_ms(path))
        valid.append((path, start_ms, end_ms))
    if not valid or total_ms <= 0:
        return False

    # Fast path: mix PCM WAV clips in memory with NumPy. This is roughly
    # 1000x faster than an FFmpeg filter graph with one input per subtitle.
    if _mix_wavs_numpy(
        valid, total_ms, out_wav, sample_rate, progress_callback
    ):
        return True

    # Fallback: let FFmpeg handle non-WAV or unusual input files.
    ensure_output_dir(out_wav)
    cmd = [ffmpeg_bin(), "-hide_banner", "-nostdin", "-y"]
    filters = []
    for path, _start_ms, _end_ms in valid:
        cmd += ["-i", path]

    labels = []
    for i, (path, start_ms, end_ms) in enumerate(valid):
        duration = max(1, end_ms - start_ms)
        delay = start_ms
        label = f"seg{i}"
        dur_sec = max(0.01, duration / 1000.0)
        fade_dur = min(0.015, dur_sec / 2.0)
        fade_out_st = max(0.001, dur_sec - fade_dur)
        filters.append(
            f"[{i}:a:0]aresample={int(sample_rate)},"
            f"aformat=sample_fmts=fltp:channel_layouts=mono,"
            f"atrim=duration={dur_sec:.3f},asetpts=PTS-STARTPTS,"
            f"adelay={delay}:all=1,"
            f"afade=t=in:st=0:d={fade_dur:.3f},"
            f"afade=t=out:st={fade_out_st:.3f}:d={fade_dur:.3f}[{label}]"
        )
        labels.append(f"[{label}]")

    filters.append(
        "".join(labels)
        + f"amix=inputs={len(valid)}:duration=longest:dropout_transition=0:normalize=0,"
        + f"alimiter=limit=0.95,apad=whole_dur={total_ms / 1000:.3f}[out]"
    )
    cmd += [
        "-filter_complex", ";".join(filters),
        "-map", "[out]", "-t", f"{total_ms / 1000:.3f}",
        "-ar", str(int(sample_rate)), "-ac", "1", "-c:a", "pcm_s16le",
        "-progress", "pipe:1", "-nostats", "-f", "wav", out_wav
    ]
    return _run_ffmpeg_progress(cmd, total_ms, progress_callback)


def _mix_wavs_numpy(
    valid: list[tuple[str, int, int]],
    total_ms: int,
    out_wav: str,
    sample_rate: int,
    progress_callback=None
) -> bool:
    """Mix mono/stereo 16-bit PCM WAV clips into one timeline WAV.

    Returns False when the clips are not plain PCM WAVs (or when NumPy is
    unavailable) so the caller can use the FFmpeg fallback instead.
    """
    try:
        import numpy as np
    except Exception:
        return False

    total_samples = max(1, int(round(total_ms * sample_rate / 1000.0)))

    # Keep the accumulator to a reasonable size; very long timelines use
    # the streaming FFmpeg path instead.
    if total_samples > 400_000_000:
        return False

    try:
        mix = np.zeros(total_samples, dtype=np.int32)
    except MemoryError:
        return False

    count = len(valid)
    report_every = max(1, count // 100)

    try:
        for n, (path, start_ms, end_ms) in enumerate(valid):
            with wave.open(path, "rb") as wf:
                if wf.getframerate() != int(sample_rate):
                    return False
                channels = wf.getnchannels()
                if wf.getsampwidth() != 2 or channels not in (1, 2):
                    return False
                frames = wf.readframes(wf.getnframes())

            data = np.frombuffer(frames, dtype="<i2")

            if channels == 2:
                data = data.reshape(-1, 2).mean(axis=1).astype(np.int32)
            else:
                data = data.astype(np.int32)

            max_len = max(
                0,
                int(round((end_ms - start_ms) * sample_rate / 1000.0))
            )
            if max_len:
                data = data[:max_len]

            # Smooth the clip edges so adjacent voice clips never click.
            data = _apply_fade_envelope(data, int(sample_rate))

            offset = int(round(start_ms * sample_rate / 1000.0))

            if offset >= total_samples or data.size == 0:
                if progress_callback and n % report_every == 0:
                    progress_callback(min(99, int((n + 1) * 100 / count)))
                continue

            if offset < 0:
                data = data[-offset:]
                offset = 0

            data = data[: total_samples - offset]
            mix[offset:offset + data.size] += data

            if progress_callback and n % report_every == 0:
                progress_callback(min(99, int((n + 1) * 100 / count)))
    except Exception as exc:
        print(f"NumPy audio mix unavailable, falling back to FFmpeg: {exc}")
        return False

    np.clip(mix, -32768, 32767, out=mix)

    try:
        ensure_output_dir(out_wav)
        with wave.open(out_wav, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(int(sample_rate))
            wf.writeframes(mix.astype("<i2").tobytes())
    except Exception as exc:
        print(f"Could not write mixed WAV: {exc}")
        return False

    if progress_callback:
        progress_callback(100)
    return True


# =========================================================
# AUDIO FADE (smooth clip boundaries)
# =========================================================

def _apply_fade_envelope(data, sample_rate: int, fade_ms: float = 15.0):
    """Apply short fade-in/fade-out to a PCM segment so clips never click.

    A 15 ms fade on each end removes the discontinuity at clip boundaries
    without being audible, making back-to-back voice clips transition
    smoothly.
    """
    try:
        import numpy as np
    except Exception:
        return data

    if data.size == 0:
        return data
    fade_samples = max(1, int(round(sample_rate * fade_ms / 1000.0)))
    if data.size <= fade_samples * 2:
        fade_samples = max(1, data.size // 4)
    envelope = np.ones(data.size, dtype=np.float64)
    ramp = np.linspace(0.0, 1.0, fade_samples)
    envelope[:fade_samples] *= ramp
    envelope[-fade_samples:] *= ramp[::-1]
    return (data.astype(np.float64) * envelope).astype(np.int32)


def _run_ffmpeg_progress(cmd, total_ms, progress_callback=None) -> bool:
    """Run FFmpeg while forwarding percentage progress and retaining errors."""
    output_lines = []
    try:
        process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, universal_newlines=True, bufsize=1
        )
        assert process.stdout is not None
        for line in process.stdout:
            output_lines.append(line.rstrip())
            if len(output_lines) > 200:
                output_lines = output_lines[-200:]
            if "out_time_ms=" in line or "out_time_us=" in line:
                try:
                    value = int(line.split("=", 1)[1].strip())
                    total_us = max(1, int(total_ms) * 1000)
                    pct = min(99, int(value * 100 / total_us))
                    if progress_callback:
                        progress_callback(pct)
                except (ValueError, IndexError):
                    pass
        return_code = process.wait()
        if return_code != 0:
            print("FFmpeg error:\n" + "\n".join(output_lines[-80:]))
            return False
        if progress_callback:
            progress_callback(100)
        return True
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"Could not run FFmpeg: {exc}")
        return False


# =========================================================
# EXPORT DUBBED VIDEO
# =========================================================

def mix_dubbed_video(
    video_path: str,
    dubbed_audio: str,
    out_path: str,
    srt_path: Optional[str] = None,
    bgm_path: Optional[str] = None,
    resolution: str = "original",
    burn_subtitles: bool = False,
    keep_original_audio: bool = False,
    font_name: str = "Khmer OS",
    progress_callback=None,
    # New Overlay Params
    logo_path: Optional[str] = None,
    logo_x: float = 0.5,
    logo_y: float = 0.5,
    logo_scale: float = 0.2,
    running_text: Optional[dict] = None,
) -> tuple[bool, str]:

    total_ms = get_duration_ms(video_path)
    if total_ms == 0: total_ms = 1000

    inputs = ["-i", video_path, "-i", dubbed_audio]
    bgm_idx = None
    if bgm_path and os.path.exists(bgm_path):
        inputs += ["-i", bgm_path]
        bgm_idx = 2

    logo_idx = None
    if logo_path and os.path.exists(logo_path):
        inputs += ["-i", logo_path]
        logo_idx = 3 if bgm_idx else 2

    filters = []

    # 1. Video Scale & Subtitles
    vf_parts = []
    scale = {"720p": "scale=-2:720", "1080p": "scale=-2:1080", "4k": "scale=-2:2160"}.get(resolution.lower(), None)
    if scale: vf_parts.append(scale)
    if burn_subtitles and srt_path and os.path.exists(srt_path):
        escaped = srt_path.replace("\\", "/").replace(":", "\\:")
        vf_parts.append(f"subtitles='{escaped}':force_style='FontName={font_name},FontSize=20,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BackColour=&H80000000,Outline=1,Shadow=1'")

    if vf_parts:
        filters.append(f"[0:v]{','.join(vf_parts)}[vsub]")
        video_map = "[vsub]"
    else:
        video_map = "0:v"

    # 2. Logo Overlay
    if logo_idx is not None:
        # Logo X/Y expressions based on video width/height (W/H)
        x_expr = f"(W-overlay_w)*{logo_x}"
        y_expr = f"(H-overlay_h)*{logo_y}"
        # Scale logo
        filters.append(f"[{logo_idx}:v]scale=iw*{logo_scale}:ih*{logo_scale}[logo]")
        filters.append(f"[{video_map}][logo]overlay={x_expr}:{y_expr}[vlogo]")
        video_map = "[vlogo]"

    # 3. Running Text
    if running_text and running_text.get("text"):
        txt = running_text["text"].replace(":", "\\:").replace("'", "")
        fnt = running_text.get("font", "Arial")
        fsize = running_text.get("size", 36)
        color = running_text.get("color", "white").replace("#", "0x")
        # Scrolling from right to left: x = w - mod(t*speed, w+tw)
        x_expr = f"w-mod(t*200\\,w+tw)"
        y_expr = f"h-th-50"
        filters.append(f"[{video_map}]drawtext=text='{txt}':fontfile=/System/Library/Fonts/Helvetica.ttc:fontsize={fsize}:fontcolor={color}:x={x_expr}:y={y_expr}[vtext]")
        video_map = "[vtext]"

    # 4. Audio Mix
    audio_map = "[1:a]"
    if keep_original_audio:
        filters.append("[0:a][1:a]amix=inputs=2:duration=first:dropout_transition=2,volume=2[aout]")
        audio_map = "[aout]"
    else:
        filters.append("[1:a]anull[aout]")
        audio_map = "[aout]"

    if bgm_idx is not None:
        filters.append(f"[{bgm_idx}:a]volume=0.18[bgm]")
        filters.append(f"[aout][bgm]amix=inputs=2:duration=first:dropout_transition=2,volume=2[amixed]")
        audio_map = "[amixed]"

    cmd = [ffmpeg_bin(), "-y"] + inputs
    filter_complex = ";".join(filters)
    cmd += ["-filter_complex", filter_complex]
    cmd += ["-map", video_map, "-map", audio_map,
            "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-c:a", "aac", "-b:a", "192k", "-shortest",
            "-progress", "pipe:1", out_path]

    try:
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, universal_newlines=True)
        output_lines = []
        for line in process.stdout:
            output_lines.append(line)
            if "out_time_ms=" in line:
                try:
                    time_us = int(line.split("=")[1])
                    pct = min(99, int((time_us / (total_ms * 1000)) * 100))
                    if progress_callback: progress_callback(pct)
                except ValueError: pass
        process.wait()
        if progress_callback: progress_callback(100)
        if process.returncode != 0: return False, "".join(output_lines[-1500:])
        return True, "Export completed successfully."
    except Exception as e:
        return False, str(e)