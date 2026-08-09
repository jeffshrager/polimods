"""Electoral institutions: how ballots become seats and a government.

The two-party model counted a national popular vote and declared whoever had
more votes the winner.  That is one institution among several, and which one you
pick changes the model's behaviour more than most of its parameters do -- the
same electorate and the same parties produce different party systems under
first-past-the-post districts than under proportional representation.

An institution is asked one question, :meth:`Institution.elect`, and answers with
seats, a governing party, and enough detail to compute disproportionality.  Some
institutions need a second round of voting; they say so, and the model re-runs
the decision with the field narrowed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar

import numpy as np

from .space import IssueSpace
from .state import ABSTAIN, Electorate

INSTITUTIONS: dict[str, type["Institution"]] = {}
DISTRICTINGS: dict[str, Any] = {}


def institution(cls: type["Institution"]) -> type["Institution"]:
    INSTITUTIONS[cls.name] = cls
    return cls


@dataclass
class ElectionResult:
    """The outcome of one election."""

    votes: np.ndarray  # (p,) ballots per party
    seats: np.ndarray  # (p,) seats per party
    winner: int  # governing party index, or ABSTAIN if undecided
    total_votes: int
    turnout: float
    district_winners: np.ndarray | None = None
    rounds: int = 1

    @property
    def vote_shares(self) -> np.ndarray:
        total = self.votes.sum()
        return self.votes / total if total else np.zeros_like(self.votes, dtype=float)

    @property
    def seat_shares(self) -> np.ndarray:
        total = self.seats.sum()
        return self.seats / total if total else np.zeros_like(self.seats, dtype=float)

    @property
    def margin(self) -> float:
        """Lead of the first party over the second, in vote-share percentage points."""
        shares = np.sort(self.vote_shares)
        if len(shares) < 2:
            return 100.0 if len(shares) else 0.0
        return float(100.0 * (shares[-1] - shares[-2]))

    @property
    def majority(self) -> bool:
        total = self.seats.sum()
        return bool(total and self.seats.max() > total / 2)


@dataclass
class Institution:
    """Base class for vote-aggregation rules."""

    name: ClassVar[str] = ""
    #: Number of districts the electorate is divided into; 1 means a single
    #: national constituency.
    districts: int = 1
    districting: str = "random"

    def needs_runoff(self, result: ElectionResult) -> np.ndarray | None:
        """Return the contenders for a second round, or ``None`` if the result stands."""
        return None

    def elect(self, electorate: Electorate, n_parties: int) -> ElectionResult:  # pragma: no cover
        raise NotImplementedError

    def describe(self) -> str:
        return self.name


def _basic_result(
    electorate: Electorate, n_parties: int, seats: np.ndarray, winner: int, **extra
) -> ElectionResult:
    votes = electorate.vote_counts(n_parties)
    return ElectionResult(
        votes=votes,
        seats=seats,
        winner=winner,
        total_votes=int(votes.sum()),
        turnout=electorate.turnout,
        **extra,
    )


def _plurality(counts: np.ndarray, rng: np.random.Generator | None = None) -> int:
    """Index of the largest count, ties broken at random rather than by order."""
    if len(counts) == 0 or counts.sum() == 0:
        return ABSTAIN
    tied = counts == counts.max()
    if tied.sum() == 1:
        return int(counts.argmax())
    candidates = np.flatnonzero(tied)
    if rng is None:
        return int(candidates[0])
    return int(rng.choice(candidates))


@institution
@dataclass
class PopularVote(Institution):
    """A single national constituency; the largest party governs.

    What the two-party model did.  Seats are reported as one per party-equivalent
    of vote share so that disproportionality is defined, but only the winner
    matters.
    """

    name: ClassVar[str] = "popular_vote"
    rng: Any = None

    def elect(self, electorate: Electorate, n_parties: int) -> ElectionResult:
        votes = electorate.vote_counts(n_parties)
        winner = _plurality(votes, self.rng)
        seats = np.zeros(n_parties, dtype=np.int64)
        if winner != ABSTAIN:
            seats[winner] = 1
        return _basic_result(electorate, n_parties, seats, winner)


@institution
@dataclass
class FirstPastThePost(Institution):
    """One seat per district, won by whoever leads in that district.

    This is where districting starts to matter: the same national vote can
    produce very different seat counts depending on how voters are grouped, which
    is the mechanism behind both manufactured majorities and gerrymanders.
    """

    name: ClassVar[str] = "fptp"
    districts: int = 50
    rng: Any = None

    def elect(self, electorate: Electorate, n_parties: int) -> ElectionResult:
        seats = np.zeros(n_parties, dtype=np.int64)
        district_winners = np.full(self.districts, ABSTAIN, dtype=np.int64)

        for district in range(self.districts):
            local = electorate.district == district
            if not local.any():
                continue
            counts = electorate.vote_counts(n_parties, mask=local)
            winner = _plurality(counts, self.rng)
            district_winners[district] = winner
            if winner != ABSTAIN:
                seats[winner] += 1

        return _basic_result(
            electorate,
            n_parties,
            seats,
            _plurality(seats, self.rng),
            district_winners=district_winners,
        )


@institution
@dataclass
class ProportionalRepresentation(Institution):
    """Seats allocated in proportion to votes, above a threshold.

    ``method`` picks the divisor sequence: ``d_hondt`` (divisors 1, 2, 3, ...)
    favours large parties slightly; ``sainte_lague`` (1, 3, 5, ...) is closer to
    proportional for small ones.  ``threshold`` excludes parties below a national
    vote share, which is the main institutional barrier to fragmentation.
    """

    name: ClassVar[str] = "pr"
    seats: int = 100
    threshold: float = 0.05
    method: str = "d_hondt"
    rng: Any = None

    def elect(self, electorate: Electorate, n_parties: int) -> ElectionResult:
        votes = electorate.vote_counts(n_parties)
        total = votes.sum()
        if total == 0:
            return _basic_result(
                electorate, n_parties, np.zeros(n_parties, dtype=np.int64), ABSTAIN
            )

        eligible = (votes / total) >= self.threshold
        if not eligible.any():
            eligible = votes == votes.max()

        allocation = allocate_seats(
            np.where(eligible, votes, 0), self.seats, self.method
        )
        return _basic_result(
            electorate, n_parties, allocation, _plurality(allocation, self.rng)
        )


@institution
@dataclass
class TwoRoundRunoff(Institution):
    """A national vote, then a head-to-head between the top two if nobody leads outright.

    The institution that most directly changes voters' *incentives* rather than
    just the arithmetic: a second round exists precisely so that support can be
    re-expressed once the field narrows.
    """

    name: ClassVar[str] = "runoff"
    majority_needed: float = 0.5
    rng: Any = None

    def elect(self, electorate: Electorate, n_parties: int) -> ElectionResult:
        votes = electorate.vote_counts(n_parties)
        winner = _plurality(votes, self.rng)
        seats = np.zeros(n_parties, dtype=np.int64)
        if winner != ABSTAIN:
            seats[winner] = 1
        return _basic_result(electorate, n_parties, seats, winner)

    def needs_runoff(self, result: ElectionResult) -> np.ndarray | None:
        if result.total_votes == 0 or len(result.votes) < 3 or result.rounds > 1:
            return None
        shares = result.vote_shares
        if shares.max() > self.majority_needed:
            return None
        return np.argsort(shares)[-2:]


def allocate_seats(votes: np.ndarray, seats: int, method: str = "d_hondt") -> np.ndarray:
    """Highest-averages seat allocation.

    Computed by building the full quotient table rather than looping seat by
    seat: with at most a few hundred seats and a handful of parties it is small,
    and it makes the divisor sequence explicit.
    """
    votes = np.asarray(votes, dtype=float)
    allocation = np.zeros(len(votes), dtype=np.int64)
    if seats <= 0 or votes.sum() <= 0:
        return allocation

    if method == "sainte_lague":
        divisors = 2 * np.arange(seats) + 1
    elif method == "d_hondt":
        divisors = np.arange(1, seats + 1)
    else:
        raise ValueError(f"unknown allocation method {method!r}")

    quotients = votes[:, None] / divisors[None, :]
    flat = np.argsort(quotients.ravel())[::-1][:seats]
    winners = flat // len(divisors)
    return np.bincount(winners, minlength=len(votes)).astype(np.int64)


# -- districting --------------------------------------------------------------


def districting(name: str):
    def register(function):
        DISTRICTINGS[name] = function
        return function

    return register


@districting("random")
def random_districts(
    positions: np.ndarray, districts: int, rng: np.random.Generator, space: IssueSpace
) -> np.ndarray:
    """Assign voters to districts at random: districts mirror the nation."""
    return rng.integers(0, districts, size=len(positions)).astype(np.int64)


@districting("sorted")
def sorted_districts(
    positions: np.ndarray, districts: int, rng: np.random.Generator, space: IssueSpace
) -> np.ndarray:
    """Equal-sized districts of ideologically similar voters.

    The extreme of residential sorting: each district is internally homogeneous,
    so most seats are safe and the national vote moves few of them.
    """
    order = np.argsort(positions[:, 0], kind="stable")
    assignment = np.zeros(len(positions), dtype=np.int64)
    assignment[order] = np.arange(len(positions)) * districts // len(positions)
    return assignment


@districting("packed")
def packed_districts(
    positions: np.ndarray, districts: int, rng: np.random.Generator, space: IssueSpace
) -> np.ndarray:
    """One district packed with the most extreme voters, the rest split evenly.

    A minimal gerrymander: concentrating one side's strongest supporters into a
    single district wastes their votes everywhere else.
    """
    if districts < 2:
        return np.zeros(len(positions), dtype=np.int64)

    order = np.argsort(positions[:, 0], kind="stable")
    packed_size = len(positions) // districts
    assignment = np.zeros(len(positions), dtype=np.int64)
    assignment[order[:packed_size]] = 0
    remainder = order[packed_size:]
    assignment[remainder] = rng.integers(1, districts, size=len(remainder))
    return assignment


def assign_districts(
    name: str,
    positions: np.ndarray,
    districts: int,
    rng: np.random.Generator,
    space: IssueSpace,
) -> np.ndarray:
    if districts <= 1:
        return np.zeros(len(positions), dtype=np.int64)
    if name not in DISTRICTINGS:
        raise ValueError(
            f"unknown districting {name!r}. Available: {', '.join(sorted(DISTRICTINGS))}"
        )
    return DISTRICTINGS[name](positions, districts, rng, space)


def build_institution(spec: str | dict[str, Any], rng=None) -> Institution:
    if isinstance(spec, str):
        spec = {"institution": spec}
    spec = dict(spec)
    name = spec.pop("institution", None) or spec.pop("name", None) or "popular_vote"
    if name not in INSTITUTIONS:
        raise ValueError(
            f"unknown institution {name!r}. Available: {', '.join(sorted(INSTITUTIONS))}"
        )
    try:
        built = INSTITUTIONS[name](**spec)
    except TypeError as error:
        raise ValueError(f"bad options for institution {name!r}: {error}") from None
    built.rng = rng
    return built
