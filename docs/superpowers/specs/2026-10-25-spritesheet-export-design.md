# Export de sprite sheet — Design

Date : 2026-10-25
Statut : validé (brainstorming)
Complète : [2026-10-24-character-viewer-design.md](2026-10-24-character-viewer-design.md)

## Objectif

Exporter les animations du personnage courant en une image PNG (sprite sheet) et un
fichier JSON décrivant chaque frame, pour une utilisation dans un jeu 2D.

## Périmètre

Inclus :
- Bouton « Exporter sprite sheet… » et bouton « ⚙ Config export… » (popup).
- Configuration par personnage : largeur de feuille, hauteur de frame, et pour chaque
  animation de la bibliothèque : exportée ou non, nombre de frames, orientations (8 directions).
- PNG à fond transparent, frames rognées au contenu, JSON des frames avec origine au sol.

Exclu (YAGNI) : caméra en plongée / isométrique, perspective, espacement (padding) entre
frames, export de plusieurs personnages à la fois, formats autres que PNG + JSON,
animations intégrées aux GLB des personnages (seules celles de `Animations/` sont proposées).

## Fichiers produits

### PNG

- Largeur fixe `sheetWidth` (défaut 1000 px), fond transparent (RGBA, alpha 0).
- Hauteur = nombre de lignes × `frameHeight`.
- Les couples (animation, orientation) se suivent dans l'ordre : animations dans l'ordre
  de la config, orientations dans l'ordre S, SE, E, NE, N, NO, O, SO.
