from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QSizePolicy

from app.theme import TEXT_DIM, TEXT_MUTED, TEXT, PRIMARY, SUCCESS, BORDER

STAGES = ["Import", "Transcribe", "Translate", "Voice", "Export"]


class _Dot(QLabel):
    def __init__(self, num: int, name: str, parent=None):
        super().__init__(parent)
        self._num = num
        self._name = name
        self._state = "pending"   # pending | active | done
        self._refresh()

    def set_state(self, state: str):
        if state == self._state:
            return
        self._state = state
        self._refresh()

    def _refresh(self):
        color = {
            "pending":  TEXT_DIM,
            "active":   PRIMARY,
            "done":     SUCCESS,
        }[self._state]
        bg = "transparent" if self._state == "pending" else color

        self.setText(f"  {self._num}  {self._name}  ")
        font = QFont(self.font())
        font.setPointSize(10)
        font.setBold(self._state != "pending")
        self.setFont(font)
        self.setStyleSheet(
            f"QLabel {{ color: {color if self._state == 'pending' else 'white'};"
            f" background: {bg};"
            f" border: 1px solid {color if self._state != 'pending' else BORDER};"
            f" border-radius: 10px; padding: 2px 8px; }}")


class _Dash(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setText("—")
        self.setStyleSheet(f"color: {BORDER}; font-size: 11px;")


class WorkflowBar(QWidget):
    stage_clicked = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.dots: list[_Dot] = []
        self.current = -1

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addStretch()

        for i, name in enumerate(STAGES):
            dot = _Dot(i + 1, name)
            self.dots.append(dot)
            layout.addWidget(dot)
            if i < len(STAGES) - 1:
                layout.addWidget(_Dash())

        layout.addStretch()

    def set_stage(self, index: int):
        """Mark stages before ``index`` as done and ``index`` as active."""
        self.current = index
        for i, dot in enumerate(self.dots):
            if i < index:
                dot.set_state("done")
            elif i == index:
                dot.set_state("active")
            else:
                dot.set_state("pending")

    def complete_all(self):
        for dot in self.dots:
            dot.set_state("done")
        self.current = len(self.dots)

    def reset(self):
        for dot in self.dots:
            dot.set_state("pending")
        self.current = -1