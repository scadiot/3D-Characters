"""Export d'une sprite sheet : échelle commune, rendu des frames, assemblage PNG + JSON."""
import math
from dataclasses import dataclass
from typing import Callable

import numpy as np
from PIL import Image

from viewer.animation import AnimationClip, Retargeter
from viewer.gltf_loader import LoadedFile
from viewer.mathutil import orthographic
from viewer.player import frame_from_globals, skinned_points
from viewer.skeleton import yaw_matrix
from viewer.sprites.config import AnimationExport, ExportConfig
from viewer.sprites.layout import ANGLES, MARGIN, build_json, compute_scale, frame_times, pack, playback_fps
from viewer.sprites.render import SpriteRenderer

SUPERSAMPLING = 2


class ExportCancelled(Exception):
    pass


@dataclass
class ExportJob:
    export: AnimationExport
    clip: AnimationClip


@dataclass
class ExportResult:
    image: Image.Image
    data: dict
    frame_count: int


def export_spritesheet(sprites: SpriteRenderer, model: LoadedFile, jobs: list[ExportJob], config: ExportConfig,
                       image_name: str, progress: Callable[[int, int], bool] | None = None) -> ExportResult:
    """`progress(fait, total)` renvoie False pour annuler (lève ExportCancelled)."""
    sk = model.skeleton
    facing = yaw_matrix(-sk.facing_yaw())
    height = config.frame_height
    plans = []
    for job in jobs:
        start, end = job.export.time_range(job.clip.duration)
        times = [start + t for t in frame_times(end - start, job.export.frames)]
        plans.append((job, Retargeter(sk, job.clip, in_place=True), times))
    total = sum(len(times) * (1 + len(job.export.orientations)) for job, _, times in plans)
    done = 0

    def tick() -> None:
        nonlocal done
        done += 1
        if progress is not None and not progress(done, total):
            raise ExportCancelled()

    # 1er passage : poses et étendue du personnage (la hauteur ne dépend pas de l'orientation).
    poses: list[list[np.ndarray]] = []
    top, bottom, radius = -math.inf, math.inf, 0.0
    for job, retargeter, times in plans:
        globals_list = []
        for t in times:
            g = facing @ sk.global_matrices(retargeter.pose(t))
            pts = skinned_points(model, frame_from_globals(model, g))
            if len(pts):
                top, bottom = max(top, pts[:, 1].max()), min(bottom, pts[:, 1].min())
                radius = max(radius, float(np.hypot(pts[:, 0], pts[:, 2]).max()))
            globals_list.append(g)
            tick()
        poses.append(globals_list)
    if not math.isfinite(top):
        top, bottom = 1.0, 0.0
    settings = sprites.renderer.settings
    margin = MARGIN + (math.ceil(settings.outline_width) if settings.outline else 0)  # le contour déborde
    scale = compute_scale(top, bottom, height, margin)
    ppu = scale.pixels_per_unit

    # Caméra orthographique de face : l'axe du personnage (x = 0) au centre de la frame.
    half_width = math.ceil(radius * ppu) + margin
    width = 2 * half_width
    depth = radius + 1.0
    view_proj = orthographic(-half_width / ppu, half_width / ppu,
                             -(height - scale.ground_y) / ppu, scale.ground_y / ppu, -depth, depth)
    render_size = (width * SUPERSAMPLING, height * SUPERSAMPLING)
    origin_y = round(scale.ground_y)

    # 2e passage : rendu, réduction et rognage de chaque frame.
    sequences, crops, entries = [], [], []
    for (job, _, _), globals_list in zip(plans, poses):
        start, end = job.export.time_range(job.clip.duration)
        for orientation in job.export.orientations:
            turn = yaw_matrix(math.radians(ANGLES[orientation]))
            sequence, images = [], []
            for g in globals_list:
                image = sprites.render(frame_from_globals(model, turn @ g), view_proj, render_size, SUPERSAMPLING)
                image = image.convert("RGBa").resize((width, height), Image.Resampling.LANCZOS).convert("RGBA")
                bbox = image.getchannel("A").getbbox()
                left, right = (bbox[0], bbox[2]) if bbox else (half_width, half_width + 1)
                images.append(image.crop((left, 0, right, height)))
                sequence.append((right - left, half_width - left, origin_y))
                tick()
            sequences.append(sequence)
            crops.append(images)
            entries.append({"name": job.export.name, "orientation": orientation,
                            "fps": playback_fps(end - start, job.export.frames)})

    placed, sheet_height = pack(sequences, config.sheet_width, height)
    sheet = Image.new("RGBA", (config.sheet_width, max(sheet_height, 1)), (0, 0, 0, 0))
    for frames, images, entry in zip(placed, crops, entries):
        for p, image in zip(frames, images):
            sheet.paste(image, (p.x, p.y))
        entry["frames"] = frames
    data = build_json(image_name, config.sheet_width, sheet.height, height, entries)
    return ExportResult(sheet, data, sum(len(f) for f in placed))
