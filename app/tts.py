
"""
Unified TTS Engine - WAV Edition
Samray Dubber Pro

Features:
- Edge TTS automatic language detection and voice matching.
- Voice validation and automatic replacement.
- Long text chunking.
- Retry with exponential backoff.
- Edge TTS, ElevenLabs, OpenAI, Piper and XTTS.
- All engines return WAV files.
- WAV PCM signed 16-bit, 44.1 kHz, mono.
- Automatic temporary-file cleanup.
"""

import asyncio
import os
import re
import shutil
import subprocess
import tempfile
import time
import uuid

from dataclasses import dataclass
from typing import Optional


# ============================================================
# LANGUAGE HELPERS
# ============================================================

LANG_NAME_TO_CODE = {
    "Khmer": "km",
    "English": "en",
    "Thai": "th",
    "Chinese": "zh",
    "Japanese": "ja",
    "Korean": "ko",
    "Vietnamese": "vi",

    "km": "km",
    "en": "en",
    "th": "th",
    "zh": "zh",
    "ja": "ja",
    "ko": "ko",
    "vi": "vi",
}

_RE_KHMER = re.compile(r"[\u1780-\u17FF]")
_RE_THAI = re.compile(r"[\u0E00-\u0E7F]")
_RE_HAN = re.compile(r"[\u4E00-\u9FFF]")
_RE_HIRA = re.compile(r"[\u3040-\u309F]")
_RE_KATA = re.compile(r"[\u30A0-\u30FF]")
_RE_HANGUL = re.compile(r"[\uAC00-\uD7AF]")
_RE_VIET = re.compile(r"[ăâđêôơưĂÂĐÊÔƠƯ]")
_RE_LATIN = re.compile(r"[A-Za-z]")

_RE_EMOJI = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U0001F1E6-\U0001F1FF"
    "]+",
    flags=re.UNICODE,
)


def _detect_lang(text: str) -> Optional[str]:

    if _RE_KHMER.search(text):
        return "km"

    if _RE_THAI.search(text):
        return "th"

    if _RE_HIRA.search(text) or _RE_KATA.search(text):
        return "ja"

    if _RE_HANGUL.search(text):
        return "ko"

    if _RE_HAN.search(text):
        return "zh"

    if _RE_VIET.search(text):
        return "vi"

    if _RE_LATIN.search(text):
        return "en"

    return None


_NETWORK_ERROR_MARKERS = (
    "cannot connect to host",
    "nodename nor servname",
    "name or service not known",
    "temporary failure in name resolution",
    "getaddrinfo failed",
    "clientconnectorerror",
    "clientconnector dnserror",
    "serverdisconnectederror",
    "network is unreachable",
    "connection reset",
    "connection refused",
    "timed out",
    "timeout",
    "ssl",
)


def is_network_error(message) -> bool:
    """True when a TTS failure looks like a connectivity problem."""
    text = str(message).lower()
    return any(marker in text for marker in _NETWORK_ERROR_MARKERS)


def _normalize_text(text: str) -> str:

    if not text:
        return ""

    text = _RE_EMOJI.sub(" ", text)

    text = re.sub(
        r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]",
        " ",
        text
    )

    text = text.replace("\u00A0", " ")

    text = re.sub(r"[ \t]+", " ", text)

    text = re.sub(r"\n{2,}", "\n", text)

    return text.strip()


# ============================================================
# VOICE CACHE
# ============================================================

_VOICE_CACHE = []
_VOICE_CACHE_AT = 0.0

_VOICE_CACHE_TTL = 60 * 60 * 12


def _ensure_voice_cache(force=False):

    global _VOICE_CACHE, _VOICE_CACHE_AT

    if (
        not force
        and _VOICE_CACHE
        and time.time() - _VOICE_CACHE_AT < _VOICE_CACHE_TTL
    ):
        return _VOICE_CACHE

    try:

        import edge_tts

        async def fetch():
            return await edge_tts.list_voices()

        _VOICE_CACHE = asyncio.run(fetch()) or []

        _VOICE_CACHE_AT = time.time()

    except Exception:
        pass

    return _VOICE_CACHE


