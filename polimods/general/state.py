"""Model state: the electorate and the party system.

Two structural changes from the two-party model drive the design here.

Parties are a *set* rather than a pair, and that set can change size while the
model runs.  Every per-party array is therefore addressed by position in the
current active list, and the party system owns the bookkeeping for keeping those
columns aligned when a party enters or exits.  Parties also keep a stable ``id``,
so a party that dies and a party that is born later are never confused in the
history even if they occupy the same column.

Partisan identity generalizes from one signed scalar to an ``(n_voters,
n_parties)`` matrix of attachments.  On a line with two parties, "leans Blue" and
"leans Red" are the same number with opposite signs; with five parties they are
not, and a voter can be warm toward two of them at once.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .space import IssueSpace

#: The value of ``vote`` and ``last_vote`` for a voter who did not vote.
ABSTAIN = -1


@dataclass
class Party:
    """One party: where it stands, how it adapts, and when it existed."""

    id: int
    name: str
    position: np.ndarray
    strategy: "object"
    born: int = 0
    died: int | None = None

    #: Vote share (0-1) in each election this party contested, most recent last.
    share_history: list[float] = field(default_factory=list)
    #: Position before the most recent adaptation, used by hill-climbing strategies.
    previous_position: np.ndarray | None = None
    #: Per-party state a strategy wants to carry between elections.
    memory: dict = field(default_factory=dict)

    @property
    def age(self) -> int:
        return len(self.share_history)

    @property
    def last_share(self) -> float:
        return self.share_history[-1] if self.share_history else 0.0

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        where = np.array2string(self.position, precision=3, suppress_small=True)
        return f"<Party {self.name} #{self.id} at {where}>"


class PartySystem:
    """The active parties, in a stable column order.

    Column ``j`` of every ``(n_voters, n_parties)`` array refers to
    ``self.parties[j]``.  Entry appends a column, exit deletes one, and
    :meth:`realign` applies the same edit to any voter-level matrix so the two
    never drift apart.
    """

    def __init__(self, space: IssueSpace, parties: list[Party] | None = None):
        self.space = space
        self.parties: list[Party] = list(parties or [])
        self.retired: list[Party] = []
        self._next_id = max((p.id for p in self.parties), default=-1) + 1

    def __len__(self) -> int:
        return len(self.parties)

    def __iter__(self):
        return iter(self.parties)

    def __getitem__(self, index: int) -> Party:
        return self.parties[index]

    @property
    def names(self) -> list[str]:
        return [party.name for party in self.parties]

    @property
    def positions(self) -> np.ndarray:
        """``(n_parties, dimensions)`` view of where the parties stand."""
        if not self.parties:
            return np.zeros((0, self.space.dimensions))
        return np.vstack([party.position for party in self.parties])

    def set_positions(self, positions: np.ndarray) -> None:
        positions = self.space.clip(np.atleast_2d(positions))
        for party, position in zip(self.parties, positions):
            party.position = position

    def index_of(self, party_id: int) -> int | None:
        for index, party in enumerate(self.parties):
            if party.id == party_id:
                return index
        return None

    def add(self, name: str, position: np.ndarray, strategy, born: int) -> tuple[Party, int]:
        """Admit a new party; returns it and the column index it now occupies."""
        party = Party(
            id=self._next_id,
            name=name,
            position=self.space.clip(np.asarray(position, dtype=float)),
            strategy=strategy,
            born=born,
        )
        self._next_id += 1
        self.parties.append(party)
        return party, len(self.parties) - 1

    def remove(self, index: int, died: int) -> Party:
        """Retire the party in column ``index``; returns it."""
        party = self.parties.pop(index)
        party.died = died
        self.retired.append(party)
        return party

    @staticmethod
    def realign(matrix: np.ndarray, *, drop: int | None = None, append: int = 0) -> np.ndarray:
        """Apply a party-set edit to an ``(n_voters, n_parties)`` matrix."""
        if drop is not None:
            matrix = np.delete(matrix, drop, axis=1)
        if append:
            padding = np.zeros((matrix.shape[0], append), dtype=matrix.dtype)
            matrix = np.hstack([matrix, padding])
        return matrix

    def describe(self) -> str:  # pragma: no cover - reporting aid
        return ", ".join(
            f"{party.name}@{np.array2string(party.position, precision=2)}"
            for party in self.parties
        )


@dataclass
class Electorate:
    """Voter-level state, as parallel arrays.

    ``position`` is ``(n, d)``, ``identity`` is ``(n, p)``, and the rest are
    ``(n,)``.  ``vote`` and ``last_vote`` hold a party column index, or
    :data:`ABSTAIN`.
    """

    space: IssueSpace
    position: np.ndarray
    salience: np.ndarray
    identity: np.ndarray
    district: np.ndarray
    last_vote: np.ndarray
    vote: np.ndarray
    voted: np.ndarray
    turnout_probability: np.ndarray
    utility: np.ndarray

    @classmethod
    def empty(cls, space: IssueSpace, n: int, n_parties: int) -> "Electorate":
        return cls(
            space=space,
            position=np.zeros((n, space.dimensions)),
            salience=np.tile(space.weights, (n, 1)),
            identity=np.zeros((n, n_parties)),
            district=np.zeros(n, dtype=np.int64),
            last_vote=np.full(n, ABSTAIN, dtype=np.int64),
            vote=np.full(n, ABSTAIN, dtype=np.int64),
            voted=np.zeros(n, dtype=bool),
            turnout_probability=np.zeros(n),
            utility=np.zeros((n, n_parties)),
        )

    def __len__(self) -> int:
        return len(self.position)

    @property
    def n_parties(self) -> int:
        return self.identity.shape[1]

    def distances_to(self, positions: np.ndarray) -> np.ndarray:
        """``(n_voters, n_parties)`` salience-weighted distances."""
        return self.space.distances(self.position, positions, salience=self.salience)

    def on_party_added(self) -> None:
        self.identity = PartySystem.realign(self.identity, append=1)
        self.utility = PartySystem.realign(self.utility, append=1)

    def on_party_removed(self, index: int) -> None:
        """Drop a party's column and repair the vote indices that pointed past it."""
        self.identity = PartySystem.realign(self.identity, drop=index)
        self.utility = PartySystem.realign(self.utility, drop=index)

        for votes in (self.vote, self.last_vote):
            # Voters who backed the departed party have nobody to be loyal to.
            votes[votes == index] = ABSTAIN
            # Everything to its right shifts one column left.
            shifted = votes > index
            votes[shifted] -= 1

    @property
    def turnout(self) -> float:
        """Share of the electorate that cast a ballot, 0-1."""
        return float(self.voted.mean()) if len(self) else 0.0

    def vote_counts(self, n_parties: int, mask: np.ndarray | None = None) -> np.ndarray:
        """Ballots cast for each party, optionally within a subset of voters."""
        votes = self.vote if mask is None else self.vote[mask]
        cast = votes[votes != ABSTAIN]
        return np.bincount(cast, minlength=n_parties).astype(np.int64)

    def dispersion(self) -> float:
        return self.space.dispersion(self.position)
