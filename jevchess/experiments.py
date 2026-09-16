"""The chess experiments. Each returns a JSON-serializable result dict.

A  move_choice   : one Choice over all legal moves (state level: fen | ascii | rich)
B  move_scores   : one Score per legal move, all in one request; code takes the argmax
C  hierarchical  : Choice which piece, then Choice which destination (two requests)
D  perception    : Nouls about the position vs exact ground truth (can it read a board?)
E  mate_in_one   : Choice over legal moves on positions with a forced mate-in-one
F  eval_score    : Score "who is better" vs Stockfish evaluation
G  play_game     : Jev plays full games (rich Choice) vs a random mover / weak Stockfish
"""
from __future__ import annotations

import asyncio
import json
import random
import statistics
from pathlib import Path
from typing import Any

import chess
import chess.engine
from typesafe_sdk import Choice, Noul, Score

from jevcommon.client import JevClient
from .engine import analyse_all_moves, cp_loss_table, eval_cp
from .state import (NAMES, build_state, legal_move_options, move_description, san_to_move, sanitize_san,
                    side)

RUNS = Path(__file__).resolve().parent.parent / "runs"
GT_CACHE = RUNS / "ground_truth.json"
_gt: dict[str, dict[str, int]] = json.loads(GT_CACHE.read_text()) if GT_CACHE.exists() else {}


def ground_truth(eng: chess.engine.SimpleEngine, board: chess.Board, depth: int = 12) -> dict[str, int]:
    key = f"{board.fen()}|{depth}"
    if key not in _gt:
        _gt[key] = analyse_all_moves(eng, board, depth)
        GT_CACHE.write_text(json.dumps(_gt))
    return _gt[key]


def summarize_losses(rows: list[dict[str, Any]]) -> dict[str, Any]:
    losses = [r["cp_loss"] for r in rows if r.get("cp_loss") is not None]
    if not losses:
        return {"n": 0}
    rand = [r["random_baseline_cp_loss"] for r in rows if r.get("random_baseline_cp_loss") is not None]
    return {
        "n": len(losses),
        "mean_cp_loss": round(statistics.mean(losses), 1),
        "median_cp_loss": round(statistics.median(losses), 1),
        "pct_best_move": round(100 * sum(l == 0 for l in losses) / len(losses), 1),
        "pct_top3": round(100 * sum(r.get("rank", 99) <= 3 for r in rows if r.get("cp_loss") is not None) / len(losses), 1),
        "pct_blunder_200cp": round(100 * sum(l >= 200 for l in losses) / len(losses), 1),
        "random_baseline_mean_cp_loss": round(statistics.mean(rand), 1) if rand else None,
        "mean_confidence": round(statistics.mean([r["confidence"] for r in rows if r.get("confidence") is not None]), 3)
        if any(r.get("confidence") is not None for r in rows) else None,
    }


def _rank_of(move_cps: dict[str, int], uci: str) -> int:
    ordered = sorted(move_cps.values(), reverse=True)
    return ordered.index(move_cps[uci]) + 1


def _random_baseline(losses: dict[str, int]) -> float:
    return statistics.mean(losses.values())


def choice_instructions(board: chess.Board) -> dict[str, str]:
    s = side(board)
    return {
        "question": f"Which legal move should {s} play now?",
        "goal": f"Pick the move that gives {s} the best chance to win the game. Prefer moves that deliver "
                f"checkmate, win material safely, or create strong threats; avoid moves that lose material or "
                f"allow the opponent a checkmate or a winning capture.",
        "options": "Every option is a legal move in standard algebraic notation with a plain description.",
    }


