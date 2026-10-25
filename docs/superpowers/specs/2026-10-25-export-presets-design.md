# Plusieurs configurations d'export par personnage — Design

Date : 2026-10-25
Statut : validé (brainstorming)
Complète : [2026-10-25-spritesheet-export-design.md](2026-10-25-spritesheet-export-design.md),
[2026-10-25-attachments-design.md](2026-10-25-attachments-design.md)

## Objectif

Enregistrer plusieurs configurations nommées pour un même personnage (ex. « golf » avec
le club, « base » sans), chacune regroupant les réglages d'export de sprite sheet et la
liste des objets attachés.

## Périmètre

Inclus : liste « Config » dans le panneau, création / duplication / renommage /
suppression, migration des anciens `spritesheet.json` et `attachments.json`.

Exclu (YAGNI) : export de toutes les configs en une fois, skins ou réglages de rendu dans
une config.

## Stockage

Un fichier par config : `Characters/<Perso>/exports/<nom>.json`.

```json
{
  "sheetWidth": 1000,
  "frameHeight": 250,
  "animations": [{ "name": "golf swing", "frames": 12, "orientations": ["S", "E"] }],
  "attachments": [{ "object": "golf_club.glb", "bone": "RightHand", "position": [0, 0.08, 0],
                    "rotation": [0, 0, 90], "scale": 1.0, "enabled": true }]
}
```

Les clés et leur validation sont celles de `spritesheet.json` (cf. design export) et de
`attachments.json` (cf. design objets attachés).

- Nom de config = nom du fichier sans `.json`. Refusés : nom vide (après suppression des
  espaces de bord), caractères `<>:"/\|?*`, nom finissant par un point, nom déjà pris
  (casse ignorée, sauf le nom actuel lors d'un renommage).
- Liste triée sans tenir compte de la casse.
- Fichier illisible : réglages par défaut + message dans la barre d'état.

### Migration

Si `exports/` ne contient aucun `.json`, la liste propose une seule config « défaut »
dont le contenu est lu dans les anciens `spritesheet.json` et `attachments.json` (s'ils
existent). Le premier enregistrement écrit `exports/défaut.json` ; créer ou dupliquer
une config l'écrit aussi d'abord, pour qu'elle ne disparaisse pas de la liste. Les anciens fichiers ne
sont ni modifiés ni supprimés, et ne sont plus lus dès qu'une config existe dans `exports/`.

## Interface

- Sous « Personnage » : liste « Config » et boutons « Nouvelle », « Dupliquer »,
  « Renommer », « Supprimer » (actifs si le personnage est skinné).
  - Nouvelle : nom demandé, réglages par défaut, aucun objet.
  - Dupliquer : nom demandé (proposé : `<config> copie`), copie de la config courante.
  - Renommer : renomme le fichier (ou écrit la config « défaut » migrée sous le nouveau nom).
  - Supprimer : après confirmation ; la liste revient à la config suivante (ou à « défaut »
    migrée s'il n'en reste aucune).
  - Nom refusé : message et nouvelle saisie.
- La config sélectionnée pilote : objets attachés affichés, « ⚙ Config export… » et
  « 🔧 Objets attachés… » (lecture/écriture de son fichier), « Exporter sprite sheet… »
  (nom proposé `<Perso>_<config>.png`).
- Enregistrer la partie export relit le fichier et ne remplace que les clés d'export ;
  enregistrer les objets ne remplace que `attachments`.
- Dernière config choisie mémorisée par personnage (QSettings, clé `presets` : JSON
  `{personnage: config}`).

## Modules

- `viewer/sprites/config.py` : `config_from_dict` / `config_to_dict` extraits de
  `load_config` / `save_config`.
- `viewer/attachments.py` : `attachments_from_data` / `attachments_to_data` extraits de
  `load_attachments` / `save_attachments`.
- `viewer/presets.py` (sans Qt) : `Preset(export, attachments)`, `list_presets(dir)`,
  `load_preset(dir, name)`, `save_preset(dir, name, preset)`, `rename_preset`,
  `delete_preset`, `check_name(name, existing, current=None)`.
- `main_window` : liste et boutons, chemin de la config courante à la place de
  `spritesheet.json` / `attachments.json`.

## Tests

Aller-retour des deux sections ; migration (anciens fichiers lus, ignorés dès qu'un
preset existe) ; noms invalides / en double / renommage sur soi-même ; liste triée ;
renommage et suppression ; fichier illisible.
