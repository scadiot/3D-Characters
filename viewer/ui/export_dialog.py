"""Popup de configuration de l'export de sprite sheet."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QFormLayout, QHeaderView, QSpinBox, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget, QHBoxLayout,
)

from viewer.sprites.config import (
    FRAMES_RANGE, FRAME_HEIGHT_RANGE, SHEET_WIDTH_RANGE, AnimationExport, ExportConfig,
)
from viewer.sprites.layout import ORIENTATIONS

COL_NAME, COL_EXPORT, COL_FRAMES = 0, 1, 2
COL_FIRST_ORIENTATION = 3


def _centered(widget: QWidget) -> QWidget:
    holder = QWidget()
    layout = QHBoxLayout(holder)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(widget)
    return holder


class ExportDialog(QDialog):
    def __init__(self, config: ExportConfig, animation_labels: list[str], character: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Configuration de l'export — {character}")
        self.resize(760, 480)
        self.labels = animation_labels

        self.width_spin = QSpinBox()
        self.width_spin.setRange(*SHEET_WIDTH_RANGE)
        self.width_spin.setSuffix(" px")
        self.width_spin.setValue(config.sheet_width)
        self.height_spin = QSpinBox()
        self.height_spin.setRange(*FRAME_HEIGHT_RANGE)
        self.height_spin.setSuffix(" px")
        self.height_spin.setValue(config.frame_height)
        form = QFormLayout()
        form.addRow("Largeur de la feuille", self.width_spin)
        form.addRow("Hauteur des frames", self.height_spin)

        existing = {a.name: a for a in config.animations}
        self.table = QTableWidget(len(animation_labels), COL_FIRST_ORIENTATION + len(ORIENTATIONS))
        self.table.setHorizontalHeaderLabels(["Animation", "Exporter", "Frames", *ORIENTATIONS])
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(COL_NAME, QHeaderView.ResizeMode.Stretch)
        for col in range(COL_EXPORT, self.table.columnCount()):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)

        self.rows: list[tuple[QCheckBox, QSpinBox, list[QCheckBox]]] = []
        for row, label in enumerate(animation_labels):
            current = existing.get(label)
            name = QTableWidgetItem(label)
            name.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.table.setItem(row, COL_NAME, name)
            export_box = QCheckBox()
            export_box.setChecked(current is not None and bool(current.orientations))
            frames = QSpinBox()
            frames.setRange(*FRAMES_RANGE)
            frames.setToolTip("Nombre d'images exportées, réparties sur la durée de l'animation")
            frames.setValue(current.frames if current else 8)
            boxes = []
            for i, orientation in enumerate(ORIENTATIONS):
                box = QCheckBox()
                box.setToolTip(orientation)
                box.setChecked(current is not None and orientation in current.orientations)
                box.toggled.connect(lambda on, e=export_box: on and e.setChecked(True))
                self.table.setCellWidget(row, COL_FIRST_ORIENTATION + i, _centered(box))
                boxes.append(box)
            export_box.toggled.connect(lambda on, b=boxes: on and not any(x.isChecked() for x in b)
                                       and b[0].setChecked(True))
            self.table.setCellWidget(row, COL_EXPORT, _centered(export_box))
            self.table.setCellWidget(row, COL_FRAMES, frames)
            self.rows.append((export_box, frames, boxes))

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.table, 1)
        layout.addWidget(buttons)

    def result_config(self) -> ExportConfig:
        animations = []
        for label, (export_box, frames, boxes) in zip(self.labels, self.rows):
            orientations = [o for o, box in zip(ORIENTATIONS, boxes) if box.isChecked()]
            if export_box.isChecked() and orientations:
                animations.append(AnimationExport(label, frames.value(), orientations))
        return ExportConfig(self.width_spin.value(), self.height_spin.value(), animations)
