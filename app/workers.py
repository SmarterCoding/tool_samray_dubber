import os
import asyncio
import socket
import traceback
from PySide6.QtCore import QThread, Signal

from app.asr import transcribe
from app.translator import Translator
from app.tts import TTSEngine, TTSRequest, is_network_error
from app.exporter import Exporter


class ASRWorker(QThread):
    progress = Signal(str)
    progress_percent = Signal(int)          # NEW
    finished = Signal(object)
    error = Signal(str)

    def __init__(self, audio_path: str, model_size: str = "base",
                 device: str = "auto", language: str | None = None):
        super().__init__()
        self.audio_path = audio_path
        self.model_size = model_size
        self.device = device
        self.language = language

    def run(self):
        try:
            result = transcribe(
                self.audio_path,
                self.model_size,
                self.device,
                self.language,
                progress=lambda m: self.progress.emit(m),
                progress_percent=lambda p: self.progress_percent.emit(p),
            )
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(f"{e}\n{traceback.format_exc()}")

class TranslateWorker(QThread):
    progress = Signal(str)
    progress_percent = Signal(int)
    item_translated = Signal(int, str)   # <-- NEW SIGNAL
    finished = Signal(list)
    error = Signal(str)

    def __init__(
        self,
        texts: list[str],
        source_lang: str,
        target_lang: str,
        provider: str,
        api_key: str,
        delay_sec: float = 0.25,
        gemini_api_key: str = "",
        gemini_model: str = "gemini-3.1-flash-lite",
        gemini_batch_size: int = 20,
    ):
        super().__init__()
        self.texts = texts
        self.source_lang = source_lang
        self.target_lang = target_lang
        self.provider = provider
        self.api_key = api_key
        self.delay_sec = delay_sec
        self.gemini_api_key = gemini_api_key
        self.gemini_model = gemini_model
        self.gemini_batch_size = gemini_batch_size

    def run(self):
        try:
            tr = Translator(
                provider=self.provider,
                api_key=self.api_key,
                delay_sec=self.delay_sec,
                gemini_api_key=self.gemini_api_key,
                gemini_model=self.gemini_model,
                gemini_batch_size=self.gemini_batch_size,
            )
            result = tr.translate_batch(
                self.texts,
                self.source_lang,
                self.target_lang,
                progress=lambda m: self.progress.emit(m),
                progress_percent=lambda p: self.progress_percent.emit(p),
                on_item_done=lambda idx, text: self.item_translated.emit(idx, text), # <-- CONNECT CALLBACK
            )
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(f"{e}\n{traceback.format_exc()}")

