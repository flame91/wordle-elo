# ELO Scoring — Formulas

Reference for the per-puzzle rating update implemented in
[`src/wordle_elo/elo.py`](../src/wordle_elo/elo.py).

> **Note on naming.** Despite the project name, this is **not** classical
> (pairwise) Elo. There is no expected-vs-actual comparison between two
> opponents. It is an *absolute* score with diminishing returns above an
> anchor, plus a day-relative speed term that injects a pairwise-flavored
> component. We keep the "ELO" label because the group adopted it before
> the formula stabilized.

---

## 1. Per-puzzle update

For each submitter $i$ on a given day:

$$
\Delta_i \;=\; \mathrm{clamp}\!\left[
  \mathrm{round}\!\bigl(\, \mathrm{damp}_i \cdot R_i \,\bigr),\;
  -C,\; +C \right]
$$

where

- $R_i$ — raw per-day score (sum of components, defined below)
- $\mathrm{damp}_i$ — diminishing-returns multiplier (Section 3)
- $C$ — symmetric clamp, default $40$

The new rating is $E_i^{\text{new}} = \max(\text{floor},\; E_i + \Delta_i)$,
where $\text{floor} = 100$ is enforced by the pipeline (not the scoring core).

---

## 2. Raw score $R_i$

$$
R_i \;=\; B_i(g_i) \;+\; S_i(g_i,\, \bar g)
$$

with no streak term and no hard-mode term (both removed — see
[CHANGELOG](../CHANGELOG.md) for the rationale).

### 2.1 Base $B_i$

Let $K_i$ be the player's K-factor (Section 4) and $g_i \in \{1,\dots,6,7\}$
the guess count ($7$ encodes X/6, i.e. failure).

$$
B_i(g_i) \;=\; \begin{cases}
+\dfrac{K_i}{4} & g_i \le 6 \;\; (\text{solve}) \\[4pt]
-\dfrac{K_i}{4} & g_i = 7 \;\; (\text{X/6, failure})
\end{cases}
$$

So an established player ($K = 24$) gets $\pm 6$ for solve/fail before any
other adjustments; a new player ($K = 40$) gets $\pm 10$.

### 2.2 Day-relative speed $S_i$

Let today's *baseline* be the mean guess count among today's solvers:

$$
\bar g \;=\;
\begin{cases}
\dfrac{1}{|W|}\displaystyle\sum_{j \in W} g_j & |W| > 0 \\[4pt]
4 & |W| = 0
\end{cases}
\qquad W = \{\,j \mid g_j \le 6\,\}
$$

Then for each submitter:

$$
S_i(g_i, \bar g) \;=\;
\begin{cases}
\alpha \cdot (\bar g - g_i) & g_i \le 6 \\[2pt]
-3 & g_i = 7
\end{cases}
$$

with slope $\alpha = 2.5$. By construction
$\sum_{i \in W} S_i = 0$, so the speed term redistributes among solvers
without inflating the day's total.

**Properties.**
- On an easy day where every solver got 2/6, $\bar g = 2$ and all winners
  get $S = 0$. Nobody is rewarded for matching an easy puzzle.
- On a brutal day where one player solved in 5 and the rest failed,
  $\bar g = 5$. That solver still gets $S = 0$ (they were the field), but
  base alone gives them $+K/4$, while every failer takes $-K/4 - 3$.
- Solo plays: $\bar g = g_i$, so $S = 0$. Their delta is purely base.
- Hard-mode players who consistently take more guesses than peers get
  $S < 0$ — no separate flag is needed.

---

## 3. Damping $\mathrm{damp}_i$

Let $A$ be the **damping anchor** (default $A = 800$). For ratings at or
below $A$, no damping. Above $A$:

$$
\mathrm{damp}_i \;=\;
\begin{cases}
1 & E_i \le A \\[2pt]
\dfrac{A}{E_i} & E_i > A \;\;\text{and}\;\; R_i > 0 \\[6pt]
\dfrac{E_i}{A} & E_i > A \;\;\text{and}\;\; R_i < 0
\end{cases}
$$

So at $E_i = 1.5A$ a gain shrinks to $\tfrac{2}{3}$ but a loss grows by
$\tfrac{3}{2}$. At $E_i = 2A$ a gain halves and a loss doubles.

---

## 4. K-factor $K_i$

$$
K_i \;=\;
\begin{cases}
K_{\text{new}} & n_i < N_{\text{new}} \\[2pt]
K & n_i \ge N_{\text{new}}
\end{cases}
$$

where $n_i$ is the player's games played before today. Defaults:
$K_{\text{new}} = 40$, $K = 24$, $N_{\text{new}} = 10$. FIDE-style "new
players move faster" pattern — they converge to their true skill in roughly
ten games instead of months.

---

## 5. Equilibrium analysis

For a player with daily win probability $p$, expected base $\bar B^+$ on
wins, and expected $\bar B^- = -\bar B^+$ on losses, *long-run* expected
$\Delta = 0$ implies (above the anchor, ignoring speed for now):

$$
p \cdot \bar B^+ \cdot \frac{A}{E^*}
\;+\;
(1-p) \cdot \bar B^- \cdot \frac{E^*}{A} \;=\; 0
$$

