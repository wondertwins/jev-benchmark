"""Calibrate the opponent bots on an Elo ladder with bot-vs-bot games (no Jev tokens), then fit Jev.

  uv run python -m jevchess.ladder calibrate --games 40      # bots round-robin -> runs/results/ladder_bots.json
  uv run python -m jevchess.ladder fit --config tactical      # Jev's performance rating from its recorded games

Anchor: Stockfish UCI_Elo 1320 (its calibrated floor) is fixed at 1320. Everything else is fitted
by maximum likelihood under the Elo logistic model. Unfinished games are adjudicated at +/-300 cp.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import shutil
from pathlib import Path

import chess
import chess.engine

from .opponents import Opponent, label

RUNS = Path(__file__).resolve().parent.parent / "runs"
BOTS = ["elo1320", "sf0", "mix25", "mix50", "greedy", "mix75", "random"]
PAIRS = [("elo1320", "sf0"), ("sf0", "mix25"), ("sf0", "mix50"), ("mix25", "mix50"), ("mix50", "greedy"), ("mix50", "mix75"),
         ("greedy", "mix75"), ("mix75", "random"), ("greedy", "random"), ("sf0", "greedy"), ("elo1320", "mix25")]


def play(a: str, b: str, seed: int, judge: chess.engine.SimpleEngine, max_plies: int = 160) -> float:
    """Score for `a` (white)."""
    rng = random.Random(seed)
    A, B = Opponent(a, random.Random(seed * 7 + 1)), Opponent(b, random.Random(seed * 7 + 2))
    board = chess.Board()
    try:
        while not board.is_game_over(claim_draw=True) and len(board.move_stack) < max_plies:
            board.push((A if board.turn == chess.WHITE else B).move(board))
    finally:
        A.close(); B.close()
    if board.is_game_over(claim_draw=True):
        r = board.result(claim_draw=True)
    else:
        cp = judge.analyse(board, chess.engine.Limit(depth=12))["score"].white().score(mate_score=10000)
        r = "1-0" if cp > 300 else "0-1" if cp < -300 else "1/2-1/2"
    return {"1-0": 1.0, "0-1": 0.0}.get(r, 0.5)


def fit_elo(results: list[tuple[str, str, float]], anchor: dict[str, float], iters: int = 3000, lr: float = 8.0) -> dict[str, float]:
    """results: (white, black, white_score). Gradient ascent on log-likelihood; anchors fixed."""
    names = sorted({n for w, b, _ in results for n in (w, b)} | set(anchor))
    elo = {n: anchor.get(n, 1000.0) for n in names}
    for _ in range(iters):
        grad = {n: 0.0 for n in names}
        for w, b, s in results:
            p = 1 / (1 + 10 ** ((elo[b] - elo[w]) / 400))
            grad[w] += s - p
            grad[b] -= s - p
        for n in names:
            if n not in anchor:
                elo[n] += lr * grad[n]
    return elo


def calibrate(games_per_pair: int) -> None:
    judge = chess.engine.SimpleEngine.popen_uci(shutil.which("stockfish"))
    results: list[tuple[str, str, float]] = []
    try:
        for a, b in PAIRS:
            for g in range(games_per_pair):
                w, bl = (a, b) if g % 2 == 0 else (b, a)
                s = play(w, bl, seed=1000 + g, judge=judge)
                results.append((w, bl, s))
            sa = sum(s if w == a else 1 - s for w, bl, s in results[-games_per_pair:])
            print(f"{a:8s} vs {b:8s}: {sa:.1f} / {games_per_pair}")
    finally:
        judge.quit()
    elo = fit_elo(results, {"elo1320": 1320.0})
    out = {"anchor": {"elo1320": 1320}, "games_per_pair": games_per_pair, "results": results,
           "elo": {k: round(v) for k, v in sorted(elo.items(), key=lambda kv: -kv[1])}, "labels": {b: label(b) for b in BOTS}}
    (RUNS / "results").mkdir(exist_ok=True, parents=True)
    (RUNS / "results" / "ladder_bots.json").write_text(json.dumps(out, indent=1))
    print("\nfitted Elo (anchor elo1320 = 1320):")
    for k, v in out["elo"].items():
        print(f"  {v:5d}  {label(k)}")


def fit_jev(config: str, model: str) -> None:
    lad = json.loads((RUNS / "results" / "ladder_bots.json").read_text())
    bot_elo = {k: float(v) for k, v in lad["elo"].items()}
    games: list[tuple[str, str, float]] = []
    rows = []
    for p in sorted((RUNS / "results").glob(f"G_game_vs_*_{model}.json")):
        r = json.loads(p.read_text())
        cfg = f"{r.get('level', 'rich')}{'_filter' if r.get('filter_blunders') else ''}"
        if cfg != config or r["opponent"] not in bot_elo:
            continue
        res = r["summary"]["result"]
        if res == "unfinished":
            cp = r["summary"].get("final_eval_cp_white")
            res = r.get("adjudicated_result") or ("1-0" if cp is not None and cp > 300 else "0-1" if cp is not None and cp < -300 else "1/2-1/2")
        jev_white = r.get("jev_color", "white") == "white"
        s_white = {"1-0": 1.0, "0-1": 0.0}.get(res, 0.5)
        games.append(("JEV", r["opponent"], s_white) if jev_white else (r["opponent"], "JEV", s_white))
        rows.append((p.name, r["opponent"], "white" if jev_white else "black", res, s_white if jev_white else 1 - s_white))
    if not games:
        print("no games for config", config); return
    elo = fit_elo(games, bot_elo)
    score = sum(s for _, _, _, _, s in rows)
    print(f"config {config}: {len(rows)} games, score {score}/{len(rows)}")
    for row in rows:
        print("  ", *row)
    # simple +/- from a bootstrap over games
    rng = random.Random(0); boots = []
    for _ in range(400):
        sample = [games[rng.randrange(len(games))] for _ in games]
        boots.append(fit_elo(sample, bot_elo, iters=800)["JEV"])
    boots.sort()
    lo, hi = boots[int(0.1 * len(boots))], boots[int(0.9 * len(boots))]
    print(f"\nJev performance rating ({config}): {elo['JEV']:.0f}   (80% bootstrap interval {lo:.0f} to {hi:.0f})")
    out = {"config": config, "games": rows, "elo": round(elo["JEV"]), "interval_80": [round(lo), round(hi)], "bot_elo": lad["elo"]}
    (RUNS / "results" / f"ladder_jev_{config}_{model}.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["calibrate", "fit"])
    ap.add_argument("--games", type=int, default=40)
    ap.add_argument("--config", default="tactical")
    ap.add_argument("--model", default="jev-latest")
    a = ap.parse_args()
    calibrate(a.games) if a.cmd == "calibrate" else fit_jev(a.config, a.model)