# ---------------------------------------------------------------- A: direct Choice
async def exp_move_choice(client: JevClient, eng: chess.engine.SimpleEngine, positions: list[dict], level: str) -> dict:
    async def one(pos: dict) -> dict:
        board = chess.Board(pos["fen"])
        gt = ground_truth(eng, board)
        losses = cp_loss_table(gt)
        opts = legal_move_options(board, level)
        resp = await client.ask(build_state(board, pos["sans"], level),
                                {"move": Choice(instructions=choice_instructions(board), criteria=opts)},
                                meta={"exp": "A", "level": level, "pos": pos["id"]})
        row: dict[str, Any] = {"pos": pos["id"], "n_legal": len(opts), "random_baseline_cp_loss": _random_baseline(losses)}
        if resp is None:
            row["error"] = True
            return row
        ans = resp.choices["move"]
        mv = san_to_move(board, ans.choice)
        if mv is None:
            row["error"] = f"unmapped choice {ans.choice}"
            return row
        best_uci = max(gt, key=gt.get)
        row.update({"chosen": ans.choice, "chosen_uci": mv.uci(), "best": board.san(chess.Move.from_uci(best_uci)),
                    "cp_loss": losses[mv.uci()], "rank": _rank_of(gt, mv.uci()), "confidence": ans.confidence,
                    "top_prob": max(ans.probabilities.values()), "input_tokens": resp.usage.input_tokens})
        return row

    rows = await asyncio.gather(*(one(p) for p in positions))
    return {"experiment": "A_move_choice", "level": level, "summary": summarize_losses(list(rows)), "rows": list(rows)}


# ---------------------------------------------------------------- B: per-move Score fan-out
MOVE_QUALITY_LEVELS = [
    "Loses material for nothing, or lets the opponent deliver checkmate or win material immediately",
    "Passive or pointless: shuffles or retreats without purpose, or weakens the king or pawn structure",
    "Sound and normal: develops a piece, defends, castles, or improves the position without changing material",
    "Strong: wins material safely, creates a serious threat the opponent must answer, or gains a clear advantage",
    "Decisive: delivers checkmate now, or forces a large material gain or an unstoppable mating attack",
]


async def exp_move_scores(client: JevClient, eng: chess.engine.SimpleEngine, positions: list[dict], level: str = "rich") -> dict:
    async def one(pos: dict) -> dict:
        board = chess.Board(pos["fen"])
        gt = ground_truth(eng, board)
        losses = cp_loss_table(gt)
        s = side(board)
        questions: dict[str, Any] = {}
        san_by_qid: dict[str, str] = {}
        for i, mv in enumerate(board.legal_moves):
            san = sanitize_san(board.san(mv))
            desc = move_description(board, mv, annotate=(level == "rich"))
            qid = f"m{i}"
            san_by_qid[qid] = san
            questions[qid] = Score(
                instructions={"question": f"How good is the move {san} ({desc}) for {s} in this position?",
                              "focus": f"Judge the consequences of this specific move for {s}, assuming the opponent replies well."},
                criteria=MOVE_QUALITY_LEVELS)
        resp = await client.ask(build_state(board, pos["sans"], level), questions,
                                meta={"exp": "B", "level": level, "pos": pos["id"]})
        row: dict[str, Any] = {"pos": pos["id"], "n_legal": len(questions), "random_baseline_cp_loss": _random_baseline(losses)}
        if resp is None:
            row["error"] = True
            return row
        scored = {san_by_qid[q]: a.score for q, a in resp.scores.items()}
        best_san = max(scored, key=scored.get)
        mv = san_to_move(board, best_san)
        if mv is None:
            row["error"] = f"unmapped {best_san}"
            return row
        # Spearman between Jev's move scores and Stockfish cp over all legal moves
        sf = {sanitize_san(board.san(chess.Move.from_uci(u))): cp for u, cp in gt.items()}
        row.update({"chosen": best_san, "chosen_score": round(scored[best_san], 3), "cp_loss": losses[mv.uci()],
                    "rank": _rank_of(gt, mv.uci()), "spearman_vs_stockfish": spearman([scored[k] for k in scored], [sf[k] for k in scored]),
                    "confidence": statistics.mean(a.confidence for a in resp.scores.values()),
                    "input_tokens": resp.usage.input_tokens})
        return row

    rows = await asyncio.gather(*(one(p) for p in positions))
    summ = summarize_losses(list(rows))
    sp = [r["spearman_vs_stockfish"] for r in rows if r.get("spearman_vs_stockfish") is not None]
    summ["mean_spearman_move_scores_vs_stockfish"] = round(statistics.mean(sp), 3) if sp else None
    return {"experiment": "B_move_scores", "level": level, "summary": summ, "rows": list(rows)}


