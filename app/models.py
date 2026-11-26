from dataclasses import dataclass, field


@dataclass
class Subtitle:
    id: int = 0
    idx: int = 0
    start_ms: int = 0
    end_ms: int = 2000
    text: str = ""
    gender: str = "Female"
    audio_path: str = ""
    selected: bool = True
    monologue: bool = False


@dataclass
class VoicePreset:
    id: int = 0
    name: str = "New Preset"
    engine: str = "edge"
    voice_id: str = "km-KH-PisethNeural"
    gender: str = "Female"
    speed: float = 1.0
    pitch: float = 0.0
    volume: float = 1.0
    emotion: str = "neutral"
    style: str = "general"


@dataclass
class TimelineClip:
    track: int              # 0=video, 1=subtitle, 2=voice, 3=music
    start_ms: int
    end_ms: int
    label: str = ""
    color: str = "#2685FF"
    waveform: list = field(default_factory=list)
    subtitle_id: int = -1
    source_path: str = ""