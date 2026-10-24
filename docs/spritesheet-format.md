# Format des sprite sheets exportées

Ce document décrit les fichiers produits par **Exporter sprite sheet…** dans 3D Characters
Viewer, pour les charger et les jouer dans un moteur de jeu.

## Fichiers

Un export produit deux fichiers côte à côte, de même nom :

| Fichier | Contenu |
|---|---|
| `<nom>.png` | L'image contenant toutes les frames. |
| `<nom>.json` | La description de chaque animation et de chaque frame. |

Le champ `image` du JSON contient le nom du PNG, sans chemin : le PNG est à chercher dans le
même dossier que le JSON.

## L'image PNG

- RGBA 8 bits, **fond transparent** (alpha = 0 hors du personnage, bords lissés).
- Largeur fixe (`width` dans le JSON, 1000 px par défaut).
- Hauteur = nombre de lignes × `frameHeight`.
- Les frames sont collées les unes aux autres, **sans espace** entre elles. Elles s'enchaînent
  de gauche à droite et passent à la ligne suivante quand la largeur est atteinte, y compris au
  milieu d'une animation. Une même ligne peut donc contenir la fin d'une animation et le début
  de la suivante.

> Ne déduisez jamais la position d'une frame à partir d'une grille : lisez toujours `x`, `y`,
> `width` et `height` dans le JSON.

## Le fichier JSON

### Exemple

Extrait d'un export réel : seules deux entrées sont montrées, et `run` est tronquée à ses
deux premières frames sur 8.

```json
{
  "image": "Human.png",
  "width": 1000,
  "height": 2000,
  "frameHeight": 250,
  "animations": [
    {
      "name": "idle",
      "orientation": "S",
      "angle": 0,
      "fps": 0.4,
      "frames": [
        { "x": 0, "y": 0, "width": 89, "height": 250, "origin": { "x": 44, "y": 242 } }
      ]
    },
    {
      "name": "run",
      "orientation": "E",
      "angle": 90,
      "fps": 11.429,
      "frames": [
        { "x": 0, "y": 250, "width": 104, "height": 250, "origin": { "x": 32, "y": 242 } },
        { "x": 104, "y": 250, "width": 162, "height": 250, "origin": { "x": 68, "y": 242 } }
      ]
    }
  ]
}
```

### Racine

| Champ | Type | Description |
|---|---|---|
| `image` | chaîne | Nom du fichier PNG associé. |
| `width` | entier | Largeur de l'image, en pixels. |
| `height` | entier | Hauteur de l'image, en pixels. |
| `frameHeight` | entier | Hauteur commune de toutes les frames, en pixels (250 par défaut). |
| `animations` | tableau | Une entrée par couple animation + orientation (voir ci-dessous). |

### Animation

Une animation exportée sous plusieurs orientations apparaît **plusieurs fois** dans le
tableau, une fois par orientation, avec le même `name`.

| Champ | Type | Description |
|---|---|---|
| `name` | chaîne | Nom de l'animation, tel qu'il apparaît dans la bibliothèque : `walk`, ou `pack / Idle` pour un fichier contenant plusieurs clips. |
| `orientation` | chaîne | Direction vers laquelle regarde le personnage : `S`, `SE`, `E`, `NE`, `N`, `NO`, `O` ou `SO`. |
| `angle` | entier | Angle de l'orientation, en degrés (voir [Orientations](#orientations)). |
| `fps` | nombre | Cadence de lecture qui respecte la durée d'origine de l'animation : nombre de frames ÷ durée, arrondi à 3 décimales. Vaut `0` pour une animation de durée nulle (pose fixe). |
| `frames` | tableau | Les frames dans l'ordre de lecture. |

Ordre des entrées : les animations dans l'ordre de la configuration d'export, puis, pour
chaque animation, les orientations dans l'ordre `S`, `SE`, `E`, `NE`, `N`, `NO`, `O`, `SO`.

### Frame

| Champ | Type | Description |
|---|---|---|
| `x`, `y` | entiers | Coin **haut-gauche** de la frame dans l'image, en pixels (origine en haut à gauche de l'image, y vers le bas). |
| `width` | entier | Largeur de la frame. Elle **varie d'une frame à l'autre**, chaque frame étant rognée au plus près du personnage. |
| `height` | entier | Hauteur de la frame, toujours égale à `frameHeight`. |
| `origin.x`, `origin.y` | entiers | Point au sol sous le personnage (là où sont posés les pieds), **relatif au coin haut-gauche de la frame**. |

## Orientations

L'orientation indique la direction vers laquelle **regarde le personnage**, vue par une
caméra de face. `S` est face à la caméra.