- Toutes les frames s'enchaînent de gauche à droite sans espace, y compris d'une animation
  à la suivante (pas de nouvelle ligne par couple, pour réduire la taille de l'image) ; si la
  frame suivante dépasse `sheetWidth`, elle passe au début de la ligne suivante.
- Chaque frame fait `frameHeight` px de haut (défaut 250) et est rognée horizontalement à la
  boîte englobante des pixels non transparents (largeur minimale 1 px pour une frame vide).

### JSON

Même chemin que le PNG, extension `.json` :

```json
{
  "image": "Soldier.png",
  "width": 1000,
  "height": 1500,
  "frameHeight": 250,
  "animations": [
    {
      "name": "walk",
      "orientation": "SE",
      "angle": 45,
      "fps": 12,
      "frames": [
        { "x": 0, "y": 0, "width": 83, "height": 250, "origin": { "x": 41, "y": 238 } }
      ]
    }
  ]
}
```

- `name` : libellé de l'animation dans la bibliothèque (ex. `walk`, `pack / Idle`).
- `x`, `y` : pixel en haut à gauche de la frame dans l'image ; `width`, `height` : taille.
- `origin` : point au sol sous le personnage, **relatif au coin haut-gauche de la frame**.
- `fps` : cadence de lecture qui respecte la durée de l'animation, `frames / durée`
  arrondi à 3 décimales (0 pour une animation de durée nulle).
- Une entrée par couple (animation, orientation).

### Orientations

L'angle est la rotation du personnage autour de l'axe vertical ; S regarde la caméra.

| Nom | Angle | Le personnage regarde |
|---|---|---|
| S | 0 | la caméra |
| SE | 45 | |
| E | 90 | la droite de l'image |
| NE | 135 | |
| N | 180 | le fond (de dos) |
| NO | 225 | |
| O | 270 | la gauche de l'image |
| SO | 315 | |

Direction regardée : `(sin a, 0, cos a)` dans le repère monde de la vue (caméra sur +Z).

## Rendu

- Caméra orthographique de face, axe de visée −Z, sans inclinaison.
- Personnage : pose retargetée, tourné vers +Z (correction d'orientation existante),
  puis tourné de l'angle de l'orientation autour de Y passant par l'origine du monde.
- **Sur place** : option `in_place` du `Retargeter` — la composante horizontale (X, Z en
  monde du modèle) du déplacement des Hips est annulée ; la composante verticale est gardée.
- **Origine** : point monde `(0, 0, 0)` — le sol sous la position de repos du personnage
  (la correction d'orientation et les rotations d'angle passent par cet axe).
- **Échelle commune** : premier passage sur toutes les frames de toutes les animations
  exportées (une seule orientation suffit, la hauteur ne dépend pas de la rotation autour
  de Y) avec les sommets déformés sur CPU :
  - `top = max(y)`, `bottom = min(min(y), 0)`, `radius = max(√(x² + z²))` ;
  - `scale = (frameHeight − 2 × marge) / (top − bottom)` pixels par unité, marge = 4 px ;
  - ligne de sol à `marge + top × scale` px depuis le haut de la frame.
- Rendu de chaque frame dans un framebuffer hors écran de
  `2 × (2 × radius × scale + 2 × marge)` × `2 × frameHeight` px (suréchantillonnage 2×),
  fond (0, 0, 0, 0), sans grille ni bones, puis réduction 2× (filtre LANCZOS en alpha
  prémultiplié) et rognage horizontal ; `origin.x` = position de l'axe du personnage moins
  le bord gauche du rognage, `origin.y` = ligne de sol.
- Éclairage identique à la vue (lumière fixe en monde : l'ombrage varie avec l'orientation).
- Skins : celles choisies dans le panneau au moment de l'export.

## Cadence

- Nombre de frames `n` configuré par animation, défaut 8, de 1 à 240.
- Temps `tᵢ = i × durée / n` pour `i < n` : répartis uniformément, la fin de la boucle
  (identique au début) est omise ; `n = 1` donne la pose à t = 0.
- Animation de durée nulle : `n` frames identiques à t = 0.

## Configuration

Fichier `Characters/<perso>/spritesheet.json` :

```json
{
  "sheetWidth": 1000,
  "frameHeight": 250,
  "animations": [
    { "name": "walk", "frames": 8, "orientations": ["S", "E", "N", "O"] }
  ]
}
```

- Une animation absente de la liste n'est pas exportée.
- Ancienne clé `fps` (premières versions) : sa valeur est reprise comme nombre de frames.
- Une animation de la config absente de la bibliothèque est ignorée (et conservée dans le
  fichier tant que la popup n'est pas validée).
- Fichier absent ou illisible : config par défaut (1000, 250, aucune animation), message en
  barre de statut si illisible.
- Bornes : `sheetWidth` 64–16384, `frameHeight` 16–2048.

## Interface

- Sous la liste des animations : boutons **Exporter sprite sheet…** et **⚙ Config export…**,
  désactivés si aucun personnage skinné n'est chargé.
- Popup de configuration (modale) :
  - champs « Largeur de la feuille » et « Hauteur des frames » ;
  - tableau, une ligne par animation de la bibliothèque (hors animations en erreur) :
    case « Exporter », nombre de frames (spinbox), 8 cases S…SO ;
  - cocher « Exporter » sans orientation coche S par défaut ;
  - OK enregistre `spritesheet.json`, Annuler ne change rien.
- Export :
  - erreur si aucune animation cochée avec au moins une orientation ;
  - « Enregistrer sous », défaut `<racine>/Exports/<perso>.png` (dossier créé si besoin) ;
  - barre de progression annulable (rien n'est écrit en cas d'annulation) ;
  - erreur si une frame rognée est plus large que `sheetWidth` (rien n'est écrit) ;
  - message en barre de statut à la fin : chemin, nombre de frames, taille de l'image.

## Architecture

```
viewer/sprites/
  config.py    # ExportConfig, AnimationExport, load_config / save_config
  layout.py    # ORIENTATIONS, frame_times, compute_scale, pack (placement), build_json
  render.py    # SpriteRenderer : rendu hors écran d'une pose → (image rognée, origine x)
  export.py    # export_spritesheet : passage échelle, rendu, assemblage PNG + JSON
viewer/ui/export_dialog.py   # popup de configuration
```

Modifications de l'existant :
- `Retargeter(model, clip, in_place=False)`.
- `Renderer.render(..., background=None, grid=True)` : fond transparent et grille désactivable.
- `viewer/player.py` : extraction de `skinned_points(model, frame)` (utilisé par
  `Player.bounds` et le passage d'échelle).
- `MainWindow` : deux boutons, popup, export avec progression.

`config.py` et `layout.py` sont indépendants de Qt et d'OpenGL.

## Erreurs

| Situation | Comportement |
|---|---|
| Aucune animation exportée | message, pas de dialogue d'enregistrement |
| Animation de la config introuvable / illisible | ignorée, signalée en fin d'export |
| Frame plus large que la feuille | erreur, rien n'est écrit |
| Annulation | rien n'est écrit |
| Écriture impossible (droits, disque) | message d'erreur avec le chemin |

## Tests

Unitaires (`pytest`) :
- `config` : aller-retour JSON, valeurs par défaut, fichier illisible, bornes.
- `layout` : temps des frames (durée nulle, arrondi), échelle et ligne de sol, placement
  à la suite d'un couple à l'autre avec retour à la ligne, structure du JSON.
- `Retargeter(in_place=True)` : déplacement horizontal des Hips annulé, vertical conservé.
- `skinned_points` : cohérent avec `Player.bounds`.

Test de fumée (manuel ou script) : export de Soldier avec 2 animations × 2 orientations,
vérification visuelle du PNG et cohérence du JSON (frames dans l'image, origines au sol).
