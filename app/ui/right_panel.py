import os
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QTabWidget, QWidget,
    QComboBox, QLineEdit, QPushButton, QSlider, QCheckBox, QGroupBox,
    QFormLayout, QMessageBox, QInputDialog, QFileDialog,
    QRadioButton, QButtonGroup,
)
import qtawesome as qta

from app.models import VoicePreset
from app.tts import list_edge_voices


class RightPanel(QFrame):
    settings_changed = Signal(dict)
    run_asr_requested = Signal()
    run_translate_requested = Signal()
    preview_voice_requested = Signal(dict)

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.setObjectName("Panel")
        self.current_preset = None
        self._build_ui()
        self._load_presets()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(8)

        title = QLabel("TOOLS")
        title.setObjectName("PanelTitle")
        root.addWidget(title)

        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)

        self.tabs.addTab(self._build_voices_tab(), "Voices")
        self.tabs.addTab(self._build_engine_tab(), "Engine")
        self.tabs.addTab(self._build_fx_tab(), "Video FX")
        self.tabs.addTab(self._build_ai_tab(), "AI")
        self.tabs.addTab(self._build_settings_tab(), "Settings")

    # ------------------------------------------------ voices
    def _build_voices_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 12, 0, 8)
        layout.setSpacing(10)

        row = QHBoxLayout()
        self.preset_combo = QComboBox()
        row.addWidget(self.preset_combo, 1)
        self.btn_new_preset = QPushButton(qta.icon('fa6s.plus', color='#E5E7EB'), "")
        self.btn_new_preset.setFixedSize(30, 30)
        self.btn_new_preset.setObjectName("Ghost")
        row.addWidget(self.btn_new_preset)
        layout.addLayout(row)

        form = QFormLayout()
        form.setSpacing(8)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.preset_name = QLineEdit()
        form.addRow("Name", self.preset_name)

        self.engine_combo = QComboBox()
        self.engine_combo.addItems(
            ["edge", "elevenlabs", "openai", "piper", "xtts", "local"])
        form.addRow("Engine", self.engine_combo)

        self.voice_combo = QComboBox()
        self.voice_combo.setEditable(True)
        form.addRow("Voice", self.voice_combo)

        self.gender_combo = QComboBox()
        self.gender_combo.addItems(["Female", "Male", "Child", "Unknown"])
        form.addRow("Gender", self.gender_combo)

        self.speed_slider = self._slider_row(form, "Speed", 50, 200, 100)
        self.pitch_slider = self._slider_row(form, "Pitch", -12, 12, 0)
        self.volume_slider = self._slider_row(form, "Volume", 0, 200, 100)

        self.emotion_combo = QComboBox()
        self.emotion_combo.addItems(
            ["neutral", "happy", "sad", "angry", "calm", "excited", "friendly"])
        form.addRow("Emotion", self.emotion_combo)

        self.style_combo = QComboBox()
        self.style_combo.addItems(
            ["general", "narration", "conversation", "news", "story"])
        form.addRow("Style", self.style_combo)

        layout.addLayout(form)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)
        self.btn_preview = QPushButton(qta.icon('fa6s.volume-high', color='white'), " Preview")
        self.btn_preview.setObjectName("Primary")
        self.btn_save_preset = QPushButton(qta.icon('fa6s.floppy-disk', color='#E5E7EB'), "")
        self.btn_update_preset = QPushButton(qta.icon('fa6s.rotate', color='#E5E7EB'), "")
        self.btn_rename_preset = QPushButton(qta.icon('fa6s.pen', color='#E5E7EB'), "")
        self.btn_delete_preset = QPushButton(qta.icon('fa6s.trash', color='white'), "")
        self.btn_delete_preset.setObjectName("Danger")
        for b in (self.btn_save_preset, self.btn_update_preset,
                  self.btn_rename_preset, self.btn_delete_preset):
            b.setFixedSize(30, 30)
        btn_row.addWidget(self.btn_preview, 1)
        for b in (self.btn_save_preset, self.btn_update_preset,
                  self.btn_rename_preset, self.btn_delete_preset):
            btn_row.addWidget(b)
        layout.addLayout(btn_row)
        layout.addStretch()

        self.preset_combo.currentIndexChanged.connect(self._on_preset_selected)
        self.btn_new_preset.clicked.connect(self._new_preset)
        self.btn_save_preset.clicked.connect(self._save_preset)
        self.btn_update_preset.clicked.connect(self._update_preset)
        self.btn_rename_preset.clicked.connect(self._rename_preset)
        self.btn_delete_preset.clicked.connect(self._delete_preset)
        self.btn_preview.clicked.connect(self._preview)
        self.engine_combo.currentTextChanged.connect(
            lambda _text: self._refresh_voices())
        return w

    def _slider_row(self, form, label, lo, hi, val):
        s = QSlider(Qt.Horizontal)
        s.setRange(lo, hi)
        s.setValue(val)
        form.addRow(label, s)
        return s

    def _load_presets(self):
        self.preset_combo.blockSignals(True)
        self.preset_combo.clear()
        self.presets = self.db.list_presets()
        for p in self.presets:
            self.preset_combo.addItem(p.name, p.id)
        self.preset_combo.blockSignals(False)
        if self.presets:
            self.preset_combo.setCurrentIndex(0)
            self._on_preset_selected(0)

    def _on_preset_selected(self, index):
        if index < 0 or index >= len(self.presets):
            return
        p = self.presets[index]
        self.current_preset = p
        self.preset_name.setText(p.name)
        self.engine_combo.setCurrentText(p.engine)
        self.gender_combo.setCurrentText(p.gender)
        self.speed_slider.setValue(int(p.speed * 100))
        self.pitch_slider.setValue(int(p.pitch))
        self.volume_slider.setValue(int(p.volume * 100))
        self.emotion_combo.setCurrentText(p.emotion)
        self.style_combo.setCurrentText(p.style)
        self._refresh_voices()
        # Voice entries show "id (gender)" as their label and keep the real
        # voice id in the item data, so match on data rather than text.
        idx = self.voice_combo.findData(p.voice_id)
        if idx < 0:
            # The cached list may not contain this voice (offline start or
            # a custom id). Keep the preset usable instead of silently
            # falling back to whichever voice happens to be first.
            self.voice_combo.addItem(
                f"{p.voice_id} ({p.gender})", p.voice_id)
            idx = self.voice_combo.count() - 1
        self.voice_combo.setCurrentIndex(idx)

    def _refresh_voices(self):
        engine = self.engine_combo.currentText()
        self.voice_combo.clear()
        if engine == "edge":
            try:
                voices = list_edge_voices("km-KH") + list_edge_voices("en-US")
            except Exception:
                voices = []

            if voices:
                for v in voices:
                    self.voice_combo.addItem(
                        f"{v['name']} ({v['gender']})", v["name"])
            else:
                # Offline fallback: keep the presets usable.
                for name, gender in (
                    ("km-KH-PisethNeural", "Male"),
                    ("km-KH-SreymomNeural", "Female"),
                    ("en-US-JennyNeural", "Female"),
                    ("en-US-AndrewNeural", "Male"),
                    ("en-US-AvaMultilingualNeural", "Female"),
                ):
                    self.voice_combo.addItem(
                        f"{name} ({gender})", name)
        elif engine == "elevenlabs":
            for name in ("21m00Tcm4TlvDq8ikWAM",
                         "AZnzlk1XvdvUeBnXmlld",
                         "EXAVITQu4vr4xnSDxMaL",
                         "ErXwobaYiN019PkySvjV"):
                self.voice_combo.addItem(name, name)
        elif engine == "openai":
            for name in ("alloy", "echo", "fable", "onyx", "nova", "shimmer"):
                self.voice_combo.addItem(name, name)
        elif engine == "piper":
            self.voice_combo.addItem("/path/to/voice.onnx",
                                     "/path/to/voice.onnx")
        else:
            self.voice_combo.addItem("default", "default")

    def _collect_preset(self):
        return VoicePreset(
            id=self.current_preset.id if self.current_preset else 0,
            name=self.preset_name.text().strip() or "Untitled",
            engine=self.engine_combo.currentText(),
            voice_id=self.voice_combo.currentData() or self.voice_combo.currentText(),
            gender=self.gender_combo.currentText(),
            speed=self.speed_slider.value() / 100.0,
            pitch=float(self.pitch_slider.value()),
            volume=self.volume_slider.value() / 100.0,
            emotion=self.emotion_combo.currentText(),
            style=self.style_combo.currentText())

    def _new_preset(self):
        self.current_preset = VoicePreset()
        self.preset_name.setText("New Preset")
        self.preset_combo.setCurrentIndex(-1)

    def _save_preset(self):
        p = self._collect_preset()
        p.id = 0
        new_id = self.db.save_preset(p)
        self._load_presets()
        idx = self.preset_combo.findData(new_id)
        if idx >= 0:
            self.preset_combo.setCurrentIndex(idx)

    def _update_preset(self):
        if not self.current_preset:
            return
        p = self._collect_preset()
        self.db.save_preset(p)
        self._load_presets()

    def _rename_preset(self):
        if not self.current_preset:
            return
        name, ok = QInputDialog.getText(
            self, "Rename Preset", "New name:", text=self.current_preset.name)
        if ok and name.strip():
            self.current_preset.name = name.strip()
            self.db.save_preset(self.current_preset)
            self._load_presets()

    def _delete_preset(self):
        if not self.current_preset:
            return
        if QMessageBox.question(
                self, "Delete Preset",
                f"Delete '{self.current_preset.name}'?") == QMessageBox.Yes:
            self.db.delete_preset(self.current_preset.id)
            self.current_preset = None
            self._load_presets()

    def _preview(self):
        p = self._collect_preset()
        text = ("សួស្តី! នេះជាការសាកល្បងសំឡេងរបស់អ្នក។"
                if p.voice_id.startswith("km")
                else "Hello! This is a voice preview.")
        self.preview_voice_requested.emit({
            "text": text, "voice_id": p.voice_id, "engine": p.engine,
            "speed": p.speed, "pitch": p.pitch, "volume": p.volume})

    def get_active_preset(self):
        return self._collect_preset()

    # ------------------------------------------------ engine
    def _build_engine_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 12, 0, 8)
        layout.setSpacing(10)

        group = QGroupBox("VOICE ENGINE")
        gl = QVBoxLayout(group)
        gl.setSpacing(4)
        self.engine_buttons = QButtonGroup(self)
        for i, name in enumerate([
                "Edge TTS (free)", "ElevenLabs API", "OpenAI TTS",
                "Piper TTS", "XTTS / Coqui", "Local AI Engine"]):
            rb = QRadioButton(name)
            if i == 0:
                rb.setChecked(True)
            self.engine_buttons.addButton(rb, i)
            gl.addWidget(rb)
        layout.addWidget(group)

        api_group = QGroupBox("API KEYS")
        al = QFormLayout(api_group)
        al.setSpacing(8)
        self.eleven_key = QLineEdit()
        self.eleven_key.setEchoMode(QLineEdit.Password)
        self.eleven_key.setPlaceholderText("ElevenLabs API key")
        al.addRow("ElevenLabs", self.eleven_key)
        self.openai_key = QLineEdit()
        self.openai_key.setEchoMode(QLineEdit.Password)
        self.openai_key.setPlaceholderText("OpenAI API key")
        al.addRow("OpenAI", self.openai_key)
        layout.addWidget(api_group)

        gpu_group = QGroupBox("PERFORMANCE")
        gpl = QVBoxLayout(gpu_group)
        self.chk_gpu = QCheckBox("Enable GPU acceleration")
        self.chk_gpu.setChecked(True)
        gpl.addWidget(self.chk_gpu)
        layout.addWidget(gpu_group)
        layout.addStretch()
        return w

    # ------------------------------------------------ FX
    def _build_fx_tab(self):
        w = QWidget()
        layout = QFormLayout(w)
        layout.setContentsMargins(0, 12, 0, 8)
        layout.setSpacing(8)
        self.fx_brightness = self._slider_row(layout, "Brightness", -100, 100, 0)
        self.fx_contrast = self._slider_row(layout, "Contrast", -100, 100, 0)
        self.fx_blur = self._slider_row(layout, "Blur", 0, 10, 0)
        self.fx_saturation = self._slider_row(layout, "Saturation", 0, 200, 100)
        self.chk_fx_subtitle = QCheckBox("Burn subtitles into video")
        self.chk_fx_subtitle.setChecked(True)
        layout.addRow(self.chk_fx_subtitle)
        return w

    # ------------------------------------------------ AI
    def _build_ai_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 12, 0, 8)
        layout.setSpacing(10)

        group = QGroupBox("LANGUAGE")
        form = QFormLayout(group)
        form.setSpacing(8)
        self.source_lang = QComboBox()
        self.target_lang = QComboBox()
        langs = ["Khmer", "English", "Thai", "Chinese", "Japanese",
                 "Korean", "Vietnamese"]
        self.source_lang.addItems(langs)
        self.target_lang.addItems(langs)
        self.target_lang.setCurrentText("Khmer")
        form.addRow("Source", self.source_lang)
        form.addRow("Target", self.target_lang)
        layout.addWidget(group)

        asr_group = QGroupBox("SPEECH RECOGNITION")
        asr_form = QFormLayout(asr_group)
        asr_form.setSpacing(8)
        self.asr_model = QComboBox()
        self.asr_model.setEditable(True)
        self.asr_model.addItems([
            "tiny", "base", "small", "medium", "large-v3",
            "Tnaot/whisper-large-v3-khmer-ct2"])
        self.asr_model.setCurrentText("base")
        asr_form.addRow("Whisper Model", self.asr_model)

        self.translate_provider = QComboBox()
        self.translate_provider.addItems(
            ["deep-translator", "google", "openai"])
        self.translate_provider.setCurrentText("deep-translator")
        asr_form.addRow("Translator", self.translate_provider)
        layout.addWidget(asr_group)

        self.btn_run_asr = QPushButton(
            qta.icon('fa6s.microphone', color='white'), "  Run Speech Recognition")
        self.btn_run_asr.setObjectName("Primary")
        self.btn_run_asr.setMinimumHeight(32)
        self.btn_run_translate = QPushButton(
            qta.icon('fa6s.language', color='white'), "  Translate Subtitles")
        self.btn_run_translate.setObjectName("Accent")
        self.btn_run_translate.setMinimumHeight(32)
        layout.addWidget(self.btn_run_asr)
        layout.addWidget(self.btn_run_translate)

        info = QLabel(
            "① Load a video  →  ② Run Speech Recognition  →  "
            "③ Edit subtitles  →  ④ Translate  →  "
            "⑤ Generate Voice  →  ⑥ Export")
        info.setObjectName("Muted")
        info.setWordWrap(True)
        info.setStyleSheet("padding: 8px; background: #1A2029; border-radius: 6px;")
        layout.addWidget(info)
        layout.addStretch()

        self.btn_run_asr.clicked.connect(self.run_asr_requested.emit)
        self.btn_run_translate.clicked.connect(self.run_translate_requested.emit)
        return w

    # ------------------------------------------------ settings
    def _build_settings_tab(self):
        w = QWidget()
        layout = QFormLayout(w)
        layout.setContentsMargins(0, 12, 0, 8)
        layout.setSpacing(8)

        self.output_dir_edit = QLineEdit(os.path.abspath("output"))
        browse = QPushButton(qta.icon('fa6s.folder-open', color='#E5E7EB'), "")
        browse.setFixedSize(30, 30)
        row = QHBoxLayout()
        row.addWidget(self.output_dir_edit, 1)
        row.addWidget(browse)
        layout.addRow("Output", row)

        self.chk_autosave = QCheckBox("Auto-save every 60 seconds")
        self.chk_autosave.setChecked(True)
        layout.addRow(self.chk_autosave)

        self.chk_confirm = QCheckBox("Confirm before deleting")
        self.chk_confirm.setChecked(True)
        layout.addRow(self.chk_confirm)

        self.font_combo = QComboBox()
        self.font_combo.addItems(
            ["Khmer OS", "Noto Sans Khmer", "Kantumruy Pro", "Battambang"])
        layout.addRow("Khmer Font", self.font_combo)

        browse.clicked.connect(self._browse_output)
        return w

    def _browse_output(self):
        d = QFileDialog.getExistingDirectory(self, "Select Output Folder")
        if d:
            self.output_dir_edit.setText(d)

    # ------------------------------------------------ helpers
    def get_ai_settings(self):
        return {
            "source_lang": self.source_lang.currentText(),
            "target_lang": self.target_lang.currentText(),
            "asr_model": self.asr_model.currentText().strip() or "base",
            "provider": self.translate_provider.currentText(),
            "openai_key": self.openai_key.text().strip(),
            "eleven_key": self.eleven_key.text().strip(),
            "gpu": self.chk_gpu.isChecked(),
            "delay_sec": 0.25,
        }

    def get_export_settings(self):
        return {
            "resolution": "original",
            "burn_subtitles": self.chk_fx_subtitle.isChecked(),
            "output_dir": self.output_dir_edit.text(),
        }