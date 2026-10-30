"""Popup de configuration de l'export de sprite sheet."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QHeaderView, QSpinBox, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget, QHBoxLayout,
)

from viewer.sprites.config import (
    FRAMES_RANGE, FRAME_HEIGHT_RANGE, SHEET_WIDTH_RANGE, AnimationExport, ExportConfig,
)
from viewer.sprites.layout import ORIENTATIONS

COL_NAME, COL_EXPORT, COL_FRAMES, COL_START, COL_END = 0, 1, 2, 3, 4
COL_FIRST_ORIENTATION = 5


def _centered(widget: QWidget) -> QWidget:
    holder = QWidget()
    layout = QHBoxLayout(holder)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(widget)
    return holder


class ExportDialog(QDialog):
    def __init__(self, config: ExportConfig, animation_labels: list[str], character: str,
                 durations: dict[str, float], parent=None):
        """`durations` : durée de chaque animation (absente si le clip n'a pas pu être lu)."""
        super().__init__(parent)
        self.setWindowTitle(f"Configuration de l'export — {character}")
        self.resize(900, 480)
        self.labels = animation_labels
        self.durations = durations
        self.config = config

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
        self.table.setHorizontalHeaderLabels(["Animation", "Exporter", "Frames", "Début", "Fin", *ORIENTATIONS])
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(COL_NAME, QHeaderView.ResizeMode.Stretch)
        for col in range(COL_EXPORT, self.table.columnCount()):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)

        self.rows: list[tuple[QCheckBox, QSpinBox, QDoubleSpinBox, QDoubleSpinBox, list[QCheckBox]]] = []
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
            start, end = self._time_spins(current, durations.get(label))
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
            self.table.setCellWidget(row, COL_START, start)
            self.table.setCellWidget(row, COL_END, end)
            self.rows.append((export_box, frames, start, end, boxes))

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.table, 1)
        layout.addWidget(buttons)

    @staticmethod
    def _time_spins(current: AnimationExport | None, duration: float | None) -> tuple[QDoubleSpinBox, QDoubleSpinBox]:
        """Début et fin de la plage exportée, en secondes ; la fin ne peut pas précéder le début."""
        start, end = QDoubleSpinBox(), QDoubleSpinBox()
        for spin in (start, end):
            spin.setDecimals(2)
            spin.setSingleStep(0.05)
            spin.setSuffix(" s")
            spin.setRange(0.0, duration or 0.0)
            spin.setEnabled(duration is not None)
        if duration is None:
            start.setToolTip("Durée inconnue : animation illisible")
            end.setToolTip("Durée inconnue : animation illisible")
            return start, end
        start.setToolTip(f"Début de la plage exportée (durée du clip : {duration:.2f} s)")
        end.setToolTip(f"Fin de la plage exportée (durée du clip : {duration:.2f} s)")
        begin, finish = current.time_range(duration) if current else (0.0, duration)
        start.setValue(begin)
        end.setValue(finish)
        end.setMinimum(start.value())
        start.valueChanged.connect(end.setMinimum)
        return start, end

    def result_config(self) -> ExportConfig:
        animations = []
        for label, (export_box, frames, start, end, boxes) in zip(self.labels, self.rows):
            orientations = [o for o, box in zip(ORIENTATIONS, boxes) if box.isChecked()]
            if export_box.isChecked() and orientations:
                if start.isEnabled():
                    # fin en bout de clip : None, pour suivre le clip si sa durée change
                    stop = None if end.value() >= end.maximum() else end.value()
                    animations.append(AnimationExport(label, frames.value(), orientations, start.value(), stop))
                else:
                    previous = next((a for a in self.config.animations if a.name == label), None)
                    animations.append(AnimationExport(label, frames.value(), orientations,
                                                      *((previous.start, previous.end) if previous else ())))
        return ExportConfig(self.width_spin.value(), self.height_spin.value(), animations)