| Nom | Angle | Le personnage regarde |
|---|---|---|
| `S` | 0 | la caméra (vers le bas de l'écran) |
| `SE` | 45 | en diagonale, vers la caméra et la droite |
| `E` | 90 | la droite de l'image |
| `NE` | 135 | en diagonale, vers le fond et la droite |
| `N` | 180 | le fond (de dos) |
| `NO` | 225 | en diagonale, vers le fond et la gauche |
| `O` | 270 | la gauche de l'image |
| `SO` | 315 | en diagonale, vers la caméra et la gauche |

Chaque orientation est un vrai rendu 3D, pas un miroir d'une autre : `O` n'est pas `E`
retourné. L'éclairage est fixe dans la scène, donc l'ombrage du personnage change d'une
orientation à l'autre.

## Afficher une frame

L'**origine** est le point d'ancrage à utiliser pour placer le personnage. Pour afficher le
personnage dont les pieds sont à la position `(px, py)` à l'écran :

```
source      = rectangle (frame.x, frame.y, frame.width, frame.height) dans l'image
destination = coin haut-gauche en (px - frame.origin.x, py - frame.origin.y)
```

Comme la largeur et l'origine changent d'une frame à l'autre, il faut appliquer ce calcul
**à chaque frame**. Le personnage reste alors parfaitement immobile au sol, sans tremblement.

Garanties utiles :

- **Même échelle partout** : toutes les frames d'un export (toutes animations et
  orientations confondues) sont dessinées à la même échelle. Un personnage a donc la même
  taille dans `idle` et dans `run`.
- **Même ligne de sol** : `origin.y` est identique pour toutes les frames d'un export.
- **Sur place** : le déplacement horizontal du personnage est retiré des animations (une
  marche ou une course se fait sur place). C'est au jeu de déplacer le personnage. Le
  mouvement vertical (saut, accroupissement) est conservé et visible dans les frames.
- **Boucle sans couture** : la dernière frame n'est pas une copie de la première ; on peut
  enchaîner directement la dernière frame et la première pour boucler.

## Jouer une animation

Chaque frame dure `1 / fps` seconde. Exemple en Python :

```python
import json

with open("Human.json", encoding="utf-8") as f:
    sheet = json.load(f)

animations = {(a["name"], a["orientation"]): a for a in sheet["animations"]}


def current_frame(name: str, orientation: str, elapsed: float) -> dict:
    """Frame à afficher après `elapsed` secondes de lecture en boucle."""
    anim = animations[(name, orientation)]
    frames = anim["frames"]
    if anim["fps"] <= 0:          # pose fixe
        return frames[0]
    index = int(elapsed * anim["fps"]) % len(frames)
    return frames[index]


def draw_rect(frame: dict, feet_x: float, feet_y: float) -> tuple:
    """Rectangle source dans l'image, et position du coin haut-gauche à l'écran."""
    source = (frame["x"], frame["y"], frame["width"], frame["height"])
    position = (feet_x - frame["origin"]["x"], feet_y - frame["origin"]["y"])
    return source, position
```

Pour choisir l'orientation à partir d'une direction de déplacement à l'écran `(dx, dy)`, avec
y vers le bas :

```python
import math

ORDER = ["S", "SE", "E", "NE", "N", "NO", "O", "SO"]


def orientation_for(dx: float, dy: float) -> str:
    angle = math.degrees(math.atan2(dx, dy)) % 360      # 0 = vers le bas (S), 90 = vers la droite (E)
    return ORDER[round(angle / 45) % 8]
```

Si toutes les orientations n'ont pas été exportées, prenez l'orientation exportée la plus
proche, ou retournez horizontalement `E` pour obtenir `O`. Ce n'est qu'une approximation :
l'éclairage et les détails asymétriques ne correspondront pas.

## Conseils d'intégration

- **Pas d'espace entre les frames** : pour éviter que les pixels d'une frame voisine
  apparaissent sur les bords, échantillonnez la texture avec un filtrage « plus proche
  voisin » ou limitez l'échantillonnage au rectangle de la frame (clamp). Pas de mipmaps sur
  cette texture.
- **Alpha** : le PNG est en alpha **non prémultiplié** (standard PNG). Si votre moteur
  travaille en alpha prémultiplié, convertissez-le au chargement pour éviter des liserés
  sombres.
- **Taille** : `frameHeight` (250 px par défaut) correspond à la hauteur maximale atteinte
  par le personnage sur l'ensemble de l'export, plus une marge de 4 px en haut et en bas.
  Pour un personnage plus grand ou plus petit à l'écran, mettez la frame à l'échelle depuis
  son origine.

## Réglages qui influencent l'export

Ces réglages se font dans **⚙ Config export…** et sont enregistrés pour chaque personnage
dans `Characters/<perso>/spritesheet.json`.

| Réglage | Effet sur les fichiers |
|---|---|
| Largeur de la feuille | `width` de l'image ; les frames passent à la ligne suivante au-delà. |
| Hauteur des frames | `frameHeight` et `height` de chaque frame. |
| Exporter (par animation) | Présence de l'animation dans le JSON. |
| Frames (par animation) | Nombre d'éléments de `frames`, répartis uniformément sur la durée de l'animation. Avec 1, on obtient la pose de départ. |
| Orientations (par animation) | Une entrée par orientation cochée. |

Les skins choisies dans le panneau principal au moment de l'export sont celles qui
apparaissent dans l'image.
