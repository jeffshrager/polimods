"""
================================================================================
 NETWORK -- who talks to whom
================================================================================
When `social_network` is on (see params.py), voters aren't isolated -- each
one is linked to a handful of others, and every election they drift their
ideology toward the average of their neighbours (see
Model.update_voter_states in model.py). This file is entirely about *how
those links get created* and *how to efficiently compute neighbour averages
across thousands of voters at once*.

Two ideas carry the whole file:

1. REPRESENTATION: instead of each voter object holding a list of neighbour
   references (as NetLogo's turtles/links do), the network is stored as one
   big edge list -- two parallel numpy arrays `src` and `dst`, where edge i
   connects voter src[i] to voter dst[i]. Every edge is stored *twice*, once
   in each direction (a<->b becomes both a->b and b->a), which turns "sum
   some value over each voter's neighbours" into a single vectorized
   `np.bincount` call instead of a Python loop over each voter's neighbour
   list.

2. CONSTRUCTION: build_network() below reproduces NetLogo's build-network
   procedure, which proposes random pairs of voters one at a time and
   accepts or rejects each pair based on chance and how similar their
   ideologies are (this is "homophily" -- the tendency to link up with
   people who already agree with you). That proposal loop genuinely has to
   run sequentially (each proposal needs to check "is this pair already
   linked?" against the pairs accepted *so far*), so unlike almost
   everything else in this model, it is NOT vectorized -- see the docstring
   on build_network for why that's the right tradeoff here.
================================================================================
"""

from __future__ import annotations

import numpy as np

# Random numbers are pulled from the generator in batches of this size,
# rather than one value per loop iteration. This is purely a performance
# detail -- np.random.Generator calls have real per-call overhead, so
# grabbing 8192 draws at once and consuming them one at a time amortizes
# that cost across many loop iterations. It does NOT change which random
# numbers get produced or in what order; it's the same stream, just fetched
# in chunks.
_CHUNK = 8192


class Network:
    """An undirected graph over `n` voters, stored as a symmetric edge list.

    "Symmetric" means every edge (a, b) is represented twice: once as
    src[i]=a, dst[i]=b, and again as src[j]=b, dst[j]=a. That redundancy is
    the whole trick that makes neighbour aggregates fast: to sum some
    per-voter array over each voter's neighbours, you just bincount `dst`'s
    values grouped by `src` -- see neighbor_sum below.
    """

    # __slots__ tells Python this class will only ever have exactly these
    # attributes, which saves memory and (slightly) speeds up attribute
    # access -- worthwhile here because a Network is created once per model
    # run and its arrays can be large (one entry per voter or per edge).
    __slots__ = ("n", "edges", "src", "dst", "degree")

    def __init__(self, n: int, edges: np.ndarray | None = None):
        self.n = n  # number of voters, whether or not they have any edges

        if edges is None or len(edges) == 0:
            # No edges at all (e.g. social_network is off): store an empty
            # (0, 2) array so downstream code can still treat `edges` as a
            # normal array rather than special-casing None everywhere.
            self.edges = np.empty((0, 2), dtype=np.int64)
        else:
            self.edges = np.asarray(edges, dtype=np.int64).reshape(-1, 2)

        # Build the symmetric (both-directions) view described above: for
        # each stored edge (a, b), add both a->b and b->a to src/dst.
        a = self.edges[:, 0]
        b = self.edges[:, 1]
        self.src = np.concatenate([a, b])
        self.dst = np.concatenate([b, a])

        # How many neighbours each voter has. bincount(src) counts how many
        # times each voter index appears as a source -- exactly the degree,
        # since every edge contributes one src-entry per endpoint.
        self.degree = np.bincount(self.src, minlength=n).astype(np.int64)

    def __len__(self) -> int:
        """Number of distinct (undirected) edges -- NOT src.size, which
        would double-count since each edge appears twice in src/dst."""
        return len(self.edges)

    @property
    def has_neighbors(self) -> np.ndarray:
        """Boolean array, one entry per voter: True if that voter has at
        least one neighbour."""
        return self.degree > 0

    @property
    def mean_degree(self) -> float:
        return float(self.degree.mean()) if self.n else 0.0

    def neighbor_sum(self, values: np.ndarray) -> np.ndarray:
        """For each voter, sum `values` over that voter's neighbours.

        Vectorized trick: src[i] is the "owner" voter of edge i, and dst[i]
        is the neighbour on the other end. `values[self.dst]` looks up each
        edge's neighbour value; bincount(src, weights=...) then adds those
        values up, grouped by owner voter -- exactly a "sum over neighbours"
        for every voter simultaneously, with no Python-level loop.
        """
        if len(self.edges) == 0:
            return np.zeros(self.n, dtype=np.float64)
        return np.bincount(
            self.src, weights=values[self.dst].astype(np.float64), minlength=self.n
        )

    def neighbor_mean(self, values: np.ndarray, fallback: np.ndarray) -> np.ndarray:
        """For each voter, the *mean* of `values` over that voter's
        neighbours -- e.g. "what's the average ideology among my contacts?"

        Voters with zero neighbours have no defined mean, so they instead
        keep whatever `fallback` supplies for them (in model.py this is
        called with fallback=the voter's own current ideology, i.e.
        "isolated voters don't drift toward anyone"). This mirrors NetLogo's
        `if any? link-neighbors [ ... ]` guard around the same computation.
        """
        result = np.asarray(fallback, dtype=np.float64).copy()
        if len(self.edges) == 0:
            return result
        linked = self.has_neighbors
        totals = self.neighbor_sum(values)
        # Only overwrite the fallback for voters that actually have
        # neighbours; everyone else keeps their fallback value untouched.
        result[linked] = totals[linked] / self.degree[linked]
        return result

    def neighbor_fraction(
        self, numerator_mask: np.ndarray, denominator_mask: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray]:
        """For each voter, what fraction of its neighbours satisfying
        `denominator_mask` also satisfy `numerator_mask`?

        Concrete use in rules.py: "what fraction of my *politically active*
        neighbours (denominator_mask = did they vote last time) voted Red
        (numerator_mask = last_vote == 1)?" -- this is how RULE 4 (social
        majority) decides whether a voter's neighbourhood leans one way.

        Returns (fraction, valid). `valid` is False for any voter with zero
        qualifying neighbours (denominator_mask never true among their
        neighbours) -- for those voters the fraction is mathematically
        undefined (0/0), matching NetLogo's `if any? active-neighbours [...]`
        guard, which simply skips the rule rather than dividing by zero.
        """
        counts = self.neighbor_sum(denominator_mask.astype(np.float64))
        hits = self.neighbor_sum(
            (numerator_mask & denominator_mask).astype(np.float64)
        )
        valid = counts > 0
        fraction = np.zeros(self.n, dtype=np.float64)
        # `where=valid` skips the division entirely for invalid entries,
        # leaving them at the pre-filled 0.0 rather than producing NaN/inf.
        np.divide(hits, counts, out=fraction, where=valid)
        return fraction, valid


