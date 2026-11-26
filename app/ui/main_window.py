import os
import tempfile

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QMainWindow, QSplitter, QMessageBox, QFileDialog, QStatusBar,
    QDialog, QVBoxLayout, QFormLayout, QComboBox, QCheckBox,
    QDialogButtonBox, QLabel, QPushButton, QHBoxLayout, QWidget,
    QInputDialog
)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
import qtawesome as qta

from app.database import ProjectDB
from app.models import Subtitle
from app.ffmpeg_utils import (
    get_duration_ms, extract_audio, has_filter, subtitle_filter_error,
)
from app.exporter import Exporter
from app.workers import (
    ASRWorker, TranslateWorker, TTSWorker, ExportWorker, DubTrackWorker,
)
from app.tts import TTSEngine, TTSRequest
from app.ui.preview import DubPreviewController
from app.ui.workflow_bar import WorkflowBar

from app.ui.left_panel import LeftPanel
from app.ui.center_panel import CenterPanel
from app.ui.right_panel import RightPanel
from app.ui.bottom_panel import BottomPanel


class ExportDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Export Final Video")
        self.setMinimumWidth(420)
        layout = QFormLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(20, 20, 20, 16)

        self.resolution = QComboBox()
        self.resolution.addItems(["Original", "720p", "1080p", "4K"])
        layout.addRow("Resolution", self.resolution)

        self.burn = QCheckBox("Burn subtitles into video")
        self.burn.setChecked(True)
        layout.addRow(self.burn)

        self.keep_audio = QCheckBox("Keep original background audio")
        layout.addRow(self.keep_audio)

        self.bgm_edit = QLabel("(none)")
        self.bgm_edit.setObjectName("Muted")
        self.btn_bgm = QPushButton(qta.icon('fa6s.music', color='#9CA3AF'), " Choose …")
        row = QHBoxLayout()
        row.addWidget(self.bgm_edit, 1)
        row.addWidget(self.btn_bgm)
        layout.addRow("Background Music", row)
        self.bgm_path = ""
        self.btn_bgm.clicked.connect(self._choose_bgm)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _choose_bgm(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose Background Music", "",
            "Audio Files (*.mp3 *.wav *.m4a *.aac);;All Files (*)")
        if path:
            self.bgm_path = path
            self.bgm_edit.setText(os.path.basename(path))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SAMRAY DUBBER PRO")
        self.resize(1600, 950)
        self.setMinimumSize(1280, 800)

        self.db = ProjectDB()
        self.exporter = Exporter()
        self.project_id = None
        self.video_path = ""
        self._preview_player = QMediaPlayer(self)
        self._preview_audio = QAudioOutput(self)
        self._preview_player.setAudioOutput(self._preview_audio)
        self._asr_worker = None
        self._translate_worker = None
        self._tts_worker = None
        self._export_worker = None
        self._dub_worker = None
        self._dub_worker_token = -1
        self._dub_enable_when_ready = False
        self._dub_cached_path = ""
        self._dub_build_id = 0

        self._build_toolbar()
        self._build_ui()
        self._build_menu()
        self._build_statusbar()
        self._restore_last_project()

        self.autosave_timer = QTimer(self)
        self.autosave_timer.timeout.connect(self.save_project)
        self.autosave_timer.start(60_000)

    def _build_toolbar(self):
        tb = QWidget()
        tb.setObjectName("Toolbar")
        tb.setFixedHeight(48)
        layout = QHBoxLayout(tb)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(6)

        self.lbl_project = QLabel("Untitled Project")
        self.lbl_project.setObjectName("ProjectName")
        layout.addWidget(self.lbl_project)

        self.lbl_saved = QLabel("• Saved")
        self.lbl_saved.setObjectName("SaveIndicator")
        layout.addWidget(self.lbl_saved)
        layout.addSpacing(24)

        self.workflow = WorkflowBar()
        layout.addWidget(self.workflow, 1)

        self.btn_prefs = QPushButton(qta.icon('fa6s.gear', color='#9CA3AF'), "")
        self.btn_prefs.setObjectName("Ghost")
        self.btn_prefs.setFixedSize(30, 30)
        layout.addWidget(self.btn_prefs)

        self._toolbar_widget = tb

    def _build_ui(self):
        self.left = LeftPanel()
        self.center = CenterPanel()
        self.right = RightPanel(self.db)
        self.bottom = BottomPanel()

        top_split = QSplitter(Qt.Horizontal)
        top_split.addWidget(self.left)
        top_split.addWidget(self.center)
        top_split.addWidget(self.right)

        top_split.setSizes([360, 800, 400])
        top_split.setStretchFactor(0, 0)
        top_split.setStretchFactor(1, 1)
        top_split.setStretchFactor(2, 0)
        top_split.setHandleWidth(6)

        main_split = QSplitter(Qt.Vertical)
        main_split.addWidget(top_split)
        main_split.addWidget(self.bottom)

        main_split.setSizes([700, 250])
        main_split.setStretchFactor(0, 1)
        main_split.setStretchFactor(1, 0)
        main_split.setHandleWidth(6)

        central = QWidget()
        vbox = QVBoxLayout(central)
        vbox.setContentsMargins(12, 0, 12, 8)
        vbox.setSpacing(8)
        vbox.addWidget(main_split)

        container = QWidget()
        cbox = QVBoxLayout(container)
        cbox.setContentsMargins(0, 0, 0, 0)
        cbox.setSpacing(0)
        cbox.addWidget(self._toolbar_widget)
        cbox.addWidget(central, 1)
        self.setCentralWidget(container)

        self.preview_controller = DubPreviewController(
            self.left.player, self.left.audio, self)
        # Immediate dub sync when the user seeks via the timeline.
        self.bottom.playhead_moved.connect(
            self.preview_controller.sync_to_position
        )

        self.left.video_loaded.connect(self._on_video_loaded)
        self.left.generate_requested.connect(self.generate_voice)
        self.left.stop_generation_requested.connect(self.stop_generation)
        self.left.export_mp3_requested.connect(self.export_mp3)
        self.left.export_video_requested.connect(self.export_video)
        self.left.player.positionChanged.connect(self._sync_playhead)
        self.left.player.durationChanged.connect(self.bottom.set_duration)
        self.left.player.playbackStateChanged.connect(
            self._on_video_playback_state
        )
        self.left.dub_preview_toggled.connect(self._on_dub_preview_toggled)
        self.left.show_subtitles_toggled.connect(
            lambda on: self._refresh_subtitle_overlay(self.left.player.position()))

        self.left.mute_original_toggled.connect(self.preview_controller.set_mute_original)

        self.center.subtitles_changed.connect(self._on_subtitles_changed)
        self.center.selection_changed.connect(self.save_project)
        self.center.play_audio_requested.connect(self._play_subtitle_audio)

        self.right.run_asr_requested.connect(self.run_asr)
        self.right.run_translate_requested.connect(self.translate_subtitles)
        self.right.preview_voice_requested.connect(self._preview_voice)

        self.bottom.playhead_moved.connect(self.left.player.setPosition)
        self.bottom.subtitle_timing_changed.connect(self._on_timeline_timing_changed)

        self.preview_controller.position_synced.connect(self._refresh_subtitle_overlay)
        self.left.player.positionChanged.connect(self._refresh_subtitle_overlay)

    def _build_menu(self):
        bar = self.menuBar()
        file_menu = bar.addMenu("File")

        act_new = QAction("New Project", self)
        act_new.setShortcut("CmdOrCtrl+N")
        act_new.triggered.connect(self.new_project)
        file_menu.addAction(act_new)

        act_open = QAction("Open Project…", self)
        act_open.setShortcut("CmdOrCtrl+O")
        act_open.triggered.connect(self.open_project)
        file_menu.addAction(act_open)

        act_save = QAction("Save Project", self)
        act_save.setShortcut("CmdOrCtrl+S")
        act_save.triggered.connect(self.save_project)
        file_menu.addAction(act_save)

        file_menu.addSeparator()
        act_quit = QAction("Quit", self)
        act_quit.setShortcut("CmdOrCtrl+Q")
        act_quit.triggered.connect(self.close)
        file_menu.addAction(act_quit)

        # Standard Help Menu without Licensing
        help_menu = bar.addMenu("Help")
        act_about = QAction("About SAMRAY DUBBER PRO", self)
        act_about.triggered.connect(lambda: QMessageBox.about(
            self, "About",
            "<h3>SAMRAY DUBBER PRO</h3>"
            "<p>Professional Video Dubbing & Subtitle Studio</p>"
            "<p>Version 1.0.0</p>"
        ))
        help_menu.addAction(act_about)

    def _build_statusbar(self):
        bar = QStatusBar()
        self.setStatusBar(bar)
        self.lbl_status = QLabel("Ready")
        bar.addWidget(self.lbl_status, 1)
        self.lbl_device = QLabel("")
        bar.addPermanentWidget(self.lbl_device)

    def _say(self, text: str, timeout: int = 0):
        self.lbl_status.setText(text)

    def _restore_last_project(self):
        p = self.db.latest_project()
        if p:
            self.project_id = p["id"]
            self.video_path = p.get("video_path", "")
            subs = self.db.load_subtitles(self.project_id)
            self.center.set_subtitles(subs)
            self.bottom.set_subtitles(subs)
            self.lbl_project.setText(p["name"])

            if self.video_path and os.path.exists(self.video_path):
                self.left.player.setSource(QUrl.fromLocalFile(self.video_path))
                self.left.video_container.show_video()
                duration = get_duration_ms(self.video_path)
                if duration > 0:
                    self.bottom.set_duration(duration)
                self._say(f"Restored: {p['name']}")
            else:
                self.left.video_container.show_empty()
                self._say(f"Restored: {p['name']} (Video file missing)")
        else:
            self.new_project()

    def new_project(self):
        self.project_id = self.db.create_project("Untitled Project")
        self.center.set_subtitles([])
        self.bottom.set_subtitles([])
        self.workflow.reset()
        self.lbl_project.setText("Untitled Project")
        self._say("New project created.")

    def open_project(self):
        rows = self.db.conn.execute("SELECT id, name FROM projects ORDER BY updated_at DESC").fetchall()
        if not rows:
            QMessageBox.information(self, "Open Project", "No saved projects.")
            return
        names = [f"{r['name']}" for r in rows]
        choice, ok = QInputDialog.getItem(self, "Open Project", "Select project:", names, 0, False)
        if not ok:
            return
        p = self.db.get_project(rows[names.index(choice)]["id"])
        self.project_id = p["id"]
        self.video_path = p.get("video_path", "")
        subs = self.db.load_subtitles(self.project_id)
        self.center.set_subtitles(subs)
        self.bottom.set_subtitles(subs)
        self.lbl_project.setText(p["name"])
        if self.video_path and os.path.exists(self.video_path):
            self.left.player.setSource(QUrl.fromLocalFile(self.video_path))
            self.left.video_container.show_video()
            duration = get_duration_ms(self.video_path)
            if duration > 0:
                self.bottom.set_duration(duration)
        self._say(f"Opened: {p['name']}")

    def save_project(self):
        if not self.project_id:
            return
        subs = self.center.get_subtitles()
        self.db.replace_subtitles(self.project_id, subs)
        self.db.update_project(self.project_id, video_path=self.video_path)
        self.lbl_saved.setText("• Saved just now")
        self._say("Project auto-saved.", 3000)

    def _on_video_loaded(self, path: str):
        if path.startswith("SRT:"):
            self._import_srt_file(path[4:])
            return
        self.video_path = path
        duration = get_duration_ms(path)
        self.bottom.set_duration(duration)
        self.db.update_project(self.project_id, video_path=path)
        self._invalidate_dub_preview()
        self.left.subtitle_overlay.show_text("")
        self.workflow.set_stage(0)
        self._say(f"Loaded: {os.path.basename(path)}")

        # Loading a new video invalidates the old mix. If playback already
        # started, rebuild the dub for the new video automatically.
        if (self.left.player.playbackState()
                == QMediaPlayer.PlaybackState.PlayingState):
            self._auto_enable_dub()

    def _on_video_playback_state(self, state):
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self._auto_enable_dub()

    def _auto_enable_dub(self):
        """Start the translated voice automatically when video plays."""
        if not self.video_path:
            return

        subs = self.center.get_subtitles()
        if not any(
            s.audio_path and os.path.exists(s.audio_path)
            for s in subs
        ):
            return

        if self.preview_controller.is_enabled():
            return

        # Going through the normal toggle path handles cached tracks,
        # running builds, and stale builds from an earlier edit.
        if not self.left.dub_enabled:
            self.left.set_dub_enabled(True)
        else:
            self._on_dub_preview_toggled(True)

    def _sync_playhead(self, ms: int):
        self.bottom.set_playhead(ms)

    def _on_subtitles_changed(self, subs):
        self.bottom.set_subtitles(subs)
        self.save_project()
        if subs and self.workflow.current < 1:
            self.workflow.set_stage(1)

        self._invalidate_dub_preview(
            "Subtitles changed — dub preview paused."
        )

    def _on_timeline_timing_changed(self, sub_id, start_ms, end_ms):
        for i, sub in enumerate(self.center.subtitles):
            if sub.id == sub_id:
                self.center.update_timecode(i, start_ms, end_ms)
                break

    def _play_subtitle_audio(self, row: int):
        subs = self.center.get_subtitles()
        if row < 0 or row >= len(subs):
            return
        path = subs[row].audio_path
        if not path or not os.path.exists(path):
            QMessageBox.information(self, "Play Audio", "No generated audio for this subtitle yet.")
            return
        self._preview_player.setSource(QUrl.fromLocalFile(path))
        self._preview_player.play()

    def import_srt(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import SRT", "", "Subtitle Files (*.srt)")
        if path:
            self._import_srt_file(path)

    def _import_srt_file(self, path: str):
        try:
            subs = parse_srt(path)
            self.center.set_subtitles(subs)
            self.bottom.set_subtitles(subs)
            self.save_project()
            self.workflow.set_stage(1)
            self._say(f"Imported {len(subs)} subtitles.")
        except Exception as e:
            QMessageBox.critical(self, "SRT Import Error", str(e))

    def export_srt(self):
        subs = self.center.get_subtitles()
        if not subs:
            QMessageBox.information(self, "Export SRT", "No subtitles to export.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export SRT", "subtitles.srt", "Subtitle Files (*.srt)")
        if path:
            self.exporter.export_srt(subs, path)
            self._say(f"SRT exported: {path}")

    def run_asr(self):
        if not self.video_path:
            QMessageBox.warning(self, "Speech Recognition", "Load a video first.")
            return
        settings = self.right.get_ai_settings()
        self.left.set_busy(True)
        self._say("Extracting audio …")
        self.workflow.set_stage(1)

        wav = os.path.join(tempfile.gettempdir(), "samray_asr.wav")
        if not extract_audio(self.video_path, wav):
            self.left.set_busy(False)
            QMessageBox.critical(self, "Error", "FFmpeg failed to extract audio.")
            return

        lang_code = {
            "Khmer": "km", "English": "en", "Thai": "th",
            "Chinese": "zh", "Japanese": "ja", "Korean": "ko",
            "Vietnamese": "vi",
        }.get(settings["source_lang"])

        self._asr_worker = ASRWorker(wav, settings["asr_model"], "auto", lang_code)
        self._asr_worker.progress.connect(self._say)
        self._asr_worker.progress_percent.connect(self.left.set_progress)
        self._asr_worker.finished.connect(self._on_asr_done)
        self._asr_worker.error.connect(self._on_worker_error)
        self._asr_worker.finished.connect(lambda _: self.left.set_busy(False))
        self._asr_worker.error.connect(lambda _: self.left.set_busy(False))
        self._asr_worker.start()

    def _on_asr_done(self, result):
        if isinstance(result, dict):
            segments = result.get("segments", [])
            detected = result.get("language", "")
        else:
            segments = result or []
            detected = ""

        subs = [Subtitle(start_ms=s["start_ms"], end_ms=s["end_ms"], text=s["text"], gender=s.get("gender", "Unknown")) for s in segments]
        self.center.set_subtitles(subs)
        self.bottom.set_subtitles(subs)
        self.save_project()
        self._say(f"Detected {len(subs)} segments ({detected})")
        if subs:
            self.workflow.set_stage(2)

    def translate_subtitles(self):
        subs = self.center.get_subtitles()
        if not subs:
            QMessageBox.information(self, "Translate", "No subtitles to translate.")
            return
        settings = self.right.get_ai_settings()
        self.left.set_busy(True)
        self.workflow.set_stage(2)
        self._invalidate_dub_preview()

        self._translate_worker = TranslateWorker(
            [s.text for s in subs],
            settings["source_lang"],
            settings["target_lang"],
            settings["provider"],
            settings["openai_key"],
            delay_sec=settings.get("delay_sec", 0.25),
            gemini_api_key=settings.get("gemini_key", ""),
            gemini_model=settings.get("gemini_model", "gemini-3.1-flash-lite"),
            gemini_batch_size=settings.get("gemini_batch_size", 20),
        )
        self._translate_worker.progress.connect(self._say)
        self._translate_worker.progress_percent.connect(self.left.set_progress)
        self._translate_worker.item_translated.connect(self._on_translate_item)
        self._translate_worker.finished.connect(self._on_translate_done)
        self._translate_worker.error.connect(self._on_worker_error)
        self._translate_worker.finished.connect(lambda _: self.left.set_busy(False))
        self._translate_worker.error.connect(lambda _: self.left.set_busy(False))
        self._translate_worker.start()

    def _on_translate_item(self, idx: int, text: str):
        if 0 <= idx < len(self.center.subtitles):
            self.center.subtitles[idx].text = text
            # The old voice clip belongs to the previous language.
            self.center.subtitles[idx].audio_path = ""
            self.center.table.blockSignals(True)
            item = self.center.table.item(idx, 3)
            if item:
                item.setText(text)
            self.center.table.blockSignals(False)

    def _on_translate_done(self, translated):
        self.center.refresh()
        self.bottom.set_subtitles(self.center.get_subtitles())
        self.save_project()
        self.workflow.set_stage(3)

        # Translated text invalidates any cached dubbed preview.
        self._invalidate_dub_preview()

        self._say("Translation complete. Generate voice again for the translated text.")

    def generate_voice(self):
        subs = self.center.get_subtitles()
        if not subs:
            QMessageBox.information(self, "Generate Voice", "No subtitles.")
            return
        if not any(s.selected for s in subs):
            QMessageBox.information(
                self, "Generate Voice",
                "Check at least one subtitle first.")
            return
        preset = self.right.get_active_preset()
        settings = self.right.get_ai_settings()
        items = [
            (i, s.text)
            for i, s in enumerate(subs)
            if s.selected and s.text.strip()
        ]
        if not items:
            QMessageBox.information(
                self, "Generate Voice",
                "The checked subtitles have no text.")
            return

        existing = [
            s for s in subs
            if s.selected and s.text.strip()
            and s.audio_path and os.path.exists(s.audio_path)
        ]
        regenerate_all = True

        if existing:
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Question)
            box.setWindowTitle("Generate Voice")
            box.setText(
                f"{len(existing)} of {len(items)} checked subtitle(s) "
                "already have voice clips."
            )
            box.setInformativeText(
                "Generate only the missing clips, or regenerate every "
                "checked subtitle?"
            )
            btn_missing = box.addButton(
                "Generate Missing", QMessageBox.AcceptRole
            )
            btn_all = box.addButton(
                "Regenerate All", QMessageBox.DestructiveRole
            )
            box.addButton(QMessageBox.Cancel)
            box.exec()

            clicked = box.clickedButton()
            if clicked is not btn_missing and clicked is not btn_all:
                return
            regenerate_all = clicked is btn_all

        items = [
            (i, s.text)
            for i, s in enumerate(subs)
            if s.selected and s.text.strip()
            and (
                regenerate_all
                or not (s.audio_path and os.path.exists(s.audio_path))
            )
        ]
        if not items:
            QMessageBox.information(
                self, "Generate Voice",
                "All checked subtitles already have voice clips."
            )
            return

        # Any preview built from the old clips is now out of date.
        self._discard_dub_build()

        self._say(f"Generating voice for {len(items)} checked subtitle(s) …")
        req = TTSRequest(
            text="", voice_id=preset.voice_id, engine=preset.engine,
            speed=preset.speed, pitch=preset.pitch, volume=preset.volume,
            emotion=preset.emotion, style=preset.style,
            api_key=settings["eleven_key"] or settings["openai_key"],
            language=settings["target_lang"])

        self.left.set_busy(True)
        self.workflow.set_stage(3)
        self._tts_worker = TTSWorker(items, req)
        self._tts_worker.progress.connect(self._say)
        self._tts_worker.progress_percent.connect(self.left.set_progress)
        self._tts_worker.item_done.connect(self._on_tts_item)
        self._tts_worker.item_failed.connect(lambda i, m: self._say(f"Subtitle {i+1} failed: {m[:80]}", 5000))
        self._tts_worker.finished.connect(lambda _: self.left.set_busy(False))
        self._tts_worker.finished.connect(self._on_tts_done)
        self._tts_worker.error.connect(self._on_tts_error)
        self._tts_worker.error.connect(self._on_worker_error)
        self._tts_worker.error.connect(lambda _: self.left.set_busy(False))
        self._tts_worker.start()

    def _on_tts_error(self):
        # A failed batch should not leave automatic dubbing armed.
        if self.left.dub_enabled:
            self.left.set_dub_enabled(False)

    def _on_tts_item(self, idx, path):
        if 0 <= idx < len(self.center.subtitles):
            self.center.set_audio_path(idx, path)
            self.bottom.update_clip_audio(idx, path)

            # Keep the subtitle on screen for the full voice duration so the
            # dub stays locked to the video.  Never shrink a subtitle and
            # never run into the next subtitle's start time.
            sub = self.center.subtitles[idx]
            voice_dur = get_duration_ms(path)
            if voice_dur > 0:
                new_end = sub.start_ms + voice_dur
                following = [
                    s for s in self.center.subtitles
                    if s.start_ms > sub.start_ms
                ]
                if following:
                    next_start = min(s.start_ms for s in following)
                    new_end = min(
                        new_end,
                        max(next_start - 50, sub.start_ms + 100)
                    )
                if int(new_end) > sub.end_ms:
                    sub.end_ms = int(new_end)
                    self.center.update_timecode(idx, sub.start_ms, sub.end_ms)

            running_current = (
                self._dub_worker is not None
                and self._dub_worker.isRunning()
                and self._dub_worker_token == self._dub_build_id
            )

            if self._dub_cached_path or running_current:
                self._discard_dub_build()

    def _on_tts_done(self, results):
        network_error = bool(
            self._tts_worker and self._tts_worker.network_error
        )
        auto_dub = bool(results) and bool(self.video_path)

        self.save_project()
        self.workflow.set_stage(4)
        self._say(f"Voice generation complete · {len(results)} clips.")

        # Force the next preview to include every newly generated clip.
        self._discard_dub_build()

        if network_error:
            if self.left.dub_enabled:
                self.left.set_dub_enabled(False)
            self._say(
                "Voice generation stopped early — partial clips were saved."
            )
            return

        # Automatically prepare the translated voice track. There is no
        # Dub button anymore; playback starts it when the video plays.
        if auto_dub:
            self._say("Voice generation complete — preparing dubbed audio …")
            self._on_dub_preview_toggled(True)

    def stop_generation(self):
        if self._tts_worker and self._tts_worker.isRunning():
            self._tts_worker.stop()
            self._say("Stopping voice generation …")

    def _preview_voice(self, data):
        try:
            engine = TTSEngine()
            path = engine.synthesize(TTSRequest(
                text=data["text"], voice_id=data["voice_id"],
                engine=data["engine"], speed=data["speed"],
                pitch=data["pitch"], volume=data["volume"],
                api_key=self.right.openai_key.text().strip()))
            self._preview_player.setSource(QUrl.fromLocalFile(path))
            self._preview_player.play()
        except Exception as e:
            QMessageBox.critical(self, "Voice Preview", str(e))

    def _busy_with_other_work(self) -> bool:
        workers = (
            self._asr_worker,
            self._translate_worker,
            self._tts_worker,
            self._export_worker,
        )
        return any(
            worker is not None and worker.isRunning()
            for worker in workers
        )

    def _remove_preview_files(self):
        try:
            names = os.listdir(self.exporter.work_dir)
        except OSError:
            return

        for name in names:
            if not (name.startswith("_preview_dub")
                    and name.endswith(".wav")):
                continue
            try:
                os.remove(os.path.join(self.exporter.work_dir, name))
            except OSError:
                pass

    def _discard_dub_build(self):
        """Make every in-flight build stale and release the current track."""
        self._dub_build_id += 1
        self._dub_worker_token = -1
        self._dub_enable_when_ready = False
        self._dub_cached_path = ""
        self.preview_controller.invalidate()
        self._remove_preview_files()

    def _invalidate_dub_preview(self, message: str = ""):
        self._discard_dub_build()
        if self.left.dub_enabled:
            self.left.set_dub_enabled(False)
        if message:
            self._say(message)

    def _on_dub_preview_toggled(self, on):
        if not on:
            self.preview_controller.set_enabled(False)
            if not self._busy_with_other_work():
                self.left.set_busy(False)
            self._say("Dub preview off.")
            return

        subs = self.center.get_subtitles()
        segments = [
            (s.audio_path, s.start_ms, s.end_ms)
            for s in subs
            if s.audio_path and os.path.exists(s.audio_path)
        ]
        if not segments:
            QMessageBox.information(self, "Dub Preview", "No generated voice clips yet.")
            self.left.set_dub_enabled(False)
            return

        # Reuse a build that is already running for the current content.
        if (self._dub_worker is not None
                and self._dub_worker.isRunning()
                and self._dub_worker_token == self._dub_build_id):
            self._dub_enable_when_ready = True
            self.left.set_busy(True)
            self._say("Finishing dubbed preview …")
            return

        if self._dub_cached_path and os.path.exists(self._dub_cached_path):
            if not self.preview_controller.has_track():
                self.preview_controller.load_dub_track(
                    self._dub_cached_path
                )
            self.preview_controller.set_enabled(True)
            self._say("Dub preview active (cached).")
            return

        # Cover the whole video, not just the last subtitle, so the dubbed
        # track stays aligned after the final line.
        video_ms = self.bottom.duration_ms if self.video_path else 0
        total_ms = max(
            max(s.end_ms for s in subs),
            int(video_ms or 0)
        ) + 500

        self._dub_build_id += 1
        build_id = self._dub_build_id
        self._dub_worker_token = build_id
        self._dub_enable_when_ready = True

        # A unique file per build means an older worker can never
        # overwrite the file a newer build is using.
        self.preview_controller.invalidate()
        self._remove_preview_files()
        out_wav = os.path.abspath(os.path.join(
            self.exporter.work_dir,
            f"_preview_dub_{build_id}.wav"
        ))

        self.left.set_progress(0)
        self.left.set_busy(True)
        self._say("Mixing dubbed audio for preview …")
        self._dub_worker = DubTrackWorker(
            self.exporter, segments, total_ms, out_wav
        )
        self._dub_worker.progress.connect(self._say)
        self._dub_worker.progress_percent.connect(self.left.set_progress)
        self._dub_worker.finished.connect(
            lambda path, token=build_id: self._on_dub_ready(path, token)
        )
        self._dub_worker.error.connect(
            lambda msg, token=build_id: self._on_dub_error(msg, token)
        )
        self._dub_worker.start()

    def _on_dub_ready(self, wav_path, build_id=0):
        # Ignore a result that finished after the content changed or after
        # a newer build was started.
        if build_id != self._dub_build_id:
            try:
                os.remove(wav_path)
            except OSError:
                pass
            if (not self._busy_with_other_work()
                    and not (self._dub_worker
                             and self._dub_worker.isRunning())):
                self.left.set_busy(False)
            return

        self._dub_cached_path = wav_path
        self.preview_controller.load_dub_track(wav_path)

        if (self.left.dub_enabled
                and self._dub_enable_when_ready):
            self.preview_controller.set_enabled(True)
            self._say("Dub preview active.")
        else:
            # Keep the finished track cached for the next play/toggle.
            self._say("Dubbed preview ready.")

        if not self._busy_with_other_work():
            self.left.set_busy(False)

        self._dub_enable_when_ready = False

    def _on_dub_error(self, message, build_id=0):
        if build_id != self._dub_build_id:
            if not self._busy_with_other_work():
                self.left.set_busy(False)
            return

        self._dub_enable_when_ready = False
        self.left.set_dub_enabled(False)
        if not self._busy_with_other_work():
            self.left.set_busy(False)
        QMessageBox.critical(self, "Dub Preview", message)

    def _refresh_subtitle_overlay(self, ms):
        overlay = self.left.subtitle_overlay
        if not self.left.chk_show_subs.isChecked():
            overlay.show_text("")
            return
        text = ""
        for s in self.center.get_subtitles():
            if s.start_ms <= ms <= s.end_ms:
                text = s.text
                break
        overlay.show_text(text)

    def export_mp3(self):
        if not self.video_path:
            QMessageBox.warning(self, "Export MP3", "Load a video first.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export MP3", "audio.mp3", "MP3 (*.mp3);;WAV (*.wav)")
        if path:
            fmt = "wav" if path.lower().endswith(".wav") else "mp3"
            try:
                self.exporter.export_audio(self.video_path, path, fmt)
                self._say(f"Audio exported: {path}")
            except Exception as e:
                QMessageBox.critical(self, "Export Error", str(e))

    def export_video(self):
        if not self.video_path:
            QMessageBox.warning(self, "Export Video", "Load a video first.")
            return
        subs = self.center.get_subtitles()
        segments = [(s.audio_path, s.start_ms, s.end_ms) for s in subs if s.audio_path and os.path.exists(s.audio_path)]
        if not segments:
            QMessageBox.warning(self, "Export Video", "No generated voice clips.")
            return
        dlg = ExportDialog(self)
        dlg.keep_audio.setChecked(not self.left.chk_mute_original.isChecked())
        if dlg.exec() != QDialog.Accepted:
            return

        if dlg.burn.isChecked() and not has_filter("subtitles"):
            QMessageBox.critical(
                self, "Subtitle Burn-in Unavailable",
                subtitle_filter_error()
            )
            return

        default_name = (os.path.splitext(os.path.basename(self.video_path))[0] + "_dubbed.mp4")
        out_path, _ = QFileDialog.getSaveFileName(self, "Save Dubbed Video", default_name, "MP4 Video (*.mp4)")
        if not out_path:
            return
        total_ms = max(
            max(s.end_ms for s in subs),
            int(self.bottom.duration_ms or 0)
        ) + 500
        resolution = dlg.resolution.currentText().lower()
        resolution = "original" if resolution == "original" else resolution

        # The preview file is deleted during export; stop using it first.
        self.left.set_dub_enabled(False)
        self._discard_dub_build()

        self.left.set_progress(0)
        self.workflow.set_stage(4)

        self._export_worker = ExportWorker(
            self.exporter, self.video_path, segments, total_ms,
            out_path, subs, dlg.bgm_path, resolution,
            dlg.burn.isChecked(), dlg.keep_audio.isChecked())

        self._export_worker.progress.connect(self._say)
        self._export_worker.progress_percent.connect(self.left.set_progress)
        self._export_worker.finished.connect(self._on_export_done)
        self._export_worker.error.connect(self._on_worker_error)
        self._export_worker.finished.connect(lambda _: self.left.set_busy(False))
        self._export_worker.error.connect(lambda _: self.left.set_busy(False))
        self._export_worker.start()

    def _on_export_done(self, path):
        self.workflow.complete_all()
        QMessageBox.information(self, "Export Complete", f"Final video saved to:\n{path}")
        self._say(f"Export complete: {path}")

        # Resume the automatic dub preview if the video is still playing.
        if (self.left.player.playbackState()
                == QMediaPlayer.PlaybackState.PlayingState):
            self._auto_enable_dub()

    def _on_worker_error(self, msg):
        self.left.set_busy(False)
        QMessageBox.critical(self, "Processing Error", msg[:2500])
        self._say("Error – see dialog.")

    def closeEvent(self, event):
        if self.project_id:
            self.save_project()
        self.db.close()
        super().closeEvent(event)


def parse_srt(path):
    import re
    with open(path, "r", encoding="utf-8-sig") as f:
        content = f.read().replace("\r\n", "\n")
    blocks = re.split(r"\n\s*\n", content.strip())
    subs = []
    time_re = re.compile(r"(\d{2}):(\d{2}):(\d{2}),(\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2}),(\d{3})")
    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) < 2: continue
        tc_idx = next((i for i, l in enumerate(lines) if "-->" in l), None)
        if tc_idx is None: continue
        m = time_re.search(lines[tc_idx])
        if not m: continue
        sh, sm, ss, sms, eh, em, es, ems = map(int, m.groups())
        start = ((sh * 3600 + sm * 60 + ss) * 1000) + sms
        end = ((eh * 3600 + em * 60 + es) * 1000) + ems
        text = " ".join(lines[tc_idx + 1:]).strip()
        subs.append(Subtitle(start_ms=start, end_ms=end, text=text))
    return subs