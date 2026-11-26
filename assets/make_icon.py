"""Render the SAMRAY DUBBER PRO macOS app icon.

The icon is drawn with QPainter so it stays sharp at every iconset size and
does not depend on an external image-generation service.
"""

import math
import os
import subprocess
import sys

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QGuiApplication,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "assets")
ICONSET = os.path.join(ASSETS, "samray.iconset")


def rounded_path(rect: QRectF, radius: float) -> QPainterPath:
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    return path


def draw_icon(size: int = 1024) -> QImage:
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)

    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

    s = size / 1024.0
    painter.scale(s, s)

    # ------------------------------------------------------------------
    # macOS-style rounded square with a soft shadow
    # ------------------------------------------------------------------
    body = QRectF(96, 88, 832, 832)
    radius = 190.0

    for i in range(18, 0, -1):
        alpha = int(1.6 * i)
        shadow_rect = body.translated(0, 10 + i * 1.6)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, alpha))
        painter.drawPath(rounded_path(shadow_rect, radius + i * 0.6))

    body_path = rounded_path(body, radius)

    # Deep studio background
    background = QLinearGradient(body.topLeft(), body.bottomRight())
    background.setColorAt(0.0, QColor("#22344D"))
    background.setColorAt(0.42, QColor("#111B2A"))
    background.setColorAt(1.0, QColor("#070A10"))
    painter.fillPath(body_path, background)

    painter.save()
    painter.setClipPath(body_path)

    # Blue glow behind the microphone
    glow = QRadialGradient(QPointF(500, 470), 500)
    glow.setColorAt(0.0, QColor(22, 131, 248, 115))
    glow.setColorAt(0.55, QColor(22, 131, 248, 32))
    glow.setColorAt(1.0, QColor(22, 131, 248, 0))
    painter.fillRect(body, glow)

    # Faint studio grid
    painter.setPen(QPen(QColor(255, 255, 255, 10), 2))
    step = 64
    for x in range(int(body.left()), int(body.right()) + 1, step):
        painter.drawLine(QPointF(x, body.top()), QPointF(x, body.bottom()))
    for y in range(int(body.top()), int(body.bottom()) + 1, step):
        painter.drawLine(QPointF(body.left(), y), QPointF(body.right(), y))

    # Subtle top highlight
    highlight = QLinearGradient(QPointF(0, body.top()), QPointF(0, body.top() + 240))
    highlight.setColorAt(0.0, QColor(255, 255, 255, 36))
    highlight.setColorAt(1.0, QColor(255, 255, 255, 0))
    painter.fillRect(QRectF(body.left(), body.top(), body.width(), 240), highlight)

    # ------------------------------------------------------------------
    # Microphone
    # ------------------------------------------------------------------
    mic_x = 418.0
    mic_y = 208.0
    mic_w = 196.0
    mic_h = 338.0

    mic_shadow = QRectF(mic_x + 8, mic_y + 16, mic_w, mic_h)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(0, 0, 0, 95))
    painter.drawRoundedRect(mic_shadow, mic_w / 2, mic_w / 2)

    capsule = QRectF(mic_x, mic_y, mic_w, mic_h)
    capsule_gradient = QLinearGradient(capsule.topLeft(), capsule.bottomRight())
    capsule_gradient.setColorAt(0.0, QColor("#FFFFFF"))
    capsule_gradient.setColorAt(0.22, QColor("#E2E8F0"))
    capsule_gradient.setColorAt(0.55, QColor("#94A3B8"))
    capsule_gradient.setColorAt(0.8, QColor("#CBD5E1"))
    capsule_gradient.setColorAt(1.0, QColor("#64748B"))
    painter.setBrush(capsule_gradient)
    painter.drawRoundedRect(capsule, mic_w / 2, mic_w / 2)

    # Mic grille
    painter.setPen(QPen(QColor(15, 23, 42, 115), 5))
    for y in range(int(mic_y + 92), int(mic_y + mic_h - 42), 30):
        painter.drawLine(
            QPointF(mic_x + 42, y),
            QPointF(mic_x + mic_w - 42, y),
        )

    # Gold accent ring
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(QColor("#F5C451"), 11))
    painter.drawRoundedRect(capsule.adjusted(14, 14, -14, -14), 84, 84)

    # Mic yoke / stand
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(QColor("#CBD5E1"), 22, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    yoke = QPainterPath()
    yoke.moveTo(330, 438)
    yoke.cubicTo(330, 640, 702, 640, 702, 438)
    painter.drawPath(yoke)

    # Stand stem and base
    painter.setPen(QPen(QColor("#94A3B8"), 24, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    painter.drawLine(QPointF(516, 626), QPointF(516, 716))
    base_gradient = QLinearGradient(QPointF(400, 0), QPointF(632, 0))
    base_gradient.setColorAt(0.0, QColor("#64748B"))
    base_gradient.setColorAt(0.5, QColor("#E2E8F0"))
    base_gradient.setColorAt(1.0, QColor("#64748B"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(base_gradient)
    painter.drawRoundedRect(QRectF(398, 704, 236, 42), 21, 21)

    # ------------------------------------------------------------------
    # Play badge
    # ------------------------------------------------------------------
    badge_center = QPointF(726, 730)
    badge_radius = 154.0

    # Soft glow
    badge_glow = QRadialGradient(badge_center, badge_radius * 1.65)
    badge_glow.setColorAt(0.0, QColor(56, 189, 248, 120))
    badge_glow.setColorAt(0.6, QColor(22, 131, 248, 40))
    badge_glow.setColorAt(1.0, QColor(22, 131, 248, 0))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(badge_glow)
    painter.drawEllipse(badge_center, badge_radius * 1.65, badge_radius * 1.65)

    badge = QRectF(
        badge_center.x() - badge_radius,
        badge_center.y() - badge_radius,
        badge_radius * 2,
        badge_radius * 2,
    )
    badge_gradient = QLinearGradient(badge.topLeft(), badge.bottomRight())
    badge_gradient.setColorAt(0.0, QColor("#67E8F9"))
    badge_gradient.setColorAt(0.45, QColor("#22A7F0"))
    badge_gradient.setColorAt(1.0, QColor("#1261D8"))
    painter.setBrush(badge_gradient)
    painter.setPen(QPen(QColor(255, 255, 255, 90), 7))
    painter.drawEllipse(badge)

    # Play triangle
    triangle = QPainterPath()
    triangle.moveTo(badge_center.x() - 38, badge_center.y() - 72)
    triangle.lineTo(badge_center.x() + 74, badge_center.y())
    triangle.lineTo(badge_center.x() - 38, badge_center.y() + 72)
    triangle.closeSubpath()
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(255, 255, 255))
    painter.drawPath(triangle)

    # ------------------------------------------------------------------
    # Waveform bars
    # ------------------------------------------------------------------
    bar_heights = (96, 168, 232, 132)
    bar_width = 26
    gap = 22
    start_x = 250
    base_y = 764
    for index, height in enumerate(bar_heights):
        x = start_x + index * (bar_width + gap)
        gradient = QLinearGradient(QPointF(0, base_y - height), QPointF(0, base_y))
        gradient.setColorAt(0.0, QColor("#6EE7B7"))
        gradient.setColorAt(1.0, QColor("#10B981"))
        painter.setBrush(gradient)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(
            QRectF(x, base_y - height, bar_width, height),
            bar_width / 2,
            bar_width / 2,
        )

    # Subtitle lines (top-left)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(255, 255, 255, 46))
    painter.drawRoundedRect(QRectF(196, 210, 150, 18), 9, 9)
    painter.setBrush(QColor(255, 255, 255, 30))
    painter.drawRoundedRect(QRectF(196, 248, 104, 16), 8, 8)

    painter.restore()

    # Crisp outer border
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(QColor(255, 255, 255, 44), 2))
    painter.drawPath(body_path)

    painter.end()
    return image


def main() -> int:
    os.makedirs(ASSETS, exist_ok=True)
    app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])

    base = draw_icon(1024)
    base_path = os.path.join(ASSETS, "icon.png")
    base.save(base_path, "PNG")
    print(f"Wrote {base_path}")

    os.makedirs(ICONSET, exist_ok=True)
    # iconutil expects this exact set of names/sizes.
    sizes = {
        "icon_16x16.png": 16,
        "icon_16x16@2x.png": 32,
        "icon_32x32.png": 32,
        "icon_32x32@2x.png": 64,
        "icon_128x128.png": 128,
        "icon_128x128@2x.png": 256,
        "icon_256x256.png": 256,
        "icon_256x256@2x.png": 512,
        "icon_512x512.png": 512,
        "icon_512x512@2x.png": 1024,
    }
    for filename, px in sizes.items():
        target = os.path.join(ICONSET, filename)
        if px == 1024:
            base.save(target, "PNG")
        else:
            scaled = base.scaled(
                px,
                px,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            scaled.save(target, "PNG")

    icns_path = os.path.join(ROOT, "samray.icns")
    result = subprocess.run(
        ["iconutil", "-c", "icns", ICONSET, "-o", icns_path],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(result.stderr or result.stdout, file=sys.stderr)
        return result.returncode

    print(f"Wrote {icns_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
