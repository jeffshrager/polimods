"""
================================================================================
 HISTORY -- the per-election logbook
================================================================================
Every time the model runs one election (Model.step in model.py), it appends
one ElectionRecord to a History. This file has nothing to do with *deciding*
anything -- it is pure bookkeeping and export formatting.

Two things worth knowing before reading the rest of this file:

1. The first eleven fields of ElectionRecord exist because NetLogo's
   "EXPORT HISTORY (TSV)" button wrote exactly those eleven columns, in
   exactly that order, with exact rounding rules. To let old analysis
   scripts/spreadsheets built against NetLogo's export keep working
   unmodified, this Python port reproduces that file byte-for-byte:
   same column names, same order, same decimal-rounding, same "50" instead
   of "50.0" number formatting quirk.

2. Everything *after* those eleven fields is new: information that never
   existed in the NetLogo export but that later analysis needed (see
   ideology_sd, ideology_p10/50/90, blue/red_voter_ideology, mean_identity).
   These are appended at the end, not interleaved into the original eleven,
   specifically so COLUMNS (the TSV export list) doesn't have to be touched
   and the file stays byte-compatible with the original.
================================================================================
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, fields

# --------------------------------------------------------------------------
# COLUMNS drives the TSV export. Each entry is:
#   (column header text, ElectionRecord attribute name, decimal places)
# `places=None` means "print the raw value with no rounding" (used only for
# the integer `election` count and the `winner` string).
# --------------------------------------------------------------------------
COLUMNS: tuple[tuple[str, str, int | None], ...] = (
    ("election", "election", None),
    ("winner", "winner", None),
    ("blue-share", "blue_share", 3),
    ("red-share", "red_share", 3),
    ("turnout", "turnout_rate", 3),
    ("margin", "margin", 3),
    ("blue-position", "blue_position", 4),
    ("red-position", "red_position", 4),
    ("party-gap", "party_gap", 4),
    ("mean-ideology", "mean_ideology", 4),
    ("switch-rate", "switch_rate", 3),
)

HEADER = "\t".join(name for name, _attr, _p in COLUMNS)


@dataclass
class ElectionRecord:
    """A snapshot of one completed election, at full floating-point
    precision (rounding only happens at export time, in to_lines()).

    --- Fields 1-11: the original NetLogo export columns, in NetLogo's order ---
    """

    election: int
    winner: str
    blue_share: float
    red_share: float
    turnout_rate: float
    margin: float
    blue_position: float
    red_position: float
    party_gap: float
    mean_ideology: float
    switch_rate: float

    # --- Fields added after the port: describe *where the electorate is*,
    # which the original eleven columns cannot show. Both electorate shapes
    # the model supports are symmetric around 0, so mean_ideology above sits
    # near zero pretty much no matter what's happening internally -- it
    # can't distinguish "electorate spread out" from "electorate collapsed
    # to a point at the centre." These fields can. ---

    #: Standard deviation of the whole electorate's ideology -- how spread
    #: out (0 = everyone identical) vs. polarized the population is.
    ideology_sd: float = 0.0
    #: The 10th/50th/90th percentile voter's ideology -- a cheap sketch of
    #: the distribution's shape (skew, tails) that a single mean/sd can't
    #: capture, e.g. can reveal a lingering two-humped shape.
    ideology_p10: float = 0.0
    ideology_p50: float = 0.0
    ideology_p90: float = 0.0
    #: Mean ideology of *only* the voters who actually voted Blue / Red this
    #: election -- i.e. the centre of gravity of each party's real coalition,
    #: which is precisely what move_losing_party/move_winning_party in
    #: model.py are chasing. NaN when a party received zero votes this
    #: election (mean of an empty set is undefined).
    blue_voter_ideology: float = float("nan")
    red_voter_ideology: float = float("nan")
    #: Mean partisan identity across the whole electorate, on the same
    #: -1 (wholly Blue) .. +1 (wholly Red) scale as any individual voter's
    #: party_identity.
    mean_identity: float = 0.0

    def as_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def field_names(cls) -> tuple[str, ...]:
        return tuple(f.name for f in fields(cls))


def netlogo_precision(value: float, places: int) -> float:
    """Round the way NetLogo's `precision` reporter rounds: half away from
    zero (0.5 -> 1, -0.5 -> -1), NOT Python/IEEE-754's default "round half to
    even" (Python's built-in round(0.5) gives 0, which would silently
    mismatch NetLogo's export on values landing exactly on a rounding
    boundary).
    """
    if math.isnan(value) or math.isinf(value):
        return value
    scale = 10.0**places
    scaled = value * scale
    # floor(x + 0.5) rounds positive halves up; for negatives we mirror the
    # same trick with ceil(x - 0.5), which is what "away from zero" requires.
    return math.floor(scaled + 0.5) / scale if scaled >= 0 else math.ceil(scaled - 0.5) / scale


def netlogo_number(value: float) -> str:
    """Format a number the way NetLogo's `word` (string-building) primitive
    does: whole numbers print without a trailing ".0" (NetLogo writes "50",
    Python's default str(50.0) would write "50.0")."""
    if isinstance(value, int) or float(value).is_integer():
        return str(int(value))
    return repr(float(value))


class History:
    """The full sequence of completed elections for one model run, mirroring
    NetLogo's `history` global (a growing list, one entry appended per
    election)."""

    def __init__(self) -> None:
        self.records: list[ElectionRecord] = []

    def __len__(self) -> int:
        return len(self.records)

    def __iter__(self):
        return iter(self.records)

    def __getitem__(self, index):
        return self.records[index]

    def append(self, record: ElectionRecord) -> None:
        self.records.append(record)

    def to_lines(self) -> list[str]:
        """Render every record as tab-separated text lines, header first --
        this is where rounding (netlogo_precision) and number formatting
        (netlogo_number) actually get applied; the stored records themselves
        stay at full precision until export time."""
        lines = [HEADER]
        for record in self.records:
            cells = []
            for _name, attr, places in COLUMNS:
                value = getattr(record, attr)
                if places is None:
                    cells.append(str(value))
                else:
                    cells.append(netlogo_number(netlogo_precision(value, places)))
            lines.append("\t".join(cells))
        return lines

    def to_tsv(self) -> str:
        return "\n".join(self.to_lines()) + "\n"

    def export_tsv(self, path) -> int:
        """Write the history to `path` as TSV; returns the number of
        elections written (i.e. len(self))."""
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(self.to_tsv())
        return len(self.records)

    def to_dicts(self) -> list[dict[str, object]]:
        """Every record as a plain dict, at full precision (no rounding) --
        useful for feeding pandas/csv/json rather than the NetLogo-compatible
        TSV format above."""
        return [record.as_dict() for record in self.records]
