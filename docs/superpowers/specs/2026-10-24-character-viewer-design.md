# 3D Characters Viewer — Design

Date : 2026-10-24
Statut : validé (brainstorming)

## Objectif

Utilitaire Python de bureau pour visualiser des personnages 3D animés :
choisir un personnage, une variante de skin et une animation, puis l'observer
en le faisant pivoter à la souris. Les squelettes suivent la convention de
nommage Mixamo.

## Périmètre v1

Inclus :
- Bibliothèque de fichiers scannée depuis un dossier racine.
- Formats : glTF binaire (`.glb`) uniquement, modèles et animations.
- Animations dans des fichiers séparés, partagées entre tous les personnages.
- Variantes de skin = remplacement de la texture base color, choisie par matériau.
- Normalisation des préfixes de bones Mixamo + rapport de vérification.
- Caméra orbitale, lecture/pause/vitesse/timeline, affichage optionnel des bones.

Exclu (YAGNI) : retargeting depuis d'autres conventions (Unreal, VRM…),
FBX, rendu PBR, remplacement des autres canaux de texture, édition, export,
mélange (blending) d'animations.

## Choix technique

PySide6 (UI) + moderngl (rendu OpenGL 3.3 core dans un `QOpenGLWidget`)
+ pygltflib (lecture glTF) + numpy (maths) + Pillow (images).
Skinning GPU codé à la main (linear blend skinning, 4 influences par vertex).

Raison : le contrôle total de la correspondance des bones par nom rend la
normalisation/vérification Mixamo naturelle, et Qt offre une UI extensible.

## Structure de la bibliothèque

```
<racine>/
  Characters/
    <perso>/
      <perso>.glb          # le premier .glb du dossier si le nom diffère
      skins/               # optionnel
        <matériau>/        # skins propres à ce matériau glTF
        <variante>.png|.jpg
  Animations/
    <anim>.glb
```

- Une liste de skins par matériau du modèle : « défaut » (texture embarquée) + les images
  de `skins/<matériau>/` + les images posées directement dans `skins/` (communes à tous les
  matériaux). Un matériau sans aucune image proposée n'a pas de liste.
- Le nom de dossier correspond au nom du matériau, casse ignorée, les caractères interdits
  par Windows (`<>:"/\|?*`) remplacés par `_` (ex. `asdf1:Beta` → `asdf1_Beta/`).
- Un sous-dossier ne correspondant à aucun matériau est signalé en barre de statut.
- Liste des animations : « aucune (T-pose) » + chaque clip trouvé. Un GLB contenant
  plusieurs clips donne une entrée par clip, libellée `<fichier> / <clip>`.

## Architecture

```
viewer/
  main.py            # point d'entrée
  library.py         # scan du dossier racine → personnages, skins, animations
  gltf_loader.py     # GLB → Mesh(es) + Skeleton (+ AnimationClip(s))
  mixamo.py          # normalize(name) + validate(skeleton, clip) → rapport
  skeleton.py        # hiérarchie, matrices locales/globales, inverse bind
  animation.py       # AnimationClip : pistes par nom de bone, sample(t)
  renderer.py        # shaders, buffers, textures, dessin mesh/grille/bones
  camera.py          # caméra orbitale (yaw, pitch, distance, cible)
  ui/
    main_window.py   # panneau latéral + vue 3D + timeline
    gl_view.py       # QOpenGLWidget : boucle ~60 fps, souris/clavier
tests/
  data/              # petit GLB skinné de test
```

Règles :
- `gltf_loader`, `mixamo`, `skeleton`, `animation`, `library` ne dépendent ni de Qt
  ni d'OpenGL (testables sans fenêtre).
- Flux à sens unique : UI → loader → animation.sample(t) → skeleton (matrices)
  → renderer. Aucun module cœur ne connaît l'UI.

## Convention Mixamo

`mixamo.normalize(name)` retire le préfixe et renvoie le nom canonique :
`mixamorig:Hips`, `mixamorig1:Hips`, `mixamorig2:Hips`, `mixamorig_Hips`, `Hips` → `Hips`
(regex `^mixamorig\d*[:_]`). Squelette et pistes d'animation sont indexés par ce nom.

`mixamo.validate()` compare à la liste de référence des bones Mixamo standard
(Hips, Spine, Spine1, Spine2, Neck, Head, épaules/bras/avant-bras/mains, doigts,
jambes/pieds/orteils, `HeadTop_End`, etc.) et produit :
- bones Mixamo absents du modèle ;
- pistes d'animation sans bone correspondant dans le modèle ;
- bones du modèle non reconnus (non Mixamo) ;
- bones du modèle non animés par le clip courant.

Les bones de doigts et `*_End` absents sont signalés en info, pas en avertissement
(beaucoup de rigs Mixamo sont exportés sans doigts).

## Application d'une animation sur un modèle

Retargeting en espace monde : chaque clip conserve le squelette de son fichier
(sa pose de repos sert de référence). Les rigs peuvent avoir des axes locaux
différents (ex. export via Blender : Hips tournées de −90° sur X) tant que leurs
poses de repos coïncident en monde (T-pose Mixamo).

