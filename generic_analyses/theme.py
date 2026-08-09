"""Colour and chrome for every figure in this folder.

Two parties, so two hues -- and they are not decorative: the model names them
Blue and Red, so the colour follows the entity and never moves.  Everything else
on the chart (the electorate, its spread, gridlines, labels) is ink, because it
is context rather than identity, and because eight hues on a chart whose story is
two parties is how a plot stops being read.

Both palettes were checked rather than eyeballed, on all pairs against the
surface they are drawn on:

    #2a78d6 / #e34948 on #fcfcfb   worst pair CVD dE 21.6, normal 32.3, both >= 3:1
    #3987e5 / #e66767 on #1a1a19   worst pair CVD dE 19.2, normal 29.0, both >= 3:1
"""

from __future__ import annotations

from dataclasses import dataclass

THEMES = {
    "light": {
        "surface": "#fcfcfb",
        "blue": "#2a78d6",
        "red": "#e34948",
        "ink": "#0b0b0b",
        "ink_secondary": "#52514e",
        "ink_muted": "#898781",
        "grid": "#e1e0d9",
        "axis": "#c3c2b7",
    },
    "dark": {
        # Selected for the dark surface, not flipped from the light values.
        "surface": "#1a1a19",
        "blue": "#3987e5",
        "red": "#e66767",
        "ink": "#ffffff",
        "ink_secondary": "#c3c2b7",
        "ink_muted": "#898781",
        "grid": "#2c2c2a",
        "axis": "#383835",
    },
}


@dataclass(frozen=True)
class Theme:
    name: str
    surface: str
    blue: str
    red: str
    ink: str
    ink_secondary: str
    ink_muted: str
    grid: str
    axis: str

    @property
    def electorate(self) -> str:
        """The electorate is drawn as ink: it is the ground the parties move over."""
        return self.ink_secondary


def get_theme(name: str = "light") -> Theme:
    if name not in THEMES:
        raise ValueError(f"unknown theme {name!r}; expected one of {sorted(THEMES)}")
    return Theme(name=name, **THEMES[name])


def apply(theme: Theme) -> None:
    """Set the chrome once, so the figures below only describe their data.

    Thin marks, solid hairline grid (a dashed grid reads as a threshold), axes one
    shade off the surface, and no top/right spines.
    """
    import matplotlib as mpl

    mpl.rcParams.update(
        {
            "figure.facecolor": theme.surface,
            "axes.facecolor": theme.surface,
            "savefig.facecolor": theme.surface,
            "axes.edgecolor": theme.axis,
            "axes.labelcolor": theme.ink_secondary,
            "axes.titlecolor": theme.ink,
            "axes.linewidth": 0.8,
            "axes.grid": True,
            "axes.grid.axis": "y",
            "axes.spines.top": False,
            "axes.spines.right": False,
            "grid.color": theme.grid,
            "grid.linewidth": 0.8,
            "grid.linestyle": "-",
            "xtick.color": theme.ink_muted,
            "ytick.color": theme.ink_muted,
            "xtick.labelcolor": theme.ink_muted,
            "ytick.labelcolor": theme.ink_muted,
            "xtick.direction": "out",
            "ytick.direction": "out",
            "text.color": theme.ink,
            "font.family": "sans-serif",
            "font.sans-serif": ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"],
            "font.size": 9,
            "axes.titlesize": 11,
            "axes.titleweight": "medium",
            "axes.titlelocation": "left",
            "axes.titlepad": 10,
            "legend.frameon": False,
            "legend.fontsize": 9,
            "legend.labelcolor": theme.ink_secondary,
            "lines.linewidth": 1.8,
            "lines.solid_capstyle": "round",
            "figure.dpi": 140,
            "savefig.dpi": 140,
            "figure.constrained_layout.use": True,
        }
    )
