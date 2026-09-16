"""Turn a chess.Board into TypeSafe state at increasing levels of code-supplied context.

Three representations, so we can measure how much Jev benefits from code doing
the exact work it can do (attacks, defenders, material) and leaving judgment to the model:

  fen      : just the FEN string and side to move.
  ascii    : ASCII board with coordinates, side to move, move history, castling rights.
  rich     : ascii + explicit piece lists + code-computed tactical facts
             (checks, hanging pieces, attacked enemy pieces, material balance).
"""
from __future__ import annotations

from typing import Any

import chess

VALUES = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0}
NAMES = {chess.PAWN: "pawn", chess.KNIGHT: "knight", chess.BISHOP: "bishop", chess.ROOK: "rook",
         chess.QUEEN: "queen", chess.KING: "king"}


def side(board: chess.Board) -> str:
    return "White" if board.turn == chess.WHITE else "Black"


def sanitize_san(san: str) -> str:
    """Never leak checkmate: '#' becomes '+' so a mating move looks like any check."""
    return san.replace("#", "+")


def history_text(sans: list[str]) -> str:
    if not sans:
        return "(game start, no moves yet)"
    parts = []
    for i, san in enumerate(sans):
        if i % 2 == 0:
            parts.append(f"{i // 2 + 1}. {san}")
        else:
            parts.append(san)
    return " ".join(parts)


def ascii_board(board: chess.Board) -> str:
    rows = []
    for rank in range(7, -1, -1):
        cells = []
        for file in range(8):
            p = board.piece_at(chess.square(file, rank))
            cells.append(p.symbol() if p else ".")
        rows.append(f"{rank + 1} " + " ".join(cells))
    rows.append("  a b c d e f g h")
    return "\n".join(rows)


def piece_lists(board: chess.Board) -> dict[str, dict[str, list[str]]]:
    out: dict[str, dict[str, list[str]]] = {"white": {}, "black": {}}
    for sq, p in sorted(board.piece_map().items(), key=lambda kv: (-VALUES[kv[1].piece_type], kv[0])):
        color = "white" if p.color == chess.WHITE else "black"
        out[color].setdefault(NAMES[p.piece_type], []).append(chess.square_name(sq))
    return out


def material(board: chess.Board) -> dict[str, int]:
    w = sum(VALUES[p.piece_type] for p in board.piece_map().values() if p.color == chess.WHITE)
    b = sum(VALUES[p.piece_type] for p in board.piece_map().values() if p.color == chess.BLACK)
    return {"white": w, "black": b, "white_minus_black": w - b}


def least_valuable_attacker(board: chess.Board, color: chess.Color, sq: chess.Square) -> chess.Piece | None:
    attackers = board.attackers(color, sq)
    best: chess.Piece | None = None
    for a in attackers:
        p = board.piece_at(a)
        if p and (best is None or VALUES[p.piece_type] < VALUES[best.piece_type]):
            best = p
    return best


def tactical_facts(board: chess.Board) -> dict[str, Any]:
    """Exact, code-computed facts about the current position for the side to move."""
    us, them = board.turn, not board.turn
    hanging_ours, attacked_theirs = [], []
    for sq, p in board.piece_map().items():
        if p.piece_type == chess.KING:
            continue
        name = f"{NAMES[p.piece_type]} on {chess.square_name(sq)}"
        if p.color == us and board.is_attacked_by(them, sq):
            defended = board.is_attacked_by(us, sq)
            lva = least_valuable_attacker(board, them, sq)
            cheap = lva is not None and VALUES[lva.piece_type] < VALUES[p.piece_type]
            if not defended or cheap:
                how = f"attacked by {NAMES[lva.piece_type]}" if lva else "attacked"
                hanging_ours.append(f"{name} ({how}, {'defended' if defended else 'undefended'})")
        elif p.color == them and board.is_attacked_by(us, sq):
            defended = board.is_attacked_by(them, sq)
            lva = least_valuable_attacker(board, us, sq)
            cheap = lva is not None and VALUES[lva.piece_type] < VALUES[p.piece_type]
            if not defended or cheap:
                how = f"can be taken by our {NAMES[lva.piece_type]}" if lva else "attacked"
                attacked_theirs.append(f"{name} ({how}, {'defended' if defended else 'undefended'})")
    return {
        "side_to_move_in_check": board.is_check(),
        "our_pieces_in_danger": hanging_ours or ["none"],
        "enemy_pieces_we_can_win": attacked_theirs or ["none"],
        "material": material(board),
    }


