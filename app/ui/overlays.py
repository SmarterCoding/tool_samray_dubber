from PySide6.QtCore import Qt, QPoint, QTimer
from PySide6.QtGui import QPixmap, QFont, QColor
from PySide6.QtWidgets import QLabel, QWidget

class DraggableWidget(QLabel):
    """Base class for elements that can be dragged with the mouse."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.dragging = False
        self.offset = QPoint()
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.setCursor(Qt.OpenHandCursor)
        self.x_ratio = 0.5
        self.y_ratio = 0.5

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragging = True
            self.offset = event.pos()
            self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, event):
        if self.dragging:
            new_pos = self.mapToParent(event.pos() - self.offset)
            parent = self.parentWidget()
            if parent:
                # Constrain to parent bounds
                x = max(0, min(new_pos.x(), parent.width() - self.width()))
                y = max(0, min(new_pos.y(), parent.height() - self.height()))
                self.move(x, y)
                self.x_ratio = x / parent.width()
                self.y_ratio = y / parent.height()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragging = False
            self.setCursor(Qt.OpenHandCursor)


class DraggableLogo(DraggableWidget):
    def __init__(self, image_path: str, parent=None):
        super().__init__(parent)
        self.setPixmap(QPixmap(image_path))
        self.setScaledContents(True)
        self.setFixedSize(100, 100)
        self.setStyleSheet("background: transparent;")


class DraggableText(DraggableWidget):
    def __init__(self, text: str, font_family: str, font_size: int, color: str, parent=None):
        super().__init__(parent)
        self.setText(text)
        self.setFont(QFont(font_family, font_size, QFont.Bold))
        self.setStyleSheet(f"color: {color}; background: transparent;")
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True) # Let clicks pass to video if needed
        self.adjustSize()