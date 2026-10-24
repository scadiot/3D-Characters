"""État de lecture et calcul de la frame courante (sans Qt)."""
from dataclasses import dataclass

import numpy as np

from viewer.animation import AnimationClip, Retargeter, loop_time
from viewer.gltf_loader import LoadedFile
from viewer.skeleton import Pose, yaw_matrix


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
        self._retargeter: Retargeter | None = None
        self._facing = np.eye(4)  # tourne le perso pour qu'il regarde +Z (vers la caméra)

    @property
    def duration(self) -> float:
        return self.clip.duration if self.clip else 0.0

    def set_model(self, model: LoadedFile | None) -> None:
        self.model = model
        self._facing = yaw_matrix(-model.skeleton.facing_yaw()) if model else np.eye(4)
        self._update_retargeter()

    def set_clip(self, clip: AnimationClip | None) -> None:
        self.clip = clip
        self.time = 0.0
        self._update_retargeter()

    def _update_retargeter(self) -> None:
        if self.model and self.clip:
            self._retargeter = Retargeter(self.model.skeleton, self.clip)
        else:
            self._retargeter = None

    def advance(self, dt: float) -> None:
        if self.playing and self.duration > 0:
            self.time = loop_time(self.time + dt * self.speed, self.duration)

    def seek(self, t: float) -> None:
        self.time = min(max(t, 0.0), self.duration)

    def frame(self) -> FrameData | None:
        if self.model is None:
            return None
        sk = self.model.skeleton
        return self._frame(self._retargeter.pose(self.time) if self._retargeter else sk.rest_pose())

    def _frame(self, pose: Pose) -> FrameData:
        return frame_from_globals(self.model, self._facing @ self.model.skeleton.global_matrices(pose))

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
        allp = skinned_points(self.model, self._frame(self.model.skeleton.rest_pose()))
        return allp.min(axis=0), allp.max(axis=0)


def frame_from_globals(model: LoadedFile, globals_: np.ndarray) -> FrameData:
    return FrameData(globals_, [globals_[s.joints] @ s.inverse_bind for s in model.skins])


def skinned_points(model: LoadedFile, frame: FrameData) -> np.ndarray:
    """Sommets de tous les meshes, déformés par le squelette dans la pose de `frame`.

    Gère les meshes stockés dans un autre repère (cm, Z vers le haut) que le monde.
    """
    points = []
    for m in model.meshes:
        p = np.c_[m.positions.astype(np.float64), np.ones(len(m.positions))]
        if m.skin is None:
            points.append((p @ frame.globals[m.node].T)[:, :3])
            continue
        weighted = m.weights.sum(axis=1) > 0
        mats = np.einsum("vk,vkij->vij", m.weights[weighted], frame.joint_matrices[m.skin][m.joints[weighted]])
        points.append(np.einsum("vij,vj->vi", mats, p[weighted])[:, :3])
    return np.concatenate(points) if points else np.zeros((0, 3))