def move_description(board: chess.Board, move: chess.Move, annotate: bool) -> str:
    """Plain-language description of a legal move; with annotate, add exact post-move safety facts."""
    p = board.piece_at(move.from_square)
    assert p is not None
    frm, to = chess.square_name(move.from_square), chess.square_name(move.to_square)
    if board.is_castling(move):
        desc = "castles " + ("kingside" if chess.square_file(move.to_square) == 6 else "queenside")
    else:
        desc = f"{NAMES[p.piece_type]} {frm} to {to}"
        if board.is_capture(move):
            cap_sq = move.to_square
            if board.is_en_passant(move):
                desc += ", captures pawn en passant"
            else:
                cp = board.piece_at(cap_sq)
                desc += f", captures {NAMES[cp.piece_type]}" if cp else ", captures"
        if move.promotion:
            desc += f", promotes to {NAMES[move.promotion]}"
    if board.gives_check(move):
        desc += ", gives check"
    if annotate and not board.is_castling(move):
        board.push(move)
        try:
            mover = board.piece_at(move.to_square)
            them = board.turn  # after push, opponent to move
            if mover and board.is_attacked_by(them, move.to_square):
                lva = least_valuable_attacker(board, them, move.to_square)
                defended = board.is_attacked_by(not them, move.to_square)
                desc += (f"; afterwards this {NAMES[mover.piece_type]} can be captured by a "
                         f"{NAMES[lva.piece_type] if lva else 'piece'} ({'defended' if defended else 'undefended'})")
            else:
                desc += "; the moved piece is safe from immediate capture"
        finally:
            board.pop()
    return desc


def legal_move_options(board: chess.Board, level: str) -> dict[str, str | None]:
    """Choice criteria: sanitized SAN -> description (None for the bare level)."""
    opts: dict[str, str | None] = {}
    for mv in board.legal_moves:
        san = sanitize_san(board.san(mv))
        if level == "fen":
            opts[san] = None
        elif level == "tactical":
            opts[san] = tactical_description(board, mv)
        else:
            opts[san] = move_description(board, mv, annotate=(level == "rich"))
    return opts


def build_state(board: chess.Board, sans: list[str], level: str) -> dict[str, Any]:
    s = side(board)
    if level == "fen":
        return {"fen": board.fen(), "side_to_move": s}
    st: dict[str, Any] = {
        "side_to_move": s,
        "board": ascii_board(board),
        "board_legend": "Uppercase = White pieces, lowercase = Black pieces, '.' = empty. "
                        "K king, Q queen, R rook, B bishop, N knight, P pawn. Rank 8 is at the top.",
        "fen": board.fen(),
        "move_history": history_text(sans),
        "castling_rights": board.fen().split(" ")[2] if board.castling_rights else "none",
    }
    if level in ("rich", "tactical"):
        st["pieces"] = piece_lists(board)
        st["facts_for_side_to_move"] = tactical_facts(board)
    if level == "tactical":
        st["how_to_read_move_options"] = (
            "Each move option ends with exact facts computed by a chess program. Priority order: (1) a move that "
            "DELIVERS CHECKMATE wins immediately; (2) never choose a move that ALLOWS THE OPPONENT TO CHECKMATE; "
            "(3) a move that LOSES material or EXPOSES a piece is bad even if it gives check or threatens something, "
            "because the opponent simply takes the piece; (4) among safe moves, prefer WINS material, then rescues, "
            "then threatens/forks, then quiet moves that develop or improve the position. Avoid repeating positions "
            "when a good alternative exists.")
    return st


def san_to_move(board: chess.Board, san: str) -> chess.Move | None:
    """Map a sanitized SAN option back to a legal move (mate '#' was shown as '+')."""
    for mv in board.legal_moves:
        if sanitize_san(board.san(mv)) == san:
            return mv
    return None


# ---------------------------------------------------------------------------
# "tactical" level: one-ply exact facts per move that any chess program computes
# in microseconds. Still no search; Jev still chooses.
# ---------------------------------------------------------------------------

def static_exchange(board: chess.Board, move: chess.Move, max_depth: int = 10) -> int:
    """Net material for the mover after the best capture sequence on the destination square (SEE).

    Uses real board pushes so pins, x-rays, and legality are handled by python-chess.
    """
    target = move.to_square
    captured = board.piece_at(target)
    gain = [1 if board.is_en_passant(move) else (VALUES[captured.piece_type] if captured else 0)]
    b = board.copy(stack=False)
    b.push(move)
    mover = b.piece_at(target)
    attacker_value = VALUES[mover.piece_type] if mover else 0
    d = 0
    while d < max_depth:
        side = b.turn
        best_mv, best_val = None, 99
        for sq in b.attackers(side, target):
            p = b.piece_at(sq)
            if p is None or VALUES[p.piece_type] >= best_val:
                continue
            cand = chess.Move(sq, target)
            if p.piece_type == chess.PAWN and chess.square_rank(target) in (0, 7):
                cand = chess.Move(sq, target, promotion=chess.QUEEN)
            if b.is_legal(cand):
                best_mv, best_val = cand, VALUES[p.piece_type]
        if best_mv is None:
            break
        d += 1
        gain.append(attacker_value - gain[d - 1])
        attacker_value = best_val
        b.push(best_mv)
    while d > 0:
        gain[d - 1] = -max(-gain[d - 1], gain[d])
        d -= 1
    return gain[0]


