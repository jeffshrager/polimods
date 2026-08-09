breed [ voters voter ]
breed [ parties party ]
undirected-link-breed [ social-links social-link ]

globals [
  blue-party
  red-party
  blue-position
  red-position

  blue-votes
  red-votes
  total-votes
  blue-share
  red-share
  turnout-rate
  election-margin
  switch-rate
  winner-id
  winner-name

  cumulative-margin
  mean-margin
  party-control-changes
  last-winner-id
  control-change-rate
  party-gap
  mean-voter-ideology

  history
]

voters-own [
  ideology              ;; internal policy position, -1 (Blue) to +1 (Red)
  party-identity        ;; internal partisan attachment, -1 to +1
  choice-score          ;; positive favors Red, negative favors Blue
  turnout-probability
  vote-choice           ;; -1 Blue, 0 abstain, +1 Red
  intended-choice       ;; party choice before the turnout decision
  last-vote             ;; most recent non-abstaining vote
  voted?
  next-ideology
  display-y             ;; arbitrary vertical position used only for display

  ;; Production-system working memory.  Every voter has the same rules,
  ;; but the rules fire differently because voters have different states.
  blue-reasons
  red-reasons
  turnout-reasons
  abstention-reasons
  rule-trace            ;; readable record of which rules fired
]

parties-own [
  party-id               ;; -1 Blue, +1 Red
]


to setup
  clear-all

  set blue-position clamp-value ((0 - initial-party-gap) / 2) -1 1
  set red-position  clamp-value (initial-party-gap / 2) -1 1
  set blue-party nobody
  set red-party nobody

  set blue-votes 0
  set red-votes 0
  set total-votes 0
  set blue-share 50
  set red-share 50
  set turnout-rate 0
  set election-margin 0
  set switch-rate 0
  set winner-id 0
  set winner-name "none yet"

  set cumulative-margin 0
  set mean-margin 0
  set party-control-changes 0
  set last-winner-id 0
  set control-change-rate 0
  set party-gap red-position - blue-position
  set mean-voter-ideology 0

  set history (list (word
    "election\twinner\tblue-share\tred-share\tturnout\tmargin"
    "\tblue-position\tred-position\tparty-gap\tmean-ideology\tswitch-rate"))

  setup-background
  setup-parties
  setup-voters

  if social-network? [ build-network ]

  update-display
  reset-ticks
end


to setup-background
  ask patches [ set pcolor white ]
  ask patches with [ pxcor = 0 ] [ set pcolor gray + 3 ]
end


to setup-parties
  create-parties 1 [
    set party-id -1
    set color blue
    set shape "star"
    set size 3.2
    set label "BLUE"
    set label-color blue - 2
    set blue-party self
  ]

  create-parties 1 [
    set party-id 1
    set color red
    set shape "star"
    set size 3.2
    set label "RED"
    set label-color red - 2
    set red-party self
  ]
end


to setup-voters
  create-voters population [
    let center 0
    if electorate-shape = "two-camp" [
      set center one-of (list (0 - electorate-polarization) electorate-polarization)
    ]

    set ideology clamp-value (random-normal center ideology-spread) -1 1
    set party-identity clamp-value (ideology + random-normal 0 identity-noise) -1 1

    set choice-score 0
    set turnout-probability 0
    set vote-choice 0
    set intended-choice 0
    set last-vote 0
    set voted? false
    set next-ideology ideology

    set blue-reasons 0
    set red-reasons 0
    set turnout-reasons 0
    set abstention-reasons 0
    set rule-trace ""

    ;; The vertical coordinate has no political meaning.  It only spreads dots out.
    set display-y (min-pycor + 2 + random-float ((max-pycor - min-pycor) - 7))
    set shape "circle"
    set size 0.65
    set color gray
  ]

  set mean-voter-ideology mean [ ideology ] of voters
end


to go
  if not any? voters [ stop ]

  ;; Let switches take effect even if changed after SETUP.
  if not social-network? and any? social-links [ ask social-links [ die ] ]
  if social-network? and network-degree > 0 and not any? social-links [ build-network ]

  run-election
  adapt-parties
  update-voter-states
  update-summary-statistics
  update-display
  record-history
  tick
end


