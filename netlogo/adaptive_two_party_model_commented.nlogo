;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
;; ADAPTIVE TWO-PARTY COMPETITION -- HEAVILY COMMENTED TEACHING VERSION
;;
;; PURPOSE
;; -------
;; This model asks a deliberately small political-science question:
;;
;;   Can two parties that adapt after elections generate persistent electoral
;;   parity, and under what conditions does that parity disappear?
;;
;; One tick represents one election.  Individual voters choose whether to vote
;; and, if they do, which party to support.  After the result is known, the
;; losing party may move toward voters it nearly won or toward its existing
;; supporters.  Voters may also slowly influence one another through an
;; explicit social network.
;;
;; IMPORTANT MODELING CHOICE: INTERNAL STATE VERSUS SCREEN POSITION
;; ----------------------------------------------------------------
;; The political calculations use variables such as IDEOLOGY, PARTY-IDENTITY,
;; BLUE-POSITION, and RED-POSITION.  They do NOT use xcor, ycor, patch location,
;; turtle distance, or in-radius.
;;
;; The screen is therefore a graph of the model, not the model's causal space:
;;   * voter x-position displays the voter's internal ideology;
;;   * voter y-position is arbitrary visual jitter;
;;   * party stars display the parties' internal policy positions;
;;   * social influence follows explicit links, not nearby screen positions.
;;
;; NETLOGO COMMENT CONVENTION
;; --------------------------
;; NetLogo has line comments beginning with semicolons, rather than a separate
;; block-comment syntax.  The large semicolon-delimited sections in this file
;; are therefore the equivalent of block comments.
;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;


;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
;; INTERFACE PARAMETER GUIDE
;;
;; The variables below are created automatically by NetLogo because widgets on
;; the Interface tab have these names.  They do not need to be declared in the
;; GLOBALS list, but they are central to understanding the model.
;;
;; ELECTORATE CONSTRUCTION -- used when SETUP creates voters
;; ----------------------------------------------------------
;; electorate-shape
;;   "single-peaked": voter ideologies form one normal distribution around 0.
;;   "two-camp": voters are drawn from two distributions, one left and one
;;   right of center.
;;
;; population
;;   Number of voter turtles.  Larger values reduce random sampling variation
;;   but make the model slower, especially when building a network.
;;
;; ideology-spread
;;   Standard deviation of each ideological distribution.  Larger values make
;;   each distribution wider.  In the two-camp case, it controls spread within
;;   each camp, not the distance between the camps.
;;
;; electorate-polarization
;;   In the two-camp electorate only, this is the absolute location of the two
;;   camp centers.  For example, 0.35 gives centers at -0.35 and +0.35.
;;   It has no effect when electorate-shape is "single-peaked".
;;
;; identity-noise
;;   Initial partisan identity begins near ideology, plus random normal noise.
;;   Zero makes identity almost identical to ideology.  Larger values weaken
;;   that initial correspondence and create cross-pressured voters.
;;
;; PARTY CONSTRUCTION AND ADAPTATION
;; ---------------------------------
;; initial-party-gap
;;   Initial distance between the parties.  Setup places Blue at -gap/2 and Red
;;   at +gap/2.  This parameter is also used by RESET PARTY POSITIONS.
;;
;; adaptive-parties?
;;   When off, party positions never change after elections.  This provides the
;;   baseline needed to test whether adaptation itself creates parity.
;;
;; party-adaptation
;;   Fraction of the distance the losing party moves toward its target after
;;   each election.  Zero means no movement; one means jump all the way to the
;;   target in a single election.
;;
;; persuadable-band
;;   Defines which opposing voters count as "narrowly lost."  A voter is called
;;   persuadable when abs(choice-score) is no greater than this value.  A small
;;   band targets only near-indifferent voters; a large band includes more of
;;   the opposing electorate.
;;
;; base-pressure
;;   Determines the losing party's target:
;;     0 = entirely the mean ideology of narrowly lost opposing voters;
;;     1 = entirely the mean ideology of the party's own current supporters;
;;     between 0 and 1 = a weighted average of those two targets.
;;   Low values usually encourage median-seeking; high values can encourage
;;   movement toward the party base.
;;
;; winner-base-adaptation
;;   Fraction of the distance the winning party moves toward the mean ideology
;;   of its own supporters.  This is separate from the losing party's movement.
;;   At zero, only the loser adapts.
;;
;; VOTE CHOICE, IDENTITY, AND TURNOUT
;; ----------------------------------
;; identity-strength
;;   Weight of partisan identity in the vote-choice score.  At zero, voting is
;;   based only on policy distance plus election noise.  Larger values make
;;   identity capable of overcoming policy-distance differences.
;;
;; identity-reinforcement
;;   After a voter casts a ballot, this is the fraction of the distance that
;;   partisan identity moves toward the chosen party (-1 Blue, +1 Red).  It
;;   creates path dependence: repeated voting can strengthen attachment.
;;
;; base-turnout
;;   Baseline probability of voting before enthusiasm is added.
;;
;; turnout-sensitivity
;;   Adds turnout probability in proportion to abs(choice-score).  A voter with
;;   a strong preference is therefore more likely to vote than an indifferent
;;   voter.  The final probability is clipped to the interval 0 through 1.
;;
;; election-noise
;;   Standard deviation of a new random shock added to every voter's choice
;;   score in every election.  It represents unmodeled campaign events, errors,
;;   candidate impressions, or other election-specific influences.
;;
;; SOCIAL NETWORK AND OPINION CHANGE
;; ---------------------------------
;; social-network?
;;   Turns creation and use of the explicit voter network on or off.
;;
;; network-degree
;;   Approximate desired average number of links per voter.  Because links are
;;   undirected, the target number of links is population * degree / 2.
;;
;; homophily
;;   Controls how strongly ideological similarity affects link formation:
;;     0 = any pair is accepted with equal probability;
;;     1 = acceptance falls linearly with ideological distance;
;;     between = a mixture of random and similarity-based connection.
;;   This affects network construction only.  After changing it, press
;;   REBUILD NETWORK to create a network under the new setting.
;;
;; social-influence
;;   Fraction of the distance each voter moves toward the mean ideology of
;;   linked neighbors after each election.  Zero means no peer influence.
;;
;; opinion-drift
;;   Standard deviation of a small random ideological change after each
;;   election.  It keeps opinions from being perfectly deterministic.
;;
;; DISPLAY ONLY
;; ------------
;; show-links?
;;   Shows or hides network links.  It changes no political calculation.
;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;


