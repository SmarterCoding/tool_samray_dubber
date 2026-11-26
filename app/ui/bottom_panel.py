
import os
import re
import wave
from pathlib import Path

import qtawesome as qta

from PySide6.QtCore import Qt, QRect, QPoint, Signal, QSize
from PySide6.QtGui import (
    QPainter, QColor, QPen, QFont, QBrush, QPolygon,
    QFontDatabase, QKeySequence, QShortcut
)
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QCheckBox, QWidget, QScrollArea, QFileDialog, QMessageBox,
    QDialog, QDialogButtonBox, QTextEdit
)

from app.models import TimelineClip
from app.theme import (
    PANEL, PANEL_ALT, BORDER, PRIMARY, SECONDARY, SUCCESS,
    WARNING, TEXT, TEXT_MUTED, BG,
)
from app.ui.waveform import generate_waveform


TRACK_NAMES = ["VIDEO", "SUBTITLES", "VOICE", "MUSIC / SFX"]
TRACK_COLORS = ["#3B82F6", "#8B5CF6", "#10B981", "#F59E0B"]

TRACK_HEIGHT = 48
RULER_HEIGHT = 28
MIN_CLIP_MS = 100

VIDEO_EXTENSIONS = (
    ".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v"
)

AUDIO_EXTENSIONS = (
    ".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"
)


def _pick_khmer_family():
    families = set(QFontDatabase.families())

    for family in (
        "Khmer OS",
        "Khmer OS System",
        "Noto Sans Khmer",
        "Kantumruy Pro",
        "Battambang"
    ):
        if family in families:
            return family

    return ""


def _audio_duration_ms(path):
    try:
        from mutagen import File as MutagenFile

        media = MutagenFile(path)

        if media and media.info and media.info.length:
            return max(
                MIN_CLIP_MS,
                int(media.info.length * 1000)
            )

    except Exception:
        pass

    if path.lower().endswith(".wav"):
        try:
            with wave.open(path, "rb") as audio_file:
                return max(
                    MIN_CLIP_MS,
                    int(
                        audio_file.getnframes()
                        / audio_file.getframerate()
                        * 1000
                    )
                )
        except Exception:
            pass

    return 30_000


def _parse_srt_time(value):
    value = value.strip().replace(",", ".")

    match = re.match(
        r"(\d{2}):(\d{2}):(\d{2})\.(\d{1,3})",
        value
    )

    if not match:
        raise ValueError("Invalid SRT timestamp: " + value)

    hours, minutes, seconds, millis = match.groups()

    return (
        int(hours) * 3_600_000
        + int(minutes) * 60_000
        + int(seconds) * 1000
        + int(millis.ljust(3, "0")[:3])
    )


def _read_srt(path):
    raw = Path(path).read_text(
        encoding="utf-8-sig",
        errors="replace"
    )

    blocks = re.split(r"\r?\n\s*\r?\n", raw.strip())

    parsed = []

    for block in blocks:

        lines = [
            line.strip("\ufeff")
            for line in block.splitlines()
            if line.strip()
        ]

        time_index = next(
            (i for i, line in enumerate(lines) if "-->" in line),
            -1
        )

        if time_index < 0:
            continue

        try:
            left, right = lines[time_index].split("-->", 1)

            start_ms = _parse_srt_time(left)
            end_ms = _parse_srt_time(right.split()[0])

        except (ValueError, IndexError):
            continue

        text = "\n".join(
            lines[time_index + 1:]
        ).strip()

        if end_ms > start_ms and text:
            parsed.append((start_ms, end_ms, text))

    return parsed


class SubtitleEditDialog(QDialog):

    def __init__(self, text, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Edit Subtitle")
        self.resize(440, 220)

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Subtitle text"))

        self.editor = QTextEdit()
        self.editor.setPlainText(text)

        layout.addWidget(self.editor)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )

        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout.addWidget(buttons)

    def value(self):
        return self.editor.toPlainText().strip()


