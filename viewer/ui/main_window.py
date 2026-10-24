"""Fenêtre principale : sélection perso / skin / animation, lecture, vérification."""
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QLabel, QMainWindow, QMessageBox,
    QPushButton, QSlider, QVBoxLayout, QWidget,
)

from viewer.gltf_loader import LoadedFile, LoadError, load_glb
from viewer.library import Library, scan
from viewer.mixamo import ValidationReport, validate
from viewer.player import Player
from viewer.renderer import MAX_BONES
from viewer.ui.gl_view import GLView

SPEEDS = [0.25, 0.5, 1.0, 1.5, 2.0]
TIMELINE_STEPS = 1000


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("3D Characters Viewer")
        self.settings = QSettings("3D-Characters", "CharacterViewer")
        self.player = Player()
        self.library = Library()
        self.root: Path | None = None
        self._anim_cache: dict[Path, LoadedFile] = {}
        self._report: ValidationReport | None = None
        self._was_playing = True

        self.view = GLView(self.player)
        self.character_combo = QComboBox()
        self.skin_combo = QComboBox()
        self.anim_combo = QComboBox()
        self.play_button = QPushButton("⏸")
        self.speed_combo = QComboBox()
        self.speed_combo.addItems([f"{s}x" for s in SPEEDS])
        self.speed_combo.setCurrentIndex(SPEEDS.index(1.0))
        self.bones_check = QCheckBox("Afficher bones")
        self.validation_label = QLabel()
        self.validation_label.setWordWrap(True)
        self.details_button = QPushButton("détails…")
        self.timeline = QSlider(Qt.Orientation.Horizontal)
        self.timeline.setRange(0, TIMELINE_STEPS)
        self.time_label = QLabel("0.00 / 0.00 s")

        self._build_layout()
        self._connect()
        self._update_validation()

        root = self.settings.value("root")
        if root and Path(root).is_dir():
            self.open_root(Path(root), restore=True)

    # --- construction ---
    def _build_layout(self) -> None:
        open_action = self.menuBar().addAction("Dossier racine…")
        open_action.triggered.connect(self._choose_root)

        side = QVBoxLayout()
        for title, combo in (("Personnage", self.character_combo), ("Skin", self.skin_combo),
                             ("Animation", self.anim_combo)):
            side.addWidget(QLabel(title))
            side.addWidget(combo)
        playback = QHBoxLayout()
        playback.addWidget(self.play_button)
        playback.addWidget(QLabel("Vitesse"))
        playback.addWidget(self.speed_combo)
        side.addLayout(playback)
        side.addWidget(self.bones_check)
        side.addSpacing(12)
        side.addWidget(QLabel("Vérification"))
        side.addWidget(self.validation_label)
        side.addWidget(self.details_button)
        side.addStretch()
        side_widget = QWidget()
        side_widget.setLayout(side)
        side_widget.setFixedWidth(240)

        timeline = QHBoxLayout()
        timeline.addWidget(self.timeline)
        timeline.addWidget(self.time_label)
        right = QVBoxLayout()
        right.addWidget(self.view, 1)
        right.addLayout(timeline)

        main = QHBoxLayout()
        main.addWidget(side_widget)
        main.addLayout(right, 1)
        central = QWidget()
        central.setLayout(main)
        self.setCentralWidget(central)

    def _connect(self) -> None:
        self.character_combo.currentIndexChanged.connect(self._on_character)
        self.skin_combo.currentIndexChanged.connect(self._on_skin)
        self.anim_combo.currentIndexChanged.connect(self._on_animation)
        self.play_button.clicked.connect(self._toggle_play)
        self.speed_combo.currentIndexChanged.connect(lambda i: setattr(self.player, "speed", SPEEDS[i]))
        self.bones_check.toggled.connect(lambda on: setattr(self.view, "show_bones", on))
        self.details_button.clicked.connect(self._show_details)
        self.timeline.sliderPressed.connect(self._timeline_pressed)
        self.timeline.sliderMoved.connect(self._timeline_moved)
        self.timeline.sliderReleased.connect(self._timeline_released)
        self.view.time_changed.connect(self._on_time)

    # --- bibliothèque ---
    def _choose_root(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Dossier racine", str(self.root or ""))
        if d:
            self.open_root(Path(d))

    def open_root(self, root: Path, restore: bool = False) -> None:
        self.root = root
        self.settings.setValue("root", str(root))
        self.library = scan(root)
        self._anim_cache.clear()
        for m in self.library.messages:
            self.statusBar().showMessage(m, 8000)

        self.character_combo.blockSignals(True)
        self.character_combo.clear()
        self.character_combo.addItems([c.name for c in self.library.characters])
        self.character_combo.blockSignals(False)

        if restore:
            self._select_text(self.character_combo, self.settings.value("character"))
        self._on_character(self.character_combo.currentIndex(),
                           animation=self.settings.value("animation") if restore else None)
        if restore:
            self._select_text(self.skin_combo, self.settings.value("skin"))
            self._on_skin(self.skin_combo.currentIndex())

    @staticmethod
    def _select_text(combo: QComboBox, text) -> None:
        if text:
            i = combo.findText(str(text))
            if i >= 0:
                combo.blockSignals(True)
                combo.setCurrentIndex(i)
                combo.blockSignals(False)

    # --- sélection ---
    def _on_character(self, index: int, animation: str | None = None) -> None:
        previous_animation = animation or self.anim_combo.currentText()
        model = None
        self.skin_combo.blockSignals(True)
        self.skin_combo.clear()
        if 0 <= index < len(self.library.characters):
            entry = self.library.characters[index]
            try:
                model = load_glb(entry.model_path)
            except LoadError as e:
                self.statusBar().showMessage(str(e), 8000)
                self.character_combo.setItemText(index, f"⚠ {entry.name}")
            else:
                self.skin_combo.addItem("défaut")
                self.skin_combo.addItems([p.stem for p in entry.skins])
                self.settings.setValue("character", entry.name)
                for info in model.infos:
                    self.statusBar().showMessage(info, 8000)
                if any(len(s.joints) > MAX_BONES for s in model.skins):
                    self.statusBar().showMessage(f"Plus de {MAX_BONES} bones : squelette tronqué", 8000)
        self.skin_combo.blockSignals(False)
        self.player.set_model(model)
        self.view.set_skin(None)
        self.view.model_changed()
        self._rebuild_animations(model, previous_animation)

    def _rebuild_animations(self, model: LoadedFile | None, selected: str | None) -> None:
        """Liste : T-pose, clips intégrés au personnage, puis clips de Animations/."""
        self.anim_combo.blockSignals(True)
        self.anim_combo.clear()
        self.anim_combo.addItem("aucune (T-pose)", None)
        for i, clip in enumerate(model.clips if model else []):
            self.anim_combo.addItem(f"{clip.name} (intégrée)", ("embedded", i))
        for i, a in enumerate(self.library.animations):
            self.anim_combo.addItem(("⚠ " if a.error else "") + a.label, ("library", i))
        self.anim_combo.blockSignals(False)
        self._select_text(self.anim_combo, selected)
        self.anim_combo.setEnabled(model is not None and model.skinned)
        self._on_animation(self.anim_combo.currentIndex())

    def _on_skin(self, index: int) -> None:
        entry = self._current_character()
        if entry is None or index <= 0:
            self.view.set_skin(None)
            self.settings.setValue("skin", "défaut")
            return
        path = entry.skins[index - 1]
        try:
            image = Image.open(path).convert("RGBA")
        except Exception as e:
            self.statusBar().showMessage(f"Skin illisible : {path.name} ({e})", 8000)
            self.skin_combo.setCurrentIndex(0)
            return
        self.view.set_skin(image)
        self.settings.setValue("skin", path.stem)

    def _on_animation(self, index: int) -> None:
        clip = None
        source = self.anim_combo.itemData(index)
        if source is not None and source[0] == "embedded":
            clip = self.player.model.clips[source[1]]
        elif source is not None:
            entry = self.library.animations[source[1]]
            if entry.error:
                self.statusBar().showMessage(f"{entry.label} : {entry.error}", 8000)
            else:
                try:
                    if entry.path not in self._anim_cache:
                        self._anim_cache[entry.path] = load_glb(entry.path)
                    clip = self._anim_cache[entry.path].clips[entry.clip_index]
                except LoadError as e:
                    self.statusBar().showMessage(str(e), 8000)
        self.settings.setValue("animation", self.anim_combo.itemText(index))
        self.player.set_clip(clip)
        self._update_validation()

    def _current_character(self):
        i = self.character_combo.currentIndex()
        return self.library.characters[i] if 0 <= i < len(self.library.characters) else None

    # --- lecture ---
    def _toggle_play(self) -> None:
        self.player.playing = not self.player.playing
        self.play_button.setText("⏸" if self.player.playing else "▶")

    def _on_time(self, t: float) -> None:
        d = self.player.duration
        self.time_label.setText(f"{t:.2f} / {d:.2f} s")
        if not self.timeline.isSliderDown():
            self.timeline.blockSignals(True)
            self.timeline.setValue(int(t / d * TIMELINE_STEPS) if d > 0 else 0)
            self.timeline.blockSignals(False)

    def _timeline_pressed(self) -> None:
        self._was_playing = self.player.playing
        self.player.playing = False

    def _timeline_moved(self, value: int) -> None:
        self.player.seek(value / TIMELINE_STEPS * self.player.duration)

    def _timeline_released(self) -> None:
        self.player.playing = self._was_playing

    # --- vérification ---
    def _update_validation(self) -> None:
        model, clip = self.player.model, self.player.clip
        self._report = None
        if model is None:
            self.validation_label.setText("—")
        elif not model.skinned:
            self.validation_label.setText("Modèle statique (pas de squelette)")
        else:
            self._report = validate(model.joint_names(), clip.track_names() if clip else None)
            if self._report.ok:
                self.validation_label.setText("✅ Squelette Mixamo OK")
            else:
                self.validation_label.setText(f"⚠ {self._report.warnings} problème(s)")
        self.details_button.setEnabled(self._report is not None)

    def _show_details(self) -> None:
        if self._report is not None:
            QMessageBox.information(self, "Vérification Mixamo", self._report.details())