;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
;; AGENT TYPES
;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;

;; VOTERS are individual citizens.
breed [ voters voter ]

;; PARTIES are two special turtles used to display the Blue and Red parties.
breed [ parties party ]

;; SOCIAL-LINKS form the explicit, undirected voter network.
;; "Undirected" means that if A is linked to B, B is automatically linked to A.
undirected-link-breed [ social-links social-link ]


;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
;; GLOBAL VARIABLES
;;
;; Globals belong to the model as a whole rather than to one agent.
;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;

globals [
  ;; References to the two party turtles.  These let observer procedures say
  ;; "ask blue-party" rather than searching through all party turtles.
  blue-party
  red-party

  ;; The parties' actual internal policy positions on the -1 to +1 scale.
  ;; These values drive voter choice.  Party turtle xcor merely displays them.
  blue-position
  red-position

  ;; Current-election results.
  blue-votes
  red-votes
  total-votes
  blue-share                 ;; percentage among ballots cast, not population
  red-share
  turnout-rate               ;; percentage of all voters who cast a ballot
  election-margin            ;; absolute percentage-point gap in vote share
  switch-rate                ;; repeat voters changing party since last vote
  winner-id                  ;; -1 for Blue, +1 for Red
  winner-name                ;; display-friendly text for the monitor/export

  ;; Across-election summary statistics.
  cumulative-margin
  mean-margin
  party-control-changes
  last-winner-id
  control-change-rate
  party-gap                  ;; red-position minus blue-position
  mean-voter-ideology

  ;; A list of tab-separated lines.  The first item is the header line; each
  ;; later item records one election and is written by EXPORT HISTORY.
  history
]


;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
;; VOTER INTERNAL STATE
;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;

voters-own [
  ideology
  ;; Policy position from -1 (left/Blue side) to +1 (right/Red side).

  party-identity
  ;; Partisan attachment from -1 (strong Blue) to +1 (strong Red).
  ;; It is conceptually distinct from ideology: a voter may be cross-pressured.

  choice-score
  ;; Current election's net preference.  Negative favors Blue; positive favors
  ;; Red.  Its magnitude indicates strength of preference.

  turnout-probability
  ;; Probability from 0 to 1 that this voter participates in this election.

  vote-choice
  ;; Current election: -1 Blue, 0 abstain, +1 Red.

  last-vote
  ;; Most recent non-abstaining vote.  Abstention does not erase vote history.

  voted?
  ;; Boolean convenience variable: true when the voter turned out this election.

  next-ideology
  ;; Temporary value used for synchronous social updating.  Everyone calculates
  ;; a future ideology before anyone actually changes ideology.

  display-y
  ;; Arbitrary vertical position used only to keep dots visually separated.
]


;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
;; PARTY INTERNAL STATE
;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;

parties-own [
  party-id
  ;; -1 identifies the Blue party and +1 identifies the Red party.
]


;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
;; SETUP: CREATE A FRESH ELECTORATE, PARTIES, AND OPTIONAL NETWORK
;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;

