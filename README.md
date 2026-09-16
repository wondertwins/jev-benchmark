# Jev Benchmark & Playground

Two hands-on benchmarks of **Jev**, the "System One" model from [TypeSafe](https://typesafe.ai). Jev doesn't generate text or reason step by step. You hand it *state* (a JSON blob) and typed *questions* (yes/no, pick-one, or rate-on-a-scale) and it returns calibrated probabilities in about 200 ms. The pitch is "programmable common sense": code owns the workflow, Jev supplies the judgment.

I wanted to know where that holds up and where it breaks, so I tested it on two very different tasks:

1. **Chess** – deliberately *outside* its lane. Chess is calculation and search wearing a judgment costume.
2. **"Who is the player talking to?"** – squarely *inside* its lane. A video game where the player speaks aloud to NPCs through speech-to-text, and the engine must decide which characters should pay attention.

Everything is here: the code, the labeled data, every raw request and response (`runs/raw/`), the metrics, and an interactive playground. Model served as `jev-1.13.0` on 2026-09-16.

---

## TL;DR

| | Chess | NPC addressee detection |
|---|---|---|
| Task shape | Pick a move from 20 to 40 legal options; needs lookahead | Read one utterance, decide per NPC: spoken to, or merely mentioned? |
| Result | **No better than random** from a raw board. Beats random by ~65% with code-supplied facts and ~78% with one-ply tactical facts. Finds mate-in-one 24% of the time. With tactical facts it plays at roughly **950 Elo** on a Stockfish-anchored ladder: checkmates every bot up to ~650, loses to depth-1 Stockfish (~1166). | **F1 0.96** on clean text, **0.93** on lowercase, punctuation-free, misheard-name transcripts. **Precision 1.0** across the board. Exact-set accuracy 92% vs 64% for a fuzzy name-matching heuristic. |
| Latency | 0.2 s median, even with 40 options | 0.17 s median with 8 to 10 questions per call |
| Cost | ~2,100 input tokens per move (rich state) | ~1,700 input tokens per utterance |

**The lesson in one line:** Jev is a judgment engine, not a calculator. Compute everything that has an exact answer in code, hand the facts to Jev, and ask every question you might need in a single call.

---

## Benchmark 1: Chess

Setup: 30 realistic middlegame positions (Stockfish self-play with sampled top-4 moves), 25 mate-in-one puzzles from random playouts, Stockfish 19 at depth 12 to 14 as ground truth. Code handles legality, board state, and scoring. Jev only ever chooses among legal moves that code enumerated, so it can never make an illegal move. Mating moves were shown as `+` rather than `#` so nothing leaked.

### How much does the *state* matter?

Same question ("which legal move should White play?"), same 30 positions, three ways of describing the board:

| State handed to Jev | Mean centipawn loss | % best move | % top-3 | % blunders (≥200 cp) |
|---|---|---|---|---|
| *Random move (baseline)* | 403 | | | |
| FEN string only | 533 | 13 | 17 | 73 |
| ASCII board + move history | 409 | 20 | 27 | 57 |
| ASCII board + **code-computed facts** ("rich") | 144 | 27 | 50 | 20 |
| rich + **one-ply tactical facts** ("tactical") | **90** | **37** | **57** | **13** |

"Code-computed facts" means python-chess did the arithmetic first: piece lists, material count, which of our pieces are attacked and whether they're defended, which enemy pieces we can take, and for every legal move, whether the moved piece can be captured afterwards and by what. Jev's job shrank from "read this grid of letters and play chess" to "given that this bishop will hang, which move is sensible?"

The "tactical" level adds what a static exchange evaluator computes in microseconds: the net material of the capture sequence on the landing square, which pieces the move newly exposes or rescues, whether it delivers mate or allows mate-in-one, what it newly threatens, and whether it repeats a position. Still one ply, still no search, and Jev still picks among all 20 to 40 legal moves.

From a FEN string, Jev is *worse* than random. With the facts spelled out, it's a different model.

### Is the harness doing the playing?

Fair question, so here is the literal text Jev receives for one move in one position, at each level:

```
ascii     Bxd5 -> bishop b3 to d5, captures pawn
rich      Bxd5 -> bishop b3 to d5, captures pawn; afterwards this bishop can be captured by a pawn (undefended)
tactical  Bxd5 -> bishop b3 to d5, captures pawn; LOSES 2 point(s) of material: the moved piece gets captured on d5
```

Every fact is one-ply exact and cheap. None of it says which move to play. Jev still has to weigh "loses 2 points" against "gives check" against "develops a piece" across ~30 options, and it does that imperfectly (see the blunder rate). Where the line gets crossed is the optional `--filter-blunders` mode used in some games below, where code plays a checkmate if one exists and removes moves that hang a piece or allow mate before Jev chooses. That's a hybrid, and it's labeled as such wherever it appears.

### Phrasing the facts matters as much as computing them

My first version of the tactical level scored *worse* than rich (241 cp mean loss). The facts were right; the wording was wrong. Every move carried "leaves hanging: pawn on e4" when that pawn was already hanging before the move, so the note was constant noise. And a losing capture read "loses 3 points; attacks queen (can be won next move)", and Jev kept taking the bait: Qxf5 was labeled "loses 8 points" and it still chose it for the pawn it attacked.

Three changes fixed it: report only *deltas* the move causes (newly exposes, rescues), lead with the material verdict in plain words, and suppress threat notes on moves whose piece doesn't survive. Same model, same facts: 241 → 90 cp.

### Other ways of asking

| Method | Mean cp loss | Note |
|---|---|---|
| One Choice over all legal moves | **144** | Cheapest and best |
| One Score per move (40 questions in one call), take argmax | 197 | Scores correlate 0.46 with Stockfish, but 4x the tokens |
| Choice which piece, then Choice which square | 217 | Picking the piece first locks in 104 cp of loss on average |

### What it can and can't see

Nouls ("is White in check?", "does White have a mate-in-one?", "is a piece hanging?", "is there a free capture?") over an ASCII board landed within a few points of the majority-class baseline. Material counting reached 65% on a 3-way choice against a 40% baseline. A 7-level "who is better?" Score correlated 0.64 with Stockfish, which is probably material recognition rather than tactics.

Mate-in-one puzzles: 6 of 25 solved, at every state level. Random baseline is 3%, so it's not nothing, but it cannot calculate.

### Full games (rich state, Jev as White)

![Jev beats Stockfish skill 0: every move with Jev's probability distribution, a live eval bar, and Stockfish's verdict](runs/media/v2_jev_vs_sf0_tactical_filter_s4_jev-latest.gif)

*Jev (White, tactical facts + code filter) checkmates Stockfish skill 0 in 38 moves. Rendered with `jevchess/gif2.py`; MP4s in `runs/media/`.*

- vs random mover: **won by checkmate** in 23 moves, mean cp loss 90.
- vs Stockfish skill level 0 (depth 1), rich state: **lost by checkmate** in 36 moves. Sacrificed a bishop on move 5 and later shuffled its queen into four losing squares. The rich annotation only looked at direct attackers of the landing square, so forks and discovered attacks slipped through.

Rematch at the tactical level, two seeds each:

| Configuration | Result | Jev mean cp loss | Blunders |
|---|---|---|---|
| tactical facts, seed 3 | lost by checkmate (44 moves) | 242 | 8 |
| tactical facts, seed 4 | unfinished at 60 moves, Stockfish +559 (adjudicated loss) | 217 | 12 |
| tactical + code filter, seed 3 | lost by checkmate (46 moves) | 469 | 16 |
| tactical + code filter, seed 4 | **won by checkmate (38 moves)** | 186 | 10 |

Facts alone were not enough to beat even depth-1 Stockfish. The one win needed the hybrid: code enforcing "never allow mate, never hang a piece for nothing" and Jev choosing among what's left. The gap between 90 cp on isolated positions and 200+ cp in full games is the endgame: with no plan and no lookahead, Jev shuffles pieces, repeats positions, and gets ground down.

### Against weaker bots (tactical facts, no filter, both colors)

| Opponent | As White | As Black |
|---|---|---|
| Random mover | win (23 moves, rich state) | **win in 7 moves** |
| Greedy capture bot | win (40 moves) | win (32 moves) |
| Stockfish skill 0 depth 1, 50% random moves | win (33 moves) | win (31 moves) |
| Stockfish skill 0 depth 1, 75% random moves | win (33 moves) | win (28 moves) |
| Stockfish skill 0 depth 1, 25% random moves | **win in 5 moves** | win (38 moves) |
| Stockfish skill 0 depth 1 | loss | loss (adjudicated) |

![Random mover vs Jev: checkmate in 7 moves as Black](runs/media/v2_jev_vs_random_tactical_s6b_jev-latest.gif)

Every win was by checkmate. Jev with one-ply facts sits clearly above "beginner bot" and clearly below depth-1 Stockfish. The Elo estimate below puts a number on that.

**Speed.** Over 425 game moves at the tactical level, the API call (one Choice over a median of 32 legal moves, ~2,100 input tokens) took a median of 166 ms, p90 256 ms, p99 403 ms. Computing all the tactical facts in python-chess adds about 9 ms. So Jev plays a move in roughly 175 ms end to end and a 40-move game in about 7 seconds of its own thinking time. It would be legal in bullet.

### How strong is that? An Elo estimate

Stockfish's calibrated strength floor is `UCI_Elo 1320`, and Jev is below it, so there is no off-the-shelf opponent with a known rating in Jev's range. I built a ladder instead. Seven bots played 40 games per pair against each other (440 bot-vs-bot games, no Jev tokens), and their ratings were fitted by maximum likelihood under the Elo model with Stockfish-at-1320 pinned as the anchor:

| Bot | Fitted Elo |
|---|---|
| Stockfish limited to 1320 Elo | 1320 |
| Stockfish skill 0, depth 1 | 1166 |
| Stockfish skill 0 depth 1, 25% random moves | 650 |
| Greedy capture bot | 484 |
| Stockfish skill 0 depth 1, 50% random moves | 388 |
| Stockfish skill 0 depth 1, 75% random moves | 169 |
| Random mover | -73 |

Jev (tactical facts, no code filter) then played 11 games up the ladder, alternating colors, and scored 9/11: every game against a bot rated 650 or below was a win by checkmate, and both games against depth-1 Stockfish (1166) were losses.

**Performance rating: about 968.** Because the results separate perfectly (all wins below 650, all losses at 1166), the maximum-likelihood point is soft. Read it as "somewhere between roughly 700 and 1150, most likely around 950", or in human terms: a club beginner who never hangs a piece outright but has no plan. Caveats that matter: the anchor is Stockfish's own Elo calibration at a fast time control, the sub-1320 scale is extrapolated through bots, and 11 games is a small sample. More games against the 650 and 1166 bots would narrow it; the code is one command.

With the code filter on (hybrid: code plays mates, prunes suicidal moves), it went 1 and 1 against the 1166 bot, which suggests the hybrid sits closer to 1100, but two games is not an estimate.

The original rich-state loss is animated too: [`runs/media/jev_vs_sf0_jev-latest.gif`](runs/media/jev_vs_sf0_jev-latest.gif). Watch the flat distribution on move 5 when it sacrifices the bishop. `gif.py` is the simple renderer; `gif2.py` adds sliding pieces, an eval bar, and title cards.

Confidence was only weakly predictive of blunders (Spearman -0.24). `jev-preview` scored marginally better than `jev-latest` (129 vs 144 mean cp loss), within noise at n=30.

Full report: [`runs/REPORT_chess_jev-latest.md`](runs/REPORT_chess_jev-latest.md)

---

## Benchmark 2: Who is the player talking to?

The game scenario: a fantasy village, 2 to 5 NPCs within earshot (Hanna the innkeeper, Jeff the guard, Anna the merchant, Marcus the blacksmith, Elara the healer, Biscuit the dog). The player speaks; speech-to-text transcribes. Which NPCs should turn around?

> "Hi Hanna, today I went to school with Jeff and Anna." → Hanna is spoken to. Jeff and Anna are mentioned; their attention is not required.
>
> "Hey, Jeff, Anna, please come over here." → Jeff and Anna both need to respond.

79 hand-labeled utterances across 16 trick categories: mention vs address, third-party relay ("Hanna, tell Anna her order is ready"), reported speech ("Jeff, Anna said 'Marcus, come here'"), group broadcasts, role-based address ("Innkeeper, a room please" / "Guards! Thief!"), description ("You with the hammer"), deixis resolved by who the player is facing, conversation continuation with no name at all ("And what about you?"), self-talk, out-of-game remarks ("hang on, my mic is cutting out"), mid-sentence vocatives, threats.

Each utterance was run three ways: **clean** text, **stt** (lowercase, no punctuation), and **stt_misheard** (plus phonetic misspellings: Hanna→hannah, Jeff→geoff, Elara→ilara, and a leading "um").

### The state Jev sees

Everything the game engine already knows:

```json
{
  "setting": "A fantasy village in a video game. The player speaks out loud and a speech-to-text system transcribes it. The characters listed are the NPCs within earshot.",
  "characters_present": [{"name": "Hanna", "role": "innkeeper"}, {"name": "Jeff", "role": "guard"}, {"name": "Anna", "role": "merchant"}],
  "recent_context": {"player_was_last_talking_to": "Hanna", "last_thing_said_to_player": {"speaker": "Hanna", "text": "We have ale and cider."}},
  "transcript": "no i meant the other one",
  "transcript_quality": "Raw speech-to-text output: lowercase, no punctuation, and names may be spelled the way they sound."
}
```

### The questions, all in one call

- One **Noul** per NPC present: *"Is the player speaking to Hanna, the innkeeper?"* with explicit definitions of what counts (name, role, description, facing, group, continuation) and what doesn't (topic, third party, relay target, quoted speech).
- **Noul** `group_address`, **Noul** `nobody` (self-talk / out-of-game / someone not present).
- **Choice** `intent` (greeting, farewell, request/command, question, statement, threat/insult, none).
- **Score** `urgency` (3 levels), **Choice** `attitude` (friendly / neutral / hostile).
- **Choice** `primary` addressee (NPC names + everyone + nobody), as a second formulation to compare against the Nouls.

### Results

Per-NPC "is being spoken to" decisions (237 per variant; 4 arguable items excluded):

| Transcript | Jev F1 | Jev precision | Jev recall | Heuristic F1 | Jev exact-set | Heuristic exact-set | Jev Brier |
|---|---|---|---|---|---|---|---|
| clean | **0.962** | 1.000 | 0.926 | 0.820 | **0.92** | 0.64 | 0.021 |
| stt | **0.944** | 1.000 | 0.895 | 0.820 | **0.88** | 0.64 | 0.033 |
| stt_misheard | **0.927** | 1.000 | 0.863 | 0.786 | **0.84** | 0.61 | 0.041 |

The heuristic is not a strawman: fuzzy name matching (edit-distance tolerant, handles "Anna's"), role synonyms, group words, and a facing/last-speaker fallback. It fails on exactly the cases that matter for a game: anyone whose name appears gets flagged, so "Hanna, have you seen Jeff?" wakes up Jeff.

Other judgments from the same call (clean variant): intent accuracy **91%** over 7 classes; the primary-addressee Choice was right on **98%** of single-addressee utterances and said "nobody" on **100%** of self-talk items; the `nobody` Noul had F1 0.82.

Where it's perfect (exact-set 1.0 on clean): direct address, multi-address, mid-sentence vocatives, role and description address, deixis via facing, group broadcasts, self-talk, out-of-game, reported speech, threats, the dog.

Where it hedges: utterances with no vocative where the addressee is only implied by conversation context and a *different* NPC is the topic ("Jeff is the laziest guard I've ever seen", said to Hanna). Jev puts Hanna at 0.32 to 0.43, just under threshold, with `nobody` around 0.55 to 0.6. It's uncertain, not confidently wrong, and the `primary` Choice picks Hanna anyway. Reported speech degrades once STT strips the quote marks, which is fair: `jeff anna said marcus come here` really is ambiguous. `jev-preview` was a hair better (F1 0.933 vs 0.927 on misheard).

Full reports: [`runs/REPORT_npc_addressee_jev-latest.md`](runs/REPORT_npc_addressee_jev-latest.md), [`runs/REPORT_npc_addressee_jev-preview.md`](runs/REPORT_npc_addressee_jev-preview.md)

### Playground

```
$ uv run python -m npcaddress.demo tavern
Scene 'tavern': Hanna (innkeeper), Jeff (guard), Anna (merchant)

player> Hanna, have you seen Jeff?
  Hanna    ███████████████████·  0.97  ◄ listening
  Jeff     █···················  0.03
  Anna     █···················  0.03
  everyone ····················  0.02
  nobody   █···················  0.03
  intent=question (1.00)  attitude=neutral  urgency=0.90/2  primary=Hanna

player> face Jeff
player> you there, come here
  Hanna    ████················  0.18
  Jeff     █████████████████···  0.86  ◄ listening
  Anna     █···················  0.05
  intent=request_or_command (1.00)  attitude=neutral  urgency=1.04/2  primary=Jeff

player> hmm where did I leave my sword
  Hanna    █···················  0.05
  Jeff     ██████··············  0.31
  Anna     █···················  0.04
  nobody   ██████████████······  0.72
  intent=none_or_unclear (0.75)  urgency=0.00/2
```

In a game loop: NPCs above 0.5 turn to face the player; `urgency` near 2 triggers the run animation instead of the walk; `attitude=hostile` nudges disposition; `intent` routes to the right dialogue handler; `nobody` high means no reaction at all. One request, all of it.

---

## What this says about building with Jev

- **Feed it facts, not puzzles.** The single biggest lever in both benchmarks was what code put in the state. Chess went from worse-than-random to clearly-better-than-random with zero model changes.
- **Phrase the facts like a checklist, not a data dump.** Deltas over constants, verdict first, no misleading upside on a losing move. The same computed facts scored 241 cp or 90 cp depending only on wording.
- **Ask everything at once.** 40 Score questions in one call cost about the same wall-clock as one. Speculative questions are free in latency, only tokens.
- **Precision is the strong suit.** In the addressee task it never once flagged an NPC that wasn't being spoken to. Misses were hedges near 0.5, which is what calibration should look like.
- **Try more than one formulation.** The per-NPC Nouls handle multi-addressee; the primary Choice was more robust on context-only cases. Run both, they're in the same request.
- **Confidence is a signal, not a guarantee.** It weakly tracked chess blunders and clearly tracked addressee uncertainty. Threshold on your own data.
- **Know the boundary.** If a domain expert would answer from the text in front of them, Jev fits. If they'd need to calculate, search, or chain steps, do that in code or route to a reasoning model, and use Jev to decide which cases need the expensive path.

---

## Reproduce

Requirements: Python ≥ 3.10, [uv](https://docs.astral.sh/uv/), a `TYPESAFE_API_KEY` from [console.typesafe.ai](https://console.typesafe.ai), and Stockfish for the chess benchmark (`brew install stockfish`).

```bash
uv sync
export TYPESAFE_API_KEY=...

# chess: all seven experiments (~810k input tokens, ~2 min)
uv run python -m jevchess.run --exp A,B,C,D,E,F,G --n 30 --n-mate 25
uv run python -m jevchess.report jev-latest

# chess: just the best config, on the preview model
uv run python -m jevchess.run --exp A,E --levels rich --model jev-preview

# addressee benchmark (~400k input tokens, ~30 s)
uv run python -m npcaddress.run --model jev-latest

# interactive playground
uv run python -m npcaddress.demo tavern

# play Jev against graded bots (random | greedy | mixNN | sfN | eloNNNN), alternating colors
uv run python -m jevchess.run --exp G --games mix50,greedy --seeds 5,6 --game-level tactical --jev-color alternate

# Elo ladder: calibrate the bots against each other (no Jev tokens), then fit Jev's performance rating
uv run python -m jevchess.ladder calibrate --games 40
uv run python -m jevchess.ladder fit --config tactical

# animate a recorded game (needs the optional media group: pillow + cairosvg, and ffmpeg)
uv run --group media python -m jevchess.gif2 --game sf0_tactical_filter_s4
```

Every request and response is written to `runs/raw/` keyed by request hash, so nothing needs re-fetching to re-analyze.

## Layout

```
jevcommon/client.py      rate-limited async TypeSafe client; persists every raw request/response
jevchess/                chess benchmark
  state.py               board → state at three levels (fen / ascii / rich); move descriptions
  experiments.py         A–G: Choice, Score fan-out, hierarchical, perception, mate-in-1, eval, full games
  engine.py positions.py Stockfish ground truth; position generation
  run.py report.py       CLI and Markdown report
  opponents.py ladder.py graded opponent bots; Elo ladder calibration and Jev's performance rating
  gif.py gif2.py         animate a recorded game (simple / social-media polish)
npcaddress/              addressee benchmark
  dataset.py             79 labeled utterances, scenes, transcript variants
  questions.py           state + questions for one utterance
  baseline.py            fuzzy name/role heuristic
  run.py demo.py         benchmark runner; interactive playground
runs/
  positions.json ground_truth.json   cached chess positions and Stockfish analysis
  results/*.json                      per-row results for every experiment
  raw/*.json                          every raw request and response
  REPORT_*.md                         generated reports
  media/                              GIF + MP4 of the recorded games
```

## Caveats

- Sample sizes are small (30 positions, 79 utterances). Treat differences of a few points as noise.
- The addressee labels are mine. Four genuinely arguable items ("Everyone except Jeff, come with me") are excluded from strict metrics and listed in the report.
- I measured latency and token counts, not price.
- The chess `runs/raw/` files from the first runs store the question objects as Python reprs rather than JSON (a persistence bug fixed before the addressee runs). Responses and state are intact.
- Models: `jev-latest` (served as `jev-1.13.0`) and `jev-preview`, both on 2026-09-16.

## License

MIT