# ---------------------------------------------------------------- C: hierarchical piece -> square
async def exp_hierarchical(client: JevClient, eng: chess.engine.SimpleEngine, positions: list[dict], level: str = "rich") -> dict:
    async def one(pos: dict) -> dict:
        board = chess.Board(pos["fen"])
        gt = ground_truth(eng, board)
        losses = cp_loss_table(gt)
        s = side(board)
        by_piece: dict[str, list[chess.Move]] = {}
        for mv in board.legal_moves:
            p = board.piece_at(mv.from_square)
            by_piece.setdefault(f"{NAMES[p.piece_type]}_{chess.square_name(mv.from_square)}", []).append(mv)
        piece_opts = {k: f"{k.split('_')[0]} on {k.split('_')[1]}; can go to " +
                      ", ".join(chess.square_name(m.to_square) for m in mvs) for k, mvs in by_piece.items()}
        state = build_state(board, pos["sans"], level)
        r1 = await client.ask(state, {"piece": Choice(
            instructions={"question": f"Which piece should {s} move now?",
                          "goal": f"Pick the piece whose best move most improves {s}'s chances: win material, "
                                  f"deliver mate or threats, or escape danger."}, criteria=piece_opts)},
            meta={"exp": "C1", "pos": pos["id"]})
        row: dict[str, Any] = {"pos": pos["id"], "n_pieces": len(piece_opts), "n_legal": len(losses),
                               "random_baseline_cp_loss": _random_baseline(losses)}
        if r1 is None or r1.choices["piece"].choice not in by_piece:
            row["error"] = "piece step failed"
            return row
        piece_key = r1.choices["piece"].choice
        mvs = by_piece[piece_key]
        best_uci = max(gt, key=gt.get)
        if len(mvs) == 1:
            mv = mvs[0]
            conf2 = None
        else:
            opts = {sanitize_san(board.san(m)): move_description(board, m, annotate=(level == "rich")) for m in mvs}
            r2 = await client.ask(state, {"move": Choice(
                instructions={"question": f"{s} has decided to move the {piece_key.replace('_', ' on ')}. Which move should it make?",
                              "goal": f"Pick the destination that gives {s} the best chance to win."}, criteria=opts)},
                meta={"exp": "C2", "pos": pos["id"]})
            if r2 is None:
                row["error"] = "square step failed"
                return row
            mv = san_to_move(board, r2.choices["move"].choice)
            conf2 = r2.choices["move"].confidence
            if mv is None:
                row["error"] = "unmapped"
                return row
        best_piece_loss = min(losses[m.uci()] for m in mvs)
        row.update({"piece": piece_key, "piece_confidence": r1.choices["piece"].confidence, "chosen": board.san(mv),
                    "best": board.san(chess.Move.from_uci(best_uci)), "cp_loss": losses[mv.uci()], "rank": _rank_of(gt, mv.uci()),
                    "best_possible_after_piece_choice": best_piece_loss, "confidence": conf2})
        return row

    rows = await asyncio.gather(*(one(p) for p in positions))
    summ = summarize_losses(list(rows))
    bp = [r["best_possible_after_piece_choice"] for r in rows if "best_possible_after_piece_choice" in r]
    summ["mean_cp_loss_locked_in_by_piece_choice"] = round(statistics.mean(bp), 1) if bp else None
    return {"experiment": "C_hierarchical", "level": level, "summary": summ, "rows": list(rows)}


# ---------------------------------------------------------------- D: perception Nouls
def perception_truth(board: chess.Board) -> dict[str, Any]:
    us, them = board.turn, not board.turn
    mate1 = False
    for mv in board.legal_moves:
        board.push(mv)
        mate1 = mate1 or board.is_checkmate()
        board.pop()
        if mate1:
            break
    free_capture = any(board.is_capture(mv) and not board.is_en_passant(mv) and not board.attackers(them, mv.to_square)
                       and board.piece_at(mv.to_square) is not None for mv in board.legal_moves)
    own_hanging = any(p.color == us and p.piece_type not in (chess.PAWN, chess.KING) and board.is_attacked_by(them, sq)
                      and not board.is_attacked_by(us, sq) for sq, p in board.piece_map().items())
    can_castle = any(board.is_castling(mv) for mv in board.legal_moves)
    from .state import material
    m = material(board)
    more = "white" if m["white_minus_black"] > 0 else "black" if m["white_minus_black"] < 0 else "equal"
    return {"in_check": board.is_check(), "mate_in_one": mate1, "free_capture": free_capture,
            "own_piece_hanging": own_hanging, "can_castle": can_castle, "more_material": more}