def hanging_pieces(board: chess.Board, color: chess.Color, exclude: chess.Square | None = None) -> list[str]:
    """Pieces of `color` (not king) attacked by the enemy and undefended, or attacked by something cheaper."""
    out = []
    them = not color
    for sq, p in board.piece_map().items():
        if p.color != color or p.piece_type == chess.KING or sq == exclude:
            continue
        if not board.is_attacked_by(them, sq):
            continue
        lva = least_valuable_attacker(board, them, sq)
        defended = board.is_attacked_by(color, sq)
        if not defended or (lva is not None and VALUES[lva.piece_type] < VALUES[p.piece_type]):
            out.append(f"{NAMES[p.piece_type]} on {chess.square_name(sq)}")
    return out


def allows_mate_in_one(board_after: chess.Board) -> bool:
    for reply in board_after.legal_moves:
        board_after.push(reply)
        mate = board_after.is_checkmate()
        board_after.pop()
        if mate:
            return True
    return False


def tactical_move_facts(board: chess.Board, move: chess.Move) -> dict[str, Any]:
    """Facts are *deltas* caused by this move, so they differ between options instead of repeating
    position-wide truths (which already sit in facts_for_side_to_move)."""
    us = board.turn
    hanging_before = set(hanging_pieces(board, us))
    attacked_before = set(hanging_pieces(board, not us))
    b = board.copy(stack=True)  # keep history so repetition can be detected
    b.push(move)
    hanging_after = set(hanging_pieces(b, us, exclude=move.to_square))
    attacked_after = set(hanging_pieces(b, not us))
    # a piece we moved away from a square no longer "exists" there; treat pieces by description string
    facts: dict[str, Any] = {
        "delivers_checkmate": b.is_checkmate(),
        "gives_check": b.is_check(),
        "allows_mate_in_one": False if b.is_game_over() else allows_mate_in_one(b),
        "exchange_on_target": static_exchange(board, move),
        "newly_exposes": sorted(hanging_after - hanging_before),
        "rescues": sorted(x for x in hanging_before - hanging_after
                          if not x.endswith(chess.square_name(move.from_square))),  # moving the piece itself counts too
        "moved_piece_was_in_danger": any(x.endswith(chess.square_name(move.from_square)) for x in hanging_before),
        "still_hanging": sorted(hanging_before & hanging_after),
        "newly_attacks": sorted(attacked_after - attacked_before),
        "repeats_position": b.is_repetition(2),
        "is_capture": board.is_capture(move),
    }
    return facts


def tactical_description(board: chess.Board, move: chess.Move) -> str:
    base = move_description(board, move, annotate=False)
    f = tactical_move_facts(board, move)
    notes = []
    x = f["exchange_on_target"]
    if f["delivers_checkmate"]:
        notes.append("DELIVERS CHECKMATE")
    if f["allows_mate_in_one"]:
        notes.append("ALLOWS THE OPPONENT TO CHECKMATE US NEXT MOVE")
    # material verdict first, in plain words; it should dominate everything below it
    if x < 0:
        notes.append(f"LOSES {-x} point(s) of material: the moved piece gets captured on {chess.square_name(move.to_square)}")
    elif x > 0:
        notes.append(f"WINS {x} point(s) of material on {chess.square_name(move.to_square)}")
    elif f["is_capture"]:
        notes.append(f"even trade on {chess.square_name(move.to_square)}")
    else:
        notes.append("moved piece is safe")
    if f["newly_exposes"]:
        notes.append("EXPOSES " + ", ".join(f["newly_exposes"]) + " to capture")
    if f["rescues"]:
        notes.append("rescues " + ", ".join(f["rescues"]))
    elif f["moved_piece_was_in_danger"]:
        notes.append("moves a piece that was in danger")
    # a threat only counts if the threatening piece survives
    if f["newly_attacks"] and x >= 0 and not f["newly_exposes"]:
        tag = "forks " if len(f["newly_attacks"]) >= 2 else "threatens "
        notes.append(tag + ", ".join(f["newly_attacks"]))
    if f["repeats_position"]:
        notes.append("repeats an earlier position")
    return base + "; " + "; ".join(notes)


def is_obvious_blunder(board: chess.Board, move: chess.Move) -> bool:
    """Hard rule for the optional code-side filter: never allow mate-in-one, never lose ≥3 material for nothing."""
    f = tactical_move_facts(board, move)
    if f["delivers_checkmate"]:
        return False
    return f["allows_mate_in_one"] or f["exchange_on_target"] <= -3