Solving for the equilibrium rating $E^*$:

$$
\boxed{\;
E^* \;=\; A \cdot \sqrt{\,\frac{p \cdot |\bar R^+|}{(1-p) \cdot |\bar R^-|}\,}
\;}
$$

with $\bar R^+ = \bar B^+ + \bar S^+$ on wins and $\bar R^- = \bar B^- + S_{\text{fail}}$
on losses ($S_{\text{fail}} = -3$).

With defaults ($A = 800$, $K = 24$, so $|\bar R^+| = 6$ and $|\bar R^-| = 9$)
and a player whose speed **matches** the field on average (so their long-run
$\bar S^+ = 0$):

| Win rate $p$ | $E^*$ above the anchor |
|---:|---:|
| $\le 0.60$ | drifts to the floor (no stable point above $A$) |
| 0.65 | $\approx 890$ |
| 0.70 | $\approx 998$ |
| 0.75 | $\approx 1131$ |
| 0.80 | $\approx 1306$ |
| 0.85 | $\approx 1555$ |
| 0.90 | $\approx 1960$ |
| 0.95 | $\approx 2847$ |
| 0.99 | $\approx 6500$ |

(At $p = 0.6$ the daily expected $\Delta$ is exactly 0 at $E = A$, so the
player hovers near the anchor. Below that, expected $\Delta < 0$ at every
rating and the player drifts toward the floor.)

A player who is *consistently faster than the field* by 1 guess (so
$\bar S^+ = +\alpha = +2.5$ on wins) sees $E^*$ shifted by
$\sqrt{(6 + 2.5)/6} \approx 1.19$ — about 19 % higher equilibrium.
Consistently slower by 1 guess pulls $E^*$ down by ~13 %.

> The pre-2026-05-13 system used a fixed (non-day-relative) speed table and
> $A = 1000$. A 95 % solver used to equilibrate near 3400; the current
> setup compresses that to ~2850 and makes speed measured against the
> field, not a fixed baseline.

---

## 6. Worked example

Three submitters on a moderately hard day:

| Player | $g$ | hard? | $E$ before | $n$ before |
|---|---:|:---:|---:|---:|
| Alice | 3 | ✓ | 1200 | 80 |
| Bob   | 5 |   | 900  | 60 |
| Carol | 7 |   | 1500 | 120 |

**Step 1 — baseline.** Winners are Alice (3) and Bob (5):

$$
\bar g \;=\; \frac{3 + 5}{2} \;=\; 4
$$

**Step 2 — raw scores** (everyone established, $K = 24$):

| | $B$ | $S$ | $R$ |
|---|---:|---:|---:|
| Alice | $+6$ | $2.5 \cdot (4-3) = +2.5$ | $+8.5$ |
| Bob   | $+6$ | $2.5 \cdot (4-5) = -2.5$ | $+3.5$ |
| Carol | $-6$ | $-3$ | $-9$ |

**Step 3 — damping** (anchor $A = 800$):

| | $E$ | $R$ | factor | scaled |
|---|---:|---:|:---:|---:|
| Alice | 1200 | $+8.5$ | $800/1200 \approx 0.667$ | $\approx 5.67$ |
| Bob   | 900  | $+3.5$ | $800/900 \approx 0.889$  | $\approx 3.11$ |
| Carol | 1500 | $-9$   | $1500/800 = 1.875$       | $\approx -16.88$ |

**Step 4 — round and clamp.** $C = 40$, none clip.

$$
\Delta_{\text{Alice}} = +6, \quad
\Delta_{\text{Bob}}   = +3, \quad
\Delta_{\text{Carol}} = -17
$$

Hard-mode flag is recorded for audit but does not change $\Delta$.

---

## 7. Default constants

Defined in [`elo.py`](../src/wordle_elo/elo.py); the env-tunable subset can
be overridden via `.env`. See [`config.py`](../src/wordle_elo/config.py).

| Symbol | Code name | Default | Env var | Tunable |
|---|---|---:|---|:---:|
| $K$ | `K` | 24 | `K_FACTOR` | ✓ |
| $K_{\text{new}}$ | `K_NEW` | 40 | `K_FACTOR_NEW` | ✓ |
| $N_{\text{new}}$ | `NEW_PLAYER_GAMES` | 10 | `NEW_PLAYER_GAMES` | ✓ |
| $C$ | `DELTA_CLAMP` | 40 | `DELTA_CLAMP` | ✓ |
| $A$ | `DAMPING_ANCHOR` | 800 | `DAMPING_ANCHOR` | ✓ |
| $\alpha$ | `SPEED_SLOPE` | 2.5 | — | edit `elo.py` |
| $S_{\text{fail}}$ | `SPEED_FAIL` | -3.0 | — | edit `elo.py` |
| Baseline fallback | `BASELINE_FALLBACK` | 4.0 | — | edit `elo.py` |
| Initial rating | `INITIAL` | 1000 | `INITIAL_ELO` | ✓ |
| ELO floor (pipeline) | `ELO_FLOOR` | 100 | — | edit `pipeline.py` |
