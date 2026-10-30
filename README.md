# 3D Characters Viewer

Outil de bureau pour visualiser des personnages 3D riggés sur le squelette **Mixamo**, leur
appliquer des animations, des skins et des objets attachés, puis **exporter des sprite sheets
2D** (PNG + JSON) prêtes à être jouées dans un moteur de jeu.

Écrit en Python avec PySide6 (interface), moderngl (rendu OpenGL 3.3) et pygltflib (lecture
des `.glb`).

## Sommaire

- [Installation](#installation)
- [Organisation des données](#organisation-des-données)
- [Utilisation](#utilisation)
- [Fonctionnement](#fonctionnement)
- [Générateurs de modèles](#générateurs-de-modèles)
- [Développement](#développement)

## Installation

Prérequis : Python 3.11 ou plus récent, et une carte graphique compatible OpenGL 3.3.

```sh
make install   # crée .venv et installe le paquet en mode éditable, avec pytest
make run       # lance le viewer
```

Sans `make` :

```sh
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e .[dev]
.venv/Scripts/python.exe -m viewer.main
```

Une fois installé, la commande `character-viewer` lance aussi l'application.

## Organisation des données

Le viewer travaille sur un **dossier racine** choisi via le menu **Dossier racine…** (il est
mémorisé d'une session à l'autre). Ce dossier doit avoir la structure suivante :

```
<racine>/
├── Characters/
│   └── Human/
│       ├── Human.glb                 modèle riggé (sinon, le premier .glb du dossier)
│       ├── skins/
│       │   ├── rouge.png             skin proposée pour tous les matériaux
│       │   ├── body/                 skins du seul matériau « body »
│       │   │   └── sport.png
│       │   └── face/
│       │       └── sport.png
│       └── exports/
│           └── défaut.json           configs du personnage (export + objets affichés)
├── Animations/
│   ├── idle.glb                      une animation par fichier…
│   └── pack.glb                      …ou plusieurs clips (listés « pack / Clip »)
├── Objects/
│   ├── golf_club.glb                 objet attachable à un bone
│   └── golf_club.json                son placement, commun à tous les personnages
└── Exports/                          sprite sheets exportées (PNG + JSON)
```

Points à connaître :

- Seuls les fichiers **`.glb`** sont lus. Les `.fbx` doivent être convertis au préalable
  (par exemple avec Blender).
- Les animations sont **partagées** par tous les personnages : n'importe quel clip de
  `Animations/` peut être joué sur n'importe quel personnage au squelette Mixamo.
- Le nom d'un sous-dossier de `skins/` doit correspondre au nom d'un **matériau** du modèle
  (casse ignorée). Un dossier qui ne correspond à aucun matériau est signalé dans la barre
  d'état.
- Le dossier `sample/` du dépôt contient un jeu de données d'exemple. Ses fichiers binaires
  (`.glb`, `.fbx`, `.png`) sont versionnés avec **Git LFS** : installer
  [Git LFS](https://git-lfs.com) avant de cloner, ou lancer `git lfs pull` après coup.

## Utilisation

### La fenêtre principale

Le panneau de gauche regroupe, de haut en bas :

| Contrôle | Rôle |
|---|---|
| **Personnage** | Personnage de `Characters/` à afficher. |
| **Config** + Nouvelle / Dupliquer / Renommer / Supprimer | Configuration nommée du personnage : réglages d'export et objets affichés. |
| **Skin · <matériau>** | Une liste par matériau ayant des skins proposées ; « défaut » garde la texture du `.glb`. |
| **Animation** | Clip joué ; « aucune (T-pose) » affiche la pose de repos. ⚠ signale un fichier illisible. |
| ⏸ / ▶ et **Vitesse** | Lecture / pause, vitesse de 0,25× à 2×. |
| **Exporter sprite sheet…** | Rend et enregistre la sprite sheet de la config courante. |
| **⚙ Config export…** | Choix des animations, frames, plages de temps et orientations à exporter. |
| **👁 Visualiser un export…** | Ouvre et rejoue une sprite sheet déjà exportée. |
| **🎨 Paramètres de rendu…** | Ombrage standard ou cel shading, contour, lumière. |
| **🔧 Objets attachés…** | Objets accrochés aux bones et leur placement. |
| **Afficher bones** | Superpose le squelette au modèle. |
| **Vérification** | État du squelette par rapport à la convention Mixamo ; « détails… » liste les problèmes. |

Sous la vue 3D, la **timeline** permet de se déplacer dans l'animation (la lecture est
suspendue pendant qu'on la fait glisser).

Le personnage, l'animation, les skins, la config choisie et les paramètres de rendu sont
mémorisés et restaurés au lancement suivant.

### Navigation dans la vue 3D

| Action | Effet |
|---|---|
| Clic gauche + glisser | Tourner autour du personnage |
| Clic milieu + glisser | Déplacer la vue |
| Molette | Zoomer |
| Double-clic ou touche `F` | Recadrer sur le personnage |

### Configs

Chaque personnage peut avoir plusieurs configs (par exemple « défaut » et « golf »), stockées
dans `Characters/<perso>/exports/<nom>.json`. Une config contient :

- la configuration d'export de sprite sheet ;
- la liste des objets attachés affichés.

Le placement d'un objet, lui, n'appartient pas à la config : il est propre à l'objet (voir
plus bas). Un personnage sans aucune config utilise « défaut », reprise des anciens fichiers
`spritesheet.json` et `attachments.json` s'ils existent.

### Objets attachés

**🔧 Objets attachés…** liste les `.glb` de `Objects/`. On coche ceux à afficher dans la
config courante, puis on règle pour chacun :

- le **bone** porteur (`RightHand` par défaut) ;
- la **position** (mètres) et la **rotation** (degrés, X puis Y puis Z) ;
- l'**échelle**.

Le résultat est visible en direct dans la vue. Le placement est enregistré à côté de l'objet
(`Objects/golf_club.json`) et s'applique à **tous les personnages** : il est exprimé dans un
repère T-pose commun (origine sur le bone, X à gauche du personnage, Y vers le haut, Z devant
lui), puis l'objet suit les rotations du bone.

### Paramètres de rendu

**🎨 Paramètres de rendu…** règle l'ombrage utilisé par la vue **et** par l'export :

- **Rendu** : `standard` ou `cel` (cel shading, par défaut) ;
- cel shading : nombre de **tons**, **adoucissement** entre tons, intensité et largeur du
  **liseré** de lumière sur les bords ;
- **contour** : activation, épaisseur (en pixels de l'image finale) et couleur ;
- **lumière** : luminosité des **ombres**, **direction** (azimut) et **hauteur** (élévation).

### Exporter une sprite sheet

1. Choisir le personnage, la config et les skins voulues : ce sont celles du panneau
   principal au moment de l'export qui apparaissent dans l'image.
2. Ouvrir **⚙ Config export…** et régler :
   - la **largeur de la feuille** et la **hauteur des frames** (px) ;
   - pour chaque animation : **Exporter**, nombre de **Frames** (réparties uniformément sur
     la plage), **Début** / **Fin** de la plage exportée (en secondes), et les
     **orientations** parmi `S`, `SE`, `E`, `NE`, `N`, `NO`, `O`, `SO`.
3. Cliquer sur **Exporter sprite sheet…** et choisir le fichier (par défaut
   `Exports/<perso>_<config>.png`).

L'export produit `<nom>.png` et `<nom>.json` côte à côte. Le format complet du JSON, les
garanties (échelle commune, ligne de sol fixe, animation sur place, boucle sans couture) et
des exemples de lecture en Python sont décrits dans
[docs/spritesheet-format.md](docs/spritesheet-format.md).

### Visualiser un export

**👁 Visualiser un export…** liste les exports de `Exports/` avec une vignette (**Parcourir…**
pour en ouvrir un ailleurs). La seconde fenêtre rejoue chaque animation dans toutes ses
orientations, avec lecture image par image (|◀ ▶|), réglage de vitesse et affichage optionnel
des **cadres et origines** de chaque frame : de quoi vérifier un export tel qu'un moteur de
jeu le lira.

## Fonctionnement

### Vue d'ensemble

```
Dossier racine ──scan──▶ Library (personnages, skins, animations)
                              │
           .glb ──gltf_loader──▶ LoadedFile (meshes, squelette, matériaux, clips)
                              │
   Objects/*.glb ──attachments──▶ modèle composé (personnage + objets sur des sockets)
                              │
      clip ──Retargeter──▶ pose ──Player──▶ matrices des bones
                                               │
                              ┌────────────────┴────────────────┐
                        Renderer (vue 3D)              SpriteRenderer (export)
                         caméra perspective          caméra orthographique de face
```

### Modules

| Module | Rôle |
|---|---|
| [viewer/library.py](viewer/library.py) | Découverte des personnages, skins et animations sous le dossier racine. |
| [viewer/gltf_loader.py](viewer/gltf_loader.py) | Lecture des `.glb` : meshes skinnés, squelette, matériaux, textures, clips. |
| [viewer/mixamo.py](viewer/mixamo.py) | Convention de nommage Mixamo (préfixe `mixamorig:` retiré) et vérification du squelette. |
| [viewer/skeleton.py](viewer/skeleton.py), [viewer/animation.py](viewer/animation.py) | Squelette, échantillonnage des clips et transfert d'animation entre rigs. |
| [viewer/player.py](viewer/player.py) | Lecture d'un clip dans le temps et calcul des matrices de skinning. |
| [viewer/attachments.py](viewer/attachments.py) | Placement des objets et composition du modèle avec ses objets. |
| [viewer/presets.py](viewer/presets.py) | Configs nommées par personnage, migration des anciens fichiers. |
| [viewer/render_settings.py](viewer/render_settings.py), [viewer/renderer.py](viewer/renderer.py) | Paramètres d'ombrage et rendu moderngl (standard / cel shading, contour, grille, bones). |
| [viewer/sprites/](viewer/sprites/) | Configuration d'export, rendu hors écran, mise en page et écriture PNG + JSON. |
| [viewer/ui/](viewer/ui/) | Fenêtre principale et dialogues Qt. |

### Transfert d'animation

Les bones sont appariés par **nom canonique** Mixamo. Pour chaque bone, la variation de
rotation monde du clip par rapport à sa T-pose est appliquée à la T-pose du personnage : les
axes locaux des deux rigs peuvent donc différer (export Blender, etc.) tant que leurs poses de
repos coïncident. Un personnage tourné vers −Z au lieu de +Z est compensé. Le déplacement des
`Hips` est mis à l'échelle de la hauteur du personnage.

Le bloc **Vérification** signale les bones Mixamo essentiels absents et les pistes du clip
sans bone correspondant (avertissements), ainsi que les bones inconnus ou non animés
(informations). Le rendu est limité à 128 bones par skin.

### Export des sprites

Pour chaque animation et orientation cochées :

1. les instants des frames sont répartis uniformément sur la plage [début, fin], sans
   dupliquer la première frame en fin de boucle ;
2. l'animation est jouée **sur place** : seule la composante verticale du déplacement des
   `Hips` est conservée ;
3. une **échelle commune** est calculée sur l'ensemble de l'export, à partir de la hauteur
   maximale atteinte par le personnage, pour qu'il ait la même taille dans toutes les frames ;
4. chaque frame est rendue hors écran avec une caméra orthographique de face, en
   suréchantillonnage ×2, sur fond transparent, avec les paramètres de rendu courants ;
5. chaque frame est rognée au plus près du personnage, puis les frames sont rangées de gauche
   à droite, ligne après ligne, et leur position et leur origine (point au sol) sont écrites
   dans le JSON.

Si une frame est plus large que la feuille, l'export s'arrête en invitant à augmenter la
largeur dans **⚙ Config export…**.

### Où sont enregistrés les réglages

| Réglage | Emplacement |
|---|---|
| Configs d'un personnage | `Characters/<perso>/exports/<nom>.json` |
| Placement d'un objet | `Objects/<objet>.json` |
| Dossier racine, dernière sélection, paramètres de rendu | Réglages Qt de l'utilisateur (`QSettings`, base de registre sous Windows) |

## Générateurs de modèles

Le dossier [tools/](tools/) contient des scripts qui génèrent des personnages **low poly** et
des animations sur le squelette Mixamo, sans logiciel 3D :

| Script | Produit |
|---|---|
| [tools/build_human.py](tools/build_human.py) | `Characters/Human/Human.glb`, ses skins (`skins/body`, `skins/face`) et ses gabarits d'UV (`uv/`) |
| [tools/build_child.py](tools/build_child.py) | `Characters/Child/Child.glb` : l'humain aux proportions d'un enfant |
| [tools/build_robot.py](tools/build_robot.py) | `Characters/Robot/Robot.glb` : pièces rigides, chacune liée à un seul bone |
| [tools/build_star.py](tools/build_star.py) | `Animations/star_pose.glb` : pose statique bras et jambes en étoile, dérivée de `TPose.glb` |
| [tools/build_talk.py](tools/build_talk.py) | Animation `talk.glb` : gestes de parole superposés à la respiration de `idle.glb` |

Les briques communes (squelette, lofts, prismes, dépliage UV et atlas) sont dans
[tools/lowpoly.py](tools/lowpoly.py). Les gabarits de `uv/` servent de base pour peindre de
nouvelles skins.

```sh
make models                                       # régénère tous les modèles dans sample/
.venv/Scripts/python.exe tools/build_human.py autre/chemin/Human.glb   # sortie personnalisée
```

## Développement

```sh
make test      # lance la suite pytest (tests/)
```

Le format des sprite sheets est documenté dans
[docs/spritesheet-format.md](docs/spritesheet-format.md) ; les spécifications et plans de
conception des fonctionnalités sont dans [docs/superpowers/](docs/superpowers/).
