"""Fenêtre principale : sélection perso / skin / animation, lecture, vérification."""
import json
import math
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QGridLayout, QHBoxLayout, QInputDialog, QLabel, QMainWindow,
    QMessageBox, QProgressDialog, QPushButton, QSlider, QVBoxLayout, QWidget,
)

from viewer.attachments import (
    OBJECTS_DIR, Attachment, apply_offset, compose, load_placement, save_placement, scan_objects, structure_key,
)
from viewer.gltf_loader import LoadedFile, LoadError, load_glb
from viewer.library import Library, scan
from viewer.mixamo import ValidationReport, validate
from viewer.player import Player
from viewer.presets import (
    DEFAULT_PRESET, Preset, check_name, delete_preset, list_presets, load_preset, preset_path, rename_preset,
    save_preset,
)
from viewer.render_settings import RenderSettings
from viewer.renderer import MAX_BONES
from viewer.sprites.export import ExportCancelled, ExportJob, export_spritesheet
from viewer.sprites.render import SpriteRenderer
from viewer.ui.attachments_dialog import AttachmentsDialog
from viewer.ui.export_dialog import ExportDialog
from viewer.ui.gl_view import GLView
from viewer.ui.render_dialog import RenderDialog
from viewer.ui.sheet_viewer import ExportPickerDialog, SheetViewerDialog

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
        self._base_model: LoadedFile | None = None  # personnage seul, sans objets attachés
        self._shown: list[str] = []  # objets affichés par la config courante
        self._placements: dict[str, Attachment] = {}  # réglages des objets, lus à la demande
        self._structure: list[tuple] = []
        self._composed = None
        self._objects: dict[str, LoadedFile | None] = {}  # objets chargés par nom (None : illisible)
        self._preset = DEFAULT_PRESET  # config courante du personnage

        self.view = GLView(self.player)
        self.character_combo = QComboBox()
        self.preset_combo = QComboBox()
        self.new_preset_button = QPushButton("Nouvelle")
        self.duplicate_preset_button = QPushButton("Dupliquer")
        self.rename_preset_button = QPushButton("Renommer")
        self.delete_preset_button = QPushButton("Supprimer")
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
        self.render_button = QPushButton("🎨 Paramètres de rendu…")
        self.attach_button = QPushButton("🔧 Objets attachés…")
        self.export_button = QPushButton("Exporter sprite sheet…")
        self.export_config_button = QPushButton("⚙ Config export…")
        self.view_exports_button = QPushButton("👁 Visualiser un export…")
        self.validation_label = QLabel()
        self.validation_label.setWordWrap(True)
        self.details_button = QPushButton("détails…")
        self.timeline = QSlider(Qt.Orientation.Horizontal)
        self.timeline.setRange(0, TIMELINE_STEPS)
        self.time_label = QLabel("0.00 / 0.00 s")

        self._build_layout()
        self._connect()
        self._update_validation()
        self._load_render_settings()

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
        side.addWidget(QLabel("Config"))
        side.addWidget(self.preset_combo)
        preset_buttons = QGridLayout()
        preset_buttons.addWidget(self.new_preset_button, 0, 0)
        preset_buttons.addWidget(self.duplicate_preset_button, 0, 1)
        preset_buttons.addWidget(self.rename_preset_button, 1, 0)
        preset_buttons.addWidget(self.delete_preset_button, 1, 1)
        side.addLayout(preset_buttons)
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
        side.addWidget(self.view_exports_button)
        side.addWidget(self.render_button)
        side.addWidget(self.attach_button)
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
        self.preset_combo.currentIndexChanged.connect(self._on_preset)
        self.new_preset_button.clicked.connect(self._new_preset)
        self.duplicate_preset_button.clicked.connect(self._duplicate_preset)
        self.rename_preset_button.clicked.connect(self._rename_preset)
        self.delete_preset_button.clicked.connect(self._delete_preset)
        self.anim_combo.currentIndexChanged.connect(self._on_animation)
        self.play_button.clicked.connect(self._toggle_play)
        self.speed_combo.currentIndexChanged.connect(lambda i: setattr(self.player, "speed", SPEEDS[i]))
        self.bones_check.toggled.connect(lambda on: setattr(self.view, "show_bones", on))
        self.details_button.clicked.connect(self._show_details)
        self.render_button.clicked.connect(self._edit_render_settings)
        self.attach_button.clicked.connect(self._edit_attachments)
        self.export_button.clicked.connect(self._export_spritesheet)
        self.export_config_button.clicked.connect(self._edit_export_config)
        self.view_exports_button.clicked.connect(self._view_exports)
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
        self._objects.clear()
        self._placements.clear()
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
        self._base_model = model
        self._current_entry = entry if model else None
        self._fill_presets()
        self._shown = self._load_preset().objects if model else []
        self.player.set_model(self._compose() if model else None)
        self.view.model_changed()
        self._rebuild_skins(entry if model else None, model)
        self.anim_combo.setEnabled(model is not None and model.skinned)
        for button in (self.export_button, self.export_config_button, self.attach_button):
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

    # --- paramètres de rendu ---
    def _load_render_settings(self) -> None:
        try:
            data = json.loads(self.settings.value("render") or "{}")
        except ValueError:
            data = {}
        self.view.set_render_settings(RenderSettings.from_dict(data))

    def _edit_render_settings(self) -> None:
        dialog = RenderDialog(self.view.render_settings, self)
        dialog.changed.connect(self.view.set_render_settings)
        if dialog.exec():
            self.settings.setValue("render", json.dumps(dialog.result_settings().to_dict()))

    # --- configs (export + objets attachés) ---
    def _character_dir(self) -> Path:
        return self._current_entry.model_path.parent

    def _fill_presets(self, select: str | None = None) -> None:
        """Remplit la liste des configs du personnage courant, sans recharger la config."""
        skinned = self._base_model is not None and self._base_model.skinned
        names = list_presets(self._character_dir()) if skinned else []
        if select is None and self._current_entry is not None:
            select = self._saved_presets().get(self._current_entry.name)
        self.preset_combo.blockSignals(True)
        self.preset_combo.clear()
        self.preset_combo.addItems(names)
        if select in names:
            self.preset_combo.setCurrentIndex(names.index(select))
        self.preset_combo.blockSignals(False)
        self._preset = self.preset_combo.currentText() or DEFAULT_PRESET
        for widget in (self.preset_combo, self.new_preset_button, self.duplicate_preset_button,
                       self.rename_preset_button):
            widget.setEnabled(skinned)
        self.delete_preset_button.setEnabled(skinned and preset_path(self._character_dir(), self._preset).is_file())
        if skinned:
            self._remember_preset()

    def _saved_presets(self) -> dict:
        try:
            saved = json.loads(self.settings.value("presets") or "{}")
        except ValueError:
            return {}
        return saved if isinstance(saved, dict) else {}

    def _remember_preset(self) -> None:
        saved = self._saved_presets()
        saved[self._current_entry.name] = self._preset
        self.settings.setValue("presets", json.dumps(saved, ensure_ascii=False))

    def _load_preset(self) -> Preset:
        preset, error = load_preset(self._character_dir(), self._preset)
        if error:
            self.statusBar().showMessage(error, 8000)
        return preset

    def _save_preset(self, preset: Preset, title: str) -> bool:
        try:
            path = save_preset(self._character_dir(), self._preset, preset)
        except OSError as e:
            QMessageBox.critical(self, title, f"Écriture impossible : {e}")
            return False
        self.delete_preset_button.setEnabled(True)
        self.statusBar().showMessage(f"Config enregistrée : {path}", 8000)
        return True

    def _select_preset(self, name: str | None) -> None:
        self._fill_presets(name)
        self._shown = self._load_preset().objects
        self.player.set_model(self._compose())
        self.view.attachments_changed()

    def _on_preset(self, index: int) -> None:
        if index >= 0:
            self._select_preset(self.preset_combo.itemText(index))

    def _ask_preset_name(self, title: str, text: str = "", current: str | None = None) -> str | None:
        while True:
            name, ok = QInputDialog.getText(self, title, "Nom de la config :", text=text)
            if not ok:
                return None
            name = name.strip()
            error = check_name(name, list_presets(self._character_dir()), current)
            if error is None:
                return name
            QMessageBox.warning(self, title, error)
            text = name

    def _new_preset(self) -> None:
        self._create_preset("Nouvelle config", "", Preset())

    def _duplicate_preset(self) -> None:
        self._create_preset("Dupliquer la config", f"{self._preset} copie", self._load_preset())

    def _create_preset(self, title: str, text: str, preset: Preset) -> None:
        name = self._ask_preset_name(title, text)
        if name is None:
            return
        try:
            if not preset_path(self._character_dir(), self._preset).is_file():
                # « défaut » migrée : l'écrire avant qu'une autre config ne la masque
                save_preset(self._character_dir(), self._preset, self._load_preset())
            save_preset(self._character_dir(), name, preset)
        except OSError as e:
            QMessageBox.critical(self, title, f"Écriture impossible : {e}")
            return
        self._select_preset(name)

    def _rename_preset(self) -> None:
        title = "Renommer la config"
        name = self._ask_preset_name(title, self._preset, current=self._preset)
        if name is None or name == self._preset:
            return
        try:
            rename_preset(self._character_dir(), self._preset, name)
        except OSError as e:
            QMessageBox.critical(self, title, f"Renommage impossible : {e}")
            return
        self._select_preset(name)

    def _delete_preset(self) -> None:
        answer = QMessageBox.question(self, "Supprimer la config", f"Supprimer la config « {self._preset} » ?")
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            delete_preset(self._character_dir(), self._preset)
        except OSError as e:
            QMessageBox.critical(self, "Supprimer la config", f"Suppression impossible : {e}")
            return
        self._select_preset(None)

    # --- objets attachés ---
    def _placement(self, name: str, messages: list[str]) -> Attachment:
        """Réglage d'un objet (Objects/<objet>.json), lu une fois par dossier racine."""
        if name not in self._placements:
            self._placements[name], error = load_placement(self.root, name)
            if error:
                messages.append(error)
        return self._placements[name]

    def _compose(self) -> LoadedFile:
        """Modèle du personnage avec les objets affichés par la config (objets chargés à la demande)."""
        messages = []
        attachments = [self._placement(name, messages) for name in self._shown]
        for name in self._shown:
            if name not in self._objects:
                try:
                    self._objects[name] = load_glb(self.root / OBJECTS_DIR / name)
                except LoadError as e:
                    self._objects[name] = None
                    messages.append(str(e))
        loaded = {name: obj for name, obj in self._objects.items() if obj is not None}
        self._composed = compose(self._base_model, attachments, loaded)
        self._structure = structure_key(attachments)
        messages += self._composed.messages
        if messages:
            self.statusBar().showMessage(" — ".join(messages), 10000)
        return self._composed.model

    def _preview_attachments(self, shown: list[str], placements: dict[str, Attachment]) -> None:
        self._shown = shown
        self._placements.update(placements)
        attachments = [self._placements[name] for name in shown]
        if structure_key(attachments) == self._structure:
            for socket in self._composed.sockets:
                apply_offset(self._composed.model, socket, attachments[socket.attachment])
            self.view.update()
        else:
            self.player.set_model(self._compose())
            self.view.attachments_changed()

    def _edit_attachments(self) -> None:
        model, entry = self._base_model, self._current_entry
        if model is None or entry is None:
            return
        objects = scan_objects(self.root)
        messages = []
        placements = {name: self._placement(name, messages) for name in objects + self._shown}
        if messages:
            self.statusBar().showMessage(" — ".join(messages), 10000)
        bones = list(dict.fromkeys(model.skeleton.names[j] for s in model.skins for j in s.joints))
        dialog = AttachmentsDialog(objects, self._shown, placements, bones, f"{entry.name} · {self._preset}", self)
        dialog.changed.connect(self._preview_attachments)
        if not dialog.exec():
            return
        try:
            for a in dialog.result_placements().values():
                save_placement(self.root, a)
        except OSError as e:
            QMessageBox.critical(self, "Objets attachés", f"Écriture impossible : {e}")
            return
        preset = self._load_preset()
        preset.objects = dialog.result_objects()
        self._save_preset(preset, "Objets attachés")

    # --- export de sprite sheet ---
    def _edit_export_config(self) -> None:
        if self._current_entry is None:
            return
        entries = [a for a in self.library.animations if not a.error]
        durations = {}
        QGuiApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            for entry in entries:
                try:
                    durations[entry.label] = self._load_clip(entry).duration
                except LoadError:
                    pass
        finally:
            QGuiApplication.restoreOverrideCursor()
        preset = self._load_preset()
        dialog = ExportDialog(preset.export, [e.label for e in entries], f"{self._current_entry.name} · {self._preset}",
                              durations, self)
        if dialog.exec():
            preset = self._load_preset()
            preset.export = dialog.result_config()
            self._save_preset(preset, "Config export")

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
        config = self._load_preset().export
        jobs, skipped = self._export_jobs(config)
        if not jobs:
            QMessageBox.information(self, "Export sprite sheet",
                                    "Aucune animation à exporter : coche des animations et des orientations "
                                    "dans « ⚙ Config export… ».")
            return

        exports_dir = self.root / "Exports"
        exports_dir.mkdir(exist_ok=True)
        path, _ = QFileDialog.getSaveFileName(self, "Exporter la sprite sheet",
                                              str(exports_dir / f"{character.name}_{self._preset}.png"), "Image PNG (*.png)")
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

    def _view_exports(self) -> None:
        if self.root is None:
            return
        current = self._current_entry.name if self._current_entry else None
        picker = ExportPickerDialog(self.root / "Exports", self.settings.value("viewedExport") or current, self)
        if picker.exec() and picker.sheet is not None:
            self.settings.setValue("viewedExport", picker.sheet.json_path.stem)
            SheetViewerDialog(picker.sheet, self).exec()

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
