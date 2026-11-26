import os

from PySide6.QtCore import Qt, QUrl, Signal, QRectF, QSize, Slot
from PySide6.QtGui import (
    QColor,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtMultimedia import (
    QMediaPlayer,
    QAudioOutput,
    QVideoSink,
    QVideoFrame,
)
from PySide6.QtWidgets import (
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QCheckBox,
    QFileDialog,
    QMessageBox,
    QWidget,
    QProgressBar,
    QStackedWidget,
    QSizePolicy,
)

import qtawesome as qta

from app.ui.preview import SubtitleOverlay
from app.theme import PANEL_ALT, BORDER


class RoundedVideoWidget(QWidget):
    """
    Paints QVideoSink frames inside a rounded video viewport.

    Unlike QVideoWidget, this widget paints the frame itself, so rounded
    clipping and borders work consistently with the custom preview UI.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self.video_sink = QVideoSink(self)
        self.video_sink.videoFrameChanged.connect(self._on_video_frame)

        self._image = QImage()
        self._outer_radius = 16
        self._video_radius = 13
        self._border_color = QColor("#293445")
        self._panel_color = QColor("#151A23")
        self._video_color = QColor("#000000")

        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.setAutoFillBackground(False)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self.setMinimumSize(120, 80)

    @Slot(QVideoFrame)
    def _on_video_frame(self, frame):
        if not frame.isValid():
            return

        image = frame.toImage()
        if image.isNull():
            return

        # Keep an owned copy; the QVideoFrame may be released after this slot.
        self._image = image.copy()
        self.update()

    def clear_frame(self):
        self._image = QImage()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(
            QPainter.RenderHint.SmoothPixmapTransform, True
        )

        outer_rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)

        # Rounded preview panel.
        outer_path = QPainterPath()
        outer_path.addRoundedRect(
            outer_rect,
            self._outer_radius,
            self._outer_radius,
        )
        painter.fillPath(outer_path, self._panel_color)

        # Inner video viewport.
        video_rect = outer_rect.adjusted(2.0, 2.0, -2.0, -2.0)
        video_path = QPainterPath()
        video_path.addRoundedRect(
            video_rect,
            self._video_radius,
            self._video_radius,
        )

        painter.save()
        painter.setClipPath(video_path)
        painter.fillRect(video_rect, self._video_color)

        if not self._image.isNull():
            target_size = video_rect.size().toSize()
            scaled_image = self._image.scaled(
                target_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )

            # Center the complete frame without stretching or cropping it.
            image_rect = QRectF(
                video_rect.center().x() - scaled_image.width() / 2,
                video_rect.center().y() - scaled_image.height() / 2,
                scaled_image.width(),
                scaled_image.height(),
            )
            painter.drawImage(image_rect, scaled_image)

        painter.restore()

        # Subtle outer border.
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(self._border_color, 1.0))
        painter.drawPath(outer_path)
        painter.end()

    def sizeHint(self):
        return QSize(640, 360)


class VideoContainer(QWidget):
    load_video_requested = Signal()
    file_dropped = Signal(str)

    SUPPORTED_VIDEO_EXTENSIONS = (
        ".mp4",
        ".mkv",
        ".mov",
        ".avi",
        ".webm",
        ".m4v",
    )

    def __init__(self, parent=None):
        super().__init__(parent)

        self.aspect = 16 / 9
        self.border_radius = 16

        self.setAcceptDrops(True)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )

        self.stack = QStackedWidget(self)
        self.stack.setContentsMargins(0, 0, 0, 0)
        self.stack.setStyleSheet(
            "QStackedWidget { background: transparent; border: none; }"
        )

        # Page 0: Empty state.
        self.empty_widget = QWidget()
        self.empty_widget.setStyleSheet("""
            QWidget {
                background: #0E1116;
                border: 1px dashed #374151;
                border-radius: 14px;
            }
        """)

        empty_layout = QVBoxLayout(self.empty_widget)
        empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.setSpacing(9)

        icon_label = QLabel()
        icon_label.setPixmap(
            qta.icon("fa6s.film", color="#64748B").pixmap(48, 48)
        )
        icon_label.setStyleSheet("border: none; background: transparent;")
        empty_layout.addWidget(
            icon_label, 0, Qt.AlignmentFlag.AlignCenter
        )

        text_label = QLabel("Drag & Drop Video Here")
        text_label.setStyleSheet("""
            QLabel {
                color: #9CA3AF;
                font-size: 13px;
                font-weight: 600;
                border: none;
                background: transparent;
            }
        """)
        empty_layout.addWidget(
            text_label, 0, Qt.AlignmentFlag.AlignCenter
        )

        self.btn_load_empty = QPushButton(
            qta.icon("fa6s.folder-open", color="white"),
            " Load Video",
        )
        self.btn_load_empty.setObjectName("Primary")
        self.btn_load_empty.setMinimumHeight(32)
        self.btn_load_empty.setFixedWidth(130)
        self.btn_load_empty.clicked.connect(
            self.load_video_requested.emit
        )
        empty_layout.addWidget(
            self.btn_load_empty, 0, Qt.AlignmentFlag.AlignCenter
        )

        # Page 1: Rounded video renderer.
        self.video_widget = RoundedVideoWidget()

        self.stack.addWidget(self.empty_widget)
        self.stack.addWidget(self.video_widget)
        self.stack.setCurrentWidget(self.empty_widget)

        # The stack is positioned manually so the selected aspect ratio
        # remains centered instead of being stretched by a parent layout.

        # Subtitle overlay stays above the video.
        self.overlay = SubtitleOverlay(self)
        self.overlay.hide()

    def show_video(self):
        self.stack.setCurrentWidget(self.video_widget)
        self.video_widget.update()

    def show_empty(self):
        self.stack.setCurrentWidget(self.empty_widget)
        self.video_widget.clear_frame()
        self.overlay.hide()

    def set_aspect(self, aspect):
        if aspect <= 0:
            return

        self.aspect = float(aspect)
        self.updateGeometry()
        self._update_preview_geometry()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    path = url.toLocalFile().lower()
                    if path.endswith(self.SUPPORTED_VIDEO_EXTENSIONS):
                        event.acceptProposedAction()
                        return
        event.ignore()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            if not url.isLocalFile():
                continue

            path = url.toLocalFile()
            if path.lower().endswith(self.SUPPORTED_VIDEO_EXTENSIONS):
                self.file_dropped.emit(path)
                event.acceptProposedAction()
                return

        event.ignore()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_preview_geometry()

    def _update_preview_geometry(self):
        available_width = max(1, self.width())
        available_height = max(1, self.height())

        preview_width = available_width
        preview_height = int(preview_width / self.aspect)

        if preview_height > available_height:
            preview_height = available_height
            preview_width = int(preview_height * self.aspect)

        x = (available_width - preview_width) // 2
        y = (available_height - preview_height) // 2

        self.stack.setGeometry(
            x, y, max(1, preview_width), max(1, preview_height)
        )

        # Position subtitle overlay inside the active preview viewport.
        margin = 16
        overlay_height = max(40, int(preview_height * 0.14))
        overlay_width = max(40, preview_width - (2 * margin))

        self.overlay.setGeometry(
            x + margin,
            y + preview_height - overlay_height - margin,
            overlay_width,
            overlay_height,
        )
        self.overlay.raise_()


class LeftPanel(QFrame):
    video_loaded = Signal(str)
    generate_requested = Signal()
    stop_generation_requested = Signal()
    export_mp3_requested = Signal()
    export_video_requested = Signal()
    dub_preview_toggled = Signal(bool)
    show_subtitles_toggled = Signal(bool)
    mute_original_toggled = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setObjectName("Panel")
        self.video_path = ""
        self._duration_ms = 0
        self._slider_is_being_updated = False
        self._dub_enabled = False

        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.player.setAudioOutput(self.audio)

        self._build_ui()
        self._connect()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(8)

        # Title and aspect-ratio controls.
        title_row = QHBoxLayout()

        title = QLabel("PREVIEW")
        title.setObjectName("PanelTitle")
        title_row.addWidget(title)
        title_row.addStretch()

        aspect_button_style = """
            QPushButton {
                background: transparent;
                border: 1px solid #293445;
                color: #9CA3AF;
                font-size: 11px;
                font-weight: 600;
                padding: 2px;
                border-radius: 6px;
            }
            QPushButton:checked {
                background: #1683F8;
                border: 1px solid #1683F8;
                color: white;
            }
            QPushButton:hover {
                border-color: #3B82F6;
                color: white;
            }
        """

        self.btn_169 = QPushButton("16:9")
        self.btn_169.setCheckable(True)
        self.btn_169.setChecked(True)
        self.btn_169.setStyleSheet(aspect_button_style)
        self.btn_169.setFixedSize(52, 30)

        self.btn_916 = QPushButton("9:16")
        self.btn_916.setCheckable(True)
        self.btn_916.setStyleSheet(aspect_button_style)
        self.btn_916.setFixedSize(52, 30)

        title_row.addWidget(self.btn_169)
        title_row.addWidget(self.btn_916)
        root.addLayout(title_row)

        # Rounded video preview.
        self.video_container = VideoContainer()
        self.video_container.setMinimumHeight(160)
        self.video_container.setMaximumHeight(360)

        # QVideoSink feeds frames to RoundedVideoWidget for custom painting.
        self.player.setVideoOutput(
            self.video_container.video_widget.video_sink
        )
        root.addWidget(self.video_container, 1)

        # Playback controls card.
        playback_card = QFrame()
        playback_card.setObjectName("PlaybackCard")
        playback_card.setStyleSheet(f"""
            QFrame#PlaybackCard {{
                background: {PANEL_ALT};
                border: 1px solid {BORDER};
                border-radius: 12px;
            }}
        """)

        playback_layout = QVBoxLayout(playback_card)
        playback_layout.setContentsMargins(10, 8, 10, 8)
        playback_layout.setSpacing(6)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 0)
        playback_layout.addWidget(self.slider)

        controls_row = QHBoxLayout()
        controls_row.setSpacing(5)

        self.btn_load = QPushButton(
            qta.icon("fa6s.folder-open", color="#E5E7EB"), ""
        )
        self.btn_load.setObjectName("Ghost")
        self.btn_load.setToolTip("Load Video")
        self.btn_load.setFixedSize(36, 36)

        self.btn_play_stop = QPushButton(
            qta.icon("fa6s.play", color="#E5E7EB"), ""
        )
        self.btn_play_stop.setObjectName("Ghost")
        self.btn_play_stop.setToolTip("Play")
        self.btn_play_stop.setFixedSize(36, 36)

        controls_row.addWidget(self.btn_load)
        controls_row.addWidget(self.btn_play_stop)
        controls_row.addStretch()

        self.lbl_current = QLabel("00:00")
        self.lbl_current.setObjectName("TimeCode")

        separator = QLabel("/")
        separator.setObjectName("TimeCode")

        self.lbl_duration = QLabel("00:00")
        self.lbl_duration.setObjectName("TimeCode")

        controls_row.addWidget(self.lbl_current)
        controls_row.addWidget(separator)
        controls_row.addWidget(self.lbl_duration)

        playback_layout.addLayout(controls_row)
        root.addWidget(playback_card)

        # Options.
        options_row = QHBoxLayout()

        self.chk_lock_speed = QCheckBox("Lock Speed")
        self.chk_autofit = QCheckBox("Auto-Fit")
        self.chk_lock_speed.setChecked(True)
        self.chk_autofit.setChecked(True)

        options_row.addWidget(self.chk_lock_speed)
        options_row.addWidget(self.chk_autofit)
        options_row.addStretch()

        root.addLayout(options_row)

        # Subtitle and original-audio options.
        self.chk_show_subs = QCheckBox("Show Subtitles Overlay")
        self.chk_show_subs.setChecked(True)
        root.addWidget(self.chk_show_subs)

        self.chk_mute_original = QCheckBox(
            "Mute Original Audio (Hide Voice)"
        )
        self.chk_mute_original.setChecked(True)
        root.addWidget(self.chk_mute_original)

        # Actions section.
        actions_label = QLabel("ACTIONS")
        actions_label.setObjectName("SectionLabel")
        root.addWidget(actions_label)

        action_row = QHBoxLayout()
        action_row.setSpacing(5)

        self.btn_load_srt = QPushButton(
            qta.icon("fa6s.file-lines", color="#9CA3AF"),
            " Load SRT",
        )
        self.btn_export_mp3 = QPushButton(
            qta.icon("fa6s.music", color="#9CA3AF"),
            " MP3",
        )
        self.btn_export_video = QPushButton(
            qta.icon("fa6s.film", color="#9CA3AF"),
            " Video",
        )

        for button in (
            self.btn_load_srt,
            self.btn_export_mp3,
            self.btn_export_video,
        ):
            button.setMinimumHeight(38)
            action_row.addWidget(button)

        root.addLayout(action_row)

        self.btn_generate = QPushButton(
            qta.icon("fa6s.wand-magic-sparkles", color="white"),
            "  Generate Voice",
        )
        self.btn_generate.setObjectName("Accent")
        self.btn_generate.setMinimumHeight(42)
        self.btn_generate.setToolTip(
            "Generate voice for the checked subtitles"
        )
        root.addWidget(self.btn_generate)

        self.btn_stop_gen = QPushButton(
            qta.icon("fa6s.ban", color="white"),
            "  Stop Generation",
        )
        self.btn_stop_gen.setObjectName("Danger")
        self.btn_stop_gen.setMinimumHeight(38)
        root.addWidget(self.btn_stop_gen)

        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setRange(0, 0)
        self.progress.hide()
        root.addWidget(self.progress)

    def _connect(self):
        self.btn_load.clicked.connect(self.load_video)
        self.video_container.load_video_requested.connect(
            self.load_video
        )
        self.video_container.file_dropped.connect(
            self._load_video_path
        )

        self.btn_play_stop.clicked.connect(self._toggle_playback)
        self.player.playbackStateChanged.connect(
            self._on_player_state_changed
        )

        self.player.positionChanged.connect(self._on_position)
        self.player.durationChanged.connect(self._on_duration)
        self.player.errorOccurred.connect(self._on_player_error)

        self.slider.sliderMoved.connect(self.player.setPosition)

        self.btn_169.clicked.connect(
            lambda: self._set_aspect(16 / 9, self.btn_169)
        )
        self.btn_916.clicked.connect(
            lambda: self._set_aspect(9 / 16, self.btn_916)
        )

        self.btn_load_srt.clicked.connect(self._load_srt)
        self.btn_export_mp3.clicked.connect(
            self.export_mp3_requested.emit
        )
        self.btn_export_video.clicked.connect(
            self.export_video_requested.emit
        )
        self.btn_generate.clicked.connect(
            self.generate_requested.emit
        )
        self.btn_stop_gen.clicked.connect(
            self.stop_generation_requested.emit
        )

        self.chk_show_subs.toggled.connect(
            self.show_subtitles_toggled.emit
        )
        self.chk_mute_original.toggled.connect(
            self.mute_original_toggled.emit
        )

    def _toggle_playback(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def _on_player_state_changed(self, state):
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.btn_play_stop.setIcon(
                qta.icon("fa6s.pause", color="#E5E7EB")
            )
            self.btn_play_stop.setToolTip("Pause")
        else:
            self.btn_play_stop.setIcon(
                qta.icon("fa6s.play", color="#E5E7EB")
            )
            self.btn_play_stop.setToolTip("Play")

    @property
    def dub_enabled(self) -> bool:
        return self._dub_enabled

    def set_dub_enabled(self, enabled: bool):
        """Enable or disable automatic dub playback.

        There is no visible Dub button anymore. The state is kept here so
        the main window can auto-start the translated voice track when the
        video plays.
        """
        enabled = bool(enabled)

        if enabled == self._dub_enabled:
            return

        self._dub_enabled = enabled
        self.dub_preview_toggled.emit(enabled)

    def _set_aspect(self, aspect, button):
        self.btn_169.setChecked(button is self.btn_169)
        self.btn_916.setChecked(button is self.btn_916)
        self.video_container.set_aspect(aspect)

    def load_video(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Video",
            "",
            "Video Files (*.mp4 *.mkv *.mov *.avi *.webm *.m4v);;All Files (*)",
        )
        if path:
            self._load_video_path(path)

    def _load_video_path(self, path):
        if not path or not os.path.isfile(path):
            QMessageBox.warning(
                self,
                "Video Not Found",
                "The selected video file does not exist.",
            )
            return

        self.video_path = path
        self.video_container.video_widget.clear_frame()
        self.player.setSource(QUrl.fromLocalFile(path))
        self.video_container.show_video()
        self.player.play()
        self.video_loaded.emit(path)

    def _on_player_error(self, error, error_string):
        if error == QMediaPlayer.Error.NoError:
            return

        self.video_container.show_empty()
        QMessageBox.critical(
            self,
            "Video Error",
            f"Could not play video.\n\n{error_string}",
        )

    def _load_srt(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open SRT",
            "",
            "Subtitle Files (*.srt);;All Files (*)",
        )
        if path:
            self.video_loaded.emit(f"SRT:{path}")

    def _on_duration(self, duration):
        self._duration_ms = duration
        self.slider.setRange(0, duration)
        self.lbl_duration.setText(self._fmt(duration))

    def _on_position(self, position):
        if not self.slider.isSliderDown():
            self.slider.setValue(position)

        self.lbl_current.setText(self._fmt(position))

    @staticmethod
    def _fmt(milliseconds):
        seconds = max(0, milliseconds // 1000)
        return f"{seconds // 60:02d}:{seconds % 60:02d}"

    @property
    def subtitle_overlay(self):
        return self.video_container.overlay

    def set_busy(self, busy: bool):
        if busy:
            self.progress.setRange(0, 0)
            self.progress.setTextVisible(False)
            self.progress.show()
        else:
            self.progress.hide()

    def set_progress(self, percent: int):
        percent = max(0, min(100, int(percent)))
        self.progress.setRange(0, 100)
        self.progress.setValue(percent)
        self.progress.setTextVisible(True)
        self.progress.setFormat(f"{percent}%")
        self.progress.show()

    def show_error(self, msg: str):
        QMessageBox.critical(self, "Error", msg)
