"""The voter social network.

NetLogo builds this with sequential rejection sampling: propose two voters, reject
the pair if they are the same voter or already linked, then accept with a
probability that falls with ideological distance when ``homophily`` is high.  The
port keeps that loop sequential.  Batching the proposals would change what
"already linked" means mid-loop, and the network is built once per run, so
fidelity is worth more here than vectorization.
"""

from __future__ import annotations

import numpy as np

# Random draws are pulled in chunks rather than one at a time.  This consumes the
# same distributions in the same order, it just amortizes the per-call overhead of
# the generator across many loop iterations.
_CHUNK = 8192


class Network:
    """An undirected graph stored as a symmetric edge list.

    ``src``/``dst`` contain each edge twice (once per direction), which makes
    neighbour aggregates a single ``np.bincount`` rather than a loop.
    """

    __slots__ = ("n", "edges", "src", "dst", "degree")

    def __init__(self, n: int, edges: np.ndarray | None = None):
        self.n = n
        if edges is None or len(edges) == 0:
            self.edges = np.empty((0, 2), dtype=np.int64)
        else:
            self.edges = np.asarray(edges, dtype=np.int64).reshape(-1, 2)

        a = self.edges[:, 0]
        b = self.edges[:, 1]
        self.src = np.concatenate([a, b])
        self.dst = np.concatenate([b, a])
        self.degree = np.bincount(self.src, minlength=n).astype(np.int64)

    def __len__(self) -> int:
        return len(self.edges)

    @property
    def has_neighbors(self) -> np.ndarray:
        return self.degree > 0

    @property
    def mean_degree(self) -> float:
        return float(self.degree.mean()) if self.n else 0.0

    def neighbor_sum(self, values: np.ndarray) -> np.ndarray:
        """Sum of ``values`` over each voter's neighbours."""
        if len(self.edges) == 0:
            return np.zeros(self.n, dtype=np.float64)
        return np.bincount(
            self.src, weights=values[self.dst].astype(np.float64), minlength=self.n
        )

    def neighbor_mean(self, values: np.ndarray, fallback: np.ndarray) -> np.ndarray:
        """Mean of ``values`` over neighbours, falling back where there are none.

        NetLogo guards this with ``if any? link-neighbors``; isolated voters simply
        keep their own value.  ``fallback`` supplies that per-voter default.
        """
        result = np.asarray(fallback, dtype=np.float64).copy()
        if len(self.edges) == 0:
            return result
        linked = self.has_neighbors
        totals = self.neighbor_sum(values)
        result[linked] = totals[linked] / self.degree[linked]
        return result

    def neighbor_fraction(
        self, numerator_mask: np.ndarray, denominator_mask: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray]:
        """Fraction of neighbours in ``numerator_mask`` among those in ``denominator_mask``.

        Returns ``(fraction, valid)``.  ``valid`` is False for voters with no
        neighbour satisfying ``denominator_mask``, where the fraction is undefined
        and NetLogo's ``if any? active-neighbors`` guard suppresses the rule.
        """
        counts = self.neighbor_sum(denominator_mask.astype(np.float64))
        hits = self.neighbor_sum(
            (numerator_mask & denominator_mask).astype(np.float64)
        )
        valid = counts > 0
        fraction = np.zeros(self.n, dtype=np.float64)
        np.divide(hits, counts, out=fraction, where=valid)
        return fraction, valid


def build_network(
    rng: np.random.Generator,
    ideology: np.ndarray,
    network_degree: float,
    homophily: float,
) -> Network:
    """Port of NetLogo's ``build-network``.

    Acceptance probability for a candidate pair is
    ``(1 - homophily) + homophily * (1 - |Ia - Ib| / 2)``, so at ``homophily = 0``
    every proposed pair is accepted and at ``homophily = 1`` acceptance falls
    linearly with ideological distance.
    """
    n = len(ideology)
    if n < 2 or network_degree <= 0:
        return Network(n)

    # NetLogo: round (count voters * network-degree / 2).  NetLogo's ROUND is
    # round-half-up, unlike Python's banker's rounding, hence the explicit floor.
    target_links = int(np.floor(n * network_degree / 2 + 0.5))
    if target_links <= 0:
        return Network(n)

    max_attempts = max(1000, target_links * 100)

    edges: list[tuple[int, int]] = []
    seen: set[tuple[int, int]] = set()

    pairs = rng.integers(0, n, size=(_CHUNK, 2))
    floats = rng.random(_CHUNK)
    pair_i = 0
    float_i = 0

    attempts = 0
    while len(edges) < target_links and attempts < max_attempts:
        attempts += 1

        if pair_i >= _CHUNK:
            pairs = rng.integers(0, n, size=(_CHUNK, 2))
            pair_i = 0
        a = int(pairs[pair_i, 0])
        b = int(pairs[pair_i, 1])
        pair_i += 1

        if a == b:
            continue
        key = (a, b) if a < b else (b, a)
        if key in seen:
            continue

        similarity = 1.0 - abs(ideology[a] - ideology[b]) / 2.0
        acceptance = (1.0 - homophily) + homophily * similarity

        if float_i >= _CHUNK:
            floats = rng.random(_CHUNK)
            float_i = 0
        draw = floats[float_i]
        float_i += 1

        if draw < acceptance:
            seen.add(key)
            edges.append(key)

    return Network(n, np.array(edges, dtype=np.int64) if edges else None)
