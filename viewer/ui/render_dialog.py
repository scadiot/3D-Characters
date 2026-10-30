"""Popup de configuration du rendu (cel shading, contour, lumière), avec aperçu en direct."""
from PySide6.QtCore import Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QGroupBox,
    QPushButton, QSpinBox, QVBoxLayout,
)

from viewer.render_settings import BANDS_RANGE, ELEVATION_RANGE, OUTLINE_WIDTH_RANGE, SHADINGS, RenderSettings

SHADING_LABELS = {"standard": "Standard", "cel": "Cartoon (cel shading)"}


def _spin(lo: float, hi: float, step: float, suffix: str = "") -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setRange(lo, hi)
    spin.setSingleStep(step)
    spin.setDecimals(2)
    spin.setSuffix(suffix)
    return spin


def _int_spin(lo: int, hi: int, suffix: str = "") -> QSpinBox:
    spin = QSpinBox()
    spin.setRange(lo, hi)
    spin.setSuffix(suffix)
    return spin


class RenderDialog(QDialog):
    """Émet `changed` à chaque modification ; à l'annulation, les réglages initiaux sont réémis."""

    changed = Signal(object)  # RenderSettings

    def __init__(self, settings: RenderSettings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Paramètres de rendu")
        self.initial = settings
        self._color = settings.outline_color

        self.shading_combo = QComboBox()
        for key in SHADINGS:
            self.shading_combo.addItem(SHADING_LABELS[key], key)
        self.bands_spin = _int_spin(*BANDS_RANGE)
        self.bands_spin.setToolTip("Nombre de tons entre l'ombre et la pleine lumière")
        self.softness_spin = _spin(0.0, 0.5, 0.01)
        self.softness_spin.setToolTip("Largeur de la transition entre deux tons (0 : limite nette)")
        self.rim_spin = _spin(0.0, 1.0, 0.05)
        self.rim_spin.setToolTip("Intensité du liseré clair sur les bords de la silhouette")
        self.rim_width_spin = _spin(0.0, 1.0, 0.05)
        cel = QGroupBox("Cel shading")
        cel_form = QFormLayout(cel)
        cel_form.addRow("Tons", self.bands_spin)
        cel_form.addRow("Adoucissement", self.softness_spin)
        cel_form.addRow("Liseré", self.rim_spin)
        cel_form.addRow("Largeur du liseré", self.rim_width_spin)
        self.cel_group = cel

        self.outline_group = QGroupBox("Contour")
        self.outline_group.setCheckable(True)
        self.outline_width_spin = _spin(*OUTLINE_WIDTH_RANGE, 0.5, " px")
        self.outline_width_spin.setToolTip("Épaisseur à l'écran, et dans les sprites exportés")
        self.color_button = QPushButton()
        self.color_button.clicked.connect(self._pick_color)
        outline_form = QFormLayout(self.outline_group)
        outline_form.addRow("Épaisseur", self.outline_width_spin)
        outline_form.addRow("Couleur", self.color_button)

        self.shadow_spin = _spin(0.0, 1.0, 0.05)
        self.shadow_spin.setToolTip("Luminosité des zones non éclairées")
        self.azimuth_spin = _int_spin(-180, 180, "°")
        self.azimuth_spin.setWrapping(True)
        self.azimuth_spin.setToolTip("0° : lumière venant de face, 90° : de la gauche du personnage")
        self.elevation_spin = _int_spin(*ELEVATION_RANGE, "°")
        light = QGroupBox("Lumière")
        light_form = QFormLayout(light)
        light_form.addRow("Ombres", self.shadow_spin)
        light_form.addRow("Direction", self.azimuth_spin)
        light_form.addRow("Hauteur", self.elevation_spin)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
                                   | QDialogButtonBox.StandardButton.RestoreDefaults)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.StandardButton.RestoreDefaults).clicked.connect(
            lambda: self._load(RenderSettings()))

        form = QFormLayout()
        form.addRow("Rendu", self.shading_combo)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(cel)
        layout.addWidget(self.outline_group)
        layout.addWidget(light)
        layout.addWidget(buttons)

        self._loading = False
        self._load(settings)
        self.shading_combo.currentIndexChanged.connect(self._emit)
        self.outline_group.toggled.connect(self._emit)
        for spin in (self.bands_spin, self.softness_spin, self.rim_spin, self.rim_width_spin, self.outline_width_spin,
                     self.shadow_spin, self.azimuth_spin, self.elevation_spin):
            spin.valueChanged.connect(self._emit)

    def _load(self, s: RenderSettings) -> None:
        self._loading = True
        self.shading_combo.setCurrentIndex(SHADINGS.index(s.shading))
        self.bands_spin.setValue(s.bands)
        self.softness_spin.setValue(s.softness)
        self.rim_spin.setValue(s.rim)
        self.rim_width_spin.setValue(s.rim_width)
        self.outline_group.setChecked(s.outline)
        self.outline_width_spin.setValue(s.outline_width)
        self._color = s.outline_color
        self.shadow_spin.setValue(s.shadow)
        self.azimuth_spin.setValue(s.light_azimuth)
        self.elevation_spin.setValue(s.light_elevation)
        self._loading = False
        self._emit()

    def _pick_color(self) -> None:
        color = QColorDialog.getColor(QColor.fromRgbF(*self._color), self, "Couleur du contour")
        if color.isValid():
            self._color = (color.redF(), color.greenF(), color.blueF())
            self._emit()

    def _emit(self) -> None:
        if self._loading:
            return
        self.cel_group.setEnabled(self.shading_combo.currentData() == "cel")
        r, g, b = (round(c * 255) for c in self._color)
        self.color_button.setStyleSheet(f"background-color: rgb({r}, {g}, {b}); min-height: 18px;")
        self.changed.emit(self.result_settings())

    def result_settings(self) -> RenderSettings:
        return RenderSettings(
            shading=self.shading_combo.currentData(),
            bands=self.bands_spin.value(),
            softness=self.softness_spin.value(),
            shadow=self.shadow_spin.value(),
            rim=self.rim_spin.value(),
            rim_width=self.rim_width_spin.value(),
            outline=self.outline_group.isChecked(),
            outline_width=self.outline_width_spin.value(),
            outline_color=self._color,
            light_azimuth=self.azimuth_spin.value(),
            light_elevation=self.elevation_spin.value(),
        )

    def reject(self) -> None:
        self.changed.emit(self.initial)
        super().reject()
