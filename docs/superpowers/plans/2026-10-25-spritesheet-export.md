# Export de sprite sheet — Plan d'implémentation

Spec : [2026-10-25-spritesheet-export-design.md](../specs/2026-10-25-spritesheet-export-design.md)

TDD sur tout ce qui est indépendant d'OpenGL ; rendu et UI vérifiés par un script de fumée.
Un commit par tâche.

## Tâche 1 — `Retargeter(in_place=True)`

- `viewer/animation.py` : paramètre `in_place: bool = False` ; si vrai, le déplacement monde
  des Hips (après alignement d'orientation et ratio) a ses composantes X et Z mises à 0.
- Test `tests/test_animation.py::test_retarget_in_place` : source qui avance en Z et monte
  en Y → Hips du modèle à X/Z de repos, Y suivi.

## Tâche 2 — `skinned_points`

- `viewer/player.py` : fonction `skinned_points(model, frame) -> (P, 3)` extraite de
  `Player.bounds` (sommets déformés, meshes statiques via leur matrice globale).
  `Player.bounds` l'utilise. Nouvelle méthode `Player.frame_at(pose_globals...)` non
  nécessaire : l'export construit ses `FrameData` lui-même via `frame_from_globals`.
- `frame_from_globals(model, globals) -> FrameData` (fonction module, réutilisée par
  `Player._frame`).
- Test : `skinned_points` sur le fixture = 4 sommets attendus.

## Tâche 3 — `sprites/config.py`

```python
ORIENTATIONS = ("S", "SE", "E", "NE", "N", "NO", "O", "SO")   # dans layout.py, importé ici

@dataclass
class AnimationExport:
    name: str
    fps: int = 12
    orientations: list[str]           # sous-ensemble ordonné de ORIENTATIONS

@dataclass
class ExportConfig:
    sheet_width: int = 1000
    frame_height: int = 250
    animations: list[AnimationExport]

def load_config(path) -> tuple[ExportConfig, str | None]   # (config, message d'erreur éventuel)
def save_config(path, config) -> None
```
- Bornes appliquées au chargement (clamp) ; orientations inconnues ignorées, réordonnées.
- Tests : aller-retour, fichier absent → défaut sans message, JSON invalide → défaut + message,
  bornes, orientations nettoyées.

## Tâche 4 — `sprites/layout.py`

```python
ORIENTATIONS: tuple[str, ...]; ANGLES: dict[str, int]       # S=0, SE=45, …, SO=315
MARGIN = 4

def frame_times(duration, fps) -> list[float]
@dataclass class Scale: pixels_per_unit: float; ground_y: float   # ground_y depuis le haut
def compute_scale(top, bottom, frame_height) -> Scale
@dataclass class Placed: x: int; y: int; width: int; height: int; origin_x: int; origin_y: int
def pack(sequences: list[list[tuple[int, int, int]]], sheet_width, frame_height)
    -> tuple[list[list[Placed]], int]        # (width, origin_x, origin_y) par frame → positions, hauteur
def build_json(image_name, sheet_width, sheet_height, frame_height, entries) -> dict
```
- `pack` lève `ValueError` si une frame est plus large que la feuille.
- Tests : durée nulle, arrondi ; échelle avec bottom < 0 ; nouvelle ligne par séquence ;
  retour à la ligne en cas de dépassement ; hauteur totale ; erreur largeur ; JSON conforme
  à la spec.

## Tâche 5 — `Renderer.render(background, grid)`

- `background: tuple | None` (défaut : couleur actuelle), `grid: bool = True`.
- Pas de test unitaire (OpenGL), couvert par la fumée.

## Tâche 6 — `sprites/render.py` + `sprites/export.py`

- `SpriteRenderer(ctx, renderer)` : `render(frame, view_proj, size) -> PIL.Image` via un
  framebuffer hors écran RGBA8 + profondeur, lecture des pixels (retournement vertical).
- `export_spritesheet(ctx, renderer, model, clips: list[(AnimationExport, clip)], config,
  progress) -> (Image, dict)` :
  1. passage échelle : `Retargeter(in_place=True)` sur tous les temps, `skinned_points`,
     top/bottom/radius ;
  2. rendu 2× de chaque (anim, orientation, temps), réduction LANCZOS en `RGBa`, rognage ;
  3. `pack` puis assemblage de l'image et `build_json`.
  `progress(done, total) -> bool` ; retour `False` = annulation (`ExportCancelled`).
- Projection : orthographique, `x ∈ [−w/2, w/2]`, `y ∈ [ground − h, ground]` en unités monde.

## Tâche 7 — UI

- `viewer/ui/export_dialog.py` : `ExportDialog(config, animation_labels, parent)` ;
  `result_config()`.
- `MainWindow` : boutons, chemin de config `Characters/<perso>/spritesheet.json`,
  `QFileDialog.getSaveFileName`, `QProgressDialog`, écriture PNG + JSON, messages.
- `GLView` : méthode `run_in_context(fn)` (makeCurrent / doneCurrent) pour l'export.

## Tâche 8 — Fumée

Script : bibliothèque copiée dans le scratchpad, config Soldier (walk S+E, SambaDance S+SO),
export, vérification : dimensions, frames dans l'image, alpha nul hors personnage, origines
au sol, inspection visuelle du PNG.