async def exp_perception(client: JevClient, positions: list[dict], level: str = "ascii") -> dict:
    async def one(pos: dict) -> dict:
        board = chess.Board(pos["fen"])
        s = side(board)
        truth = perception_truth(board)
        qs = {
            "in_check": Noul(instructions=f"{s}, the side to move, is currently in check: the {s} king is attacked by an enemy piece.",
                             criteria={"true": f"The {s} king is under attack right now.", "false": f"The {s} king is not attacked."}),
            "mate_in_one": Noul(instructions=f"{s} has a legal move that delivers checkmate immediately (mate in one).",
                                criteria={"true": "Some legal move ends the game by checkmate this turn.", "false": "No move gives checkmate this turn."}),
            "free_capture": Noul(instructions=f"{s} can capture an enemy piece or pawn that is completely undefended, winning it for free.",
                                 criteria={"true": "A legal capture exists whose target square is not protected by any enemy piece.",
                                           "false": "Every capturable enemy piece is protected, or no captures exist."}),
            "own_piece_hanging": Noul(instructions=f"{s} has a knight, bishop, rook, or queen that is attacked by the opponent and defended by nothing.",
                                      criteria={"true": f"At least one {s} piece (not a pawn or the king) can be taken for free.",
                                                "false": f"All attacked {s} pieces are defended, or none are attacked."}),
            "can_castle": Noul(instructions=f"{s} can legally castle on this move (kingside or queenside).",
                               criteria={"true": "Castling is a legal move right now.", "false": "Castling is not legal right now."}),
            "more_material": Choice(instructions="Which side has more material, counting pawn 1, knight 3, bishop 3, rook 5, queen 9?",
                                    criteria={"white": "White's pieces add up to more", "black": "Black's pieces add up to more",
                                              "equal": "Both sides have the same total"}),
        }
        resp = await client.ask(build_state(board, pos["sans"], level), qs, meta={"exp": "D", "pos": pos["id"]})
        row: dict[str, Any] = {"pos": pos["id"], "truth": truth}
        if resp is None:
            row["error"] = True
            return row
        row["pred"] = {k: round(resp.nouls[k].noul, 3) for k in qs if k != "more_material"}
        row["pred"]["more_material"] = resp.choices["more_material"].choice
        row["pred_material_conf"] = resp.choices["more_material"].confidence
        row["input_tokens"] = resp.usage.input_tokens
        return row

    rows = [r for r in await asyncio.gather(*(one(p) for p in positions))]
    ok = [r for r in rows if "pred" in r]
    summ: dict[str, Any] = {"n": len(ok)}
    for k in ["in_check", "mate_in_one", "free_capture", "own_piece_hanging", "can_castle"]:
        acc = statistics.mean(((r["pred"][k] >= 0.5) == r["truth"][k]) for r in ok) if ok else None
        brier = statistics.mean((r["pred"][k] - float(r["truth"][k])) ** 2 for r in ok) if ok else None
        base = statistics.mean(float(r["truth"][k]) for r in ok) if ok else None
        summ[k] = {"accuracy": round(acc, 3), "brier": round(brier, 3), "positive_rate": round(base, 3),
                   "majority_baseline": round(max(base, 1 - base), 3)}
    summ["more_material"] = {"accuracy": round(statistics.mean(r["pred"]["more_material"] == r["truth"]["more_material"] for r in ok), 3)
                             if ok else None}
    return {"experiment": "D_perception", "level": level, "summary": summ, "rows": rows}


