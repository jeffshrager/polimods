"""Election-level history and TSV export.

The exported file is byte-compatible with NetLogo's ``EXPORT HISTORY (TSV)``: same
column names, same order, same rounding, and the same number formatting (NetLogo
prints ``50`` rather than ``50.0``).
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, fields

#: The columns NetLogo writes, with the decimal places it rounds each to.
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
    """One completed election, at full floating-point precision."""

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

    def as_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def field_names(cls) -> tuple[str, ...]:
        return tuple(f.name for f in fields(cls))


def netlogo_precision(value: float, places: int) -> float:
    """NetLogo's ``precision``: round half away from zero, not half to even."""
    if math.isnan(value) or math.isinf(value):
        return value
    scale = 10.0**places
    scaled = value * scale
    return math.floor(scaled + 0.5) / scale if scaled >= 0 else math.ceil(scaled - 0.5) / scale


def netlogo_number(value: float) -> str:
    """Format a number the way NetLogo's ``word`` does: no trailing ``.0``."""
    if isinstance(value, int) or float(value).is_integer():
        return str(int(value))
    return repr(float(value))


class History:
    """The list of completed elections, mirroring NetLogo's ``history`` global."""

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
        """Write the history to ``path``; returns the number of elections written."""
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(self.to_tsv())
        return len(self.records)

    def to_dicts(self) -> list[dict[str, object]]:
        return [record.as_dict() for record in self.records]
