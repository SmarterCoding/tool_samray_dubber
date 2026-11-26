# SAMRAY DUBBER PRO

Professional desktop video dubbing and subtitle studio built with **Python 3.11+**, **PySide6**, **FFmpeg**, **faster-whisper**, and **Edge TTS**.

## Features

- Four-panel dark studio workspace (video preview, subtitle editor, settings, timeline)
- 9:16 / 16:9 video preview with playback controls
- Subtitle table with Khmer Unicode support, editing, split/merge, search, gender
- Multi-track timeline with drag/resize, zoom, snapping, playhead, waveform
- Voice presets with speed, pitch, volume, emotion, style
- Edge TTS, ElevenLabs, OpenAI TTS, Piper, XTTS/Coqui, local hook
- faster-whisper speech recognition and pluggable translation
- FFmpeg export to MP4, SRT, MP3, WAV
- SQLite project storage with auto-save

## Installation

```bash
# 1. FFmpeg (required)
# Windows: winget install ffmpeg  |  macOS: brew install ffmpeg-full
# Ubuntu: sudo apt install ffmpeg

# 2. Python dependencies
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 3. Run
python main.py
```

### macOS: burning subtitles

Subtitle burn-in uses FFmpeg's `subtitles` filter, which needs **libass**.
The regular Homebrew `ffmpeg` bottle may be built without it, while
`ffmpeg-full` includes it:

```bash
brew install ffmpeg-full
```

`ffmpeg-full` is keg-only, but SAMRAY DUBBER PRO automatically prefers
`/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg` (or `/usr/local/...` on Intel).
To use a different build, set:

```bash
export SAMRAY_FFMPEG=/path/to/ffmpeg
export SAMRAY_FFPROBE=/path/to/ffprobe
```
