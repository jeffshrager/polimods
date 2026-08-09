# Findings: does homophily manufacture polarization, or only sharpen it?

Slopes are `numpy.polyfit(homophily, value, 1)`, pooled over all five
`social_influence` levels, on the final-election value of each run.

| electorate_shape | d(ideology_sd)/d(homophily) | d(coalition_gap)/d(homophily) |
|---|---:|---:|
| single-peaked | +0.0022 | +0.0008 |
| two-camp | +0.0087 | +0.0083 |

`coalition_gap` is `red_voter_ideology - blue_voter_ideology` at the final
election: how far apart each party's actual supporters sit, as opposed to
`ideology_sd`, which is the spread of the whole electorate and cannot tell a
unimodal electorate from two camps sitting close together.

A positive `coalition_gap` slope in `single-peaked` is the manufacture
signature: homophily is pulling the two parties' voters apart even though
they started drawn from one hump. A positive slope in `two-camp` is the
sharpen signature: the camps were already separate and homophily widens the
gap further, or at least resists the collapse `network_sweep` documented.
