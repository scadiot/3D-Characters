"""Popups de visualisation des sprite sheets exportées : choix de l'export, puis lecture d'une animation."""
from pathlib import Path

from PySide6.QtCore import QElapsedTimer, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QMessageBox, QPushButton, QSplitter, QVBoxLayout, QWidget,
)

from viewer.sprites.sheet import Sheet, SheetAnimation, list_exports, load_sheet

SPEEDS = [0.25, 0.5, 1.0, 1.5, 2.0]
THUMBNAIL = QSize(96, 96)
CELL_GAP = 24  # pixels écran entre deux orientations
LABEL_HEIGHT = 20
PADDING = 12


def _checkerboard() -> QPixmap:
    tile = QPixmap(16, 16)
    tile.fill(QColor(70, 70, 70))
    with QPainter(tile) as p:
        p.fillRect(0, 0, 8, 8, QColor(90, 90, 90))
        p.fillRect(8, 8, 8, 8, QColor(90, 90, 90))
    return tile


class ExportPickerDialog(QDialog):
    """1re popup : liste des exports (JSON) du dossier, avec vignette."""

    def __init__(self, directory: Path, current: str | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Visualiser un export")
        self.resize(460, 520)
        self.directory = directory
        self.sheet: Sheet | None = None

        self.list = QListWidget()
        self.list.setIconSize(THUMBNAIL)
        self.list.itemDoubleClicked.connect(lambda _: self.accept())
        for path in list_exports(directory):
            self._add(path)
        if self.list.count() == 0:
            item = QListWidgetItem(f"Aucun export dans {directory}")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.list.addItem(item)
        self._select(current)

        browse = QPushButton("Parcourir…")
        browse.clicked.connect(self._browse)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.addButton(browse, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.list, 1)
        layout.addWidget(buttons)

    def _add(self, path: Path) -> None:
        try:
            sheet = load_sheet(path)
        except ValueError as e:
            item = QListWidgetItem(f"⚠ {path.stem}\n{e}")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.list.addItem(item)
            return
        pixmap = QPixmap(str(sheet.image_path))
        item = QListWidgetItem(f"{path.stem}\n{len(sheet.animations)} animation(s) · "
                               + (f"{pixmap.width()}×{pixmap.height()} px" if not pixmap.isNull()
                                  else f"⚠ {sheet.image_path.name} introuvable"))
        if not pixmap.isNull():
            item.setIcon(QIcon(pixmap.scaled(THUMBNAIL, Qt.AspectRatioMode.KeepAspectRatio,
                                             Qt.TransformationMode.SmoothTransformation)))
        item.setData(Qt.ItemDataRole.UserRole, str(path))
        self.list.addItem(item)

    def _select(self, name: str | None) -> None:
        for row in range(self.list.count()):
            item = self.list.item(row)
            path = item.data(Qt.ItemDataRole.UserRole)
            if path and (not name or Path(path).stem == name):
                self.list.setCurrentRow(row)
                return

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Ouvrir un export", str(self.directory), "Sprite sheet (*.json)")
        if path:
            self._open(Path(path))

    def accept(self) -> None:
        item = self.list.currentItem()
        if item is not None and item.data(Qt.ItemDataRole.UserRole):
            self._open(Path(item.data(Qt.ItemDataRole.UserRole)))

    def _open(self, path: Path) -> None:
        try:
            sheet = load_sheet(path)
        except ValueError as e:
            QMessageBox.warning(self, "Visualiser un export", str(e))
            return
        if not sheet.animations:
            QMessageBox.information(self, "Visualiser un export", f"{path.name} ne contient aucune animation.")
            return
        self.sheet = sheet
        super().accept()


class SheetPreview(QWidget):
    """Joue toutes les orientations d'une animation côte à côte, alignées sur leur origine (le sol)."""

    def __init__(self, pixmap: QPixmap, frame_height: int, parent=None):
        super().__init__(parent)
        self.pixmap = pixmap
        self.frame_height = frame_height
        self.animation: SheetAnimation | None = None
        self.time = 0.0
        self.show_frames = False
        self._background = QBrush(_checkerboard())
        self.setMinimumSize(200, 200)

    def set_animation(self, animation: SheetAnimation | None) -> None:
        self.animation = animation
        self.time = 0.0
        self.update()

    def _extents(self) -> list[tuple[int, int]]:
        """(débord à gauche, débord à droite) de l'origine, sur toutes les frames de chaque orientation."""
        return [(max(f.origin_x for f in s.frames), max(f.width - f.origin_x for f in s.frames))
                for s in self.animation.sequences]

    def paintEvent(self, event) -> None:
        with QPainter(self) as p:
            p.fillRect(self.rect(), self._background)
            if self.animation is None or self.pixmap.isNull():
                return
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            extents = self._extents()
            gaps = CELL_GAP * (len(extents) - 1) + 2 * PADDING
            content_width = sum(left + right for left, right in extents)
            scale = min((self.width() - gaps) / max(content_width, 1),
                        (self.height() - LABEL_HEIGHT - 2 * PADDING) / max(self.frame_height, 1))
            scale = max(scale, 0.05)
            x = (self.width() - content_width * scale - gaps) / 2 + PADDING
            top = (self.height() - self.frame_height * scale - LABEL_HEIGHT) / 2
            for sequence, (left, right) in zip(self.animation.sequences, extents):
                frame = sequence.frame_at(self.time)
                origin_x = x + left * scale
                target = QRectF(origin_x - frame.origin_x * scale, top, frame.width * scale, frame.height * scale)
                p.drawPixmap(target, self.pixmap, QRectF(frame.x, frame.y, frame.width, frame.height))
                if self.show_frames:
                    p.setPen(QPen(QColor(255, 200, 0, 160), 1, Qt.PenStyle.DashLine))
                    p.drawRect(target)
                    ground = top + frame.origin_y * scale
                    p.setPen(QPen(QColor(0, 200, 255), 1))
                    p.drawLine(int(origin_x - 6), int(ground), int(origin_x + 6), int(ground))
                    p.drawLine(int(origin_x), int(ground - 6), int(origin_x), int(ground + 6))
                p.setPen(QColor(230, 230, 230))
                cell = QRectF(x, top + self.frame_height * scale, (left + right) * scale, LABEL_HEIGHT)
                p.drawText(cell, Qt.AlignmentFlag.AlignCenter, sequence.orientation)
                x += (left + right) * scale + CELL_GAP


class SheetViewerDialog(QDialog):
    """2e popup : choix de l'animation de l'export et lecture."""

    def __init__(self, sheet: Sheet, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Export — {sheet.json_path.stem}")
        self.resize(960, 560)
        self.sheet = sheet
        self.playing = True

        self.list = QListWidget()
        self.list.setMinimumWidth(180)
        for animation in sheet.animations:
            orientations = ", ".join(s.orientation for s in animation.sequences)
            self.list.addItem(f"{animation.name}\n{animation.frame_count} frame(s) · {orientations}")
        self.preview = SheetPreview(QPixmap(str(sheet.image_path)), sheet.frame_height)
        self.play_button = QPushButton("⏸")
        self.play_button.setFixedWidth(36)
        self.previous_button = QPushButton("|◀")
        self.previous_button.setFixedWidth(36)
        self.next_button = QPushButton("▶|")
        self.next_button.setFixedWidth(36)
        self.speed_combo = QComboBox()
        self.speed_combo.addItems([f"{s}x" for s in SPEEDS])
        self.speed_combo.setCurrentIndex(SPEEDS.index(1.0))
        self.frames_check = QCheckBox("Cadres et origines")
        self.info_label = QLabel()

        controls = QHBoxLayout()
        controls.addWidget(self.previous_button)
        controls.addWidget(self.play_button)
        controls.addWidget(self.next_button)
        controls.addWidget(QLabel("Vitesse"))
        controls.addWidget(self.speed_combo)
        controls.addWidget(self.frames_check)
        controls.addStretch()
        controls.addWidget(self.info_label)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(self.preview, 1)
        right_layout.addLayout(controls)
        splitter = QSplitter()
        splitter.addWidget(self.list)
        splitter.addWidget(right)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([220, 740])
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(splitter, 1)
        layout.addWidget(buttons)

        self.list.currentRowChanged.connect(self._on_animation)
        self.play_button.clicked.connect(self._toggle_play)
        self.previous_button.clicked.connect(lambda: self._step(-1))
        self.next_button.clicked.connect(lambda: self._step(1))
        self.frames_check.toggled.connect(self._toggle_frames)

        self._clock = QElapsedTimer()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)
        self._clock.start()
        if self.preview.pixmap.isNull():
            self.info_label.setText(f"⚠ {sheet.image_path.name} introuvable")
        self.list.setCurrentRow(0)

    def _sequence(self):
        animation = self.preview.animation
        return animation.sequences[0] if animation and animation.sequences else None

    def _on_animation(self, row: int) -> None:
        self.preview.set_animation(self.sheet.animations[row] if 0 <= row < len(self.sheet.animations) else None)
        self._update_info()

    def _toggle_play(self) -> None:
        self.playing = not self.playing
        self.play_button.setText("⏸" if self.playing else "▶")
        self._clock.restart()

    def _toggle_frames(self, on: bool) -> None:
        self.preview.show_frames = on
        self.preview.update()

    def _step(self, delta: int) -> None:
        """Met en pause et avance d'une frame (selon la cadence de la première orientation)."""
        sequence = self._sequence()
        if sequence is None:
            return
        if self.playing:
            self._toggle_play()
        index = sequence.index_at(self.preview.time) + delta
        # milieu de la frame visée, pour ne pas tomber sur une frontière à cause des arrondis
        self.preview.time = (index % len(sequence.frames) + 0.5) / sequence.fps if sequence.fps > 0 else 0.0
        self.preview.update()
        self._update_info()

    def _tick(self) -> None:
        elapsed = self._clock.restart() / 1000
        if self.playing and self.preview.animation is not None:
            self.preview.time += elapsed * SPEEDS[self.speed_combo.currentIndex()]
            self.preview.update()
            self._update_info()

    def _update_info(self) -> None:
        sequence = self._sequence()
        if sequence is None or self.preview.pixmap.isNull():
            return
        index = sequence.index_at(self.preview.time)
        self.info_label.setText(f"frame {index + 1} / {len(sequence.frames)} · {sequence.fps:g} fps")

    def done(self, result: int) -> None:
        self._timer.stop()
        super().done(result)