class TimelineCanvas(QWidget):

    playhead_moved = Signal(int)
    clip_changed = Signal(int, int, int)
    selection_changed = Signal(int)
    clip_added = Signal(str, int)
    clip_removed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.clips = []

        self.duration_ms = 60_000
        self.px_per_sec = 80.0
        self.playhead_ms = 0

        self.snap_ms = 100
        self.snap_enabled = True

        self._drag_clip = -1
        self._drag_mode = None
        self._drag_offset = 0

        self.selected_index = -1

        self._khmer_family = _pick_khmer_family()

        self.setMouseTracking(True)
        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._update_size()

    def _update_size(self):

        width = int(
            (self.duration_ms / 1000.0)
            * self.px_per_sec
        ) + 200

        width = max(width, 800)

        height = (
            RULER_HEIGHT
            + TRACK_HEIGHT * len(TRACK_NAMES)
            + 12
        )

        self.setMinimumSize(width, height)
        self.resize(width, height)
        self.update()

    def sizeHint(self):
        return QSize(
            900,
            RULER_HEIGHT + TRACK_HEIGHT * 4 + 12
        )

    def _x(self, ms):
        return int(ms / 1000.0 * self.px_per_sec)

    def _ms(self, x):
        return int(x / self.px_per_sec * 1000)

    def _track_y(self, track):
        return RULER_HEIGHT + track * TRACK_HEIGHT

    def _track_at_y(self, y):
        track = (y - RULER_HEIGHT) // TRACK_HEIGHT

        return (
            int(track)
            if 0 <= track < len(TRACK_NAMES)
            else -1
        )

    def _clip_rect(self, clip):

        x1 = self._x(clip.start_ms)
        x2 = self._x(clip.end_ms)

        y = self._track_y(clip.track) + 6

        return QRect(
            x1,
            y,
            max(5, x2 - x1),
            TRACK_HEIGHT - 12
        )

    def paintEvent(self, event):

        painter = QPainter(self)

        try:
            self._paint(painter)
        finally:
            painter.end()

    def _paint(self, p):

        p.setRenderHint(
            QPainter.RenderHint.Antialiasing,
            True
        )

        p.fillRect(self.rect(), QColor(BG))

        # Ruler
        p.fillRect(
            0, 0, self.width(), RULER_HEIGHT,
            QColor(PANEL_ALT)
        )

        p.setPen(QPen(QColor(BORDER), 1))

        p.drawLine(
            0, RULER_HEIGHT,
            self.width(), RULER_HEIGHT
        )

        step_sec = max(
            1,
            int(80 / max(self.px_per_sec, 1))
        )

        total_sec = self.duration_ms // 1000 + 6

        font = QFont(p.font())
        font.setPointSize(8)
        p.setFont(font)

        for sec in range(0, total_sec, step_sec):

            x = self._x(sec * 1000)

            if x > self.width():
                break

            p.setPen(QPen(QColor(TEXT_MUTED), 1))

            p.drawLine(
                x, RULER_HEIGHT - 7,
                x, RULER_HEIGHT
            )

            p.drawText(
                x + 4,
                RULER_HEIGHT - 10,
                f"{sec}s"
            )

        # Track lanes
        for track in range(len(TRACK_NAMES)):

            y = self._track_y(track)

            p.fillRect(
                0,
                y,
                self.width(),
                TRACK_HEIGHT - 2,
                QColor(
                    PANEL if track % 2 == 0
                    else "#161C26"
                )
            )

            p.setPen(QPen(QColor(BORDER), 1))

            p.drawLine(
                0,
                y + TRACK_HEIGHT - 2,
                self.width(),
                y + TRACK_HEIGHT - 2
            )

            p.setPen(QColor(TRACK_COLORS[track]))

            p.drawText(
                10,
                y + 18,
                TRACK_NAMES[track]
            )

        # Clips
        clip_font = QFont(p.font())

        if self._khmer_family:
            clip_font.setFamily(self._khmer_family)

        clip_font.setPointSize(8)

        for index, clip in enumerate(self.clips):

            if clip.track < 0 or clip.track >= len(TRACK_NAMES):
                continue

            rect = self._clip_rect(clip)

            color = QColor(
                clip.color or TRACK_COLORS[clip.track]
            )

            p.setBrush(QBrush(color))

            border_color = (
                QColor("#FFFFFF")
                if index == self.selected_index
                else color.lighter(135)
            )

            p.setPen(
                QPen(
                    border_color,
                    2 if index == self.selected_index else 1
                )
            )

            p.drawRoundedRect(rect, 6, 6)

            # Audio waveform
            waveform = getattr(clip, "waveform", None)

            if waveform and clip.track in (2, 3):

                p.save()

                p.setClipRect(
                    rect.adjusted(2, 2, -2, -2)
                )

                p.setPen(Qt.PenStyle.NoPen)

                p.setBrush(
                    QColor(255, 255, 255, 75)
                )

                count = len(waveform)

                bar_width = max(
                    1.0,
                    rect.width() / max(1, count)
                )

                for j, amplitude in enumerate(waveform):

                    bar_height = max(
                        1,
                        int(
                            float(amplitude)
                            * (rect.height() - 10)
                        )
                    )

                    x = int(rect.x() + j * bar_width)

                    y = int(
                        rect.center().y()
                        - bar_height / 2
                    )

                    p.drawRoundedRect(
                        QRect(
                            x,
                            y,
                            max(1, int(bar_width * 0.55)),
                            bar_height
                        ),
                        1,
                        1
                    )

                p.restore()

            p.setPen(QColor("#FFFFFF"))
            p.setFont(clip_font)

            label = getattr(clip, "label", "") or "Clip"

            p.drawText(
                rect.adjusted(6, 0, -4, 0),
                Qt.AlignmentFlag.AlignVCenter
                | Qt.AlignmentFlag.AlignLeft,
                label[:48]
            )

        # Playhead
        playhead_x = self._x(self.playhead_ms)

        p.setPen(QPen(QColor(WARNING), 2))

        p.drawLine(
            playhead_x,
            0,
            playhead_x,
            self.height()
        )

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(WARNING))

        p.drawPolygon(QPolygon([
            QPoint(playhead_x - 6, 0),
            QPoint(playhead_x + 6, 0),
            QPoint(playhead_x, 9)
        ]))

    def _hit_clip(self, pos):

        for index in range(len(self.clips) - 1, -1, -1):

            clip = self.clips[index]

            if clip.track < 0 or clip.track >= len(TRACK_NAMES):
                continue

            rect = self._clip_rect(clip)

            if rect.adjusted(-2, 0, 2, 0).contains(pos):

                if abs(pos.x() - rect.left()) <= 6:
                    return index, "left"

                if abs(pos.x() - rect.right()) <= 6:
                    return index, "right"

                return index, "move"

        return -1, None

    def mousePressEvent(self, event):

        if event.button() != Qt.MouseButton.LeftButton:
            return

        self.setFocus()

        pos = event.position().toPoint()

        index, mode = self._hit_clip(pos)

        if index >= 0:

            self.selected_index = index

            self.selection_changed.emit(index)

            self._drag_clip = index
            self._drag_mode = mode

            self._drag_offset = (
                pos.x()
                - self._x(self.clips[index].start_ms)
            )

            self.setCursor(
                Qt.CursorShape.SizeHorCursor
                if mode in ("left", "right")
                else Qt.CursorShape.ClosedHandCursor
            )

        else:

            ms = max(0, self._ms(pos.x()))

            self.playhead_ms = ms
            self.playhead_moved.emit(ms)

            self.selected_index = -1
            self.selection_changed.emit(-1)

        self.update()

    def mouseMoveEvent(self, event):

        pos = event.position().toPoint()

        if self._drag_clip >= 0 and self._drag_mode:

            clip = self.clips[self._drag_clip]

            target_track = self._track_at_y(pos.y())

            ms = max(
                0,
                self._ms(
                    pos.x()
                    - (
                        self._drag_offset
                        if self._drag_mode == "move"
                        else 0
                    )
                )
            )

            if self.snap_enabled:
                ms = max(
                    0,
                    round(ms / self.snap_ms) * self.snap_ms
                )

            if self._drag_mode == "move":

                length = clip.end_ms - clip.start_ms

                clip.start_ms = ms
                clip.end_ms = ms + length

                if target_track >= 0:

                    clip.track = target_track
                    clip.color = TRACK_COLORS[target_track]

            elif self._drag_mode == "left":

                clip.start_ms = min(
                    ms,
                    clip.end_ms - MIN_CLIP_MS
                )

            elif self._drag_mode == "right":

                clip.end_ms = max(
                    ms,
                    clip.start_ms + MIN_CLIP_MS
                )

            self.clip_changed.emit(
                self._drag_clip,
                clip.start_ms,
                clip.end_ms
            )

            self._update_size()

        else:

            _, mode = self._hit_clip(pos)

            if mode in ("left", "right"):
                self.setCursor(Qt.CursorShape.SizeHorCursor)

            elif mode == "move":
                self.setCursor(Qt.CursorShape.OpenHandCursor)

            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)

    def mouseReleaseEvent(self, event):

        self._drag_clip = -1
        self._drag_mode = None

        self.setCursor(Qt.CursorShape.ArrowCursor)

        self.update()

    def dragEnterEvent(self, event):

        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):

        target_track = self._track_at_y(
            event.position().toPoint().y()
        )

        if target_track < 0:
            event.ignore()
            return

        added = False

        for url in event.mimeData().urls():

            if not url.isLocalFile():
                continue

            path = url.toLocalFile()

            if os.path.isfile(path):

                self.clip_added.emit(path, target_track)
                added = True

        if added:
            event.acceptProposedAction()
        else:
            event.ignore()

    def keyPressEvent(self, event):

        if event.key() in (
            Qt.Key.Key_Delete,
            Qt.Key.Key_Backspace
        ):

            self.remove_selected()
            event.accept()
            return

        super().keyPressEvent(event)

    # -----------------------------------------------------
    # CLIP MANAGEMENT
    # -----------------------------------------------------

    def add_clip(
        self,
        track,
        start_ms,
        end_ms,
        label,
        path="",
        waveform=None,
        subtitle_id=-1,
        select=True,
        refresh=True
    ):

        track = max(0, min(3, int(track)))

        start_ms = max(0, int(start_ms))

        end_ms = max(
            start_ms + MIN_CLIP_MS,
            int(end_ms)
        )

        clip = TimelineClip(
            track=track,
            start_ms=start_ms,
            end_ms=end_ms,
            label=label,
            color=TRACK_COLORS[track],
            subtitle_id=subtitle_id,
            source_path=path,
            waveform=waveform or [],
        )

        self.clips.append(clip)

        if select:

            self.selected_index = len(self.clips) - 1

            self.selection_changed.emit(
                self.selected_index
            )

        self.duration_ms = max(
            self.duration_ms,
            end_ms + 5000
        )

        if refresh:
            self._update_size()

        return clip

    def set_subtitles(self, subs, audio_paths=None):

        """
        Rebuild subtitle and voice tracks.

        audio_paths:
            list: audio_paths[row]
            dict: audio_paths[subtitle.id]
            dict: audio_paths[row]

        Subtitle.audio_path is also supported.
        """

        self.clips = [
            clip for clip in self.clips
            if clip.track not in (1, 2)
        ]

        audio_paths = audio_paths or {}

        for row, sub in enumerate(subs):

            subtitle_id = getattr(sub, "id", row)

            audio_path = getattr(
                sub,
                "audio_path",
                None
            )

            if not audio_path:

                if isinstance(audio_paths, dict):

                    audio_path = (
                        audio_paths.get(subtitle_id)
                        or audio_paths.get(row)
                    )

                elif isinstance(audio_paths, (list, tuple)):

                    if row < len(audio_paths):
                        audio_path = audio_paths[row]

            # Subtitle track
            self.add_clip(
                1,
                sub.start_ms,
                sub.end_ms,
                sub.text[:80],
                subtitle_id=subtitle_id,
                select=False,
                refresh=False
            )

            # Existing generated voice track
            if audio_path and os.path.isfile(audio_path):

                try:
                    waveform = generate_waveform(audio_path)
                except Exception:
                    waveform = []

                duration = _audio_duration_ms(audio_path)

                self.add_clip(
                    2,
                    sub.start_ms,
                    sub.start_ms + duration,
                    f"VO {row + 1}",
                    path=audio_path,
                    waveform=waveform,
                    subtitle_id=subtitle_id,
                    select=False,
                    refresh=False
                )

        self.selected_index = -1

        self._update_size()

    def find_voice_clip(self, subtitle_id):

        """
        Find a generated voice clip by subtitle ID.
        """

        for clip in self.clips:

            if (
                clip.track == 2
                and clip.subtitle_id == subtitle_id
                and clip.source_path
                and os.path.isfile(clip.source_path)
            ):
                return clip

        return None

    def set_duration(self, ms):

        self.duration_ms = max(1000, int(ms))

        has_video = False

        for clip in self.clips:

            if clip.track == 0:

                clip.end_ms = self.duration_ms
                has_video = True
                break

        if not has_video:

            self.add_clip(
                0,
                0,
                self.duration_ms,
                "Main Video",
                select=False,
                refresh=False
            )

        self._update_size()

    def set_playhead(self, ms):

        self.playhead_ms = max(
            0,
            min(int(ms), self.duration_ms)
        )

        self.update()

    def zoom_in(self):

        self.px_per_sec = min(
            800,
            self.px_per_sec * 1.3
        )

        self._update_size()

    def zoom_out(self):

        self.px_per_sec = max(
            10,
            self.px_per_sec / 1.3
        )

        self._update_size()

    def selected_clip(self):

        if 0 <= self.selected_index < len(self.clips):
            return self.clips[self.selected_index]

        return None

    def remove_selected(self):

        clip = self.selected_clip()

        if clip is None:
            return

        path = getattr(
            clip,
            "source_path",
            ""
        ) or ""

        self.clips.pop(self.selected_index)

        self.selected_index = -1

        self.selection_changed.emit(-1)
        self.clip_removed.emit(path)

        self._update_size()

    def split_selected_at_playhead(self):

        clip = self.selected_clip()

        if clip is None:
            return False

        if not (
            clip.start_ms + MIN_CLIP_MS
            <= self.playhead_ms
            <= clip.end_ms - MIN_CLIP_MS
        ):
            return False

        original_end = clip.end_ms

        clip.end_ms = self.playhead_ms

        right = TimelineClip(
            track=clip.track,
            start_ms=self.playhead_ms,
            end_ms=original_end,
            label=clip.label + " (Split)",
            color=clip.color,
            subtitle_id=getattr(
                clip,
                "subtitle_id",
                -1
            ),
            source_path=getattr(
                clip,
                "source_path",
                ""
            ),
            waveform=list(
                getattr(clip, "waveform", []) or []
            ),
        )

        self.clips.insert(
            self.selected_index + 1,
            right
        )

        self.selected_index += 1

        self.selection_changed.emit(
            self.selected_index
        )

        self._update_size()

        return True

    def update_single_audio_clip(self, sub_idx, path):

        if not path or not os.path.isfile(path):
            return False

        for clip in self.clips:

            if (
                clip.track == 2
                and clip.subtitle_id == sub_idx
            ):

                clip.source_path = path

                try:
                    clip.waveform = generate_waveform(path)
                except Exception:
                    clip.waveform = []

                clip.end_ms = (
                    clip.start_ms
                    + _audio_duration_ms(path)
                )

                clip.label = f"VO {sub_idx + 1}"

                self.update()

                return True

        subtitle_clip = next(
            (
                c for c in self.clips
                if c.track == 1
                and c.subtitle_id == sub_idx
            ),
            None
        )

        if subtitle_clip:

            try:
                waveform = generate_waveform(path)
            except Exception:
                waveform = []

            self.add_clip(
                2,
                subtitle_clip.start_ms,
                subtitle_clip.start_ms + _audio_duration_ms(path),
                f"VO {sub_idx + 1}",
                path=path,
                waveform=waveform,
                subtitle_id=sub_idx,
                select=False,
                refresh=True
            )

            return True

        return False

    def edit_selected_subtitle(self, parent=None):

        clip = self.selected_clip()

        if clip is None or clip.track != 1:
            return False

        dialog = SubtitleEditDialog(
            clip.label,
            parent
        )

        if dialog.exec() == QDialog.DialogCode.Accepted:

            new_text = dialog.value()

            if new_text:

                clip.label = new_text
                self.update()

                return True

        return False


