"""CLI: uv run python -m jevchess.run --exp A,B,C,D,E,F,G --n 30 --model jev-latest

Loads TYPESAFE_API_KEY from the environment (source ~/.env first).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from pathlib import Path

import chess

from . import experiments as X
from jevcommon.client import JevClient
from .engine import open_engine
from .positions import load_or_generate

RESULTS = Path(__file__).resolve().parent.parent / "runs" / "results"


def save(res: dict, name: str, model: str) -> Path:
    RESULTS.mkdir(parents=True, exist_ok=True)
    p = RESULTS / f"{name}_{model}.json"
    p.write_text(json.dumps(res, indent=1, default=str))
    return p


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exp", default="probe", help="comma list of A,B,C,D,E,F,G or 'probe'")
    ap.add_argument("--n", type=int, default=30, help="positions per experiment")
    ap.add_argument("--n-mate", type=int, default=25)
    ap.add_argument("--model", default="jev-latest")
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--levels", default="fen,ascii,rich", help="state levels for A and E")
    ap.add_argument("--games", default="random,sf0", help="opponents for G, comma list (random | sfN)")
    ap.add_argument("--max-plies", type=int, default=120)
    ap.add_argument("--game-level", default="rich", help="state level Jev gets when playing games (rich | tactical)")
    ap.add_argument("--seeds", default="3", help="comma list of seeds, one game per seed per opponent")
    ap.add_argument("--filter-blunders", action="store_true", help="code plays mates and removes obvious blunders before Jev chooses")
    ap.add_argument("--jev-color", default="white", help="white | black | alternate (by seed parity)")
    args = ap.parse_args()
    if not os.environ.get("TYPESAFE_API_KEY"):
        raise SystemExit("TYPESAFE_API_KEY not set; run: set -a; source ~/.env; set +a")

    exps = [e.strip().upper() for e in args.exp.split(",")]
    levels = [l.strip() for l in args.levels.split(",")]
    t0 = time.time()
    with open_engine() as eng:
        data = load_or_generate(eng, n_real=max(args.n, 1), n_mate=args.n_mate)
        real, mate1 = data["realistic"][: args.n], data["mate1"][: args.n_mate]
        print(f"positions: {len(real)} realistic, {len(mate1)} mate-in-one  (engine ready in {time.time()-t0:.1f}s)")

        async with JevClient(model=args.model, concurrency=args.concurrency, tag=args.model) as client:
            if "PROBE" in exps:
                pos = real[0]
                for lvl in levels:
                    r = await X.exp_move_choice(client, eng, [pos], lvl)
                    row = r["rows"][0]
                    print(f"[probe A/{lvl}] tokens={row.get('input_tokens')} chosen={row.get('chosen')} best={row.get('best')} "
                          f"cp_loss={row.get('cp_loss')} err={row.get('error')}")
                r = await X.exp_move_scores(client, eng, [pos])
                row = r["rows"][0]
                print(f"[probe B/rich] tokens={row.get('input_tokens')} chosen={row.get('chosen')} cp_loss={row.get('cp_loss')} "
                      f"spearman={row.get('spearman_vs_stockfish')} err={row.get('error')}")
                r = await X.exp_perception(client, [pos])
                print(f"[probe D] tokens={r['rows'][0].get('input_tokens')} pred={r['rows'][0].get('pred')} truth={r['rows'][0]['truth']}")
                print("usage:", client.usage.summary())
                return

            if "A" in exps:
                for lvl in levels:
                    r = await X.exp_move_choice(client, eng, real, lvl)
                    p = save(r, f"A_move_choice_{lvl}", args.model)
                    print(f"A/{lvl}: {r['summary']}  -> {p.name}")
            if "B" in exps:
                r = await X.exp_move_scores(client, eng, real)
                print(f"B: {r['summary']}  -> {save(r, 'B_move_scores', args.model).name}")
            if "C" in exps:
                r = await X.exp_hierarchical(client, eng, real)
                print(f"C: {r['summary']}  -> {save(r, 'C_hierarchical', args.model).name}")
            if "D" in exps:
                r = await X.exp_perception(client, real + mate1)
                print(f"D: {json.dumps(r['summary'])}  -> {save(r, 'D_perception', args.model).name}")
            if "E" in exps:
                for lvl in levels:
                    r = await X.exp_mate_in_one(client, mate1, lvl)
                    print(f"E/{lvl}: {r['summary']}  -> {save(r, f'E_mate_in_one_{lvl}', args.model).name}")
            if "F" in exps:
                r = await X.exp_eval_score(client, eng, real + mate1)
                print(f"F: {r['summary']}  -> {save(r, 'F_eval_score', args.model).name}")
            if "G" in exps:
                for opp in [o.strip() for o in args.games.split(",") if o.strip()]:
                    for seed in [int(x) for x in args.seeds.split(",")]:
                        color = chess.WHITE if args.jev_color == "white" or (args.jev_color == "alternate" and seed % 2 == 1) else chess.BLACK
                        r = await X.exp_play_game(client, eng, args.game_level, opp, jev_color=color, max_plies=args.max_plies,
                                                  seed=seed, filter_blunders=args.filter_blunders)
                        suffix = "" if (args.game_level == "rich" and not args.filter_blunders and seed == 3 and color == chess.WHITE) else \
                            f"_{args.game_level}{'_filter' if args.filter_blunders else ''}_s{seed}{'' if color == chess.WHITE else 'b'}"
                        print(f"G vs {opp} [{args.game_level}{' +filter' if args.filter_blunders else ''} seed {seed}]: {r['summary']}\n"
                              f"   {r['pgn_moves']}\n   -> {save(r, f'G_game_vs_{opp}{suffix}', args.model).name}")
            print("usage:", client.usage.summary(), f"elapsed {time.time()-t0:.0f}s")


if __name__ == "__main__":
    asyncio.run(main())