to run-election
  ask voters [
    ifelse production-system? [
      run-production-system
    ] [
      run-weighted-choice-model
    ]
  ]

  let repeat-voters voters with [ voted? and last-vote != 0 ]
  ifelse any? repeat-voters [
    set switch-rate 100 *
      count repeat-voters with [ vote-choice != last-vote ] /
      count repeat-voters
  ] [
    set switch-rate 0
  ]

  set blue-votes count voters with [ vote-choice = -1 ]
  set red-votes count voters with [ vote-choice = 1 ]
  set total-votes blue-votes + red-votes
  set turnout-rate 100 * total-votes / count voters

  ifelse total-votes > 0 [
    set blue-share 100 * blue-votes / total-votes
    set red-share 100 * red-votes / total-votes
  ] [
    set blue-share 50
    set red-share 50
  ]

  set election-margin abs (blue-share - red-share)

  ifelse red-votes > blue-votes [
    set winner-id 1
    set winner-name "Red"
  ] [
    ifelse blue-votes > red-votes [
      set winner-id -1
      set winner-name "Blue"
    ] [
      set winner-id one-of (list -1 1)
      ifelse winner-id = -1
        [ set winner-name "Blue (tie-break)" ]
        [ set winner-name "Red (tie-break)" ]
    ]
  ]
end


;; Original continuous voter model, retained for direct comparison.
to run-weighted-choice-model
  set blue-reasons 0
  set red-reasons 0
  set turnout-reasons 0
  set abstention-reasons 0
  set rule-trace "weighted equation"

  set choice-score
    (abs (ideology - blue-position) - abs (ideology - red-position))
    + identity-strength * party-identity
    + random-normal 0 election-noise

  set turnout-probability clamp-value
    (base-turnout + turnout-sensitivity * abs choice-score) 0 1

  set voted? (random-float 1 < turnout-probability)

  ifelse choice-score < 0
    [ set intended-choice -1 ]
    [ set intended-choice 1 ]

  ifelse voted?
    [ set vote-choice intended-choice ]
    [ set vote-choice 0 ]
end


