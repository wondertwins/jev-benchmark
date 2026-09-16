"""Stockfish helpers: ground truth for move quality and position evaluation."""
from __future__ import annotations

import shutil
from typing import Iterator
from contextlib import contextmanager

import chess
import chess.engine

MATE_CP = 10_000


@contextmanager
def open_engine(threads: int = 4, hash_mb: int = 256) -> Iterator[chess.engine.SimpleEngine]:
    path = shutil.which("stockfish")
    if not path:
        raise RuntimeError("stockfish binary not found on PATH")
    eng = chess.engine.SimpleEngine.popen_uci(path)
    eng.configure({"Threads": threads, "Hash": hash_mb})
    try:
        yield eng
    finally:
        eng.quit()


def eval_cp(eng: chess.engine.SimpleEngine, board: chess.Board, depth: int = 14) -> int:
    """Centipawn evaluation from White's perspective (mates clamped to +/-MATE_CP)."""
    info = eng.analyse(board, chess.engine.Limit(depth=depth))
    return info["score"].white().score(mate_score=MATE_CP)


def analyse_all_moves(eng: chess.engine.SimpleEngine, board: chess.Board, depth: int = 12) -> dict[str, int]:
    """Centipawn value of every legal move from the side-to-move's perspective.

    Uses MultiPV over all legal moves so values are comparable within the position.
    Returns {uci: cp}. Higher is better for the side to move.
    """
    n = board.legal_moves.count()
    if n == 0:
        return {}
    infos = eng.analyse(board, chess.engine.Limit(depth=depth), multipv=n)
    out: dict[str, int] = {}
    for info in infos:
        pv = info.get("pv")
        if not pv:
            continue
        out[pv[0].uci()] = info["score"].pov(board.turn).score(mate_score=MATE_CP)
    # MultiPV can occasionally omit moves (pruned); fill by one-ply evaluation
    for mv in board.legal_moves:
        if mv.uci() not in out:
            board.push(mv)
            try:
                inf = eng.analyse(board, chess.engine.Limit(depth=max(1, depth - 2)))
                out[mv.uci()] = -inf["score"].pov(board.turn).score(mate_score=MATE_CP)
            finally:
                board.pop()
    return out


def cp_loss_table(move_cps: dict[str, int]) -> dict[str, int]:
    """Centipawn loss of each move relative to the best move (0 = best)."""
    best = max(move_cps.values())
    return {u: max(0, min(best - cp, 2000)) for u, cp in move_cps.items()}
