"""Generate and cache test positions.

  realistic : middlegame positions from Stockfish-vs-Stockfish play with sampled top-K moves.
  mate1     : positions where the side to move has at least one mate-in-one (exact, python-chess).
"""
from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

import chess
import chess.engine

RUNS = Path(__file__).resolve().parent.parent / "runs"
CACHE = RUNS / "positions.json"


def _play_sampled(eng: chess.engine.SimpleEngine, rng: random.Random, plies: int, top_k: int = 4,
                  depth: int = 6) -> tuple[chess.Board, list[str]]:
    board = chess.Board()
    sans: list[str] = []
    for _ in range(plies):
        if board.is_game_over():
            break
        n = min(top_k, board.legal_moves.count())
        infos = eng.analyse(board, chess.engine.Limit(depth=depth), multipv=n)
        cands = [i["pv"][0] for i in infos if i.get("pv")]
        # weight towards better moves so games stay realistic
        weights = [0.5 ** k for k in range(len(cands))]
        mv = rng.choices(cands, weights=weights, k=1)[0]
        sans.append(board.san(mv))
        board.push(mv)
    return board, sans


def gen_realistic(eng: chess.engine.SimpleEngine, n: int, seed: int = 7) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    out: list[dict[str, Any]] = []
    tries = 0
    while len(out) < n and tries < n * 5:
        tries += 1
        plies = rng.randint(10, 44)
        board, sans = _play_sampled(eng, rng, plies)
        if board.is_game_over() or board.legal_moves.count() < 8:
            continue
        out.append({"id": f"real_{len(out):03d}", "fen": board.fen(), "sans": sans, "kind": "realistic"})
    return out


def gen_mate_in_one(n: int, seed: int = 11) -> list[dict[str, Any]]:
    """Random-vs-random playouts; keep positions where the mover has a mate-in-one and >= 6 legal moves."""
    rng = random.Random(seed)
    out: list[dict[str, Any]] = []
    games = 0
    while len(out) < n and games < 5000:
        games += 1
        board = chess.Board()
        sans: list[str] = []
        while not board.is_game_over() and len(sans) < 200:
            mates = []
            for mv in board.legal_moves:
                board.push(mv)
                if board.is_checkmate():
                    mates.append(mv)
                board.pop()
            if mates and board.legal_moves.count() >= 6 and len(sans) >= 6:
                out.append({"id": f"mate1_{len(out):03d}", "fen": board.fen(), "sans": sans, "kind": "mate1",
                            "mating_moves": [m.uci() for m in mates], "n_legal": board.legal_moves.count()})
                break
            mv = rng.choice(list(board.legal_moves))
            sans.append(board.san(mv))
            board.push(mv)
    return out


def load_or_generate(eng: chess.engine.SimpleEngine, n_real: int = 30, n_mate: int = 25) -> dict[str, list[dict[str, Any]]]:
    if CACHE.exists():
        data = json.loads(CACHE.read_text())
        if len(data.get("realistic", [])) >= n_real and len(data.get("mate1", [])) >= n_mate:
            return {"realistic": data["realistic"][:n_real], "mate1": data["mate1"][:n_mate]}
    data = {"realistic": gen_realistic(eng, n_real), "mate1": gen_mate_in_one(n_mate)}
    RUNS.mkdir(exist_ok=True)
    CACHE.write_text(json.dumps(data, indent=1))
    return data


def board_from(pos: dict[str, Any]) -> tuple[chess.Board, list[str]]:
    return chess.Board(pos["fen"]), list(pos["sans"])