class BottomPanel(QFrame):

    playhead_moved = Signal(int)
    subtitle_timing_changed = Signal(int, int, int)
    subtitle_file_requested = Signal(str)
    media_added = Signal(str, int)

    # Existing generated voice playback request:
    # audio path, voice start time, voice end time
    voice_clip_requested = Signal(str, int, int)

    # Missing voice clip
    voice_clip_missing = Signal(int)

    VIDEO_EXTENSIONS = "*.mp4 *.mkv *.mov *.avi *.webm *.m4v"

    AUDIO_EXTENSIONS = "*.mp3 *.wav *.m4a *.aac *.flac *.ogg"

    def __init__(self, parent=None):

        super().__init__(parent)

        self.setObjectName("Panel")

        self._build_ui()

    def _build_ui(self):

        root = QVBoxLayout(self)

        root.setContentsMargins(14, 10, 14, 12)
        root.setSpacing(9)

        # Header
        header = QHBoxLayout()

        title = QLabel("TIMELINE")
        title.setObjectName("PanelTitle")

        header.addWidget(title)
        header.addStretch()

        self.btn_zoom_out = QPushButton(
            qta.icon(
                "fa6s.magnifying-glass-minus",
                color="#9CA3AF"
            ),
            ""
        )

        self.btn_zoom_in = QPushButton(
            qta.icon(
                "fa6s.magnifying-glass-plus",
                color="#9CA3AF"
            ),
            ""
        )

        for button in (
            self.btn_zoom_out,
            self.btn_zoom_in
        ):

            button.setFixedSize(28, 28)
            button.setObjectName("Ghost")

        self.chk_snap = QCheckBox("Snap")
        self.chk_snap.setChecked(True)

        header.addWidget(self.btn_zoom_out)
        header.addWidget(self.btn_zoom_in)
        header.addWidget(self.chk_snap)

        root.addLayout(header)

        # Toolbar
        actions = QHBoxLayout()

        self.btn_add_video = QPushButton(
            qta.icon("fa6s.video", color=TRACK_COLORS[0]),
            " Add Video"
        )

        self.btn_add_srt = QPushButton(
            qta.icon(
                "fa6s.closed-captioning",
                color=TRACK_COLORS[1]
            ),
            " Add Subtitle"
        )

        self.btn_add_voice = QPushButton(
            qta.icon(
                "fa6s.microphone",
                color=TRACK_COLORS[2]
            ),
            " Add Voice"
        )

        self.btn_add_music = QPushButton(
            qta.icon(
                "fa6s.music",
                color=TRACK_COLORS[3]
            ),
            " Add Music"
        )

        self.btn_edit_subtitle = QPushButton(
            qta.icon("fa6s.pen", color="#D1D5DB"),
            " Edit"
        )

        self.btn_split = QPushButton(
            qta.icon("fa6s.scissors", color="#D1D5DB"),
            " Split"
        )

        self.btn_replace = QPushButton(
            qta.icon("fa6s.arrows-rotate", color="#D1D5DB"),
            " Replace"
        )

        self.btn_delete = QPushButton(
            qta.icon("fa6s.trash", color="#F87171"),
            " Delete"
        )

        for button in (
            self.btn_add_video,
            self.btn_add_srt,
            self.btn_add_voice,
            self.btn_add_music,
            self.btn_edit_subtitle,
            self.btn_split,
            self.btn_replace,
            self.btn_delete
        ):

            button.setMinimumHeight(29)
            actions.addWidget(button)

        root.addLayout(actions)

        # Timeline scroll area
        self.scroll_area = QScrollArea()

        self.scroll_area.setWidgetResizable(False)

        self.scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )

        self.scroll_area.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )

        self.scroll_area.setStyleSheet(
            "QScrollArea{border:1px solid #242C3A;"
            "border-radius:7px;background:transparent;}"
            "QScrollBar:horizontal{background:#10141D;height:10px;}"
            "QScrollBar:vertical{background:#10141D;width:10px;}"
        )

        self.canvas = TimelineCanvas()

        self.scroll_area.setWidget(self.canvas)

        root.addWidget(self.scroll_area, 1)

        # Events
        self.btn_zoom_in.clicked.connect(
            self.canvas.zoom_in
        )

        self.btn_zoom_out.clicked.connect(
            self.canvas.zoom_out
        )

        self.chk_snap.toggled.connect(
            lambda value: setattr(
                self.canvas,
                "snap_enabled",
                value
            )
        )

        self.canvas.playhead_moved.connect(
            self.playhead_moved.emit
        )

        self.canvas.clip_changed.connect(
            self._on_clip_changed
        )

        self.canvas.clip_added.connect(
            self._add_dropped_media
        )

        self.btn_add_video.clicked.connect(
            lambda: self.add_media_to_track(0)
        )

        self.btn_add_srt.clicked.connect(
            self.import_srt
        )

        self.btn_add_voice.clicked.connect(
            lambda: self.add_media_to_track(2)
        )

        self.btn_add_music.clicked.connect(
            lambda: self.add_media_to_track(3)
        )

        self.btn_edit_subtitle.clicked.connect(
            self.edit_selected_subtitle
        )

        self.btn_split.clicked.connect(
            self.split_selected
        )

        self.btn_replace.clicked.connect(
            self.replace_selected
        )

        self.btn_delete.clicked.connect(
            self.delete_selected
        )

        QShortcut(
            QKeySequence.StandardKey.Delete,
            self,
            activated=self.delete_selected
        )

        QShortcut(
            QKeySequence("Ctrl+K"),
            self,
            activated=self.split_selected
        )

    # -----------------------------------------------------
    # ADD MEDIA
    # -----------------------------------------------------

    def _add_dropped_media(self, path, track):
        self._add_media_path(path, track)

    def add_media_to_track(self, track):

        if track == 0:

            file_filter = (
                f"Video Files ({self.VIDEO_EXTENSIONS});;"
                "All Files (*)"
            )

            title = "Add Video Clip"

        elif track == 1:

            self.import_srt()
            return

        else:

            file_filter = (
                f"Audio Files ({self.AUDIO_EXTENSIONS});;"
                "All Files (*)"
            )

            title = "Add Voice / Music"

        paths, _ = QFileDialog.getOpenFileNames(
            self,
            title,
            "",
            file_filter
        )

        for path in paths:
            self._add_media_path(path, track)

    def _add_media_path(self, path, track):

        if not path or not os.path.isfile(path):
            return

        extension = os.path.splitext(path)[1].lower()

        if track == 0 and extension not in VIDEO_EXTENSIONS:

            QMessageBox.warning(
                self,
                "Unsupported file",
                "Please select a video file."
            )

            return

        if track in (2, 3) and extension not in AUDIO_EXTENSIONS:

            QMessageBox.warning(
                self,
                "Unsupported file",
                "Please select an audio file."
            )

            return

        if track in (2, 3):

            duration = _audio_duration_ms(path)

            try:
                waveform = generate_waveform(path)
            except Exception:
                waveform = []

        else:

            duration = max(
                1000,
                self.canvas.duration_ms
            )

            waveform = []

        start = self.canvas.playhead_ms

        label_prefix = (
            "VIDEO",
            "",
            "VOICE",
            "MUSIC"
        )[track]

        label = (
            f"{label_prefix} "
            f"{Path(path).stem[:30]}"
        )

        self.canvas.add_clip(
            track,
            start,
            start + duration,
            label,
            path=path,
            waveform=waveform
        )

        self.media_added.emit(path, track)

        self.scroll_area.ensureVisible(
            self.canvas._x(start),
            0,
            100,
            0
        )

    # -----------------------------------------------------
    # SRT
    # -----------------------------------------------------

    def import_srt(self):

        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Subtitles",
            "",
            "SubRip Subtitles (*.srt);;All Files (*)"
        )

        if not path:
            return

        try:
            entries = _read_srt(path)

        except Exception as exc:

            QMessageBox.critical(
                self,
                "SRT Error",
                str(exc)
            )

            return

        if not entries:

            QMessageBox.warning(
                self,
                "SRT Error",
                "No valid subtitle entries were found."
            )

            return

        self.canvas.clips = [
            clip for clip in self.canvas.clips
            if clip.track != 1
        ]

        for start, end, text in entries:

            self.canvas.add_clip(
                1,
                start,
                end,
                text[:100],
                subtitle_id=-1,
                select=False,
                refresh=False
            )

        self.canvas.selected_index = -1

        self.canvas._update_size()

        self.subtitle_file_requested.emit(path)

    # -----------------------------------------------------
    # CLIP CHANGES
    # -----------------------------------------------------

    def _on_clip_changed(
        self,
        index,
        start_ms,
        end_ms
    ):

        if 0 <= index < len(self.canvas.clips):

            clip = self.canvas.clips[index]

            subtitle_id = getattr(
                clip,
                "subtitle_id",
                -1
            )

            if subtitle_id >= 0:

                self.subtitle_timing_changed.emit(
                    subtitle_id,
                    start_ms,
                    end_ms
                )

    def _selected_clip(self):
        return self.canvas.selected_clip()

    def edit_selected_subtitle(self):

        if not self.canvas.edit_selected_subtitle(self):

            QMessageBox.information(
                self,
                "Edit Subtitle",
                "Select a subtitle clip first."
            )

    def split_selected(self):

        if not self.canvas.split_selected_at_playhead():

            QMessageBox.information(
                self,
                "Split Clip",
                "Select a clip and move the playhead "
                "inside it before splitting."
            )

    def delete_selected(self):

        if self._selected_clip() is None:
            return

        self.canvas.remove_selected()

    def replace_selected(self):

        clip = self._selected_clip()

        if clip is None:

            QMessageBox.information(
                self,
                "Replace Clip",
                "Select a clip first."
            )

            return

        track = clip.track

        if track == 1:
            self.import_srt()
            return

        if track == 0:

            file_filter = (
                f"Video Files ({self.VIDEO_EXTENSIONS})"
            )

            title = "Replace Video Clip"

        else:

            file_filter = (
                f"Audio Files ({self.AUDIO_EXTENSIONS})"
            )

            title = "Replace Audio Clip"

        path, _ = QFileDialog.getOpenFileName(
            self,
            title,
            "",
            file_filter
        )

        if not path:
            return

        if not os.path.isfile(path):
            return

        old_start = clip.start_ms
        old_index = self.canvas.selected_index

        self.canvas.clips.pop(old_index)

        self.canvas.selected_index = -1

        self._add_media_path(path, track)

        new_clip = self.canvas.selected_clip()

        if new_clip:

            length = (
                new_clip.end_ms - new_clip.start_ms
            )

            new_clip.start_ms = old_start
            new_clip.end_ms = old_start + length

            self.canvas.update()

        self.canvas._update_size()

    # -----------------------------------------------------
    # SUBTITLE / VOICE CONNECTION
    # -----------------------------------------------------

    def set_subtitles(self, subs, audio_paths=None):

        self.canvas.set_subtitles(
            subs,
            audio_paths
        )

    def play_subtitle_voice(self, subtitle_id):

        """
        Find the matching green VOICE clip.

        subtitle_id must match TimelineClip.subtitle_id.
        """

        clip = self.canvas.find_voice_clip(
            subtitle_id
        )

        if clip is None:

            self.voice_clip_missing.emit(
                subtitle_id
            )

            return False

        index = self.canvas.clips.index(clip)

        self.canvas.selected_index = index

        self.canvas.set_playhead(
            clip.start_ms
        )

        self.canvas.update()

        self.scroll_area.ensureVisible(
            self.canvas._x(clip.start_ms),
            0,
            100,
            0
        )

        self.voice_clip_requested.emit(
            clip.source_path,
            clip.start_ms,
            clip.end_ms
        )

        return True

    def set_duration(self, ms):
        self.canvas.set_duration(ms)

    @property
    def duration_ms(self) -> int:
        return int(self.canvas.duration_ms)

    def set_playhead(self, ms):

        self.canvas.set_playhead(ms)

        self.scroll_area.ensureVisible(
            self.canvas._x(ms),
            0,
            100,
            0
        )

    def update_clip_audio(self, sub_idx, path):

        return self.canvas.update_single_audio_clip(
            sub_idx,
            path
        )

    def add_generated_voice(
        self,
        path,
        start_ms=None,
        end_ms=None,
        label=None,
        subtitle_id=-1
    ):

        if not path or not os.path.isfile(path):
            return None

        start = (
            self.canvas.playhead_ms
            if start_ms is None
            else int(start_ms)
        )

        end = (
            int(end_ms)
            if end_ms is not None
            else start + _audio_duration_ms(path)
        )

        try:
            waveform = generate_waveform(path)
        except Exception:
            waveform = []

        return self.canvas.add_clip(
            2,
            start,
            end,
            label or f"VOICE {Path(path).stem[:24]}",
            path=path,
            waveform=waveform,
            subtitle_id=subtitle_id
        )