to setup
  ;; Remove all agents, links, plots, and old variable values.
  clear-all

  ;; Place parties symmetrically around zero.  CLAMP-VALUE prevents either
  ;; position from extending beyond the ideological scale [-1, +1].
  set blue-position clamp-value ((0 - initial-party-gap) / 2) -1 1
  set red-position  clamp-value (initial-party-gap / 2) -1 1

  ;; These will be assigned actual party turtles in SETUP-PARTIES.
  set blue-party nobody
  set red-party nobody

  ;; Initialize current-election displays before any election has occurred.
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

  ;; Initialize statistics that accumulate over multiple elections.
  set cumulative-margin 0
  set mean-margin 0
  set party-control-changes 0
  set last-winner-id 0
  set control-change-rate 0
  set party-gap red-position - blue-position
  set mean-voter-ideology 0

  ;; Store the TSV header as the first line in the in-memory history list.
  set history (list (word
    "election\twinner\tblue-share\tred-share\tturnout\tmargin"
    "\tblue-position\tred-position\tparty-gap\tmean-ideology\tswitch-rate"))

  ;; Break setup into named procedures so each conceptual task is visible.
  setup-background
  setup-parties
  setup-voters

  ;; Build links only when the network switch is on.
  if social-network? [ build-network ]

  ;; Translate internal state into screen positions and colors.
  update-display

  ;; Start the election counter at zero.
  reset-ticks
end


;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
;; DISPLAY BACKGROUND
;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;

to setup-background
  ;; White background everywhere.
  ask patches [ set pcolor white ]

  ;; A light vertical line at ideological zero helps orient the display.
  ;; It has no causal effect on voters or parties.
  ask patches with [ pxcor = 0 ] [ set pcolor gray + 3 ]
end


;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
;; CREATE THE TWO PARTY TURTLES
;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;

