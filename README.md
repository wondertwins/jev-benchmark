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
| Result | **No better than random** from a raw board. Beats random by ~65% once code supplies the tactical facts. Finds mate-in-one 24% of the time. Beats a random mover, loses to Stockfish level 0. | **F1 0.96** on clean text, **0.93** on lowercase, punctuation-free, misheard-name transcripts. **Precision 1.0** across the board. Exact-set accuracy 92% vs 64% for a fuzzy name-matching heuristic. |
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
| ASCII board + **code-computed facts** | **144** | **27** | **50** | **20** |

"Code-computed facts" means python-chess did the arithmetic first: piece lists, material count, which of our pieces are attacked and whether they're defended, which enemy pieces we can take, and for every legal move, whether the moved piece can be captured afterwards and by what. Jev's job shrank from "read this grid of letters and play chess" to "given that this bishop will hang, which move is sensible?"

From a FEN string, Jev is *worse* than random. With the facts spelled out, it's a different model.

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

- vs random mover: **won by checkmate** in 23 moves, mean cp loss 90.
- vs Stockfish skill level 0: **lost by checkmate** in 36 moves. Sacrificed a bishop on move 5 and later shuffled its queen into four losing squares. My "is the moved piece safe?" annotation only looked at direct attackers of the landing square, so forks and discovered attacks slipped through. That's the obvious next lever: more exact computation in code, zero extra tokens.

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
```

## Caveats

- Sample sizes are small (30 positions, 79 utterances). Treat differences of a few points as noise.
- The addressee labels are mine. Four genuinely arguable items ("Everyone except Jeff, come with me") are excluded from strict metrics and listed in the report.
- I measured latency and token counts, not price.
- The chess `runs/raw/` files from the first runs store the question objects as Python reprs rather than JSON (a persistence bug fixed before the addressee runs). Responses and state are intact.
- Models: `jev-latest` (served as `jev-1.13.0`) and `jev-preview`, both on 2026-09-16.

## License

MIT