# ---------------------------------------------------------------- E: mate in one
async def exp_mate_in_one(client: JevClient, positions: list[dict], level: str) -> dict:
    async def one(pos: dict) -> dict:
        board = chess.Board(pos["fen"])
        opts = legal_move_options(board, level)
        resp = await client.ask(build_state(board, pos["sans"], level),
                                {"move": Choice(instructions=choice_instructions(board), criteria=opts)},
                                meta={"exp": "E", "level": level, "pos": pos["id"]})
        mates = set(pos["mating_moves"])
        row: dict[str, Any] = {"pos": pos["id"], "n_legal": len(opts), "n_mating": len(mates),
                               "random_baseline": len(mates) / len(opts)}
        if resp is None:
            row["error"] = True
            return row
        ans = resp.choices["move"]
        mv = san_to_move(board, ans.choice)
        mate_prob = sum(p for san, p in ans.probabilities.items()
                        if (m := san_to_move(board, san)) is not None and m.uci() in mates)
        row.update({"chosen": ans.choice, "found_mate": bool(mv and mv.uci() in mates), "confidence": ans.confidence,
                    "prob_mass_on_mating_moves": round(mate_prob, 3), "input_tokens": resp.usage.input_tokens})
        return row

    rows = list(await asyncio.gather(*(one(p) for p in positions)))
    ok = [r for r in rows if "found_mate" in r]
    summ = {"n": len(ok),
            "accuracy": round(statistics.mean(r["found_mate"] for r in ok), 3) if ok else None,
            "random_baseline": round(statistics.mean(r["random_baseline"] for r in ok), 3) if ok else None,
            "mean_prob_mass_on_mating_moves": round(statistics.mean(r["prob_mass_on_mating_moves"] for r in ok), 3) if ok else None}
    return {"experiment": "E_mate_in_one", "level": level, "summary": summ, "rows": rows}


# ---------------------------------------------------------------- F: position evaluation Score
EVAL_LEVELS = [
    "Black is winning: Black is far ahead in material, or has an unstoppable attack or forced mate",
    "Black is clearly better: Black is ahead by about a minor piece or more, or has a large lasting advantage",
    "Black is slightly better: a small edge for Black such as an extra pawn, more active pieces, or a safer king",
    "Roughly equal: material is level and neither side has a meaningful advantage",
    "White is slightly better: a small edge for White such as an extra pawn, more active pieces, or a safer king",
    "White is clearly better: White is ahead by about a minor piece or more, or has a large lasting advantage",
    "White is winning: White is far ahead in material, or has an unstoppable attack or forced mate",
]


def cp_bucket(cp: int) -> int:
    if cp < -500: return 0
    if cp < -200: return 1
    if cp < -60: return 2
    if cp <= 60: return 3
    if cp <= 200: return 4
    if cp <= 500: return 5
    return 6


def spearman(x: list[float], y: list[float]) -> float | None:
    if len(x) < 3:
        return None
    def ranks(v: list[float]) -> list[float]:
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2 + 1
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r
    rx, ry = ranks(x), ranks(y)
    mx, my = statistics.mean(rx), statistics.mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = (sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)) ** 0.5
    return round(num / den, 3) if den else None


async def exp_eval_score(client: JevClient, eng: chess.engine.SimpleEngine, positions: list[dict], level: str = "ascii") -> dict:
    async def one(pos: dict) -> dict:
        board = chess.Board(pos["fen"])
        cp = eval_cp(eng, board, depth=14)
        resp = await client.ask(build_state(board, pos["sans"], level), {"eval": Score(
            instructions={"question": "Who is better in this position, and by how much?",
                          "focus": "Weigh material, king safety, piece activity, and immediate tactics. "
                                   "The scale runs from Black winning (low) to White winning (high)."},
            criteria=EVAL_LEVELS)}, meta={"exp": "F", "pos": pos["id"]})
        row: dict[str, Any] = {"pos": pos["id"], "stockfish_cp_white": cp, "truth_bucket": cp_bucket(cp)}
        if resp is None:
            row["error"] = True
            return row
        a = resp.scores["eval"]
        row.update({"score": round(a.score, 3), "pred_bucket": round(a.score), "confidence": a.confidence,
                    "input_tokens": resp.usage.input_tokens})
        return row

    rows = list(await asyncio.gather(*(one(p) for p in positions)))
    ok = [r for r in rows if "score" in r]
    def sign(b: int) -> int: return (b > 3) - (b < 3)
    summ = {"n": len(ok),
            "spearman_vs_stockfish": spearman([r["score"] for r in ok], [r["stockfish_cp_white"] for r in ok]) if ok else None,
            "exact_bucket_accuracy": round(statistics.mean(r["pred_bucket"] == r["truth_bucket"] for r in ok), 3) if ok else None,
            "within_one_bucket": round(statistics.mean(abs(r["pred_bucket"] - r["truth_bucket"]) <= 1 for r in ok), 3) if ok else None,
            "who_is_better_accuracy": round(statistics.mean(sign(r["pred_bucket"]) == sign(r["truth_bucket"]) for r in ok), 3) if ok else None,
            "always_equal_baseline": round(statistics.mean(r["truth_bucket"] == 3 for r in ok), 3) if ok else None}
    return {"experiment": "F_eval_score", "level": level, "summary": summ, "rows": rows}


