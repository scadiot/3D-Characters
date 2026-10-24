"""État de lecture et calcul de la frame courante (sans Qt)."""
from dataclasses import dataclass

import numpy as np

from viewer.animation import AnimationClip, apply_clip, hips_ratio, loop_time
from viewer.gltf_loader import LoadedFile


@dataclass
class FrameData:
    globals: np.ndarray               # (N, 4, 4) par nœud
    joint_matrices: list[np.ndarray]  # par skin : (J, 4, 4)


class Player:
    def __init__(self):
        self.model: LoadedFile | None = None
        self.clip: AnimationClip | None = None
        self.time = 0.0
        self.speed = 1.0
        self.playing = True
        self._ratio = 1.0

    @property
    def duration(self) -> float:
        return self.clip.duration if self.clip else 0.0

    def set_model(self, model: LoadedFile | None) -> None:
        self.model = model
        self._update_ratio()

    def set_clip(self, clip: AnimationClip | None) -> None:
        self.clip = clip
        self.time = 0.0
        self._update_ratio()

    def _update_ratio(self) -> None:
        if self.model and self.clip:
            self._ratio = hips_ratio(self.model.skeleton, self.clip)
        else:
            self._ratio = 1.0

    def advance(self, dt: float) -> None:
        if self.playing and self.duration > 0:
            self.time = loop_time(self.time + dt * self.speed, self.duration)

    def seek(self, t: float) -> None:
        self.time = min(max(t, 0.0), self.duration)

    def frame(self) -> FrameData | None:
        if self.model is None:
            return None
        sk = self.model.skeleton
        pose = sk.rest_pose()
        if self.clip is not None:
            apply_clip(self.clip, sk, pose, self.time, self._ratio)
        g = sk.global_matrices(pose)
        return FrameData(g, [g[s.joints] @ s.inverse_bind for s in self.model.skins])

    def bone_segments(self, frame: FrameData | None) -> np.ndarray:
        if self.model is None or frame is None or not self.model.skins:
            return np.zeros((0, 2, 3), np.float32)
        joints = self.model.skins[0].joints
        joint_set = set(joints.tolist())
        parents = self.model.skeleton.parents
        segs = [(frame.globals[parents[j]][:3, 3], frame.globals[j][:3, 3])
                for j in joints if parents[j] in joint_set]
        return np.array(segs, np.float32).reshape(-1, 2, 3)

    def bounds(self) -> tuple[np.ndarray, np.ndarray]:
        if self.model is None or not self.model.meshes:
            return np.array([-1.0, 0, -1]), np.array([1.0, 2, 1])
        g = self.model.skeleton.global_matrices(self.model.skeleton.rest_pose())
        points = []
        for m in self.model.meshes:
            p = m.positions.astype(np.float64)
            if m.skin is None:
                p = p @ g[m.node][:3, :3].T + g[m.node][:3, 3]
            points.append(p)
        allp = np.concatenate(points)
        return allp.min(axis=0), allp.max(axis=0)
