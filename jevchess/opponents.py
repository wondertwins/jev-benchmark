"""Opponent bots of graded strength, all driven by one spec string.

  random        uniformly random legal move
  sf0           Stockfish skill level 0, depth 1  (sfN for skill N; sfN-dD for depth D)
  elo1320       Stockfish UCI_LimitStrength at that Elo, 50 ms per move (Stockfish's calibrated floor is 1320)
  mix50         plays a random move 50% of the time, otherwise sf0  (mixNN for NN %)
  greedy        captures the most valuable piece it can, else random (a classic ~beginner bot)
"""
from __future__ import annotations

import random
import re
import shutil

import chess
import chess.engine

VALUES = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0}


class Opponent:
    def __init__(self, spec: str, rng: random.Random):
        self.spec, self.rng = spec, rng
        self.eng: chess.engine.SimpleEngine | None = None
        self.limit = chess.engine.Limit(depth=1)
        self.p_random = 0.0
        if spec == "random":
            self.p_random = 1.0
        elif spec == "greedy":
            pass
        else:
            self.eng = chess.engine.SimpleEngine.popen_uci(shutil.which("stockfish"))
            self.eng.configure({"Threads": 1, "Hash": 16})
            if m := re.fullmatch(r"sf(\d+)(?:-d(\d+))?", spec):
                self.eng.configure({"Skill Level": int(m.group(1))})
                self.limit = chess.engine.Limit(depth=int(m.group(2) or 1))
            elif m := re.fullmatch(r"elo(\d+)", spec):
                self.eng.configure({"UCI_LimitStrength": True, "UCI_Elo": int(m.group(1))})
                self.limit = chess.engine.Limit(time=0.05)
            elif m := re.fullmatch(r"mix(\d+)", spec):
                self.p_random = int(m.group(1)) / 100
                self.eng.configure({"Skill Level": 0})
                self.limit = chess.engine.Limit(depth=1)
            else:
                raise ValueError(f"unknown opponent spec {spec!r}")

    def move(self, board: chess.Board) -> chess.Move:
        legal = list(board.legal_moves)
        if self.spec == "greedy":
            caps = [(VALUES[board.piece_at(m.to_square).piece_type] if board.piece_at(m.to_square) else 1, m)
                    for m in legal if board.is_capture(m)]
            if caps:
                best = max(v for v, _ in caps)
                return self.rng.choice([m for v, m in caps if v == best])
            return self.rng.choice(legal)
        if self.p_random and self.rng.random() < self.p_random:
            return self.rng.choice(legal)
        assert self.eng is not None
        return self.eng.play(board, self.limit).move

    def close(self) -> None:
        if self.eng is not None:
            self.eng.quit()


def label(spec: str) -> str:
    if spec == "random":
        return "Random mover"
    if spec == "greedy":
        return "Greedy capture bot"
    if m := re.fullmatch(r"sf(\d+)(?:-d(\d+))?", spec):
        return f"Stockfish skill {m.group(1)}, depth {m.group(2) or 1}"
    if m := re.fullmatch(r"elo(\d+)", spec):
        return f"Stockfish limited to {m.group(1)} Elo"
    if m := re.fullmatch(r"mix(\d+)", spec):
        return f"Stockfish skill 0 depth 1, {m.group(1)}% random moves"
    return spec