def _voice_exists(voice_id):

    voices = _ensure_voice_cache()

    if not voices:
        return True

    return any(
        v.get("ShortName") == voice_id
        for v in voices
    )


def _voice_locale(voice_id):

    parts = voice_id.split("-")

    return "-".join(parts[:2]) if len(parts) >= 2 else ""


def _pick_voice_for_lang(lang_code):

    voices = _ensure_voice_cache()

    if not voices or not lang_code:
        return None

    prefix = lang_code.lower() + "-"

    candidates = [
        v for v in voices
        if v.get("Locale", "").lower().startswith(prefix)
    ]

    if not candidates:
        return None

    multilingual = [
        v for v in candidates
        if "Multilingual" in v.get("ShortName", "")
    ]

    return (
        multilingual or candidates
    )[0]["ShortName"]


# ============================================================
# TTS REQUEST
# ============================================================

@dataclass
class TTSRequest:

    text: str

    voice_id: str

    engine: str = "edge"

    speed: float = 1.0

    pitch: float = 0.0

    volume: float = 1.0

    emotion: str = "neutral"

    style: str = "general"

    api_key: str = ""

    language: str = "km"


# ============================================================
# TTS ENGINE
# ============================================================

class TTSEngine:

    def __init__(self, output_dir="output/audio"):

        self.output_dir = output_dir

        os.makedirs(
            self.output_dir,
            exist_ok=True
        )

        self.sample_rate = 44100

        self.channels = 1

        self.audio_codec = "pcm_s16le"

    # ========================================================
    # OUTPUT PATH
    # ========================================================

    def _wav_path(self):

        return os.path.join(
            self.output_dir,
            f"tts_{uuid.uuid4().hex[:10]}.wav"
        )

    def _temp_path(self, extension):

        return os.path.join(
            self.output_dir,
            f"_temp_{uuid.uuid4().hex[:10]}.{extension}"
        )

    # ========================================================
    # FFMPEG DETECTION
    # ========================================================

    def _get_ffmpeg(self):

        ffmpeg = shutil.which("ffmpeg")

        if not ffmpeg:

            raise RuntimeError(
                "FFmpeg not found.\n"
                "Please install FFmpeg and add it to PATH."
            )

        return ffmpeg

    # ========================================================
    # CONVERT AUDIO TO WAV
    # ========================================================

    def _convert_to_wav(self, input_path):

        if not os.path.isfile(input_path):

            raise FileNotFoundError(
                f"Audio file not found: {input_path}"
            )

        ffmpeg = self._get_ffmpeg()

        output_path = self._wav_path()

        command = [
            ffmpeg,
            "-hide_banner",
            "-loglevel", "error",
            "-y",

            "-i", input_path,

            "-vn",

            "-ac", str(self.channels),

            "-ar", str(self.sample_rate),

            "-c:a", self.audio_codec,

            output_path
        ]

        try:

            result = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False
            )

            if result.returncode != 0:

                raise RuntimeError(
                    "FFmpeg WAV conversion failed:\n"
                    + result.stderr[-2000:]
                )

            if (
                not os.path.isfile(output_path)
                or os.path.getsize(output_path) <= 44
            ):

                raise RuntimeError(
                    "WAV conversion produced an empty file."
                )

            return output_path

        except Exception:

            if os.path.exists(output_path):
                os.remove(output_path)

            raise

    # ========================================================
    # SYNTHESIZE ROUTER
    # ========================================================

    def synthesize(self, req: TTSRequest):

        engine = (req.engine or "edge").lower()

        if engine == "edge":
            return self._edge(req)

        if engine == "elevenlabs":
            return self._elevenlabs(req)

        if engine == "openai":
            return self._openai(req)

        if engine == "piper":
            return self._piper(req)

        if engine in ("xtts", "coqui"):
            return self._xtts(req)

        if engine == "local":
            return self._local(req)

        raise ValueError(
            f"Unknown TTS engine: {engine}"
        )

    # ========================================================
    # EDGE VOICE RESOLUTION
    # ========================================================

    def _resolve_edge_voice(self, req, text):

        voice = (req.voice_id or "").strip()
        text_lang = _detect_lang(text)
        req_lang = LANG_NAME_TO_CODE.get(
            req.language,
            req.language or ""
        ).lower()

        target = text_lang or req_lang
        if not voice:
            replacement = (
                _pick_voice_for_lang(target)
                if target else None
            )
            return replacement or "en-US-AvaMultilingualNeural"

        if not _voice_exists(voice):
            replacement = (
                _pick_voice_for_lang(target)
                if target else None
            )
            if replacement:
                return replacement
            raise ValueError(
                f"Voice '{voice}' is not available. "
                f"Language: {target}"
            )

        if target:

            voice_lang = (
                _voice_locale(voice)
                .split("-")[0]
                .lower()
            )

            if (
                voice_lang
                and voice_lang != target
                and "Multilingual" not in voice
            ):

                replacement = _pick_voice_for_lang(target)

                if replacement:
                    return replacement

        return voice

    # ========================================================
    # EDGE TTS
    # ========================================================

    def _edge(self, req):

        import edge_tts

        text = _normalize_text(req.text)

        if not text:

            raise ValueError(
                "Empty text. Nothing to synthesize."
            )

        voice_id = self._resolve_edge_voice(
            req,
            text
        )

        rate = self._fmt_percent(req.speed)

        volume = self._fmt_percent(req.volume)

        pitch = self._fmt_hz(req.pitch)

        chunks = self._split_for_tts(
            text,
            max_chars=2800
        )

        mp3_path = self._temp_path("mp3")

        async def synth_one(part):

            communicate = edge_tts.Communicate(
                part,
                voice_id,
                rate=rate,
                pitch=pitch,
                volume=volume
            )

            buffer = bytearray()

            async for message in communicate.stream():

                if message.get("type") == "audio":

                    buffer.extend(
                        message["data"]
                    )

            return bytes(buffer)

        try:

            audio_parts = []

            for index, part in enumerate(chunks):

                data = self._edge_with_retry(
                    synth_one,
                    part,
                    voice_id,
                    text,
                    index,
                    len(chunks)
                )

                if not data:

                    raise RuntimeError(
                        f"No audio received from Edge TTS. "
                        f"Voice: {voice_id}. "
                        f"Language: {_detect_lang(text)}. "
                        f"Text: {text[:80]!r}"
                    )

                audio_parts.append(data)

            if len(audio_parts) == 1:

                with open(mp3_path, "wb") as file:
                    file.write(audio_parts[0])

            else:

                self._concat_mp3_chunks(
                    audio_parts,
                    mp3_path
                )

            return self._convert_to_wav(mp3_path)

        finally:

            if os.path.exists(mp3_path):
                os.remove(mp3_path)

    # ========================================================
    # EDGE RETRY
    # ========================================================

    def _edge_with_retry(
        self,
        synth_fn,
        text_part,
        voice_id,
        full_text,
        part_index,
        total,
        attempts=4
    ):

        last_error = None

        for attempt in range(1, attempts + 1):

            try:

                data = asyncio.run(
                    synth_fn(text_part)
                )

                if data:
                    return data

                last_error = RuntimeError(
                    "Empty audio payload"
                )

            except Exception as error:

                last_error = error

            if attempt < attempts:

                delay = 0.6 * (2 ** (attempt - 1))

                # Give DNS/VPN/network hiccups a little more time.
                if is_network_error(last_error):
                    delay = max(delay, 2.0 * attempt)

                time.sleep(delay)

        hint = ""

        if is_network_error(last_error):

            hint = (
                "\n\nCannot reach the Microsoft Edge TTS service. "
                "Check your internet connection, VPN, firewall, or DNS "
                "settings, then try again."
            )

        raise RuntimeError(
            f"Edge TTS failed after {attempts} attempts.\n"
            f"Voice: {voice_id}\n"
            f"Chunk: {part_index + 1}/{total}\n"
            f"Language: {_detect_lang(full_text)}\n"
            f"Error: {last_error}\n"
            f"Text: {full_text[:80]!r}"
            f"{hint}"
        )

    # ========================================================
    # CONCATENATE MP3 CHUNKS
    # ========================================================

    def _concat_mp3_chunks(self, parts, output_path):

        ffmpeg = self._get_ffmpeg()

        temp_dir = tempfile.mkdtemp(
            prefix="tts_chunks_",
            dir=self.output_dir
        )

        try:

            list_path = os.path.join(
                temp_dir,
                "concat.txt"
            )

            chunk_paths = []

            for index, data in enumerate(parts):

                path = os.path.join(
                    temp_dir,
                    f"chunk_{index:04d}.mp3"
                )

                with open(path, "wb") as file:
                    file.write(data)

                chunk_paths.append(path)

            with open(
                list_path,
                "w",
                encoding="utf-8"
            ) as file:

                for path in chunk_paths:

                    safe_path = (
                        os.path.abspath(path)
                        .replace("\\", "/")
                        .replace("'", "'\\''")
                    )

                    file.write(
                        f"file '{safe_path}'\n"
                    )

            result = subprocess.run(
                [
                    ffmpeg,
                    "-hide_banner",
                    "-loglevel", "error",
                    "-y",
                    "-f", "concat",
                    "-safe", "0",
                    "-i", list_path,
                    "-c", "copy",
                    output_path
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            if result.returncode != 0:

                raise RuntimeError(
                    "MP3 concatenation failed:\n"
                    + result.stderr[-2000:]
                )

            if not os.path.isfile(output_path):

                raise RuntimeError(
                    "MP3 concatenation produced no output."
                )

        finally:

            shutil.rmtree(
                temp_dir,
                ignore_errors=True
            )

    # ========================================================
    # ELEVENLABS
    # ========================================================

    def _elevenlabs(self, req):

        from elevenlabs.client import ElevenLabs

        text = _normalize_text(req.text)

        if not text:
            raise ValueError("Empty text.")

        mp3_path = self._temp_path("mp3")

        client = ElevenLabs(
            api_key=(
                req.api_key
                or os.environ.get("ELEVENLABS_API_KEY", "")
            )
        )

        try:

            audio = client.text_to_speech.convert(
                voice_id=req.voice_id,
                text=text,
                model_id="eleven_multilingual_v2",
                output_format="mp3_44100_128",
                voice_settings={
                    "stability": 0.5,
                    "similarity_boost": 0.75,
                    "style": 0.0,
                    "use_speaker_boost": True
                }
            )

            with open(mp3_path, "wb") as file:

                for chunk in audio:

                    if chunk:
                        file.write(chunk)

            return self._convert_to_wav(mp3_path)

        finally:

            if os.path.exists(mp3_path):
                os.remove(mp3_path)

    # ========================================================
    # OPENAI
    # ========================================================

    def _openai(self, req):

        from openai import OpenAI

        text = _normalize_text(req.text)

        if not text:
            raise ValueError("Empty text.")

        mp3_path = self._temp_path("mp3")

        client = OpenAI(
            api_key=(
                req.api_key
                or os.environ.get("OPENAI_API_KEY", "")
            )
        )

        voice = (
            req.voice_id
            if req.voice_id in (
                "alloy",
                "echo",
                "fable",
                "onyx",
                "nova",
                "shimmer"
            )
            else "nova"
        )

        try:

            with client.audio.speech.with_streaming_response.create(
                model="tts-1-hd",
                voice=voice,
                input=text,
                speed=req.speed,
                response_format="mp3"
            ) as response:

                response.stream_to_file(mp3_path)

            return self._convert_to_wav(mp3_path)

        finally:

            if os.path.exists(mp3_path):
                os.remove(mp3_path)

    # ========================================================
    # PIPER
    # ========================================================

    def _piper(self, req):

        out_path = self._wav_path()

        piper = shutil.which("piper")

        if not piper:

            raise RuntimeError(
                "Piper binary not found in PATH."
            )

        text = _normalize_text(req.text)

        if not text:
            raise ValueError("Empty text.")

        try:

            process = subprocess.run(
                [
                    piper,
                    "--model", req.voice_id,
                    "--output_file", out_path
                ],
                input=text.encode("utf-8"),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )

            if process.returncode != 0:

                raise RuntimeError(
                    process.stderr.decode(
                        "utf-8",
                        errors="ignore"
                    )
                )

            if not os.path.isfile(out_path):
                raise RuntimeError("Piper did not create WAV.")

            # Normalize Piper WAV to standard output format.
            normalized_path = self._convert_to_wav(out_path)

            return normalized_path

        finally:

            if os.path.exists(out_path):
                os.remove(out_path)

    # ========================================================
    # XTTS / COQUI
    # ========================================================

    def _xtts(self, req):

        try:

            from TTS.api import TTS

        except ImportError:

            raise RuntimeError(
                "Coqui TTS not installed. "
                "Run: pip install TTS"
            )

        text = _normalize_text(req.text)

        if not text:
            raise ValueError("Empty text.")

        out_path = self._wav_path()

        try:

            tts = TTS(
                "tts_models/multilingual/multi-dataset/xtts_v2"
            )

            tts.tts_to_file(
                text=text,
                speaker=req.voice_id,
                language=LANG_NAME_TO_CODE.get(
                    req.language,
                    req.language
                ),
                file_path=out_path,
                speed=req.speed
            )

            normalized_path = self._convert_to_wav(
                out_path
            )

            return normalized_path

        finally:

            if os.path.exists(out_path):
                os.remove(out_path)

    # ========================================================
    # LOCAL ENGINE
    # ========================================================

    def _local(self, req):

        raise RuntimeError(
            "Local AI voice engine is not configured. "
            "Implement TTSEngine._local() with your model."
        )

    # ========================================================
    # FORMATTING HELPERS
    # ========================================================

    @staticmethod
    def _fmt_percent(value):

        try:

            pct = int(
                round((float(value) - 1.0) * 100)
            )

        except (TypeError, ValueError):

            pct = 0

        pct = max(-100, min(200, pct))

        return f"{pct:+d}%"

    @staticmethod
    def _fmt_hz(value):

        try:

            hz = int(
                round(float(value) * 10)
            )

        except (TypeError, ValueError):

            hz = 0

        hz = max(-500, min(500, hz))

        return f"{hz:+d}Hz"

    # ========================================================
    # LONG TEXT SPLITTER
    # ========================================================

    @staticmethod
    def _split_for_tts(text, max_chars=2800):

        if len(text) <= max_chars:
            return [text]

        sentences = re.split(
            r"(?<=[.!?។])\s+",
            text
        )

        chunks = []

        buffer = ""

        for sentence in sentences:

            if not sentence:
                continue

            candidate = (
                f"{buffer} {sentence}".strip()
                if buffer else sentence
            )

            if len(candidate) <= max_chars:

                buffer = candidate

            else:

                if buffer:
                    chunks.append(buffer)

                buffer = sentence

        if buffer:
            chunks.append(buffer)

        output = []

        for chunk in chunks:

            while len(chunk) > max_chars:

                output.append(
                    chunk[:max_chars]
                )

                chunk = chunk[max_chars:]

            if chunk:
                output.append(chunk)

        return output


# ============================================================
# PUBLIC EDGE VOICE HELPER
# ============================================================

def list_edge_voices(language_prefix=""):

    # Reuse the shared cache so switching presets does not refetch the
    # voice list (or randomly lose voices when a fetch fails).
    voices = _ensure_voice_cache()

    output = []

    for voice in voices:

        if (
            language_prefix
            and not voice["ShortName"].startswith(
                language_prefix
            )
        ):
            continue

        output.append({
            "name": voice["ShortName"],
            "gender": voice["Gender"],
            "locale": voice["Locale"]
        })

    return output
