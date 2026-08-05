;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
;; ADAPTIVE TWO-PARTY COMPETITION WITH VOTER PRODUCTIONS
;; -- HEAVILY COMMENTED TEACHING VERSION
;;
;; PURPOSE
;; -------
;; This model asks a deliberately small political-science question:
;;
;;   Can two parties that adapt after elections generate persistent electoral
;;   parity, and under what conditions does that parity disappear?
;;
;; One tick represents one election.  Individual voters choose whether to vote
;; and, if they do, which party to support.  The Interface can select either
;; the original continuous weighted-choice equation or an explicit production
;; system in which every voter executes the same switchable IF-THEN rules.
;; After the result is known, the losing party may move toward voters it nearly
;; won or toward its existing supporters.  Voters may also slowly influence one
;; another through an explicit social network.
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
;;   persuadable when abs(choice-score) is no greater than this value.  Under the
;;   weighted model the score is continuous.  Under the production model it is
;;   normally an integer reason-count difference, so the default 0.25 includes
;;   essentially only tied reason sets; a value of at least 1 includes voters
;;   decided by one reason.
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
;; VOTER DECISION ARCHITECTURE
;; ---------------------------
;; production-system?
;;   Off selects the original continuous weighted equation.  On selects the
;;   explicit production system.  This master switch makes the two decision
;;   architectures directly comparable while leaving the rest of the model
;;   unchanged.
;;
;; rule-policy?
;;   Enables policy-proximity productions.  A party must be more than 0.15
;;   closer than its opponent before the voter receives a reason for it.
;;
;; rule-identity?
;;   Enables partisan-identity productions.  IDENTITY-STRENGTH scales identity
;;   before it is compared with the activation threshold of 0.25.
;;
;; rule-habit?
;;   Enables a repetition production based on LAST-VOTE, the voter's most
;;   recent non-abstaining ballot.
;;
;; rule-neighbors?
;;   Enables a social-majority production.  At least 60% of linked neighbors
;;   with a previous vote must support one party.  It can fire only when the
;;   social network is enabled and the voter has politically active neighbors.
;;
;; rule-engagement?
;;   Enables turnout productions for a strong policy preference (at least
;;   0.35) and for strong effective identity (at least 0.60).  Both can fire,
;;   yielding two turnout reasons.
;;
;; rule-indifference?
;;   Enables an abstention production when the two parties differ in policy
;;   attractiveness by no more than 0.15.
;;
;; rule-alienation?
;;   Enables an abstention production when even the closer party is at least
;;   0.55 ideological units away.
;;
;; rule-cross-pressure?
;;   Enables an abstention production when policy and partisan identity both
;;   clearly activate but point toward opposite parties.
;;
;; In the production system, each enabled production adds one discrete reason
;; to BLUE-REASONS, RED-REASONS, TURNOUT-REASONS, or ABSTENTION-REASONS.  The
;; rule switches therefore change which considerations exist, not merely their
;; numerical weights.  RULE-TRACE records the productions that fired.
;;
;; VOTE CHOICE, IDENTITY, AND TURNOUT
;; ----------------------------------
;; identity-strength
;;   In the weighted model, this continuously scales identity in the vote-choice
;;   score.  In the production model, it scales identity before the result is
;;   compared with activation thresholds.  At zero, identity productions cannot
;;   fire; larger values make them easier to activate.
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
;;   In the weighted model, adds turnout probability in proportion to
;;   abs(choice-score).  In the production model, it is the size of each discrete
;;   net turnout- or abstention-reason step.  The probability is clipped to 0..1.
;;
;; election-noise
;;   In the weighted model, this is the standard deviation of a random shock
;;   added to choice.  In the production model, it supplies the sign of the
;;   stochastic party tie-break when Blue and Red reason counts are equal.
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
  ;; Current election's net party preference.  In the weighted model this is a
  ;; continuous score.  In the production model it is RED-REASONS minus
  ;; BLUE-REASONS, except that a stochastic tie-break is stored as +/-0.001.

  turnout-probability
  ;; Probability from 0 to 1 that this voter participates in this election.

  vote-choice
  ;; Current election: -1 Blue, 0 abstain, +1 Red.

  intended-choice
  ;; Party selected before turnout is drawn: -1 Blue or +1 Red.  Keeping this
  ;; separate from VOTE-CHOICE lets an abstainer still have a latent preference.

  last-vote
  ;; Most recent non-abstaining vote.  Abstention does not erase vote history.

  voted?
  ;; Boolean convenience variable: true when the voter turned out this election.

  next-ideology
  ;; Temporary value used for synchronous social updating.  Everyone calculates
  ;; a future ideology before anyone actually changes ideology.

  display-y
  ;; Arbitrary vertical position used only to keep dots visually separated.

  ;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
  ;; PRODUCTION-SYSTEM WORKING MEMORY
  ;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;

  blue-reasons
  ;; Number of enabled productions that fired in favor of Blue this election.

  red-reasons
  ;; Number of enabled productions that fired in favor of Red this election.

  turnout-reasons
  ;; Number of enabled productions that increased the inclination to vote.

  abstention-reasons
  ;; Number of enabled productions that decreased the inclination to vote.

  rule-trace
  ;; Human-readable semicolon-separated record of fired productions.  Inspect a
  ;; voter after an election to see why its party and turnout decisions occurred.
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
    set intended-choice 0
    set last-vote 0
    set voted? false
    set next-ideology ideology

    ;; Clear production-system working memory.  These values are reset again at
    ;; the start of every election, whether or not the production system is used.
    set blue-reasons 0
    set red-reasons 0
    set turnout-reasons 0
    set abstention-reasons 0
    set rule-trace ""

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
  ;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
  ;; INDIVIDUAL DECISION ARCHITECTURE
  ;;
  ;; Every voter uses the same architecture in a given run.  The master switch
  ;; selects either the explicit production system or the original weighted
  ;; equation.  The procedures themselves operate in turtle context because
  ;; they are called inside ASK VOTERS.
  ;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
  ask voters [
    ifelse production-system? [
      run-production-system
    ] [
      run-weighted-choice-model
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
;; ORIGINAL WEIGHTED VOTER MODEL
;;
;; This procedure is retained as a comparison condition.  It combines policy,
;; identity, and election noise into one continuous score rather than allowing
;; independently inspectable productions to fire.
;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;

to run-weighted-choice-model
  ;; Clear working-memory fields so inspectors never show reasons left over from
  ;; an earlier election run under the production system.
  set blue-reasons 0
  set red-reasons 0
  set turnout-reasons 0
  set abstention-reasons 0
  set rule-trace "weighted equation"

  ;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
  ;; VOTE-CHOICE SCORE
  ;;
  ;; The first term is distance to Blue minus distance to Red.  It is negative
  ;; when Blue is closer and positive when Red is closer.  Identity contributes
  ;; continuously according to IDENTITY-STRENGTH, and a new normal random shock
  ;; represents unmodeled election-specific influences.
  ;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
  set choice-score
    (abs (ideology - blue-position) - abs (ideology - red-position))
    + identity-strength * party-identity
    + random-normal 0 election-noise

  ;; Stronger absolute preference increases turnout in the weighted model.
  set turnout-probability clamp-value
    (base-turnout + turnout-sensitivity * abs choice-score) 0 1

  set voted? (random-float 1 < turnout-probability)

  ;; Save latent party preference before participation is resolved.
  ifelse choice-score < 0
    [ set intended-choice -1 ]
    [ set intended-choice 1 ]

  ifelse voted?
    [ set vote-choice intended-choice ]
    [ set vote-choice 0 ]
end


;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
;; EXPLICIT VOTER PRODUCTION SYSTEM
;;
;; Every voter executes exactly the same productions.  Heterogeneous behavior
;; arises because voters have different ideologies, identities, histories, and
;; neighbors.  Enabled productions add discrete reasons to working memory.
;;
;; The productions are deliberately written as separate IF statements rather
;; than one IFELSE chain.  Several rules can therefore fire in the same cycle,
;; creating reinforcement, conflict, or cross-pressure that is resolved only
;; after all enabled rules have been evaluated.
;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;

to run-production-system
  ;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
  ;; CLEAR WORKING MEMORY
  ;;
  ;; Nothing carries over except durable voter state such as PARTY-IDENTITY and
  ;; LAST-VOTE.  The reason counters and trace describe only the current election.
  ;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
  set blue-reasons 0
  set red-reasons 0
  set turnout-reasons 0
  set abstention-reasons 0
  set rule-trace ""

  ;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
  ;; PRECOMPUTED PERCEPTUAL QUANTITIES
  ;;
  ;; POLICY-ADVANTAGE is distance-to-Blue minus distance-to-Red, matching the
  ;; sign convention of the weighted model: negative favors Blue, positive Red.
  ;; EFFECTIVE-IDENTITY lets the existing IDENTITY-STRENGTH slider regulate how
  ;; readily partisan identity crosses the production threshold.
  ;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
  let blue-distance abs (ideology - blue-position)
  let red-distance abs (ideology - red-position)
  let policy-advantage blue-distance - red-distance
  let effective-identity identity-strength * party-identity

  ;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
  ;; PRELIMINARY ACTIVATION THRESHOLDS
  ;;
  ;; These constants are grouped here so that rule conditions remain readable
  ;; and the preliminary theory can be revised in one place.  They are not yet
  ;; Interface sliders because this version emphasizes testing rule presence or
  ;; absence before adding a larger parameter space.
  ;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
  let policy-threshold 0.15
  let identity-threshold 0.25
  let strong-policy-threshold 0.35
  let strong-identity-threshold 0.60
  let neighbor-majority-threshold 0.60
  let alienation-threshold 0.55

  ;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
  ;; RULE 1: POLICY PROXIMITY
  ;;
  ;; IF one party is substantially closer than the other,
  ;; THEN add one reason to support that party.
  ;;
  ;; Small distance differences inside +/- POLICY-THRESHOLD activate neither
  ;; party production.  Such voters may still decide through identity, habit,
  ;; neighbors, or the final tie-break.
  ;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
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

  ;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
  ;; RULE 2: PARTISAN IDENTITY
  ;;
  ;; IF effective partisan identity crosses its threshold,
  ;; THEN add one reason to support the corresponding party.
  ;;
  ;; Identity remains conceptually separate from ideology.  A voter can receive
  ;; a policy reason for one party and an identity reason for the other.
  ;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
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

  ;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
  ;; RULE 3: VOTING HABIT
  ;;
  ;; IF the voter previously chose a party,
  ;; THEN add one reason to repeat that choice.
  ;;
  ;; LAST-VOTE stores the most recent non-abstaining ballot, so abstaining for
  ;; one or more elections does not erase the habit cue.
  ;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
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

  ;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
  ;; RULE 4: SOCIAL MAJORITY
  ;;
  ;; IF at least 60% of politically active linked neighbors previously chose a
  ;; party, THEN add one reason for that party.
  ;;
  ;; Only neighbors with a nonzero LAST-VOTE enter the denominator.  This rule
  ;; uses explicit links and prior behavior; it does not inspect nearby turtles
  ;; on the screen.  It is distinct from the later opinion-convergence process.
  ;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
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

  ;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
  ;; RULE 5: ENGAGEMENT
  ;;
  ;; IF policy preference is strong, THEN add one turnout reason.
  ;; IF effective identity is strong, THEN add one turnout reason.
  ;;
  ;; These are two separate productions inside one conceptual rule family, so a
  ;; voter strongly engaged on both dimensions receives two turnout reasons.
  ;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
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

  ;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
  ;; RULE 6: INDIFFERENCE
  ;;
  ;; IF the two parties are nearly equally attractive on policy,
  ;; THEN add one abstention reason.
  ;;
  ;; Indifference concerns the difference between the parties.  It is therefore
  ;; distinct from alienation, which concerns the absolute distance to both.
  ;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
  if rule-indifference? [
    if abs policy-advantage <= policy-threshold [
      set abstention-reasons abstention-reasons + 1
      set rule-trace word rule-trace "indifference->abstain; "
    ]
  ]

  ;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
  ;; RULE 7: ALIENATION
  ;;
  ;; IF even the closer party is far from the voter,
  ;; THEN add one abstention reason.
  ;;
  ;; A voter can be alienated without being indifferent: one party may still be
  ;; less bad than the other, while both remain outside an acceptable range.
  ;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
  if rule-alienation? [
    if min (list blue-distance red-distance) >= alienation-threshold [
      set abstention-reasons abstention-reasons + 1
      set rule-trace word rule-trace "alienation->abstain; "
    ]
  ]

  ;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
  ;; RULE 8: CROSS-PRESSURE
  ;;
  ;; IF policy and identity both clearly favor parties, but favor opposite ones,
  ;; THEN add one abstention reason.
  ;;
  ;; This production computes its own policy and identity directions.  It can
  ;; therefore be enabled independently even when RULE-POLICY? or RULE-IDENTITY?
  ;; is off.  The switch controls whether cross-pressure affects turnout, not
  ;; whether the underlying state can be perceived.
  ;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
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

  ;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
  ;; CONFLICT RESOLUTION FOR PARTY CHOICE
  ;;
  ;; More Blue than Red reasons produces an intended Blue vote; more Red than
  ;; Blue reasons produces an intended Red vote.  The count difference is saved
  ;; in CHOICE-SCORE so downstream party adaptation can still identify weakly
  ;; decided voters.
  ;;
  ;; IMPORTANT: the score is now discrete.  With the default PERSUADABLE-BAND of
  ;; 0.25, ordinary +/-1 reason advantages are outside the band.  Only an exact
  ;; reason tie, stored after tie-breaking as +/-0.001, counts as persuadable.
  ;; Thus PERSUADABLE-BAND has a different operational meaning under the two
  ;; voter architectures.
  ;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
  set choice-score red-reasons - blue-reasons

  if choice-score < 0 [ set intended-choice -1 ]
  if choice-score > 0 [ set intended-choice 1 ]

  ;; Exact reason ties require a residual decision mechanism.  When
  ;; ELECTION-NOISE is positive, only its sign matters here; its magnitude does
  ;; not continuously weight any production.  At zero, choose a party uniformly.
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

  ;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
  ;; CONFLICT RESOLUTION FOR TURNOUT
  ;;
  ;; Turnout remains probabilistic.  Each net turnout reason shifts the baseline
  ;; by one discrete step of TURNOUT-SENSITIVITY.  For example, with baseline
  ;; 0.55 and sensitivity 0.12, one net abstention reason yields 0.43, while two
  ;; net turnout reasons yield 0.79.  CLAMP-VALUE keeps the result in [0, 1].
  ;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
  set turnout-probability clamp-value
    (base-turnout
     + turnout-sensitivity * (turnout-reasons - abstention-reasons))
    0 1

  set voted? (random-float 1 < turnout-probability)

  ifelse voted?
    [ set vote-choice intended-choice ]
    [ set vote-choice 0 ]
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
  ;;
  ;; Under the weighted model CHOICE-SCORE is continuous, so PERSUADABLE-BAND
  ;; selects a conventional interval around zero.  Under the production model
  ;; CHOICE-SCORE is normally an integer reason-count difference.  At the default
  ;; band of 0.25, only voters whose reasons tied and were resolved to +/-0.001
  ;; enter this set.  Increase the band to at least 1 to include one-reason wins.
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
