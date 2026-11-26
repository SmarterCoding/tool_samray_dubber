
import os

import qtawesome as qta

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QAbstractItemView,
    QMessageBox,
    QComboBox,
    QCheckBox,
)

from app.models import Subtitle
from app.ffmpeg_utils import srt_time


class CenterPanel(QFrame):

    # Subtitle data changed
    subtitles_changed = Signal(list)

    # Checkbox state changed (Generate Voice / Delete selection)
    selection_changed = Signal()

    # Request generated translated voice playback
    play_audio_requested = Signal(int)

    # Request voice playback stop
    stop_audio_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setObjectName("Panel")

        self.subtitles: list[Subtitle] = []

        self._playing_row = -1
        self._play_buttons = {}

        self._build_ui()

    # =====================================================
    # UI
    # =====================================================

    def _build_ui(self):

        root = QVBoxLayout(self)

        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(10)

        # ---------------- HEADER ----------------

        header = QHBoxLayout()

        title = QLabel("SUBTITLES")
        title.setObjectName("PanelTitle")

        header.addWidget(title)

        self.lbl_count = QLabel("0")
        self.lbl_count.setObjectName("Muted")
        self.lbl_count.setStyleSheet("padding: 0 8px;")

        header.addWidget(self.lbl_count)

        self.lbl_checked = QLabel("0 checked")
        self.lbl_checked.setObjectName("Muted")
        self.lbl_checked.setStyleSheet("padding: 0 8px;")

        header.addWidget(self.lbl_checked)

        header.addStretch()

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search ...")
        self.search.setFixedWidth(250)

        header.addWidget(self.search)

        root.addLayout(header)

        # ---------------- TOOLBAR ----------------

        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)

        self.btn_add = QPushButton(
            qta.icon("fa6s.plus", color="#E5E7EB"),
            " Add"
        )

        self.btn_split = QPushButton(
            qta.icon("fa6s.scissors", color="#E5E7EB"),
            " Split"
        )

        self.btn_merge = QPushButton(
            qta.icon("fa6s.code-merge", color="#E5E7EB"),
            " Merge"
        )

        self.btn_detect = QPushButton(
            qta.icon("fa6s.robot", color="white"),
            " Auto Detect"
        )

        self.btn_detect.setObjectName("Accent")

        self.btn_delete = QPushButton(
            qta.icon("fa6s.trash", color="white"),
            " Delete"
        )

        self.btn_delete.setObjectName("Danger")
        self.btn_delete.setToolTip("Delete checked subtitles")

        for button in (
            self.btn_add,
            self.btn_split,
            self.btn_merge
        ):
            toolbar.addWidget(button)

        self.chk_select_all = QCheckBox("Select All")
        self.chk_select_all.setTristate(True)
        self.chk_select_all.setToolTip(
            "Check or uncheck every subtitle. Checked subtitles are used "
            "by Generate Voice and Delete."
        )
        self.chk_select_all.clicked.connect(self._toggle_select_all)
        toolbar.addWidget(self.chk_select_all)

        toolbar.addStretch()

        toolbar.addWidget(self.btn_detect)
        toolbar.addWidget(self.btn_delete)

        root.addLayout(toolbar)

        # ---------------- TABLE ----------------

        self.table = QTableWidget(0, 7)

        self.table.setHorizontalHeaderLabels([
            "USE",
            "THOUGHT",
            "ID",
            "TIMECODE",
            "SUBTITLE",
            "SPEAKER",
            "PLAY"
        ])

        self.table.horizontalHeaderItem(0).setToolTip(
            "Checked subtitles are used by Generate Voice and Delete"
        )
        self.table.horizontalHeaderItem(1).setToolTip(
            "Internal monologue: uses the separate thought voice/effect "
            "configured in Tools → Monologue"
        )

        self.table.setAlternatingRowColors(True)

        self.table.setSelectionBehavior(
            QAbstractItemView.SelectRows
        )

        self.table.setSelectionMode(
            QAbstractItemView.ExtendedSelection
        )

        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(42)

        self.table.setShowGrid(False)

        self.table.setEditTriggers(
            QAbstractItemView.DoubleClicked |
            QAbstractItemView.SelectedClicked
        )

        # Column sizing

        hdr = self.table.horizontalHeader()

        hdr.setSectionResizeMode(0, QHeaderView.Fixed)
        hdr.resizeSection(0, 42)

        hdr.setSectionResizeMode(1, QHeaderView.Fixed)
        hdr.resizeSection(1, 72)

        hdr.setSectionResizeMode(2, QHeaderView.Fixed)
        hdr.resizeSection(2, 45)

        hdr.setSectionResizeMode(3, QHeaderView.Fixed)
        hdr.resizeSection(3, 290)

        hdr.setSectionResizeMode(4, QHeaderView.Stretch)

        hdr.setSectionResizeMode(5, QHeaderView.Fixed)
        hdr.resizeSection(5, 120)

        hdr.setSectionResizeMode(6, QHeaderView.Fixed)
        hdr.resizeSection(6, 60)

        self.table.itemChanged.connect(
            self._on_item_changed
        )

        root.addWidget(self.table, 1)

        # ---------------- EVENTS ----------------

        self.btn_add.clicked.connect(
            self.add_subtitle
        )

        self.btn_split.clicked.connect(
            self.split_selected
        )

        self.btn_merge.clicked.connect(
            self.merge_selected
        )

        self.btn_delete.clicked.connect(
            self.delete_selected
        )

        self.btn_detect.clicked.connect(
            self._show_detect_message
        )

        self.search.textChanged.connect(
            self._filter
        )

    # =====================================================
    # PLAY BUTTON
    # =====================================================

    def _create_play_button(self, row):

        button = QPushButton()

        button.setFixedSize(34, 30)

        button.setCursor(Qt.PointingHandCursor)

        button.setToolTip(
            f"Play translated voice - Subtitle {row + 1}"
        )

        button.setStyleSheet("""
            QPushButton {
                background-color: #10B981;
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 14px;
                font-weight: bold;
            }

            QPushButton:hover {
                background-color: #059669;
            }

            QPushButton:pressed {
                background-color: #047857;
            }

            QPushButton:disabled {
                background-color: #374151;
                color: #9CA3AF;
            }
        """)

        button.clicked.connect(
            lambda checked=False, r=row:
                self._on_play_clicked(r)
        )

        self._update_play_button(button, row)

        return button

    def _update_play_button(self, button, row):

        has_audio = False

        if 0 <= row < len(self.subtitles):

            path = self.subtitles[row].audio_path

            has_audio = bool(path) and os.path.exists(path)

        if not has_audio:

            button.setText("▶")
            button.setEnabled(False)
            button.setToolTip(
                "No generated voice yet - use Generate Voice"
            )

            button.setStyleSheet("""
                QPushButton {
                    background-color: #374151;
                    color: #9CA3AF;
                    border: none;
                    border-radius: 6px;
                    font-size: 14px;
                    font-weight: bold;
                }
            """)

            return

        button.setEnabled(True)

        if row == self._playing_row:

            button.setText("■")
            button.setToolTip("Stop translated voice")

            button.setStyleSheet("""
                QPushButton {
                    background-color: #EF4444;
                    color: white;
                    border: none;
                    border-radius: 6px;
                    font-size: 14px;
                    font-weight: bold;
                }

                QPushButton:hover {
                    background-color: #DC2626;
                }
            """)

        else:

            button.setText("▶")
            button.setToolTip(
                f"Play translated voice - Subtitle {row + 1}"
            )

            button.setStyleSheet("""
                QPushButton {
                    background-color: #10B981;
                    color: white;
                    border: none;
                    border-radius: 6px;
                    font-size: 14px;
                    font-weight: bold;
                }

                QPushButton:hover {
                    background-color: #059669;
                }
            """)

    def _on_play_clicked(self, row):

        if not 0 <= row < len(self.subtitles):
            return

        # Click currently playing row = stop
        if self._playing_row == row:

            self.stop_audio_requested.emit()
            self.set_playing_row(-1)

            return

        # Start another translated voice
        self.set_playing_row(row)

        self.play_audio_requested.emit(row)

    def set_audio_path(self, row, path):

        if 0 <= row < len(self.subtitles):

            self.subtitles[row].audio_path = path

            button = self._play_buttons.get(row)

            if button is not None:
                self._update_play_button(button, row)

    def set_playing_row(self, row):

        """
        Call this method from your audio player when
        a translated voice starts or stops.
        """

        self._playing_row = row

        for index, button in self._play_buttons.items():

            self._update_play_button(button, index)

    def stop_playback_ui(self):

        self.set_playing_row(-1)

    # =====================================================
    # SET SUBTITLES
    # =====================================================

    def set_subtitles(self, subs):

        self.subtitles = subs or []

        self._playing_row = -1

        self.refresh()

    # =====================================================
    # REFRESH TABLE
    # =====================================================

    def refresh(self):

        self.table.blockSignals(True)

        self.table.setRowCount(len(self.subtitles))

        self._play_buttons.clear()

        khmer_font = QFont("Khmer OS", 11)

        for row, sub in enumerate(self.subtitles):

            sub.idx = row

            # ---------------- USE CHECKBOX ----------------

            item_use = QTableWidgetItem("")

            item_use.setFlags(
                Qt.ItemIsEnabled |
                Qt.ItemIsSelectable |
                Qt.ItemIsUserCheckable
            )

            item_use.setCheckState(
                Qt.CheckState.Checked
                if sub.selected
                else Qt.CheckState.Unchecked
            )

            item_use.setData(
                Qt.UserRole,
                sub.id
            )

            item_use.setToolTip(
                "Include this subtitle in Generate Voice / Delete"
            )

            self.table.setItem(
                row, 0, item_use
            )

            # ---------------- INTERNAL MONOLOGUE ----------------

            item_thought = QTableWidgetItem("")

            item_thought.setFlags(
                Qt.ItemIsEnabled |
                Qt.ItemIsSelectable |
                Qt.ItemIsUserCheckable
            )

            item_thought.setCheckState(
                Qt.CheckState.Checked
                if sub.monologue
                else Qt.CheckState.Unchecked
            )

            item_thought.setData(
                Qt.UserRole,
                sub.id
            )

            item_thought.setToolTip(
                "Dub this line as an internal thought using the "
                "separate voice/effect from Tools → Monologue"
            )

            self.table.setItem(
                row, 1, item_thought
            )

            # ---------------- ID ----------------

            item_id = QTableWidgetItem(
                str(row + 1)
            )

            item_id.setFlags(
                Qt.ItemIsEnabled |
                Qt.ItemIsSelectable
            )

            item_id.setData(
                Qt.UserRole,
                sub.id
            )

            self.table.setItem(
                row, 2, item_id
            )

            # ---------------- TIMECODE ----------------

            item_tc = QTableWidgetItem(
                f"{srt_time(sub.start_ms)} → "
                f"{srt_time(sub.end_ms)}"
            )

            item_tc.setFlags(
                Qt.ItemIsEnabled |
                Qt.ItemIsSelectable
            )

            item_tc.setFont(
                QFont("Consolas", 10)
            )

            self.table.setItem(
                row, 3, item_tc
            )

            # ---------------- SUBTITLE ----------------

            item_text = QTableWidgetItem(
                sub.text
            )

            item_text.setFont(khmer_font)

            self.table.setItem(
                row, 4, item_text
            )

            # ---------------- SPEAKER ----------------

            combo = QComboBox()

            combo.addItems([
                "Female",
                "Male",
                "Child",
                "Unknown"
            ])

            combo.setCurrentText(
                sub.gender or "Female"
            )

            combo.setStyleSheet("""
                QComboBox {
                    border: none;
                    background: transparent;
                    padding: 4px;
                }
            """)

            combo.currentTextChanged.connect(
                lambda value, r=row:
                    self._set_gender(r, value)
            )

            self.table.setCellWidget(
                row, 5, combo
            )

            # ---------------- PLAY BUTTON ----------------

            button = self._create_play_button(row)

            self._play_buttons[row] = button

            container = QWidget()

            layout = QHBoxLayout(container)

            layout.setContentsMargins(
                2, 2, 2, 2
            )

            layout.setAlignment(
                Qt.AlignCenter
            )

            layout.addWidget(button)

            self.table.setCellWidget(
                row, 6, container
            )

        self.table.blockSignals(False)

        self._update_selection_summary()

        self._filter(self.search.text())

    # =====================================================
    # SEARCH
    # =====================================================

    def _filter(self, text):

        text = text.lower().strip()

        for row in range(self.table.rowCount()):

            item = self.table.item(row, 4)

            match = (
                item is not None and
                text in item.text().lower()
            )

            self.table.setRowHidden(
                row, not match
            )

    # =====================================================
    # CHECKED SUBTITLES
    # =====================================================

    def checked_rows(self):

        return [
            index
            for index, sub in enumerate(self.subtitles)
            if sub.selected
        ]

    def checked_subtitles(self):

        return [
            sub
            for sub in self.subtitles
            if sub.selected
        ]

    def _toggle_select_all(self, _checked=False):

        target = (
            not all(sub.selected for sub in self.subtitles)
            if self.subtitles
            else True
        )

        self._set_all_selected(target)

    def _set_all_selected(self, checked: bool):

        if not self.subtitles:
            return

        for sub in self.subtitles:
            sub.selected = bool(checked)

        self.table.blockSignals(True)

        for row in range(self.table.rowCount()):

            item = self.table.item(row, 0)

            if item is not None:
                item.setCheckState(
                    Qt.CheckState.Checked
                    if checked
                    else Qt.CheckState.Unchecked
                )

        self.table.blockSignals(False)

        self._update_selection_summary()

        self.selection_changed.emit()

    def _update_selection_summary(self):

        total = len(self.subtitles)
        checked = sum(
            1 for sub in self.subtitles if sub.selected
        )

        self.lbl_count.setText(str(total))
        self.lbl_checked.setText(f"{checked} checked")

        self.chk_select_all.blockSignals(True)

        if total and checked == total:
            self.chk_select_all.setCheckState(
                Qt.CheckState.Checked
            )
        elif checked:
            self.chk_select_all.setCheckState(
                Qt.CheckState.PartiallyChecked
            )
        else:
            self.chk_select_all.setCheckState(
                Qt.CheckState.Unchecked
            )

        self.chk_select_all.blockSignals(False)

    # =====================================================
    # EDIT SUBTITLE
    # =====================================================

    def _on_item_changed(self, item):

        row = item.row()

        if not (0 <= row < len(self.subtitles)):
            return

        # Checkbox column: update the model and the header summary.
        if item.column() == 0:

            self.subtitles[row].selected = (
                item.checkState() == Qt.CheckState.Checked
            )

            self._update_selection_summary()

            # Persist the checkbox state so it survives app restarts.
            self.selection_changed.emit()

            return

        # Internal-monologue checkbox: the generated voice may use a
        # different voice, so the old clip no longer matches.
        if item.column() == 1:

            sub = self.subtitles[row]

            monologue = (
                item.checkState() == Qt.CheckState.Checked
            )

            if sub.monologue != monologue:

                sub.monologue = monologue
                sub.audio_path = ""

                button = self._play_buttons.get(row)

                if button is not None:
                    self._update_play_button(button, row)

                self.subtitles_changed.emit(
                    self.subtitles
                )

            return

        if item.column() != 4:
            return

        if self.subtitles[row].text != item.text():

            self.subtitles[row].text = item.text()

            # The old voice clip no longer matches the edited text.
            self.subtitles[row].audio_path = ""

            button = self._play_buttons.get(row)

            if button is not None:
                self._update_play_button(button, row)

            self.subtitles_changed.emit(
                self.subtitles
            )

    # =====================================================
    # CHANGE SPEAKER
    # =====================================================

    def _set_gender(self, row, gender):

        if 0 <= row < len(self.subtitles):

            self.subtitles[row].gender = gender

            self.subtitles_changed.emit(
                self.subtitles
            )

    # =====================================================
    # ADD SUBTITLE
    # =====================================================

    def add_subtitle(self):

        start = (
            self.subtitles[-1].end_ms + 100
            if self.subtitles else 0
        )

        self.subtitles.append(
            Subtitle(
                start_ms=start,
                end_ms=start + 2000,
                text="New subtitle",
                gender="Female"
            )
        )

        self.refresh()

        self.subtitles_changed.emit(
            self.subtitles
        )

    # =====================================================
    # DELETE
    # =====================================================

    def delete_selected(self):

        rows = self.checked_rows()

        if not rows:

            QMessageBox.information(
                self,
                "Delete Subtitles",
                "Check at least one subtitle to delete."
            )

            return

        answer = QMessageBox.question(
            self,
            "Delete Subtitles",
            f"Delete {len(rows)} checked subtitle(s)?",
            QMessageBox.Yes | QMessageBox.No
        )

        if answer != QMessageBox.Yes:
            return

        self.stop_audio_requested.emit()

        self._playing_row = -1

        for row in reversed(rows):

            if 0 <= row < len(self.subtitles):

                del self.subtitles[row]

        self.refresh()

        self.subtitles_changed.emit(
            self.subtitles
        )

    # =====================================================
    # SPLIT
    # =====================================================

    def split_selected(self):

        rows = sorted({
            index.row()
            for index in self.table.selectedIndexes()
        })

        if len(rows) != 1:

            QMessageBox.information(
                self,
                "Split",
                "Select one subtitle."
            )

            return

        row = rows[0]

        sub = self.subtitles[row]

        mid = (
            sub.start_ms + sub.end_ms
        ) // 2

        half = len(sub.text) // 2

        left = Subtitle(
            start_ms=sub.start_ms,
            end_ms=mid,
            text=sub.text[:half].strip(),
            gender=sub.gender,
            selected=sub.selected,
            monologue=sub.monologue
        )

        right = Subtitle(
            start_ms=mid,
            end_ms=sub.end_ms,
            text=sub.text[half:].strip(),
            gender=sub.gender,
            selected=sub.selected,
            monologue=sub.monologue
        )

        self.stop_audio_requested.emit()

        self._playing_row = -1

        self.subtitles[row:row + 1] = [
            left,
            right
        ]

        self.refresh()

        self.subtitles_changed.emit(
            self.subtitles
        )

    # =====================================================
    # MERGE
    # =====================================================

    def merge_selected(self):

        rows = sorted({
            index.row()
            for index in self.table.selectedIndexes()
        })

        if len(rows) < 2:

            QMessageBox.information(
                self,
                "Merge",
                "Select at least two subtitles."
            )

            return

        first = rows[0]
        last = rows[-1]

        merged = Subtitle(
            start_ms=self.subtitles[first].start_ms,
            end_ms=self.subtitles[last].end_ms,

            text=" ".join(
                sub.text.strip()
                for sub in self.subtitles[first:last + 1]
            ),

            gender=self.subtitles[first].gender,

            selected=any(
                sub.selected
                for sub in self.subtitles[first:last + 1]
            ),

            monologue=any(
                sub.monologue
                for sub in self.subtitles[first:last + 1]
            )
        )

        self.stop_audio_requested.emit()

        self._playing_row = -1

        self.subtitles[first:last + 1] = [
            merged
        ]

        self.refresh()

        self.subtitles_changed.emit(
            self.subtitles
        )

    # =====================================================
    # UPDATE TIMECODE
    # =====================================================

    def update_timecode(
        self,
        row,
        start_ms,
        end_ms
    ):

        if 0 <= row < len(self.subtitles):

            self.subtitles[row].start_ms = start_ms

            self.subtitles[row].end_ms = end_ms

            self.refresh()

            self.subtitles_changed.emit(
                self.subtitles
            )

    # =====================================================
    # GET SUBTITLES
    # =====================================================

    def get_subtitles(self):

        return self.subtitles

    # =====================================================
    # AUTO DETECT MESSAGE
    # =====================================================

    def _show_detect_message(self):

        QMessageBox.information(
            self,
            "Auto Detect",
            "Use the AI tab → Run Speech Recognition "
            "to detect subtitles from the loaded video."
        )
