"""The issue space.

The two-party model put every voter and party on a single line from -1 to +1 and
measured preference as absolute difference.  Here a position is a point in a
``d``-dimensional space and distance is a weighted norm, so "how far is this
voter from this party" becomes a question with an answer that depends on which
issues the voter cares about.

Salience is the weighting.  It can be global (everyone weighs the economy twice
as heavily as the environment) or per-voter (some people are single-issue
voters), which is the point of separating it from the positions themselves: two
voters at the same point in issue space can rank the same two parties
differently.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

METRICS = ("euclidean", "cityblock", "chebyshev")


@dataclass(frozen=True)
class IssueSpace:
    """A ``d``-dimensional space of political positions, each on ``[-1, 1]``.

    ``salience`` weights the dimensions when distances are computed.  It is
    normalized to mean 1 so that changing the number of dimensions does not
    silently rescale every distance in the model -- a two-dimensional space with
    default salience produces distances on the same scale as a one-dimensional
    one, which keeps thresholds like ``persuadable_band`` meaningful across
    configurations.
    """

    dimensions: int = 1
    names: tuple[str, ...] = ()
    salience: tuple[float, ...] = ()
    metric: str = "euclidean"

    def __post_init__(self) -> None:
        if self.dimensions < 1:
            raise ValueError(f"dimensions must be at least 1, got {self.dimensions}")
        if self.metric not in METRICS:
            raise ValueError(f"metric must be one of {METRICS}, got {self.metric!r}")

        names = self.names or tuple(self._default_name(i) for i in range(self.dimensions))
        if len(names) != self.dimensions:
            raise ValueError(
                f"got {len(names)} dimension name(s) for {self.dimensions} dimension(s)"
            )
        object.__setattr__(self, "names", tuple(names))

        weights = np.array(self.salience or (1.0,) * self.dimensions, dtype=float)
        if len(weights) != self.dimensions:
            raise ValueError(
                f"got {len(weights)} salience weight(s) for {self.dimensions} dimension(s)"
            )
        if np.any(weights < 0):
            raise ValueError("salience weights must be non-negative")
        if weights.sum() <= 0:
            raise ValueError("at least one dimension must have non-zero salience")
        object.__setattr__(self, "salience", tuple(weights / weights.mean()))

    @staticmethod
    def _default_name(index: int) -> str:
        return "left-right" if index == 0 else f"issue-{index + 1}"

    @property
    def weights(self) -> np.ndarray:
        return np.asarray(self.salience, dtype=float)

    @property
    def is_one_dimensional(self) -> bool:
        return self.dimensions == 1

    def distances(
        self,
        positions: np.ndarray,
        targets: np.ndarray,
        salience: np.ndarray | None = None,
    ) -> np.ndarray:
        """Distance from each position to each target.

        ``positions`` is ``(n, d)``, ``targets`` is ``(p, d)``, the result is
        ``(n, p)``.  ``salience`` may be ``(d,)`` for a shared weighting or
        ``(n, d)`` to give every voter their own.
        """
        positions = np.atleast_2d(positions)
        targets = np.atleast_2d(targets)

        weights = self.weights if salience is None else np.asarray(salience, dtype=float)
        if weights.ndim == 1:
            weights = weights[None, None, :]
        else:
            weights = weights[:, None, :]

        delta = np.abs(positions[:, None, :] - targets[None, :, :])

        if self.metric == "cityblock":
            return np.einsum("npd,npd->np", delta, np.broadcast_to(weights, delta.shape))
        if self.metric == "chebyshev":
            return (delta * weights).max(axis=2)
        return np.sqrt(np.einsum("npd,npd->np", delta**2, np.broadcast_to(weights, delta.shape)))

    def clip(self, positions: np.ndarray) -> np.ndarray:
        return np.clip(positions, -1.0, 1.0)

    def centroid(self, positions: np.ndarray, mask: np.ndarray | None = None) -> np.ndarray:
        """Mean position, or the origin when the selection is empty."""
        if mask is not None:
            positions = positions[mask]
        if len(positions) == 0:
            return np.zeros(self.dimensions)
        return positions.mean(axis=0)

    def dispersion(self, positions: np.ndarray) -> float:
        """Spread of a cloud of positions: the salience-weighted RMS distance to its centre.

        Reduces to the standard deviation in one dimension, so it reads the same
        way as ``ideology_sd`` did in the two-party model.
        """
        if len(positions) == 0:
            return 0.0
        centre = positions.mean(axis=0, keepdims=True)
        return float(np.sqrt((self.distances(positions, centre)[:, 0] ** 2).mean()))

    def describe(self) -> str:
        parts = [
            f"{name} (salience {weight:.2f})"
            for name, weight in zip(self.names, self.salience)
        ]
        return f"{self.dimensions}-D {self.metric}: " + ", ".join(parts)


#: The space the two-party model lived in, for configurations that want it.
LINE = IssueSpace(dimensions=1)