# ---------------------------------------------------------------- G: play full games
async def exp_play_game(client: JevClient, eng: chess.engine.SimpleEngine, level: str, opponent: str,
                        jev_color: chess.Color = chess.WHITE, max_plies: int = 120, seed: int = 3) -> dict:
    rng = random.Random(seed)
    board = chess.Board()
    sans: list[str] = []
    jev_moves: list[dict[str, Any]] = []
    opp_eng: chess.engine.SimpleEngine | None = None
    if opponent.startswith("sf"):
        import shutil
        opp_eng = chess.engine.SimpleEngine.popen_uci(shutil.which("stockfish"))
        opp_eng.configure({"Skill Level": int(opponent[2:]) if opponent[2:].isdigit() else 0})
    try:
        while not board.is_game_over() and len(sans) < max_plies:
            if board.turn == jev_color:
                gt = ground_truth(eng, board, depth=10)
                losses = cp_loss_table(gt)
                opts = legal_move_options(board, level)
                resp = await client.ask(build_state(board, sans, level),
                                        {"move": Choice(instructions=choice_instructions(board), criteria=opts)},
                                        meta={"exp": "G", "ply": len(sans)})
                mv = san_to_move(board, resp.choices["move"].choice) if resp else None
                if mv is None:
                    mv = rng.choice(list(board.legal_moves))
                    jev_moves.append({"ply": len(sans), "san": board.san(mv), "fallback_random": True})
                else:
                    jev_moves.append({"ply": len(sans), "san": board.san(mv), "cp_loss": losses[mv.uci()],
                                      "rank": _rank_of(gt, mv.uci()), "confidence": resp.choices["move"].confidence,
                                      "n_legal": len(opts)})
            elif opp_eng is not None:
                mv = opp_eng.play(board, chess.engine.Limit(depth=1)).move
            else:
                mv = rng.choice(list(board.legal_moves))
            sans.append(board.san(mv))
            board.push(mv)
    finally:
        if opp_eng:
            opp_eng.quit()
    losses = [m["cp_loss"] for m in jev_moves if "cp_loss" in m]
    outcome = board.result(claim_draw=True) if board.is_game_over(claim_draw=True) else "unfinished"
    return {"experiment": "G_play_game", "level": level, "opponent": opponent,
            "jev_color": "white" if jev_color == chess.WHITE else "black",
            "summary": {"result": outcome, "termination": board.outcome(claim_draw=True).termination.name if board.outcome(claim_draw=True) else "ply_cap",
                        "plies": len(sans), "jev_mean_cp_loss": round(statistics.mean(losses), 1) if losses else None,
                        "jev_pct_best_move": round(100 * sum(l == 0 for l in losses) / len(losses), 1) if losses else None,
                        "jev_blunders_200cp": sum(l >= 200 for l in losses),
                        "final_eval_cp_white": eval_cp(eng, board, 12) if not board.is_game_over() else None},
            "pgn_moves": " ".join(f"{i//2+1}. {s}" if i % 2 == 0 else s for i, s in enumerate(sans)),
            "final_fen": board.fen(), "jev_moves": jev_moves}