class TTSWorker(QThread):
    progress = Signal(str)
    progress_percent = Signal(int)
    item_done = Signal(int, str)
    item_failed = Signal(int, str)
    finished = Signal(list)
    error = Signal(str)

    def __init__(self, items: list[tuple[int, str]], req_template: TTSRequest):
        super().__init__()
        self.items = items
        self.req_template = req_template
        self._stop = False
        self.network_error = ""

    def stop(self):
        self._stop = True

    def _check_edge_connection(self) -> str:
        """Return an error message when Edge TTS cannot even be resolved."""
        if (self.req_template.engine or "edge").lower() != "edge":
            return ""
        if any(os.environ.get(name) for name in (
            "HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY",
            "https_proxy", "http_proxy", "all_proxy",
        )):
            return ""

        host = "speech.platform.bing.com"
        try:
            import edge_tts.constants as edge_constants
            host = edge_constants.BASE_URL.split("/", 1)[0]
        except Exception:
            pass

        try:
            socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        except OSError as error:
            return (
                "Cannot reach Microsoft Edge TTS: DNS lookup failed.\n\n"
                "Check your internet connection, VPN, firewall, or DNS "
                "settings, then try again.\n\n"
                f"Host: {host}\n"
                f"Details: {error}"
            )
        return ""

    def run(self):
        # FIX: macOS asyncio compatibility for QThreads
        asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())

        engine = TTSEngine()
        results = []
        failures = []
        try:
            connection_error = self._check_edge_connection()
            if connection_error:
                self.error.emit(connection_error)
                return

            total = len(self.items)
            self.progress_percent.emit(0)
            for n, (idx, text) in enumerate(self.items):
                if self._stop:
                    break
                self.progress.emit(f"Generating voice {n + 1}/{total} …")
                req = TTSRequest(
                    text=text,
                    voice_id=self.req_template.voice_id,
                    engine=self.req_template.engine,
                    speed=self.req_template.speed,
                    pitch=self.req_template.pitch,
                    volume=self.req_template.volume,
                    emotion=self.req_template.emotion,
                    style=self.req_template.style,
                    api_key=self.req_template.api_key,
                    language=self.req_template.language,
                )
                try:
                    path = engine.synthesize(req)
                    results.append((idx, path))
                    self.item_done.emit(idx, path)
                except Exception as e:
                    message = str(e)
                    failures.append((idx, message))
                    self.item_failed.emit(idx, message)

                    # Do not spend an hour retrying 1188 lines when the
                    # network is down. Stop after the first network error.
                    if is_network_error(message):
                        self.network_error = message
                        break

                self.progress_percent.emit(int((n + 1) / total * 100))

            if results:
                self.finished.emit(results)

            if self.network_error:
                self.error.emit(
                    "Voice generation stopped because the TTS service "
                    "could not be reached.\n\n"
                    f"{len(results)} clip(s) were generated before the "
                    "connection failed.\n\n"
                    f"First error:\n{self.network_error}"
                )
            elif not results and failures:
                self.error.emit(
                    f"All {total} voice generations failed.\n\n"
                    f"First error:\n{failures[0][1]}"
                )
        except Exception as e:
            self.error.emit(f"{e}\n{traceback.format_exc()}")

class DubTrackWorker(QThread):
    progress = Signal(str)
    progress_percent = Signal(int)  # <-- NEW
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, exporter: Exporter, segments: list,
                 total_ms: int, out_path: str):
        super().__init__()
        self.exporter = exporter
        self.segments = segments
        self.total_ms = total_ms
        self.out_path = out_path

    def run(self):
        try:
            self.progress.emit("Building dubbed preview track …")
            self.exporter.build_dub_track(
                self.segments,
                self.total_ms,
                self.out_path,
                progress_callback=lambda p: self.progress_percent.emit(p)
            )
            self.finished.emit(self.out_path)
        except Exception as e:
            self.error.emit(f"{e}\n{traceback.format_exc()}")

class ExportWorker(QThread):
    progress = Signal(str)
    progress_percent = Signal(int)
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, exporter: Exporter, video_path: str, segments: list,
                 total_ms: int, out_path: str, subtitles: list,
                 bgm_path: str, resolution: str, burn: bool,
                 keep_original: bool):
        super().__init__()
        self.exporter = exporter
        self.video_path = video_path
        self.segments = segments
        self.total_ms = total_ms
        self.out_path = out_path
        self.subtitles = subtitles
        self.bgm_path = bgm_path
        self.resolution = resolution
        self.burn = burn
        self.keep_original = keep_original

    def run(self):
        dub_wav = os.path.join(self.exporter.work_dir, "_dub_track.wav")
        try:
            self.progress.emit("Cleaning up old temporary files …")
            self.exporter.clean_temp_files()

            self.progress.emit("Building dubbed audio track …")
            self.exporter.build_dub_track(self.segments, self.total_ms, dub_wav)

            self.progress.emit("Encoding final video with FFmpeg …")

            self.exporter.export_video(
                self.video_path, dub_wav, self.out_path,
                subtitles=self.subtitles,
                bgm_path=self.bgm_path,
                resolution=self.resolution,
                burn_subtitles=self.burn,
                keep_original_audio=self.keep_original,
                progress_callback=lambda p: self.progress_percent.emit(p),
            )
            self.finished.emit(self.out_path)
        except Exception as e:
            self.error.emit(f"{e}\n{traceback.format_exc()}")
        finally:
            self.exporter.clean_temp_files()