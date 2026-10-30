"""Popup des objets : choix des objets affichés dans la config et réglage de chaque objet, avec aperçu en direct."""
from dataclasses import replace

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QVBoxLayout, QWidget,
)

from viewer.attachments import Attachment


def _spin(lo: float, hi: float, step: float, decimals: int, suffix: str) -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setRange(lo, hi)
    spin.setSingleStep(step)
    spin.setDecimals(decimals)
    spin.setSuffix(suffix)
    return spin


def _row(*widgets: QWidget) -> QWidget:
    holder = QWidget()
    layout = QHBoxLayout(holder)
    layout.setContentsMargins(0, 0, 0, 0)
    for w in widgets:
        layout.addWidget(w)
    return holder


class AttachmentsDialog(QDialog):
    """Émet `changed(objets affichés, réglages)` à chaque modification ; à l'annulation, l'état initial est réémis.

    Les cases cochées sont propres à la config ; le réglage d'un objet est commun à tous les personnages.
    """

    changed = Signal(object, object)  # list[str], dict[str, Attachment]

    def __init__(self, objects: list[str], shown: list[str], placements: dict[str, Attachment], bones: list[str],
                 title: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Objets attachés — {title}")
        self.names = objects + [n for n in shown if n not in objects]  # objets disparus d'Objects/ en fin de liste
        self.initial = (list(shown), dict(placements))
        self.placements = dict(placements)
        self.bones = bones

        self.list = QListWidget()
        for name in self.names:
            item = QListWidgetItem(name if name in objects else f"⚠ {name}")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if name in shown else Qt.CheckState.Unchecked)
            self.list.addItem(item)
        if not self.names:
            self.list.addItem("Aucun fichier .glb dans le dossier Objects/")

        self.bone_combo = QComboBox()
        self.position_spins = [_spin(-10.0, 10.0, 0.005, 3, " m") for _ in range(3)]
        self.rotation_spins = [_spin(-360.0, 360.0, 1.0, 1, "°") for _ in range(3)]
        self.scale_spin = _spin(0.001, 1000.0, 0.05, 3, "")
        self.editor = QWidget()
        form = QFormLayout(self.editor)
        form.addRow("Bone", self.bone_combo)
        form.addRow("Position X/Y/Z", _row(*self.position_spins))
        form.addRow("Rotation X/Y/Z", _row(*self.rotation_spins))
        form.addRow("Échelle", self.scale_spin)
        note = QLabel("Réglage de l'objet, commun à tous les personnages et à toutes les configs. "
                      "Axes du personnage en T-pose, vu de face : X à sa gauche, Y vers le haut, Z devant lui ; "
                      "origine sur le bone, rotation appliquée X puis Y puis Z.")
        note.setWordWrap(True)
        form.addRow(note)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        top = QHBoxLayout()
        top.addWidget(self.list)
        top.addWidget(self.editor, 1)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Cocher les objets affichés dans cette config :"))
        layout.addLayout(top)
        layout.addWidget(buttons)
        self.resize(760, 340)

        self._loading = False
        self.list.currentRowChanged.connect(self._select)
        self.list.itemChanged.connect(lambda _: self._emit())
        self.bone_combo.currentIndexChanged.connect(self._edited)
        for spin in (*self.position_spins, *self.rotation_spins, self.scale_spin):
            spin.valueChanged.connect(self._edited)
        self.list.setCurrentRow(0 if self.names else -1)
        self._select(self.list.currentRow())

    def _current(self) -> str | None:
        row = self.list.currentRow()
        return self.names[row] if 0 <= row < len(self.names) else None

    def _select(self, _row: int) -> None:
        name = self._current()
        self.editor.setEnabled(name is not None)
        if name is None:
            return
        a = self.placements.setdefault(name, Attachment(name))
        self._loading = True
        self.bone_combo.clear()
        for bone in self.bones:
            self.bone_combo.addItem(bone, bone)
        if a.bone not in self.bones:
            self.bone_combo.addItem(f"⚠ {a.bone}", a.bone)
        self.bone_combo.setCurrentIndex(self.bone_combo.findData(a.bone))
        for spin, v in zip(self.position_spins, a.position):
            spin.setValue(v)
        for spin, v in zip(self.rotation_spins, a.rotation):
            spin.setValue(v)
        self.scale_spin.setValue(a.scale)
        self._loading = False

    def _edited(self) -> None:
        name = self._current()
        if self._loading or name is None:
            return
        self.placements[name] = replace(self.placements[name],
                                        bone=self.bone_combo.currentData(),
                                        position=tuple(s.value() for s in self.position_spins),
                                        rotation=tuple(s.value() for s in self.rotation_spins),
                                        scale=self.scale_spin.value())
        self._emit()

    def _emit(self) -> None:
        self.changed.emit(self.result_objects(), dict(self.placements))

    def result_objects(self) -> list[str]:
        return [name for i, name in enumerate(self.names)
                if self.list.item(i).checkState() == Qt.CheckState.Checked]

    def result_placements(self) -> dict[str, Attachment]:
        """Réglages modifiés dans le dialogue."""
        initial = self.initial[1]
        return {name: a for name, a in self.placements.items() if initial.get(name, Attachment(name)) != a}

    def reject(self) -> None:
        self.changed.emit(*self.initial)
        super().reject()