- Rotations : pour chaque bone apparié par nom canonique, variation monde
  `D = R_anim(t) · R_anim_reposᵀ`, puis `R_modèle(t) = D · R_modèle_repos`,
  reconvertie en rotation locale à partir du parent déjà calculé. Les bones non
  animés gardent leur rotation locale de repos.
- Translations : ignorées sauf pour `Hips` (les autres bones gardent la
  translation de repos du modèle, ce qui évite les déformations entre
  personnages de proportions différentes).
- Position monde de `Hips` : `repos_modèle + (anim(t) − repos_anim) × ratio`, avec
  `ratio = hauteur monde des Hips au repos du modèle / celle de l'animation`, puis
  exprimée dans l'espace du parent. Ceci gère les écarts d'unités cm/m fréquents
  avec Mixamo.
- Même squelette des deux côtés : résultat identique à une copie des pistes locales.
- Orientation : la direction vers laquelle regarde chaque rig au repos est déduite
  de l'axe gauche → droite (UpLeg, Arm, Shoulder). Les variations source sont
  exprimées dans le repère du modèle (rotation autour de Y de l'écart), et
  l'affichage tourne chaque perso pour qu'il regarde +Z, vers la caméra.
- Cadrage : boîte englobante calculée sur le mesh déformé par le squelette au repos
  (les meshes peuvent être stockés en cm et Z vers le haut).
- Vérification : une piste visant un bone optionnel absent du modèle (doigts, yeux,
  `*_End`) est une info, pas un avertissement.
- Échelles d'animation : ignorées.
- Interpolation : `LINEAR` (lerp pour translation, slerp pour rotation) et `STEP`.
  `CUBICSPLINE` est échantillonné en ne gardant que les valeurs (sans tangentes).
- Lecture en boucle ; durée = max des temps de keyframes du clip.

## Interface

```
┌──────────────────────────────────────────────────────────────┐
│ 3D Characters Viewer                    [Dossier racine…]    │
├────────────────────┬─────────────────────────────────────────┤
│ Personnage  [▾]    │                                         │
│ Skin · mat. [▾] ×N │              (vue 3D)                   │
│ Animation   [▾]    │                                         │
│ ▶ ⏸  Vitesse [1.0x]│                                         │
│ ☐ Afficher bones   │                                         │
│ ⚠ Vérification     │                                         │
│  résumé [détails…] ├─────────────────────────────────────────┤
│                    │ ━━━━━━━━━━●━━━━━━━━━━  0.84 / 1.20 s     │
└────────────────────┴─────────────────────────────────────────┘
```

Vue 3D :
- clic gauche + glisser : rotation orbitale ;
- molette : zoom ;
- clic milieu + glisser : pan ;
- double-clic ou `F` : recadrage sur la boîte englobante du personnage.

Lecture : lecture/pause, vitesse 0.25x–2x, timeline glissable (met en pause pendant le glissement).

Vérification : résumé ✅/⚠ + compteur ; « détails… » ouvre une boîte listant le rapport de `validate()`.

Persistance via `QSettings` : dossier racine, dernier personnage, skin par matériau, animation.

Rendu : fond neutre, grille au sol, une lumière directionnelle + ambiante,
ombrage Lambert sur la texture base color. Bones optionnels dessinés en lignes
par-dessus le mesh (sans test de profondeur).

## Gestion des erreurs

Principe : un fichier défectueux n'arrête jamais l'application.

| Situation | Comportement |
|---|---|
| GLB illisible / corrompu | entrée marquée ⚠ dans la liste, message en barre de statut |
| Modèle sans skin | affiché statique, liste d'animations désactivée |
| Plusieurs meshes skinnés | tous rendus, squelette partagé |
| Pistes vers des bones absents | ignorées, signalées dans le rapport |
| Bones du modèle non animés | restent en pose de repos, signalés en info |
| `skins/` absent ou vide | seule l'option « défaut » est proposée |
| Image de skin illisible | message en barre de statut, retour à « défaut » |
| Résolution de skin différente | aucun traitement (UV normalisées) |
| Jeu `JOINTS_1`/`WEIGHTS_1` présent | ignoré (4 influences max), signalé en info |
| Dossier racine sans `Characters/` ou `Animations/` | listes vides + message explicatif |

## Tests

Unitaires (`pytest`, sans fenêtre) :
- `mixamo.normalize` : tous les préfixes, noms inconnus ; `validate` sur squelettes factices.
- `animation.sample` : t = 0, milieu, fin, bouclage ; lerp/slerp/step.
- `skeleton` : pose de repos × inverse bind = identité.
- Ratio de translation des Hips.
- `library` : scan d'une arborescence factice dans `tmp_path`.
- `gltf_loader` : chargement de `tests/data/` (petit GLB skinné versionné).

Manuel : charger un vrai personnage Mixamo + 2–3 animations ; vérifier rotation,
zoom, pan, recadrage, changement de skin, scrub de la timeline, affichage des bones.

## Dépendances

`PySide6`, `moderngl`, `pygltflib`, `numpy`, `Pillow` ; dev : `pytest`.
Python ≥ 3.11.