;; Every voter executes this same production system once per election.
;; Each enabled rule is a separate IF-THEN production.  Rules add discrete
;; reasons to working memory rather than contributing continuous weights.
to run-production-system
  set blue-reasons 0
  set red-reasons 0
  set turnout-reasons 0
  set abstention-reasons 0
  set rule-trace ""

  let blue-distance abs (ideology - blue-position)
  let red-distance abs (ideology - red-position)
  let policy-advantage blue-distance - red-distance
  let effective-identity identity-strength * party-identity

  ;; Preliminary activation thresholds.  These are deliberately collected
  ;; here so they are easy to inspect and revise as the rule set develops.
  let policy-threshold 0.15
  let identity-threshold 0.25
  let strong-policy-threshold 0.35
  let strong-identity-threshold 0.60
  let neighbor-majority-threshold 0.60
  let alienation-threshold 0.55

  ;; RULE 1: POLICY PROXIMITY
  ;; IF one party is substantially closer, THEN add a reason for that party.
  if rule-policy? [
    if policy-advantage < (0 - policy-threshold) [
      set blue-reasons blue-reasons + 1
      set rule-trace word rule-trace "policy->Blue; "
    ]
    if policy-advantage > policy-threshold [
      set red-reasons red-reasons + 1
      set rule-trace word rule-trace "policy->Red; "
    ]
  ]

  ;; RULE 2: PARTISAN IDENTITY
  ;; IF partisan identity is sufficiently strong, THEN add a party reason.
  if rule-identity? [
    if effective-identity <= (0 - identity-threshold) [
      set blue-reasons blue-reasons + 1
      set rule-trace word rule-trace "identity->Blue; "
    ]
    if effective-identity >= identity-threshold [
      set red-reasons red-reasons + 1
      set rule-trace word rule-trace "identity->Red; "
    ]
  ]

  ;; RULE 3: VOTING HABIT
  ;; IF the voter previously chose a party, THEN add a reason to repeat it.
  if rule-habit? [
    if last-vote = -1 [
      set blue-reasons blue-reasons + 1
      set rule-trace word rule-trace "habit->Blue; "
    ]
    if last-vote = 1 [
      set red-reasons red-reasons + 1
      set rule-trace word rule-trace "habit->Red; "
    ]
  ]

  ;; RULE 4: SOCIAL MAJORITY
  ;; IF a clear majority of politically active neighbors previously chose one
  ;; party, THEN add a reason for that party.
  if (rule-neighbors? and social-network? and any? link-neighbors) [
    let active-neighbors link-neighbors with [ last-vote != 0 ]
    if any? active-neighbors [
      let red-neighbor-fraction
        (count active-neighbors with [ last-vote = 1 ]) / count active-neighbors

      if red-neighbor-fraction <= (1 - neighbor-majority-threshold) [
        set blue-reasons blue-reasons + 1
        set rule-trace word rule-trace "neighbors->Blue; "
      ]
      if red-neighbor-fraction >= neighbor-majority-threshold [
        set red-reasons red-reasons + 1
        set rule-trace word rule-trace "neighbors->Red; "
      ]
    ]
  ]

  ;; RULE 5: ENGAGEMENT
  ;; IF policy preference or identity is strong, THEN add a turnout reason.
  if rule-engagement? [
    if abs policy-advantage >= strong-policy-threshold [
      set turnout-reasons turnout-reasons + 1
      set rule-trace word rule-trace "strong-policy->turnout; "
    ]
    if abs effective-identity >= strong-identity-threshold [
      set turnout-reasons turnout-reasons + 1
      set rule-trace word rule-trace "strong-identity->turnout; "
    ]
  ]

  ;; RULE 6: INDIFFERENCE
  ;; IF the parties are nearly equally attractive, THEN add an abstention reason.
  if rule-indifference? [
    if abs policy-advantage <= policy-threshold [
      set abstention-reasons abstention-reasons + 1
      set rule-trace word rule-trace "indifference->abstain; "
    ]
  ]

  ;; RULE 7: ALIENATION
  ;; IF even the nearer party is far away, THEN add an abstention reason.
  if rule-alienation? [
    if min (list blue-distance red-distance) >= alienation-threshold [
      set abstention-reasons abstention-reasons + 1
      set rule-trace word rule-trace "alienation->abstain; "
    ]
  ]

  ;; RULE 8: CROSS-PRESSURE
  ;; IF policy and identity clearly favor opposite parties, THEN add an
  ;; abstention reason.  This rule can fire even if either underlying choice
  ;; rule is switched off, because cross-pressure is itself an independent rule.
  if rule-cross-pressure? [
    let policy-direction 0
    let identity-direction 0

    if policy-advantage < (0 - policy-threshold) [ set policy-direction -1 ]
    if policy-advantage > policy-threshold [ set policy-direction 1 ]
    if effective-identity <= (0 - identity-threshold) [ set identity-direction -1 ]
    if effective-identity >= identity-threshold [ set identity-direction 1 ]

    if (policy-direction != 0 and
        identity-direction != 0 and
        policy-direction != identity-direction) [
      set abstention-reasons abstention-reasons + 1
      set rule-trace word rule-trace "cross-pressure->abstain; "
    ]
  ]

  ;; Conflict resolution: the side with more reasons becomes the intended vote.
  ;; Exact ties are resolved stochastically; election-noise controls the scale of
  ;; that residual uncertainty without continuously weighting the rules.
  set choice-score red-reasons - blue-reasons

  if choice-score < 0 [ set intended-choice -1 ]
  if choice-score > 0 [ set intended-choice 1 ]

  if choice-score = 0 [
    let tie-break 0
    ifelse election-noise > 0
      [ set tie-break random-normal 0 election-noise ]
      [ set tie-break one-of (list -1 1) ]

    ifelse tie-break < 0 [
      set intended-choice -1
      set choice-score -0.001
    ] [
      set intended-choice 1
      set choice-score 0.001
    ]
    set rule-trace word rule-trace "tie-break; "
  ]

  ;; Turnout is still probabilistic, but enabled turnout and abstention rules
  ;; shift the baseline in discrete steps of TURNOUT-SENSITIVITY.
  set turnout-probability clamp-value
    (base-turnout
     + turnout-sensitivity * (turnout-reasons - abstention-reasons))
    0 1

  set voted? (random-float 1 < turnout-probability)
  ifelse voted?
    [ set vote-choice intended-choice ]
    [ set vote-choice 0 ]
end

to adapt-parties
  if not adaptive-parties? [ stop ]

  if winner-id = 1 [
    move-losing-party -1
    move-winning-party 1
  ]

  if winner-id = -1 [
    move-losing-party 1
    move-winning-party -1
  ]

  enforce-party-order
end


