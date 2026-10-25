# Objets attachés aux bones — Plan d'implémentation

Spec : [2026-10-25-attachments-design.md](../specs/2026-10-25-attachments-design.md)

TDD sur tout ce qui est indépendant de Qt/OpenGL ; dialogue et vue vérifiés par un script
de fumée hors écran sur `sample/`.

## Tâche 1 — `viewer/attachments.py` : config

- `Attachment(object, bone="RightHand", position=(0,0,0), rotation=(0,0,0), scale=1.0, enabled=True)`.
- `load_attachments(path) -> (list[Attachment], str | None)` : fichier absent → `[]` ;
  entrées sans `object` ignorées ; valeurs invalides → défaut ; JSON illisible → `[]` + message.
- `save_attachments(path, attachments)` : JSON indenté, UTF-8.
- `scan_objects(root) -> list[str]` : `.glb` sous `root/Objects`, chemins relatifs `/`.
- Tests : aller-retour, défauts, fichier absent, fichier invalide, scan.

## Tâche 2 — `viewer/attachments.py` : composition

- `euler_quat(rotation)` : `Rz @ Ry @ Rx` en degrés → quaternion xyzw.
- `socket_trs(attachment, bone_scale) -> (t, r, s)`.
- `Socket(attachment, node, bone_scale)` ; `Composed(model, sockets, messages)`.
- `compose(model, attachments, objects: dict[str, LoadedFile]) -> Composed` : nouveau
  `Skeleton` (nœuds du perso + socket + nœuds de l'objet préfixés `attach<i>/`), meshes
  de l'objet ajoutés avec `node` décalé, `skin=None`, `material=None` (hors skins).
- `apply_offset(model, socket, attachment)` : met à jour le TRS de repos du socket.
- `structure_key(attachments)` : (objet, bone, actif) par entrée, pour savoir s'il faut
  recomposer ou seulement déplacer.
- Tests : matrice monde objet = bone sans échelle × T R S (bone à 0.01), noms/parents,
  ignorés avec message (désactivé, objet manquant, bone manquant), suivi pendant une
  animation, `Player.bounds()` inclut l'objet, `apply_offset`.

## Tâche 3 — Interface

- `viewer/ui/attachments_dialog.py` : liste + éditeur, signal `changed(list)`, Annuler
  réémet la config initiale.
- `GLView.attachments_changed()` : recharge les meshes sans toucher caméra ni skins.
- `main_window` : bouton « 🔧 Objets attachés… », cache des objets, composition au
  changement de personnage, aperçu (recomposition seulement si `structure_key` change),
  enregistrement dans `attachments.json`.
- Fumée : Human + golf_club sur RightHand, rendu hors écran d'une frame via
  `SpriteRenderer` et export d'une petite sprite sheet.
