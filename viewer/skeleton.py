"""Hiérarchie de nœuds et calcul des matrices globales."""
from dataclasses import dataclass, field

import numpy as np

from viewer.mathutil import trs_to_mat4


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
