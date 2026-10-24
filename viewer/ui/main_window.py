"""Fenêtre principale : sélection perso / skin / animation, lecture, vérification."""
import json
import math
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QLabel, QMainWindow, QMessageBox,
    QProgressDialog, QPushButton, QSlider, QVBoxLayout, QWidget,
)

from viewer.gltf_loader import LoadedFile, LoadError, load_glb
from viewer.library import Library, scan
from viewer.mixamo import ValidationReport, validate
from viewer.player import Player
from viewer.renderer import MAX_BONES
from viewer.sprites.config import load_config, save_config
from viewer.sprites.export import ExportCancelled, ExportJob, export_spritesheet
from viewer.sprites.render import SpriteRenderer
from viewer.ui.export_dialog import ExportDialog
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
        self._current_entry = None

        self.view = GLView(self.player)
        self.character_combo = QComboBox()
        self.skin_combos: dict[str, QComboBox] = {}  # matériau -> liste de skins
        self._skin_paths: dict[str, list[Path]] = {}
        self.skins_layout = QVBoxLayout()
        self.skins_layout.setContentsMargins(0, 0, 0, 0)
        self.anim_combo = QComboBox()
        self.play_button = QPushButton("⏸")
        self.speed_combo = QComboBox()
        self.speed_combo.addItems([f"{s}x" for s in SPEEDS])
        self.speed_combo.setCurrentIndex(SPEEDS.index(1.0))
        self.bones_check = QCheckBox("Afficher bones")
        self.export_button = QPushButton("Exporter sprite sheet…")
        self.export_config_button = QPushButton("⚙ Config export…")
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
        side.addWidget(QLabel("Personnage"))
        side.addWidget(self.character_combo)
        skins_widget = QWidget()
        skins_widget.setLayout(self.skins_layout)
        side.addWidget(skins_widget)
        side.addWidget(QLabel("Animation"))
        side.addWidget(self.anim_combo)
        playback = QHBoxLayout()
        playback.addWidget(self.play_button)
        playback.addWidget(QLabel("Vitesse"))
        playback.addWidget(self.speed_combo)
        side.addLayout(playback)
        side.addWidget(self.export_button)
        side.addWidget(self.export_config_button)
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
        self.anim_combo.currentIndexChanged.connect(self._on_animation)
        self.play_button.clicked.connect(self._toggle_play)
        self.speed_combo.currentIndexChanged.connect(lambda i: setattr(self.player, "speed", SPEEDS[i]))
        self.bones_check.toggled.connect(lambda on: setattr(self.view, "show_bones", on))
        self.details_button.clicked.connect(self._show_details)
        self.export_button.clicked.connect(self._export_spritesheet)
        self.export_config_button.clicked.connect(self._edit_export_config)
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

        self.anim_combo.blockSignals(True)
        self.anim_combo.clear()
        self.anim_combo.addItem("aucune (T-pose)")
        for a in self.library.animations:
            self.anim_combo.addItem(("⚠ " if a.error else "") + a.label)
        self.anim_combo.blockSignals(False)

        self.character_combo.blockSignals(True)
        self.character_combo.clear()
        self.character_combo.addItems([c.name for c in self.library.characters])
        self.character_combo.blockSignals(False)

        saved_skins = {}
        if restore:
            self._select_text(self.character_combo, self.settings.value("character"))
            self._select_text(self.anim_combo, self.settings.value("animation"))
            try:
                saved_skins = json.loads(self.settings.value("skins") or "{}")
            except ValueError:
                pass
        self._on_character(self.character_combo.currentIndex())
        self._on_animation(self.anim_combo.currentIndex())
        for material, stem in saved_skins.items():
            combo = self.skin_combos.get(material)
            if combo is not None:
                self._select_text(combo, stem)
                self._on_skin(material, combo.currentIndex())

    @staticmethod
    def _select_text(combo: QComboBox, text) -> None:
        if text:
            i = combo.findText(str(text))
            if i >= 0:
                combo.blockSignals(True)
                combo.setCurrentIndex(i)
                combo.blockSignals(False)

    # --- sélection ---
    def _on_character(self, index: int) -> None:
        model = None
        entry = None
        if 0 <= index < len(self.library.characters):
            entry = self.library.characters[index]
            try:
                model = load_glb(entry.model_path)
            except LoadError as e:
                self.statusBar().showMessage(str(e), 8000)
                self.character_combo.setItemText(index, f"⚠ {entry.name}")
            else:
                self.settings.setValue("character", entry.name)
                for info in model.infos:
                    self.statusBar().showMessage(info, 8000)
                if any(len(s.joints) > MAX_BONES for s in model.skins):
                    self.statusBar().showMessage(f"Plus de {MAX_BONES} bones : squelette tronqué", 8000)
        self.player.set_model(model)
        self.view.model_changed()
        self._rebuild_skins(entry if model else None, model)
        self.anim_combo.setEnabled(model is not None and model.skinned)
        self._current_entry = entry if model else None
        for button in (self.export_button, self.export_config_button):
            button.setEnabled(model is not None and model.skinned)
        self._update_validation()

    def _rebuild_skins(self, entry, model: LoadedFile | None) -> None:
        """Une liste de skins par matériau du modèle ayant au moins une image proposée."""
        while self.skins_layout.count():
            self.skins_layout.takeAt(0).widget().deleteLater()
        self.skin_combos, self._skin_paths = {}, {}
        materials = model.materials() if model else []
        for material in materials:
            paths = entry.skins_for(material)
            if not paths:
                continue
            combo = QComboBox()
            combo.addItem("défaut")
            combo.addItems([p.stem for p in paths])
            combo.currentIndexChanged.connect(lambda i, m=material: self._on_skin(m, i))
            label = QLabel(f"Skin · {material}")
            label.setWordWrap(True)
            self.skins_layout.addWidget(label)
            self.skins_layout.addWidget(combo)
            self.skin_combos[material], self._skin_paths[material] = combo, paths
        if not self.skin_combos:
            self.skins_layout.addWidget(QLabel("Skin : aucune variante"))
        if entry is not None:
            orphans = entry.unmatched_folders(materials)
            if orphans:
                self.statusBar().showMessage(
                    f"skins/ : aucun matériau nommé {', '.join(orphans)} (matériaux : {', '.join(materials)})", 10000)
        self._save_skins()

    def _on_skin(self, material: str, index: int) -> None:
        if index <= 0:
            self.view.set_skin(material, None)
            self._save_skins()
            return
        path = self._skin_paths[material][index - 1]
        try:
            image = Image.open(path).convert("RGBA")
        except Exception as e:
            self.statusBar().showMessage(f"Skin illisible : {path.name} ({e})", 8000)
            self.skin_combos[material].setCurrentIndex(0)
            return
        self.view.set_skin(material, image)
        self._save_skins()

    def _save_skins(self) -> None:
        chosen = {m: c.currentText() for m, c in self.skin_combos.items() if c.currentIndex() > 0}
        self.settings.setValue("skins", json.dumps(chosen))

    def _on_animation(self, index: int) -> None:
        clip = None
        if index > 0:
            entry = self.library.animations[index - 1]
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

    # --- export de sprite sheet ---
    def _export_config_path(self) -> Path:
        return self._current_entry.model_path.parent / "spritesheet.json"

    def _load_export_config(self):
        config, error = load_config(self._export_config_path())
        if error:
            self.statusBar().showMessage(error, 8000)
        return config

    def _edit_export_config(self) -> None:
        if self._current_entry is None:
            return
        labels = [a.label for a in self.library.animations if not a.error]
        dialog = ExportDialog(self._load_export_config(), labels, self._current_entry.name, self)
        if dialog.exec():
            try:
                save_config(self._export_config_path(), dialog.result_config())
            except OSError as e:
                QMessageBox.critical(self, "Config export", f"Écriture impossible : {e}")
                return
            self.statusBar().showMessage(f"Config enregistrée : {self._export_config_path()}", 8000)

    def _load_clip(self, entry):
        if entry.path not in self._anim_cache:
            self._anim_cache[entry.path] = load_glb(entry.path)
        return self._anim_cache[entry.path].clips[entry.clip_index]

    def _export_jobs(self, config) -> tuple[list[ExportJob], list[str]]:
        entries = {a.label: a for a in self.library.animations if not a.error}
        jobs, skipped = [], []
        for anim in config.animations:
            if not anim.orientations:
                continue
            entry = entries.get(anim.name)
            try:
                if entry is None:
                    raise LoadError(anim.name)
                jobs.append(ExportJob(anim, self._load_clip(entry)))
            except LoadError:
                skipped.append(anim.name)
        return jobs, skipped

    def _export_spritesheet(self) -> None:
        model, character = self.player.model, self._current_entry
        if model is None or character is None:
            return
        config = self._load_export_config()
        jobs, skipped = self._export_jobs(config)
        if not jobs:
            QMessageBox.information(self, "Export sprite sheet",
                                    "Aucune animation à exporter : coche des animations et des orientations "
                                    "dans « ⚙ Config export… ».")
            return

        exports_dir = self.root / "Exports"
        exports_dir.mkdir(exist_ok=True)
        path, _ = QFileDialog.getSaveFileName(self, "Exporter la sprite sheet",
                                              str(exports_dir / f"{character.name}.png"), "Image PNG (*.png)")
        if not path:
            return
        self.export_to(Path(path).with_suffix(".png"), config, jobs, skipped)

    def export_to(self, png: Path, config, jobs: list[ExportJob], skipped: list[str]) -> bool:
        progress = QProgressDialog("Rendu des frames…", "Annuler", 0, 100, self)
        progress.setWindowTitle("Export sprite sheet")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        model = self.player.model

        def on_progress(done: int, total: int) -> bool:
            progress.setValue(math.floor(done * 100 / max(total, 1)))
            QApplication.processEvents()
            self.view.makeCurrent()  # un rafraîchissement de la vue a pu changer de contexte
            return not progress.wasCanceled()

        def run(ctx, renderer):
            sprites = SpriteRenderer(ctx, renderer)
            try:
                return export_spritesheet(sprites, model, jobs, config, png.name, on_progress)
            finally:
                sprites.release()

        QGuiApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            result = self.view.run_in_context(run)
        except ExportCancelled:
            self.statusBar().showMessage("Export annulé", 8000)
            return False
        except ValueError as e:
            QMessageBox.warning(self, "Export sprite sheet",
                                f"{e}.\nAugmente la largeur de la feuille dans « ⚙ Config export… ».")
            return False
        finally:
            QGuiApplication.restoreOverrideCursor()
            progress.close()

        try:
            result.image.save(png)
            png.with_suffix(".json").write_text(json.dumps(result.data, indent=2, ensure_ascii=False) + "\n",
                                                encoding="utf-8")
        except OSError as e:
            QMessageBox.critical(self, "Export sprite sheet", f"Écriture impossible ({png}) : {e}")
            return False
        message = f"Exporté : {png} — {result.frame_count} frames, {result.image.width}×{result.image.height} px"
        if skipped:
            message += f" — ignorées : {', '.join(skipped)}"
        self.statusBar().showMessage(message, 15000)
        return True

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
