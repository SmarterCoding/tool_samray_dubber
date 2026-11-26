
import os
import sys
from faster_whisper import WhisperModel

def format_timestamp(seconds):
    milliseconds = round(seconds * 1000)

    hours = milliseconds // 3600000
    milliseconds %= 3600000

    minutes = milliseconds // 60000
    milliseconds %= 60000

    secs = milliseconds // 1000
    milliseconds %= 1000

    return (
        f"{hours:02}:{minutes:02}:"
        f"{secs:02},{milliseconds:03}"
    )


def transcribe_video(video_path):
    if not os.path.isfile(video_path):
        print("Video file not found!")
        return

    output_path = os.path.splitext(video_path)[0] + ".srt"

    print("Loading Faster-Whisper model...")

    model = WhisperModel(
        "large-v3",
        device="auto",
        compute_type="auto"
    )

    print("Transcribing Chinese video...")

    segments, info = model.transcribe(
        video_path,
        language="zh",
        task="transcribe",
        beam_size=5,
        vad_filter=True
    )

    print("Detected language:", info.language)
    print("Generating SRT...")

    with open(output_path, "w", encoding="utf-8-sig") as f:

        for index, segment in enumerate(segments, start=1):

            start = format_timestamp(segment.start)
            end = format_timestamp(segment.end)

            text = segment.text.strip()

            if not text:
                continue

            f.write(f"{index}\n")
            f.write(f"{start} --> {end}\n")
            f.write(f"{text}\n\n")

            print(f"{index}: {text}")

    print("\nCompleted!")
    print("SRT file:", output_path)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python transcribe_chinese.py video.mp4")
    else:
        transcribe_video(sys.argv[1])