to setup-parties
  create-parties 1 [
    set party-id -1
    set color blue
    set shape "star"
    set size 3.2
    set label "BLUE"
    set label-color blue - 2

    ;; Save this turtle itself in the global BLUE-PARTY variable.
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


;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
;; CREATE VOTERS AND THEIR INITIAL INTERNAL STATES
;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;

to setup-voters
  create-voters population [
    ;; CENTER is the mean of the normal distribution from which this voter's
    ;; ideology will be drawn.
    let center 0

    ;; In a two-camp electorate, randomly assign each voter to a left-centered
    ;; or right-centered distribution.  ONE-OF chooses one list item uniformly.
    if electorate-shape = "two-camp" [
      set center one-of (list (0 - electorate-polarization) electorate-polarization)
    ]

    ;; Draw ideology from a normal distribution, then clip it to [-1, +1].
    set ideology clamp-value (random-normal center ideology-spread) -1 1

    ;; Initial party identity is correlated with ideology but not identical to
    ;; it.  IDENTITY-NOISE controls the strength of the mismatch.
    set party-identity clamp-value (ideology + random-normal 0 identity-noise) -1 1

    ;; No election has occurred yet, so election-specific variables are blank.
    set choice-score 0
    set turnout-probability 0
    set vote-choice 0
    set last-vote 0
    set voted? false
    set next-ideology ideology

    ;; This y-coordinate is deliberately unrelated to politics.  It gives each
    ;; dot a stable visual row so that dots do not all lie on one horizontal line.
    set display-y (min-pycor + 2 + random-float ((max-pycor - min-pycor) - 7))

    set shape "circle"
    set size 0.65
    set color gray
  ]

  ;; This aggregate is useful for monitoring electorate drift over time.
  set mean-voter-ideology mean [ ideology ] of voters
end


;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
;; GO: ONE COMPLETE ELECTION CYCLE
;;
;; The order matters.  Each tick performs these conceptual stages:
;;   1. maintain network consistency with current switches;
;;   2. voters decide whether and how to vote;
;;   3. parties adapt to the election result;
;;   4. identities and opinions update;
;;   5. summary statistics, display, and history update;
;;   6. advance the election counter.
;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;

to go
  ;; Defensive stop: there is no election without voters.
  if not any? voters [ stop ]

  ;; Interface switches may be changed after SETUP.  Remove links immediately
  ;; when the network is turned off.
  if not social-network? and any? social-links [
    ask social-links [ die ]
  ]

  ;; If the network is turned on after setup and no links exist, construct it.
  ;; Changes to homophily or degree while links already exist require the user
  ;; to press REBUILD NETWORK, because network structure is persistent.
  if social-network? and network-degree > 0 and not any? social-links [
    build-network
  ]

  run-election
  adapt-parties
  update-voter-states
  update-summary-statistics
  update-display
  record-history

  ;; One tick equals one completed election.
  tick
end


;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
;; RUN-ELECTION: COMPUTE INDIVIDUAL CHOICES AND AGGREGATE THE RESULT
;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;

to run-election
  ask voters [
    ;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
    ;; VOTE-CHOICE SCORE
    ;;
    ;; The first term compares policy distances:
    ;;
    ;;   distance to Blue - distance to Red
    ;;
    ;; If Red is closer, distance-to-Blue is larger and this term is positive.
    ;; If Blue is closer, it is negative.
    ;;
    ;; The second term adds partisan identity, scaled by IDENTITY-STRENGTH.
    ;; The final term is a fresh election-specific random shock.
    ;;
    ;; Political calculations use internal variables only.  xcor and ycor are
    ;; not read anywhere in this procedure.
    ;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
    set choice-score
      (abs (ideology - blue-position) - abs (ideology - red-position))
      + identity-strength * party-identity
      + random-normal 0 election-noise

    ;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
    ;; TURNOUT
    ;;
    ;; Everyone begins with BASE-TURNOUT.  Strong preference, measured by the
    ;; absolute score, can increase participation.  CLAMP-VALUE makes sure the
    ;; result remains a legal probability between zero and one.
    ;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
    set turnout-probability clamp-value
      (base-turnout + turnout-sensitivity * abs choice-score) 0 1

    ;; Draw one random number to determine whether this voter participates.
    set voted? (random-float 1 < turnout-probability)

    ;; Among voters, the sign of CHOICE-SCORE determines party choice.
    ;; Exact zero goes to Red because the second branch includes zero; with
    ;; continuous random noise, exact ties are extraordinarily rare.
    ifelse voted? [
      ifelse choice-score < 0
        [ set vote-choice -1 ]
        [ set vote-choice 1 ]
    ] [
      set vote-choice 0
    ]
  ]

  ;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
  ;; VOTE SWITCHING
  ;;
  ;; Only voters who participated now and have a previous non-abstaining vote
  ;; enter this statistic.  Thus abstention is not counted as party switching.
  ;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
  let repeat-voters voters with [ voted? and last-vote != 0 ]

  ifelse any? repeat-voters [
    set switch-rate 100 *
      count repeat-voters with [ vote-choice != last-vote ] /
      count repeat-voters
  ] [
    set switch-rate 0
  ]

  ;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
  ;; AGGREGATE VOTES AND TURNOUT
  ;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
  set blue-votes count voters with [ vote-choice = -1 ]
  set red-votes count voters with [ vote-choice = 1 ]
  set total-votes blue-votes + red-votes

  ;; Turnout denominator is the full voter population.
  set turnout-rate 100 * total-votes / count voters

  ;; Vote-share denominator is ballots cast.  If nobody votes, assign 50/50 so
  ;; plots and later calculations remain defined.
  ifelse total-votes > 0 [
    set blue-share 100 * blue-votes / total-votes
    set red-share 100 * red-votes / total-votes
  ] [
    set blue-share 50
    set red-share 50
  ]

  ;; Absolute percentage-point gap: 51 to 49 gives a margin of 2.
  set election-margin abs (blue-share - red-share)

  ;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
  ;; DETERMINE THE WINNER
  ;;
  ;; An exact vote tie is resolved randomly so that the adaptation stage has a
  ;; winner and loser.  The label records that a tie-break occurred.
  ;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
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


;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
;; ADAPT-PARTIES: APPLY DIFFERENT RULES TO LOSER AND WINNER
;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;

to adapt-parties
  ;; Turning adaptation off creates a fixed-party comparison condition.
  if not adaptive-parties? [ stop ]

  ;; If Red won, Blue is the loser; if Blue won, Red is the loser.
  if winner-id = 1 [
    move-losing-party -1
    move-winning-party 1
  ]

  if winner-id = -1 [
    move-losing-party 1
    move-winning-party -1
  ]

  ;; Keep all positions legal and preserve the named left/right ordering.
  enforce-party-order
end


;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
;; MOVE-LOSING-PARTY: THE MAIN ADAPTIVE POLITICAL MECHANISM
;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;

to move-losing-party [ loser-id ]
  ;; Party ids are symmetric: the opposing id is simply the negative.
  let opposing-id (0 - loser-id)

  ;; Current supporters are voters who actually voted for the losing party.
  ;; Abstainers are not included in this definition of the base.
  let supporters voters with [ vote-choice = loser-id ]

  ;; Start with everyone who voted for the winner.
  let opposing-voters voters with [ vote-choice = opposing-id ]

  ;; Narrow the opposing voters to those whose score was close enough to zero
  ;; that the losing party might plausibly have won them.
  let persuadables opposing-voters with [ abs choice-score <= persuadable-band ]

  ;; Fallback target: the mean ideology of the entire electorate.  This is used
  ;; only when no narrowly lost opposing voters exist.
  let electoral-target mean [ ideology ] of voters

  ;; Preferred electoral target: mean ideology of narrowly lost voters.
  if any? persuadables [
    set electoral-target mean [ ideology ] of persuadables
  ]

  ;; Fallback base target is the electoral target.  This avoids an undefined
  ;; mean when the losing party received no votes.
  let base-target electoral-target

  ;; Normal base target: mean ideology of actual supporters.
  if any? supporters [
    set base-target mean [ ideology ] of supporters
  ]

  ;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
  ;; COMBINE ELECTORAL AND BASE TARGETS
  ;;
  ;; BASE-PRESSURE = 0:
  ;;   target = electoral-target
  ;;
  ;; BASE-PRESSURE = 1:
  ;;   target = base-target
  ;;
  ;; Intermediate values produce a linear weighted average.
  ;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
  let target
    ((1 - base-pressure) * electoral-target + base-pressure * base-target)

  ;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
  ;; MOVE PARTWAY TOWARD THE TARGET
  ;;
  ;; New position = old position + adaptation-rate * remaining distance.
  ;; This is a standard partial-adjustment rule.  At 0.25 the party closes one
  ;; quarter of the gap to its target during this election cycle.
  ;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
  if loser-id = -1 [
    set blue-position
      blue-position + party-adaptation * (target - blue-position)
  ]

  if loser-id = 1 [
    set red-position
      red-position + party-adaptation * (target - red-position)
  ]
end


;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
;; MOVE-WINNING-PARTY: OPTIONAL RESPONSE TO ITS OWN SUPPORTERS
;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;

to move-winning-party [ winning-id ]
  ;; Zero means a winning party holds its position.
  if winner-base-adaptation <= 0 [ stop ]

  let supporters voters with [ vote-choice = winning-id ]

  ;; No supporters means there is no defined base target.
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


;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
;; ENFORCE-PARTY-ORDER: KEEP POSITIONS LEGAL AND NAMES CONSISTENT
;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;

to enforce-party-order
  ;; Keep both parties inside the modeled ideological interval.
  set blue-position clamp-value blue-position -1 1
  set red-position clamp-value red-position -1 1

  ;; This model defines Blue as the party on the left and Red as the party on
  ;; the right.  If adaptation would make them cross or coincide, place them a
  ;; tiny distance apart around their midpoint.  The 0.02 minimum gap is a
  ;; naming convention, not an empirically estimated political claim.
  if blue-position > red-position - 0.02 [
    let midpoint (blue-position + red-position) / 2
    set blue-position clamp-value (midpoint - 0.01) -1 1
    set red-position clamp-value (midpoint + 0.01) -1 1
  ]
end


;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
;; UPDATE-VOTER-STATES: REINFORCE IDENTITY AND UPDATE IDEOLOGY
;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;

to update-voter-states
  ;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
  ;; PARTISAN IDENTITY REINFORCEMENT
  ;;
  ;; A voter who voted moves identity toward the chosen party id.  For example,
  ;; with reinforcement 0.03, identity closes 3% of the remaining distance to
  ;; -1 or +1.  Abstainers receive no identity reinforcement this election.
  ;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
  ask voters with [ vote-choice != 0 ] [
    set party-identity clamp-value
      ((1 - identity-reinforcement) * party-identity
       + identity-reinforcement * vote-choice)
      -1 1

    ;; Save the current vote for next election's switching statistic.
    set last-vote vote-choice
  ]

  ;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
  ;; SYNCHRONOUS SOCIAL INFLUENCE
  ;;
  ;; Everyone computes NEXT-IDEOLOGY from the old state first.  Only after all
  ;; calculations are finished do voters copy NEXT-IDEOLOGY into IDEOLOGY.
  ;; This prevents arbitrary ASK order from making early-updated voters affect
  ;; later-updated voters during the same election cycle.
  ;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
  ask voters [
    ;; A voter without usable neighbors simply has itself as the peer mean, so
    ;; the social-influence term becomes zero.
    let peer-mean ideology

    if social-network? and any? link-neighbors [
      set peer-mean mean [ ideology ] of link-neighbors
    ]

    ;; Move toward peers, add independent random drift, and clip to [-1, +1].
    set next-ideology clamp-value
      (ideology
       + social-influence * (peer-mean - ideology)
       + random-normal 0 opinion-drift)
      -1 1
  ]

  ;; Commit all opinion changes simultaneously.
  ask voters [ set ideology next-ideology ]
end


;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
;; UPDATE SUMMARY STATISTICS ACROSS ELECTIONS
;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;

to update-summary-statistics
  ;; Running mean of absolute election margins.
  set cumulative-margin cumulative-margin + election-margin
  set mean-margin cumulative-margin / (ticks + 1)

  ;; Count winner changes, excluding the first election because it has no prior
  ;; winner to compare with.
  if last-winner-id != 0 and winner-id != last-winner-id [
    set party-control-changes party-control-changes + 1
  ]
  set last-winner-id winner-id

  ;; TICKS is still the number of previously completed elections at this point.
  ;; After the first election it is zero, so guard against division by zero.
  ifelse ticks > 0
    [ set control-change-rate 100 * party-control-changes / ticks ]
    [ set control-change-rate 0 ]

  set party-gap red-position - blue-position
  set mean-voter-ideology mean [ ideology ] of voters
end


;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
;; UPDATE DISPLAY: MAP INTERNAL POLITICAL STATE TO SCREEN GEOMETRY
;;
;; This procedure is intentionally one-way.  Internal state determines screen
;; position and color.  No political procedure later reads the screen position.
;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;

to update-display
  ask voters [
    ;; Map ideology [-1,+1] to almost the full horizontal width of the world.
    set xcor ideology * (max-pxcor - 3)

    ;; Reuse the arbitrary y-position assigned at setup.
    set ycor display-y

    ;; Color indicates the current election action, not permanent identity.
    if vote-choice = -1 [ set color blue + 1 ]
    if vote-choice = 1  [ set color red + 1 ]
    if vote-choice = 0  [ set color gray ]
  ]

  ;; Party stars sit near the top so they remain visually distinct from voters.
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

  ;; SHOW-LINKS? affects hiddenness only.  Hidden links still exist and can
  ;; still transmit social influence.
  ask social-links [
    set hidden? not show-links?
    set color gray + 1
    set thickness 0.08
  ]
end


;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
;; BUILD NETWORK: CREATE AN APPROXIMATE-DEGREE HOMOPHILOUS SOCIAL GRAPH
;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;

to build-network
  ;; Rebuilding means replace, not add to, the current network.
  ask social-links [ die ]

  ;; These conditions make the button safe under any interface setting.
  if not social-network? [ stop ]
  if network-degree <= 0 [ stop ]

  ;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
  ;; TARGET NUMBER OF LINKS
  ;;
  ;; Sum of all voter degrees = 2 * number of undirected links.  Therefore an
  ;; average degree D among N voters requires about N * D / 2 links.
  ;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
  let target-links round (count voters * network-degree / 2)

  ;; Because candidate pairs are proposed randomly and may be rejected, impose
  ;; an attempt limit so extreme settings cannot create an endless loop.
  let attempts 0
  let maximum-attempts max (list 1000 (target-links * 100))

  while [ count social-links < target-links and attempts < maximum-attempts ] [
    set attempts attempts + 1

    ;; Propose two random voters.
    let a one-of voters
    let b one-of voters

    ;; Reject self-links and duplicate links.
    if a != b and not [ link-neighbor? b ] of a [
      ;; Ideological distance ranges from 0 to 2.
      let ideological-distance abs ([ ideology ] of a - [ ideology ] of b)

      ;; Similarity therefore ranges from 1 for identical ideology to 0 for
      ;; opposite endpoints of the scale.
      let similarity 1 - ideological-distance / 2

      ;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
      ;; LINK ACCEPTANCE PROBABILITY
      ;;
      ;; homophily = 0: probability is always 1.
      ;; homophily = 1: probability equals similarity.
      ;; intermediate values blend those two cases.
      ;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
      let acceptance-probability
        ((1 - homophily) + homophily * similarity)

      if random-float 1 < acceptance-probability [
        ask a [ create-social-link-with b ]
      ]
    ]
  ]

  update-display
end


;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
;; RESET PARTY POSITIONS WITHOUT RECREATING VOTERS OR THE NETWORK
;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;

to reset-party-positions
  ;; The button is meaningful only after SETUP has created party turtles.
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


;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
;; RECORD ONE TAB-SEPARATED HISTORY ROW IN MEMORY
;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;

to record-history
  ;; TICKS has not yet advanced, so the election just completed is ticks + 1.
  ;; PRECISION controls displayed decimal places without changing internal data.
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


;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
;; EXPORT THE IN-MEMORY HISTORY LIST AS A TSV FILE
;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;

to export-history
  ;; Defensive check for calling the procedure before SETUP.
  if not is-list? history [
    user-message "Press SETUP and run at least one election first."
    stop
  ]

  ;; Open a standard file-save dialog.  FALSE means the user canceled.
  let filename user-new-file
  if filename = false [ stop ]

  ;; NetLogo will otherwise append to an existing file; explicitly replace it.
  if file-exists? filename [ file-delete filename ]

  file-open filename
  foreach history [ line -> file-print line ]
  file-close

  user-message (word "Saved " (length history - 1) " elections as tab-separated text.")
end


;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
;; GENERAL HELPER REPORTER
;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;

to-report clamp-value [ value minimum maximum ]
  ;; First take max(value, minimum), then min(that result, maximum).
  ;; The result can never lie outside the requested interval.
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

This is the **heavily commented teaching version** of the Adaptive Two-Party Competition model. It asks whether repeated adaptation by two political parties can generate persistently close elections, and under what conditions that near-parity breaks down.

The model is intentionally smaller than a realistic election system. Its purpose is to make mechanisms visible and testable. A student should be able to identify every important assumption, change one assumption at a time, and observe the result.

Each tick is one election.

## THE CENTRAL MODELING DISTINCTION

Voters and parties have **internal political state**. Their positions in the NetLogo world are only a visualization of that state.

A voter has an internal `ideology` from -1 to +1. The display procedure places the voter horizontally according to that value, but voting calculations use `ideology` itself—not `xcor`, `ycor`, turtle distance, patches, or spatial neighborhoods.

Similarly, the party stars display the internal variables `blue-position` and `red-position`. Social influence follows explicit NetLogo links rather than screen proximity.

This distinction matters because it separates:

* the theoretical state of an agent;
* the rules that transform that state; and
* the picture used to help a human inspect it.

## AGENTS AND RELATIONS

The model contains three kinds of object:

1. **Voter turtles**, representing individual citizens.
2. **Party turtles**, representing the Blue and Red parties.
3. **Social links**, representing persistent relationships through which opinions may influence one another.

The party turtles are mostly display objects. The actual party positions are global variables because each party has one system-wide policy position.

## ONE ELECTION CYCLE

Every press of ONE ELECTION, or every iteration of GO, performs the following stages in order:

1. Ensure the network matches the current on/off switch.
2. Calculate each voter’s preference between the parties.
3. Calculate each voter’s probability of turnout.
4. Draw whether each voter participates.
5. Count votes and determine the winner.
6. Move the losing party and, optionally, the winning party.
7. Reinforce the partisan identity of voters who participated.
8. Update ideology through linked peers and random drift.
9. Update statistics, plots, display positions, and export history.
10. Advance the tick counter by one election.

The order is part of the theory. For example, parties react to the electorate that voted in the just-completed election; voter opinions then change before the next election.

## HOW VOTERS CHOOSE

Each voter’s `choice-score` is:

`distance to Blue - distance to Red + identity contribution + random election shock`

A positive score favors Red. A negative score favors Blue.

The policy-distance term works because a voter closer to Red has a larger distance to Blue than to Red, producing a positive difference. `identity-strength` determines how much partisan attachment matters relative to policy distance. `election-noise` adds a new random shock for every voter in every election.

## HOW TURNOUT WORKS

A voter’s turnout probability begins at `base-turnout`. It then increases with the absolute strength of the voter’s preference:

`base-turnout + turnout-sensitivity * abs(choice-score)`

The result is restricted to the interval from 0 to 1. Thus, in this model, strongly committed voters tend to participate more often than nearly indifferent voters.

## HOW THE LOSING PARTY ADAPTS

The losing party considers two possible targets.

The **electoral target** is the mean ideology of opposing voters whose choice score lies within `persuadable-band` of zero. These are voters the losing party narrowly failed to attract.

The **base target** is the mean ideology of voters who supported the losing party.

`base-pressure` mixes those two targets:

* 0 means respond entirely to narrowly lost opposing voters;
* 1 means respond entirely to current supporters;
* intermediate values create a weighted average.

`party-adaptation` determines what fraction of the remaining distance the losing party travels toward that target after one election.

The winning party has a separate, usually smaller, rule. `winner-base-adaptation` moves it toward the mean ideology of its own supporters.

## HOW IDENTITY CHANGES

After voting, a voter’s `party-identity` moves slightly toward the chosen party. `identity-reinforcement` controls the fraction of the remaining distance moved in one election.

This creates path dependence. Voting Blue can make future Blue voting more likely, even if ideology itself has not changed. Abstainers receive no reinforcement during that election, and abstention does not erase the last recorded party vote.

## HOW THE SOCIAL NETWORK WORKS

When `social-network?` is on, the model builds an undirected network among voters.

`network-degree` sets the approximate desired average number of links per voter. Because every undirected link contributes one degree to each endpoint, the model aims for approximately:

`population * network-degree / 2`

links.

`homophily` changes the probability that a proposed pair becomes linked. At zero, ideological similarity does not matter. At one, identical voters are most likely to connect and voters at opposite ideological endpoints have zero acceptance probability.

The network is persistent. Changing `homophily` or `network-degree` does not retroactively alter links, so press REBUILD NETWORK after changing either parameter.

After each election, `social-influence` moves each voter partway toward the mean ideology of linked neighbors. `opinion-drift` adds an independent random change.

Opinion updating is synchronous: every voter first computes `next-ideology` from the old network state, and only then do all voters adopt their new values. This prevents NetLogo’s agent execution order from becoming an unintended causal mechanism.

## PARAMETER REFERENCE

### Electorate construction

**electorate-shape**

`single-peaked` draws everyone from one normal distribution centered at zero. `two-camp` draws each voter from either a left-centered or right-centered normal distribution.

**population**

Number of voter agents. Larger populations reduce random sampling fluctuations but take more time to simulate and network.

**ideology-spread**

Standard deviation of the ideological distribution. In a two-camp electorate it controls variation within each camp.

**electorate-polarization**

Distance of each camp center from zero in the two-camp condition. A value of 0.35 creates centers at -0.35 and +0.35. It has no effect on a single-peaked electorate.

**identity-noise**

Random mismatch between initial ideology and initial partisan identity. Zero makes the two almost identical; larger values create more cross-pressured voters.

### Initial party positions and adaptation

**initial-party-gap**

Initial distance between the parties. Blue begins at negative half the gap and Red at positive half.

**adaptive-parties?**

Turns all post-election party movement on or off.

**party-adaptation**

Fraction of the distance the losing party moves toward its current target. Zero means no movement. One means complete movement in one step.

**persuadable-band**

Maximum absolute choice score for an opposing voter to count as narrowly lost. Small values select only very close calls; large values create a broader persuasion target.

**base-pressure**

Weight given to existing supporters rather than narrowly lost opposing voters when constructing the losing party’s target.

**winner-base-adaptation**

Fraction of the distance the winning party moves toward its own supporters.

### Voting, partisan identity, and turnout

**identity-strength**

Weight of partisan identity in vote choice. At zero, identity has no direct electoral effect.

**identity-reinforcement**

Fraction of the distance a voter’s identity moves toward the party just supported.

**base-turnout**

Baseline probability that every voter participates.

**turnout-sensitivity**

Additional turnout associated with strength of preference.

**election-noise**

Standard deviation of random election-specific shocks to vote choice.

### Network and opinion change

**social-network?**

Turns network construction and network influence on or off.

**network-degree**

Approximate target average number of social links per voter.

**homophily**

Strength of preference for links between ideologically similar voters.

**social-influence**

Fraction of the distance a voter moves toward linked neighbors’ mean ideology after each election.

**opinion-drift**

Standard deviation of random ideological movement after each election.

**show-links?**

Display-only switch. Hidden links still exist and still influence voters.

## OUTPUTS AND MONITORS

**Blue vote % / Red vote %** report shares among ballots cast, not shares of the whole population.

**turnout %** reports the percentage of all voter agents who participated.

**margin** is the absolute percentage-point difference between party vote shares.

**mean margin** is the running average of election margins across the current simulation.

**control changes** counts transitions from one winning party to the other. The first election cannot count as a change because there is no previous winner.

**Blue position / Red position** show the parties’ internal policy positions.

**party gap** is `red-position - blue-position`.

**vote switching %** is calculated only among voters who participated in the current election and also have a previous non-abstaining vote.

## BUTTONS

**SETUP** creates an entirely new electorate, resets the parties and statistics, and builds a new network when enabled.

**GO** repeatedly runs elections.

**ONE ELECTION** runs exactly one election cycle, useful for inspecting causal order.

**REBUILD NETWORK** discards current links and constructs new links using the current degree and homophily settings.

**RESET PARTY POSITIONS** returns the parties to positions implied by `initial-party-gap` without recreating voters or links.

**EXPORT HISTORY (TSV)** writes one tab-separated row per election, plus a header row.

## RECOMMENDED FIRST EXPERIMENT

The cleanest first study is a comparison of party adaptation with a fixed-party baseline.

1. Turn `social-network?` off.
2. Set `identity-reinforcement`, `opinion-drift`, and `winner-base-adaptation` to zero.
3. Compare `party-adaptation = 0` with several positive values.
4. Repeat each condition many times because election noise and sampled electorates create variation.
5. Compare `mean-margin`, `control-change-rate`, and final `party-gap`.

This isolates the proposition that losing-party adaptation can itself create a feedback process tending toward close competition.

## FURTHER EXPERIMENTS

### Electoral responsiveness versus base pressure

Sweep `base-pressure` from 0 to 1 while varying `party-adaptation`. Test whether parties converge when they pursue narrowly lost voters but diverge when they respond mainly to supporters.

### Partisan identity and lock-in

Compare `identity-reinforcement = 0` with larger values. Examine vote switching, control changes, and whether early random election outcomes produce persistent differences.

### Network homophily and polarization

Use a two-camp electorate and vary `homophily` and `social-influence`. Rebuild the network for every structural condition. Examine the ideology histogram and party gap in addition to election margins.

### Turnout and apparent parity

Vary `turnout-sensitivity`. A model may produce close vote shares even when the full electorate is not evenly divided, because participation depends on preference strength.

## BEHAVIORSPACE

Two experiments are included under Tools > BehaviorSpace:

* **Parity sweep - adaptation x base pressure**
* **Network sweep - homophily x social influence**

BehaviorSpace repeats the model across parameter combinations and random runs. This is preferable to drawing a conclusion from one visually interesting simulation.

## WHAT WOULD COUNT AS A RESULT?

A useful conclusion is not “the model proves why American elections are close.” A defensible conclusion has the form:

> Under this explicit set of assumptions, mechanism X is sufficient—or insufficient—to generate pattern Y over repeated simulations.

Examples include:

* Losing-party pursuit of narrowly lost voters reduces average margins.
* Strong base pressure prevents convergence or increases party separation.
* Identity reinforcement reduces vote switching and produces historical lock-in.
* Homophilous networks alter the ideological distribution without necessarily changing average election margins.

## LIMITATIONS

The model contains one ideological dimension, two parties, no primaries, no districts, no institutions, no campaign spending, no incumbency, and no changing economy. Parties use simple mechanical adaptation rules and possess information that real organizations may not have.

These omissions are not hidden errors; they define the scope of the experiment. Extensions should be added only when they answer a specific research question.

## EXTENDING THE MODEL

Possible extensions include asymmetric party strategies, primary electorates, third parties, incumbency, issue salience, economic shocks, district-based elections, endogenous turnout campaigns, or comparison with historical two-party vote-share summaries.

Before adding complexity, preserve a baseline version. Then change one mechanism at a time so that any change in behavior can be interpreted.
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