to move-losing-party [ loser-id ]
  let opposing-id (0 - loser-id)
  let supporters voters with [ vote-choice = loser-id ]
  let opposing-voters voters with [ vote-choice = opposing-id ]
  let persuadables opposing-voters with [ abs choice-score <= persuadable-band ]

  let electoral-target mean [ ideology ] of voters
  if any? persuadables [
    set electoral-target mean [ ideology ] of persuadables
  ]

  let base-target electoral-target
  if any? supporters [
    set base-target mean [ ideology ] of supporters
  ]

  ;; BASE-PRESSURE = 0 means chase narrowly lost voters.
  ;; BASE-PRESSURE = 1 means move toward current supporters instead.
  let target
    ((1 - base-pressure) * electoral-target + base-pressure * base-target)

  if loser-id = -1 [
    set blue-position
      blue-position + party-adaptation * (target - blue-position)
  ]

  if loser-id = 1 [
    set red-position
      red-position + party-adaptation * (target - red-position)
  ]
end


to move-winning-party [ winning-id ]
  if winner-base-adaptation <= 0 [ stop ]

  let supporters voters with [ vote-choice = winning-id ]
  if not any? supporters [ stop ]
  let target mean [ ideology ] of supporters

  if winning-id = -1 [
    set blue-position
      blue-position + winner-base-adaptation * (target - blue-position)
  ]

  if winning-id = 1 [
    set red-position
      red-position + winner-base-adaptation * (target - red-position)
  ]
end


to enforce-party-order
  set blue-position clamp-value blue-position -1 1
  set red-position clamp-value red-position -1 1

  ;; Keep the named Blue party to the left of the named Red party.
  if blue-position > red-position - 0.02 [
    let midpoint (blue-position + red-position) / 2
    set blue-position clamp-value (midpoint - 0.01) -1 1
    set red-position clamp-value (midpoint + 0.01) -1 1
  ]
end


to update-voter-states
  ;; Voting can reinforce partisan identity, producing path dependence.
  ask voters with [ vote-choice != 0 ] [
    set party-identity clamp-value
      ((1 - identity-reinforcement) * party-identity
       + identity-reinforcement * vote-choice)
      -1 1
    set last-vote vote-choice
  ]

  ;; Opinion updating is synchronous: everyone computes NEXT-IDEOLOGY first.
  ask voters [
    let peer-mean ideology
    if social-network? and any? link-neighbors [
      set peer-mean mean [ ideology ] of link-neighbors
    ]

    set next-ideology clamp-value
      (ideology
       + social-influence * (peer-mean - ideology)
       + random-normal 0 opinion-drift)
      -1 1
  ]

  ask voters [ set ideology next-ideology ]
end


to update-summary-statistics
  set cumulative-margin cumulative-margin + election-margin
  set mean-margin cumulative-margin / (ticks + 1)

  if last-winner-id != 0 and winner-id != last-winner-id [
    set party-control-changes party-control-changes + 1
  ]
  set last-winner-id winner-id

  ifelse ticks > 0
    [ set control-change-rate 100 * party-control-changes / ticks ]
    [ set control-change-rate 0 ]

  set party-gap red-position - blue-position
  set mean-voter-ideology mean [ ideology ] of voters
end


to update-display
  ;; Geometry is a visualization of internal state, never an input to the rules.
  ask voters [
    set xcor ideology * (max-pxcor - 3)
    set ycor display-y

    if vote-choice = -1 [ set color blue + 1 ]
    if vote-choice = 1  [ set color red + 1 ]
    if vote-choice = 0  [ set color gray ]
  ]

  if blue-party != nobody [
    ask blue-party [
      setxy (blue-position * (max-pxcor - 3)) (max-pycor - 2)
    ]
  ]

  if red-party != nobody [
    ask red-party [
      setxy (red-position * (max-pxcor - 3)) (max-pycor - 2)
    ]
  ]

  ask social-links [
    set hidden? not show-links?
    set color gray + 1
    set thickness 0.08
  ]
end


to build-network
  ask social-links [ die ]
  if not social-network? [ stop ]
  if network-degree <= 0 [ stop ]

  let target-links round (count voters * network-degree / 2)
  let attempts 0
  let maximum-attempts max (list 1000 (target-links * 100))

  while [ count social-links < target-links and attempts < maximum-attempts ] [
    set attempts attempts + 1
    let a one-of voters
    let b one-of voters

    if a != b and not [ link-neighbor? b ] of a [
      let ideological-distance abs ([ ideology ] of a - [ ideology ] of b)
      let similarity 1 - ideological-distance / 2
      let acceptance-probability
        ((1 - homophily) + homophily * similarity)

      if random-float 1 < acceptance-probability [
        ask a [ create-social-link-with b ]
      ]
    ]
  ]

  update-display
