"""Hiérarchie de nœuds et calcul des matrices globales."""
from dataclasses import dataclass, field

import numpy as np

from viewer.mathutil import trs_to_mat4

_LEFT_RIGHT = (("LeftUpLeg", "RightUpLeg"), ("LeftArm", "RightArm"), ("LeftShoulder", "RightShoulder"))


@dataclass
class Pose:
    t: np.ndarray  # (N, 3)
    r: np.ndarray  # (N, 4) xyzw
    s: np.ndarray  # (N, 3)


@dataclass
class Skeleton:
    names: list[str]       # canoniques
    raw_names: list[str]
    parents: np.ndarray    # (N,) int, -1 = racine
    rest_t: np.ndarray
    rest_r: np.ndarray
    rest_s: np.ndarray
    order: list[int] = field(init=False)
    _index: dict[str, int] = field(init=False, repr=False)

    def __post_init__(self):
        self._index = {}
        for i, name in enumerate(self.names):
            self._index.setdefault(name, i)
        self.order = _parents_first(self.parents)

    def index(self, name: str) -> int | None:
        return self._index.get(name)

    def rest_pose(self) -> Pose:
        return Pose(self.rest_t.copy(), self.rest_r.copy(), self.rest_s.copy())

    def global_matrices(self, pose: Pose) -> np.ndarray:
        local = trs_to_mat4(pose.t, pose.r, pose.s)
        result = np.empty_like(local)
        for i in self.order:
            p = self.parents[i]
            result[i] = local[i] if p < 0 else result[p] @ local[i]
        return result

    def facing_yaw(self) -> float:
        """Angle autour de Y entre +Z et la direction vers laquelle regarde le perso au repos."""
        g = self.global_matrices(self.rest_pose())
        left = np.zeros(3)
        for left_name, right_name in _LEFT_RIGHT:
            i, j = self.index(left_name), self.index(right_name)
            if i is not None and j is not None:
                left += g[i][:3, 3] - g[j][:3, 3]
        forward = np.cross(left, [0.0, 1.0, 0.0])
        if np.hypot(forward[0], forward[2]) < 1e-8:
            return 0.0
        return float(np.arctan2(forward[0], forward[2]))


def yaw_matrix(angle: float) -> np.ndarray:
    """Rotation 4x4 autour de Y."""
    c, s = np.cos(angle), np.sin(angle)
    return np.array([[c, 0, s, 0], [0, 1, 0, 0], [-s, 0, c, 0], [0, 0, 0, 1.0]])


def _parents_first(parents: np.ndarray) -> list[int]:
    order, done = [], set()

    def visit(i: int) -> None:
        if i in done:
            return
        if parents[i] >= 0:
            visit(int(parents[i]))
        done.add(i)
        order.append(i)

    for i in range(len(parents)):
        visit(i)
    return order
