# Objets attachés aux bones — Design

Date : 2026-10-25
Statut : validé (brainstorming)
Complète : [2026-10-24-character-viewer-design.md](2026-10-24-character-viewer-design.md),
[2026-10-25-spritesheet-export-design.md](2026-10-25-spritesheet-export-design.md)

## Objectif

Attacher des objets 3D (ex. `Objects/golf_club.glb`) à un bone d'un personnage, avec une
position, une rotation et une échelle précises, visibles dans la vue 3D et dans les
sprite sheets exportées.

## Périmètre

Inclus :
- Objets pris dans `<racine>/Objects/*.glb`.
- Plusieurs objets par personnage, configuration enregistrée par personnage.
- Dialogue « 🔧 Objets attachés… » avec champs numériques et aperçu en direct.
- Objets rendus dans l'export de sprites et pris en compte dans le cadrage.

Exclu (YAGNI) : gizmo de manipulation à la souris, objets différents selon l'animation,
objets animés (les clips d'un .glb d'objet sont ignorés), skinning des objets.

## Fichier de configuration

`Characters/<Perso>/attachments.json` (à côté de `spritesheet.json`) :

```json
{
  "attachments": [
    {
      "object": "golf_club.glb",
      "bone": "RightHand",
      "position": [0.0, 0.08, 0.02],
      "rotation": [0.0, 0.0, 90.0],
      "scale": 1.0,
      "enabled": true
    }
  ]
}
```

- `object` : chemin relatif au dossier `Objects/` (séparateur `/`).
- `bone` : nom canonique (normalisé Mixamo, cf. `viewer/mixamo.py`), pour qu'une config
  reste valable entre variantes de rigs (`mixamorig:RightHand`, `mixamorig1:RightHand`…).
- `position` : en mètres, dans le repère local du bone **sans son échelle**.
- `rotation` : degrés, angles d'Euler appliqués dans l'ordre X puis Y puis Z
  (matrice `Rz @ Ry @ Rx`), dans le repère du bone.
- `scale` : facteur uniforme appliqué à l'objet (> 0).
- `enabled` : objet affiché/exporté ou non.

Valeurs absentes ou invalides : valeur par défaut (position/rotation nulles, échelle 1,
actif). Fichier absent : aucun objet. Fichier illisible : aucun objet + message, comme
`load_config` de l'export. Écriture : JSON indenté, UTF-8.

## Géométrie

Pour chaque attachement actif dont l'objet et le bone existent, le squelette composé
reçoit :

1. un nœud **socket** `attach<i>`, enfant du bone, dont la transformation locale vaut
   `S(1/k) @ T(position) @ R(rotation) @ S(scale)`, où `k` est l'échelle globale du bone
   en pose de repos (moyenne des normes des colonnes de sa matrice globale). Comme `S(1/k)`
   est uniforme, cela s'écrit en un seul TRS : `t = position / k`, `r = rotation`,
   `s = scale / k`. Les bones Mixamo en centimètres (échelle 0.01, ex. Police, Soldier)
   donnent ainsi un objet en mètres.
2. tous les nœuds du .glb de l'objet, avec leurs transformations d'origine ; ses racines
   deviennent enfants du socket.

Les meshes de l'objet sont ajoutés au modèle comme meshes rigides (`skin = None`,
`node` réindexé). Un mesh skinné dans un objet est rendu de façon rigide par son nœud.

Conséquences sans code supplémentaire :
- le `Retargeter` laisse en pose de repos les nœuds sans piste, donc le socket suit le
  bone animé ;
- le renderer dessine déjà les meshes rigides avec `frame.globals[m.node]` ;
- `skinned_points`, `Player.bounds()` et les deux passes de l'export incluent l'objet.

Les noms des nœuds greffés sont préfixés (`attach<i>/<nom>`) pour ne jamais être
appariés à une piste d'animation. Les matériaux de l'objet gardent leur nom, mais les
listes de skins de l'interface sont construites à partir des matériaux du personnage
seul (les meshes d'objet sont exclus des remplacements de skin).

Édition en direct : modifier position/rotation/échelle met à jour le TRS de repos du
socket (`rest_t`, `rest_r`, `rest_s`) du squelette composé ; aucun rechargement GPU.
Ajouter, retirer, activer/désactiver un objet ou changer son objet/bone recompose le
modèle et recharge les meshes, sans réinitialiser la caméra ni les skins choisies.

## Modules

### `viewer/attachments.py` (sans Qt)

- `Attachment` (dataclass) : `object`, `bone`, `position`, `rotation`, `scale`, `enabled`.
- `load_attachments(path) -> (list[Attachment], str | None)` et
  `save_attachments(path, attachments)`.
- `scan_objects(root) -> list[Path]` : `.glb` sous `Objects/`, triés.
- `compose(model, attachments, objects) -> Composed` où `objects` associe un nom
  d'objet à son `LoadedFile` ; `Composed` contient le `LoadedFile` composé, l'index du
  socket de chaque attachement retenu et les messages d'erreur.
- `socket_trs(attachment, bone_scale)` : TRS local du socket (utilisé par `compose` et
  pour l'édition en direct).

### `viewer/ui/attachments_dialog.py`

- Liste des attachements (ajouter / supprimer).
- Pour l'attachement sélectionné : objet (liste de `Objects/`), bone (joints du squelette
  du personnage, `RightHand` par défaut s'il existe), position X/Y/Z (m, pas 0.005),
  rotation X/Y/Z (°, pas 1), échelle (pas 0.05), case « actif ».
- Signal `changed(list[Attachment])` émis à chaque modification pour l'aperçu.
- OK : enregistre ; Annuler : la fenêtre principale restaure la config d'avant.

### Modifications

- `main_window` : bouton « 🔧 Objets attachés… » (actif si le personnage est skinné) ;
  au changement de personnage, chargement de `attachments.json`, des objets (cache par
  chemin) et composition ; messages d'erreur dans la barre d'état. `Player.model`
  reçoit le modèle composé ; validation Mixamo et listes de skins utilisent le modèle
  d'origine.
- `GLView` : `attachments_changed()` qui recharge les meshes sans `clear_skins()` ni
  `frame_all()`.
- `Renderer.set_model` : inchangé ; le remplacement de skin ignore les meshes marqués
  comme objets.

## Erreurs

Entrée ignorée (et conservée dans le JSON), message dans la barre d'état :
- objet introuvable dans `Objects/` ou .glb illisible ;
- bone absent du squelette du personnage.

## Tests

- `socket_trs` : bone d'échelle 1 et bone d'échelle 0.01 → la matrice monde de l'objet
  vaut la matrice du bone sans échelle × `T(position) R(rotation) S(scale)`.
- `compose` : nombre de nœuds/meshes, parenté, noms préfixés, index de nœud des meshes
  réindexés ; attachement désactivé, objet manquant et bone manquant ignorés avec message.
- L'objet suit le bone pendant une animation (Retargeter) et `Player.bounds()` l'inclut.
- Aller-retour `save_attachments` / `load_attachments`, valeurs par défaut, fichier
  absent ou invalide.