end


to reset-party-positions
  if not any? parties [
    user-message "Press SETUP before resetting the parties."
    stop
  ]

  set blue-position clamp-value ((0 - initial-party-gap) / 2) -1 1
  set red-position clamp-value (initial-party-gap / 2) -1 1
  enforce-party-order
  set party-gap red-position - blue-position
  update-display
end


to record-history
  set history lput (word
    (ticks + 1) "\t"
    winner-name "\t"
    (precision blue-share 3) "\t"
    (precision red-share 3) "\t"
    (precision turnout-rate 3) "\t"
    (precision election-margin 3) "\t"
    (precision blue-position 4) "\t"
    (precision red-position 4) "\t"
    (precision party-gap 4) "\t"
    (precision mean-voter-ideology 4) "\t"
    (precision switch-rate 3))
    history
end


to export-history
  if not is-list? history [
    user-message "Press SETUP and run at least one election first."
    stop
  ]

  let filename user-new-file
  if filename = false [ stop ]
  if file-exists? filename [ file-delete filename ]

  file-open filename
  foreach history [ line -> file-print line ]
  file-close

  user-message (word "Saved " (length history - 1) " elections as tab-separated text.")
end


to-report clamp-value [ value minimum maximum ]
  report min (list maximum (max (list minimum value)))
end
@#$#@#$#@
GRAPHICS-WINDOW
445
10
960
325
-1
-1
5.0
1
10
1
1
1
0
1
1
1
-50
50
-30
30
1
1
1
elections
30.0

CHOOSER
5
5
215
50
electorate-shape
electorate-shape
"single-peaked" "two-camp"
0

BUTTON
220
5
285
38
setup
setup
NIL
1
T
OBSERVER
NIL
NIL
NIL
NIL
1

BUTTON
290
5
355
38
go
go
T
1
T
OBSERVER
NIL
NIL
NIL
NIL
0

BUTTON
360
5
435
38
one election
go
NIL
1
T
OBSERVER
NIL
NIL
NIL
NIL
0

SLIDER
5
80
215
113
population
population
50
2000
500.0
50
1
voters
HORIZONTAL

SLIDER
220
80
435
113
initial-party-gap
initial-party-gap
0.1
1.8
1.0
0.05
1
NIL
HORIZONTAL

SLIDER
5
114
215
147
ideology-spread
ideology-spread
0.02
0.8
0.25
0.01
1
NIL
HORIZONTAL

SLIDER
220
114
435
147
party-adaptation
party-adaptation
0
1
0.25
0.01
1
NIL
HORIZONTAL

SLIDER
5
148
215
181
electorate-polarization
electorate-polarization
0
0.9
0.35
0.01
1
NIL
HORIZONTAL

SLIDER
220
148
435
181
base-pressure
base-pressure
0
1
0.15
0.01
1
NIL
HORIZONTAL

SLIDER
5
182
215
215
identity-noise
identity-noise
0
1
0.35
0.01
1
NIL
HORIZONTAL

SLIDER
220
182
435
215
persuadable-band
persuadable-band
0.01
1
0.25
0.01
1
NIL
HORIZONTAL

SLIDER
5
216
215
249
identity-strength
identity-strength
0
2
0.6
0.02
1
NIL
HORIZONTAL

SLIDER
220
216
435
249
winner-base-adaptation
winner-base-adaptation
0
0.5
0.03
0.01
1
NIL
HORIZONTAL

SLIDER
5
250
215
283
identity-reinforcement
identity-reinforcement
0
0.25
0.03
0.005
1
NIL
HORIZONTAL

SLIDER
220
250
435
283
base-turnout
base-turnout
0
1
0.55
0.01
1
NIL
HORIZONTAL

SLIDER
5
284
215
317
turnout-sensitivity
turnout-sensitivity
0
0.5
0.12
0.01
1
NIL
HORIZONTAL

SLIDER
220
284
435
317
election-noise
election-noise
0
0.5
0.08
0.01
1
NIL
HORIZONTAL

SLIDER
5
318
215
351
network-degree
network-degree
0
20
6.0
1
1
links/voter
HORIZONTAL

SLIDER
220
318
435
351
homophily
homophily
0
1
0.7
0.01
1
NIL
HORIZONTAL

