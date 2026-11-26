import os
import glob
from typing import Optional
from app import ffmpeg_utils
from app.models import Subtitle

class Exporter:

    def __init__(self, work_dir: str = "output"):
        self.work_dir = work_dir
        os.makedirs(self.work_dir, exist_ok=True)

    # ---------------------------------------------------------
    # EXPORT CAPABILITY CHECK
    # ---------------------------------------------------------

    def check_export_support(
        self,
        burn_subtitles: bool = False
    ):
        """
        Fail before spending time on audio/video work when the
        selected FFmpeg build cannot handle the requested export.
        """
        if burn_subtitles and not ffmpeg_utils.has_filter("subtitles"):
            raise RuntimeError(
                ffmpeg_utils.subtitle_filter_error()
            )

    # ---------------------------------------------------------
    # CLEAN TEMPORARY FILES
    # ---------------------------------------------------------

    def clean_temp_files(self):
        """Delete intermediate files created during export or preview."""
        patterns = [
            os.path.join(self.work_dir, "_dub_track.wav"),
            os.path.join(self.work_dir, "_preview_dub*.wav"),
            os.path.join(self.work_dir, "_burn.srt"),
            os.path.join(self.work_dir, "audio", "_chunk_*"),
            os.path.join(self.work_dir, "audio", "_concat.txt")
        ]

        for pattern in patterns:
            for file_path in glob.glob(pattern):
                try:
                    if os.path.isfile(file_path):
                        os.remove(file_path)
                except OSError:
                    pass

    # ---------------------------------------------------------
    # EXPORT SRT SUBTITLES
    # ---------------------------------------------------------

    def export_srt(
        self,
        subtitles: list[Subtitle],
        out_path: str
    ) -> str:

        directory = os.path.dirname(os.path.abspath(out_path))
        os.makedirs(directory, exist_ok=True)

        ffmpeg_utils.write_srt(subtitles, out_path)

        if not os.path.isfile(out_path):
            raise RuntimeError(
                f"Failed to create subtitle file: {out_path}"
            )

        return out_path

    # ---------------------------------------------------------
    # EXPORT AUDIO
    # ---------------------------------------------------------

    def export_audio(
        self,
        video_path: str,
        out_path: str,
        fmt: str = "mp3"
    ) -> str:
        if not os.path.isfile(video_path):
            raise FileNotFoundError(
                f"Video file not found: {video_path}"
            )

        directory = os.path.dirname(os.path.abspath(out_path))
        os.makedirs(directory, exist_ok=True)

        if fmt.lower() == "wav":
            ok = ffmpeg_utils.convert_to_wav(
                video_path,
                out_path
            )
        else:
            ok = ffmpeg_utils.extract_audio_mp3(
                video_path,
                out_path
            )

        if not ok:
            raise RuntimeError(
                f"Failed to export audio: {out_path}"
            )

        return out_path

    # ---------------------------------------------------------
    # BUILD DUBBED AUDIO TRACK
    # ---------------------------------------------------------

    def build_dub_track(
        self,
        segments: list[tuple[str, int, int]],
        total_ms: int,
        out_wav: str,
        progress_callback=None
    ) -> str:

        directory = os.path.dirname(os.path.abspath(out_wav))
        os.makedirs(directory, exist_ok=True)

        ok = ffmpeg_utils.concat_audio_with_timing(
            segments,
            total_ms,
            out_wav,
            progress_callback=progress_callback
        )

        if not ok:
            raise RuntimeError(
                "Failed to build dubbed audio track."
            )

        return out_wav

    # ---------------------------------------------------------
    # EXPORT FINAL VIDEO
    # ---------------------------------------------------------

    def export_video(
        self,
        video_path: str,
        dub_wav: str,
        out_path: str,
        subtitles: Optional[list[Subtitle]] = None,
        bgm_path: Optional[str] = None,
        resolution: str = "original",
        burn_subtitles: bool = False,
        keep_original_audio: bool = False,
        khmer_font: str = "Khmer OS",
        progress_callback=None,
        logo_path: Optional[str] = None,
        logo_x: float = 0.5,
        logo_y: float = 0.5,
        logo_scale: float = 0.2,
        running_text: Optional[dict] = None,
    ) -> str:
        srt_path = None
        if subtitles and burn_subtitles:
            srt_path = os.path.join(self.work_dir, "_burn.srt")
            ffmpeg_utils.write_srt(subtitles, srt_path)

        ok, msg = ffmpeg_utils.mix_dubbed_video(
            video_path=video_path,
            dubbed_audio=dub_wav,
            out_path=out_path,
            srt_path=srt_path,
            bgm_path=bgm_path,
            resolution=resolution,
            burn_subtitles=burn_subtitles,
            keep_original_audio=keep_original_audio,
            font_name=khmer_font,
            progress_callback=progress_callback,
            logo_path=logo_path,
            logo_x=logo_x,
            logo_y=logo_y,
            logo_scale=logo_scale,
            running_text=running_text,
        )
        if not ok:
            raise RuntimeError(f"FFmpeg export failed:\n{msg}")
        return out_path