def build_network(
    rng: np.random.Generator,
    ideology: np.ndarray,
    network_degree: float,
    homophily: float,
) -> Network:
    """Randomly wire up `len(ideology)` voters into a Network with roughly
    `network_degree` connections per voter on average, biased toward linking
    ideologically similar voters when `homophily` is high.

    Algorithm (a direct port of NetLogo's build-network): repeatedly propose
    a uniformly random pair of voters; reject the pair outright if it's a
    self-pair or already linked; otherwise accept it with a probability that
    depends on how similar the two voters' ideologies are:

        similarity  = 1 - |ideology[a] - ideology[b]| / 2      (in [0, 1])
        acceptance  = (1 - homophily) + homophily * similarity

    At homophily=0, acceptance is always 1 -- every proposed (non-duplicate)
    pair is linked, i.e. purely random wiring, ideology irrelevant. At
    homophily=1, acceptance *equals* similarity -- distant pairs are
    unlikely to link and identical-ideology pairs are always linked, i.e.
    "birds of a feather."

    Why this loop is NOT vectorized, unlike nearly everything else in this
    model: each proposal must be checked against the *growing* set of edges
    accepted so far ("is this pair already linked?"). Batching many
    proposals at once would mean some of them don't yet know about edges
    accepted earlier in the same batch, which would change how many edges
    get built (a genuinely different outcome, not just a faster path to the
    same one). Since this only runs once per model run (unlike the
    per-election voter update, which runs every tick), keeping it faithful
    and sequential is worth far more than the speedup would be.
    """
    n = len(ideology)
    if n < 2 or network_degree <= 0:
        return Network(n)

    # NetLogo: `round (count voters * network-degree / 2)`. NetLogo's ROUND
    # is round-half-up (0.5 -> 1), but Python's round() uses round-half-to-
    # even (0.5 -> 0) -- the explicit floor(x + 0.5) below reproduces
    # NetLogo's convention instead of Python's.
    target_links = int(np.floor(n * network_degree / 2 + 0.5))
    if target_links <= 0:
        return Network(n)

    # A safety valve: if homophily is high and ideologies are tightly
    # clustered, acceptance probabilities can be low enough that reaching
    # target_links could take a very long time (or, in a degenerate case,
    # never happen). Capping attempts means the function always terminates,
    # possibly with fewer edges than requested, rather than hanging.
    max_attempts = max(1000, target_links * 100)

    edges: list[tuple[int, int]] = []
    seen: set[tuple[int, int]] = set()  # already-accepted pairs, for O(1) dup checks

    # Pre-draw a batch of candidate pairs and a batch of acceptance-test
    # random floats; refill each batch only when it runs out (the _CHUNK
    # amortization trick described at the top of the file).
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
            continue  # can't link a voter to itself

        # Store pairs with the smaller index first so (a, b) and (b, a)
        # dedupe to the same key -- the network is undirected.
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