SLIDER
5
352
215
385
social-influence
social-influence
0
0.5
0.08
0.01
1
NIL
HORIZONTAL

SLIDER
220
352
435
385
opinion-drift
opinion-drift
0
0.1
0.01
0.002
1
NIL
HORIZONTAL

SWITCH
5
395
215
428
adaptive-parties?
adaptive-parties?
0
1
-1000

SWITCH
220
395
435
428
social-network?
social-network?
1
1
-1000

SWITCH
5
430
215
463
show-links?
show-links?
1
1
-1000

BUTTON
220
430
435
463
rebuild network
build-network
NIL
1
T
OBSERVER
NIL
NIL
NIL
NIL
1

BUTTON
5
467
215
500
reset party positions
reset-party-positions
NIL
1
T
OBSERVER
NIL
NIL
NIL
NIL
1

BUTTON
220
467
435
500
export history (TSV)
export-history
NIL
1
T
OBSERVER
NIL
NIL
NIL
NIL
1

TEXTBOX
5
505
435
525
VOTER PRODUCTION SYSTEM
13
0.0
1

SWITCH
5
526
215
559
production-system?
production-system?
0
1
-1000

SWITCH
220
526
435
559
rule-policy?
rule-policy?
0
1
-1000

SWITCH
5
561
215
594
rule-identity?
rule-identity?
0
1
-1000

SWITCH
220
561
435
594
rule-habit?
rule-habit?
0
1
-1000

SWITCH
5
596
215
629
rule-neighbors?
rule-neighbors?
0
1
-1000

SWITCH
220
596
435
629
rule-engagement?
rule-engagement?
0
1
-1000

SWITCH
5
631
215
664
rule-indifference?
rule-indifference?
0
1
-1000

SWITCH
220
631
435
664
rule-alienation?
rule-alienation?
0
1
-1000

SWITCH
5
666
215
699
rule-cross-pressure?
rule-cross-pressure?
0
1
-1000

MONITOR
970
10
1120
55
election
ticks
0
1
11

MONITOR
1125
10
1280
55
winner
winner-name
0
1
11

MONITOR
970
58
1120
103
Blue vote %
blue-share
1
1
11

MONITOR
1125
58
1280
103
Red vote %
red-share
1
1
11

MONITOR
970
106
1120
151
turnout %
turnout-rate
1
1
11

MONITOR
1125
106
1280
151
margin (points)
election-margin
1
1
11

MONITOR
970
154
1120
199
mean margin
mean-margin
1
1
11

MONITOR
1125
154
1280
199
control changes
party-control-changes
0
1
11

MONITOR
970
202
1120
247
Blue position
blue-position
3
1
11

MONITOR
1125
202
1280
247
Red position
red-position
3
1
11

MONITOR
970
250
1120
295
party gap
party-gap
3
1
11

MONITOR
1125
250
1280
295
vote switching %
switch-rate
1
1
11

PLOT
445
335
720
510
Vote share
election
percent
0.0
50.0
0.0
100.0
true
true
"" ""
PENS
"Blue" 1.0 0 -13345367 true "" "plot blue-share"
"Red" 1.0 0 -2674135 true "" "plot red-share"
"Parity" 1.0 0 -16777216 false "" "plot 50"

PLOT
725
335
1000
510
Party positions
election
position
0.0
50.0
-1.0
1.0
true
true
"" ""
PENS
"Blue" 1.0 0 -13345367 true "" "plot blue-position"
"Red" 1.0 0 -2674135 true "" "plot red-position"

PLOT
1005
335
1280
510
Margin and turnout
election
percent / points
0.0
50.0
0.0
100.0
true
true
"" ""
PENS
"margin" 1.0 0 -16777216 true "" "plot election-margin"
"turnout" 1.0 0 -10899396 true "" "plot turnout-rate"

PLOT
445
520
800
700
Voter ideology distribution
ideology
voters
-1.0
1.0
0.0
100.0
true
false
"" "clear-plot"
PENS
"voters" 0.05 1 -7500403 true "" "set-plot-pen-interval 0.05 histogram [ ideology ] of voters"

TEXTBOX
815
530
1280
695
DISPLAY: each voter dot is placed horizontally at its internal ideology. Its vertical position is arbitrary. Party stars display the parties' internal positions. Neither turtle distance nor patch location affects voting or party adaptation. Social influence uses explicit network links, not spatial neighbors.
13
0.0
1
@#$#@#$#@
## WHAT IS IT?

This model asks whether adaptive competition between two parties can produce persistently close elections, and when that near-parity breaks down.  It is intended as a small, modifiable high-school research model rather than a realistic election forecast.

Each tick is one election.  Voters and parties have internal political state.  The turtles' geometric positions are only a display of that state.

## HOW IT WORKS

### Voters

Each voter has:

* an `ideology` between -1 (Blue) and +1 (Red);
* a `party-identity` between -1 and +1;
* a turnout probability;
* a current and previous vote.

The `production-system?` switch selects between two voter decision systems.

When it is off, the original continuous preference equation is used:

`distance advantage for Red + identity-strength * party-identity + noise`

When it is on, every voter executes the same set of explicit IF-THEN productions.  Enabled rules add discrete Blue reasons, Red reasons, turnout reasons, or abstention reasons to the voter's working memory.  The side with more reasons becomes the intended vote; exact ties are broken stochastically.  Turnout begins at `base-turnout`, and each net turnout reason changes it by `turnout-sensitivity`.

The preliminary productions represent policy proximity, partisan identity, voting habit, linked-neighbor majority, political engagement, indifference, alienation, and policy/identity cross-pressure.  In the production system, `identity-strength` changes whether identity crosses the rule thresholds rather than acting as a continuous vote weight.  Every production has its own Interface switch.  The activation thresholds are grouped near the top of `run-production-system` so they can be revised easily.  The `rule-trace` voter variable records which productions fired and can be viewed in a voter inspector.

After voting, `identity-reinforcement` moves partisan identity slightly toward the chosen party.  This lets repeated voting create path dependence or lock-in.

### Parties

The losing party identifies opposing voters whose preference score was within `persuadable-band` of zero.  These are voters it narrowly failed to attract.  It moves toward a mixture of:

* those narrowly lost voters; and
* its own current supporters.

`base-pressure` controls that mixture.  At 0, the loser chases narrowly lost voters.  At 1, it moves toward its own supporters.  `party-adaptation` controls how far it moves in one election.

The winning party may move toward its own supporters at the smaller rate `winner-base-adaptation`.

### Social network

When `social-network?` is on, voters are connected by explicit links.  `network-degree` sets the approximate mean number of links.  `homophily` makes ideologically similar voters more likely to be connected.  Each election, `social-influence` moves a voter toward the mean ideology of linked neighbors.  `opinion-drift` adds a small random movement.

Changing `network-degree` or `homophily` does not alter an already-created network; press REBUILD NETWORK.

### Display versus model state

The view does **not** implement political interaction through geometry.

* A voter's x-coordinate is recalculated from its internal `ideology`.
* Its y-coordinate is arbitrary and only prevents dots from overlapping completely.
* Party stars are placed at the parties' internal policy positions.
* Social influence uses NetLogo links, not distance, patches, `in-radius`, or turtle neighborhoods.

## HOW TO USE IT

1. Choose a single-peaked or two-camp electorate.
2. Adjust parameters or begin with the defaults.
3. Press SETUP.
4. Press ONE ELECTION to inspect individual steps, or GO for repeated elections.
5. Watch vote shares, party positions, margins, turnout, and the ideology histogram.
6. Use EXPORT HISTORY to save one row per election as tab-separated text.

`adaptive-parties?` turns party movement on or off.  `social-network?` turns network influence on or off.  `show-links?` changes only the display.

`production-system?` turns the voter production system on or off.  The eight `rule-...?` switches independently enable or disable its preliminary productions.  With all rule switches off, voters turn out at `base-turnout` and their party choice is a stochastic tie-break.

## SUGGESTED EXPERIMENTS

### 1. Does party adaptation create parity?

Turn the social network off.  Compare `party-adaptation = 0` with positive values.  Measure mean election margin and the number of changes in party control.

### 2. When does adaptation polarize instead of converge?

Sweep `base-pressure` from 0 to 1.  Low values make a losing party chase persuadable opponents; high values make it respond to its existing supporters.  Examine both election margins and party gap.

### 3. Does partisan identity create lock-in?

Compare `identity-reinforcement = 0` with larger values.  Look at vote switching and changes in party control.

### 4. What does a homophilous network do?

Use a two-camp electorate, turn the network on, and vary `homophily` and `social-influence`.  Rebuild the network after changing its structural settings.

### 5. Which voter rules matter?

Turn `production-system?` on and switch off one production at a time.  Compare vote share, turnout, switching, control changes, and party movement with the all-rules condition.  Particularly useful contrasts are policy versus identity, indifference versus alienation, and neighbor influence with versus without ideological opinion updating.

## BEHAVIORSPACE

Two experiments are included under Tools > BehaviorSpace:

* **Parity sweep - adaptation x base pressure**
* **Network sweep - homophily x social influence**

BehaviorSpace repeats simulations while systematically varying parameters, making it useful for replacing impressions from one run with distributions over many runs.

## THINGS TO NOTICE

A close election is not necessarily a stable equilibrium.  Near-parity may result from continuing feedback: a loss causes one party to move, which changes the next electorate-facing contest, which may make the other party lose and adapt.

The same adaptive mechanism can have opposite effects depending on the target.  Chasing marginal opposing voters tends to pull parties inward; responding mainly to existing supporters can pull them outward.

## LIMITATIONS

The model has one policy dimension, two parties, no primaries, no geography, no institutions, and no campaign resources.  Its purpose is to test whether a small set of mechanisms is sufficient to generate qualitative patterns, not to estimate real elections.

The empirical project should compare simulated summary statistics with an observed election series, rather than claim that one simulated run predicts history.

## EXTENDING THE MODEL

Possible extensions include asymmetric party rules, incumbency, third parties, changing economic conditions, district-based elections, primaries, or fitting parameters to historical two-party vote shares.
@#$#@#$#@
default
true
0
Polygon -7500403 true true 150 5 40 250 150 205 260 250

circle
false
0
Circle -7500403 true true 0 0 300

star
false
0
Polygon -7500403 true true 151 1 185 108 298 108 207 175 242 282 151 216 59 282 94 175 3 108 116 108
@#$#@#$#@
NetLogo 6.4.0
@#$#@#$#@
setup
repeat 20 [ go ]
@#$#@#$#@

@#$#@#$#@
<experiments>
  <experiment name="Parity sweep - adaptation x base pressure" repetitions="10" runMetricsEveryStep="false">
    <setup>setup</setup>
    <go>go</go>
    <timeLimit steps="100"/>
    <metric>mean-margin</metric>
    <metric>control-change-rate</metric>
    <metric>party-gap</metric>
    <metric>blue-position</metric>
    <metric>red-position</metric>
    <metric>turnout-rate</metric>
    <enumeratedValueSet variable="social-network?">
      <value value="false"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="adaptive-parties?">
      <value value="true"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="production-system?">
      <value value="false"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="population">
      <value value="500"/>
    </enumeratedValueSet>
    <steppedValueSet variable="party-adaptation" first="0" step="0.1" last="0.5"/>
    <enumeratedValueSet variable="base-pressure">
      <value value="0"/>
      <value value="0.25"/>
      <value value="0.5"/>
      <value value="0.75"/>
      <value value="1"/>
    </enumeratedValueSet>
  </experiment>
  <experiment name="Network sweep - homophily x social influence" repetitions="10" runMetricsEveryStep="false">
    <setup>setup</setup>
    <go>go</go>
    <timeLimit steps="100"/>
    <metric>mean-margin</metric>
    <metric>control-change-rate</metric>
    <metric>party-gap</metric>
    <metric>mean-voter-ideology</metric>
    <metric>switch-rate</metric>
    <enumeratedValueSet variable="social-network?">
      <value value="true"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="adaptive-parties?">
      <value value="true"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="production-system?">
      <value value="false"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="electorate-shape">
      <value value="&quot;two-camp&quot;"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="population">
      <value value="500"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="network-degree">
      <value value="6"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="homophily">
      <value value="0"/>
      <value value="0.25"/>
      <value value="0.5"/>
      <value value="0.75"/>
      <value value="1"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="social-influence">
      <value value="0"/>
      <value value="0.05"/>
      <value value="0.1"/>
      <value value="0.2"/>
      <value value="0.4"/>
    </enumeratedValueSet>
  </experiment>
</experiments>
@#$#@#$#@

@#$#@#$#@
default
0.0
-0.2 0 0.0 1.0
0.0 1 1.0 0.0
0.2 0 0.0 1.0
link direction
true
0
Line -7500403 true 150 150 90 180
Line -7500403 true 150 150 210 180
@#$#@#$#@
0
@#$#@#$#@
