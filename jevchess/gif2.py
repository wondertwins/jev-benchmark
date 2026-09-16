"""v2 renderer: smooth, social-media-friendly animation of a recorded Jev game.

  uv run --group media python -m jevchess.gif2 --game random
  uv run --group media python -m jevchess.gif2 --game sf0_tactical_s3

Compared with gif.py (kept as-is): pieces slide between squares with easing, captured pieces
fade, a live Stockfish eval bar animates beside the board, Jev's probability bars grow in,
verdict pills, title and end cards, 1280x720 MP4 at 24 fps plus an 800px GIF via ffmpeg palettegen.
"""
from __future__ import annotations

import argparse
import glob
import io
import json
import math
import shutil
import subprocess
from pathlib import Path

import cairosvg
import chess
import chess.svg
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .engine import eval_cp, open_engine

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "runs"
MEDIA = RUNS / "media"

W, H, FPS = 1280, 720, 24
BX, BY, BS = 64, 60, 600          # board origin and size
SQ = BS // 8
PX = BX + BS + 52                  # panel x
LIGHT, DARK = (240, 217, 181), (181, 136, 99)
BG_TOP, BG_BOT = (11, 14, 20), (22, 28, 40)
FG, DIM, MUTED = (240, 242, 247), (150, 158, 176), (60, 66, 82)
GOLD, TEAL, GREEN, RED, AMBER = (250, 204, 77), (78, 205, 196), (94, 214, 130), (240, 96, 96), (255, 170, 70)
SLIDE, BARS, HOLD_JEV, HOLD_OPP = 9, 8, 12, 6


# ----------------------------------------------------------------------------- assets
def _font(size: int, bold: bool = False, mono: bool = False) -> ImageFont.FreeTypeFont:
    if mono:
        for p in ["/System/Library/Fonts/Menlo.ttc", "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"]:
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                pass
    for p in ["/System/Library/Fonts/SFNS.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf"]:
        try:
            f = ImageFont.truetype(p, size)
            if bold and p.endswith("SFNS.ttf"):
                try:
                    f.set_variation_by_name("Bold")
                except Exception:  # noqa: BLE001
                    pass
            return f
        except OSError:
            continue
    return ImageFont.load_default()


F_H1, F_H2, F_SAN, F_TXT, F_SM, F_MONO, F_CARD = _font(38, True), _font(18), _font(54, True), _font(20), _font(15), _font(17, mono=True), _font(46, True)
_PIECES: dict[str, Image.Image] = {}


def piece_img(p: chess.Piece) -> Image.Image:
    k = p.symbol()
    if k not in _PIECES:
        svg = chess.svg.piece(p, size=SQ)
        _PIECES[k] = Image.open(io.BytesIO(cairosvg.svg2png(bytestring=svg.encode(), output_width=SQ, output_height=SQ))).convert("RGBA")
    return _PIECES[k]


def background(glow: bool = True) -> Image.Image:
    im = Image.new("RGB", (W, H), BG_TOP)
    d = ImageDraw.Draw(im)
    for y in range(H):
        t = y / H
        d.line([(0, y), (W, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(BG_TOP, BG_BOT)))
    if not glow:
        return im
    # soft glow behind the board
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(glow).rounded_rectangle([BX - 30, BY - 30, BX + BS + 30, BY + BS + 30], 40, fill=(GOLD[0], GOLD[1], GOLD[2], 38))
    glow = glow.filter(ImageFilter.GaussianBlur(40))
    im.paste(glow, (0, 0), glow)
    return im


BG = None
BG_PLAIN = None


def sq_xy(sq: chess.Square) -> tuple[int, int]:
    return BX + chess.square_file(sq) * SQ, BY + (7 - chess.square_rank(sq)) * SQ


def ease(t: float) -> float:
    return 1 - (1 - t) ** 3


def eval_to_share(cp: int) -> float:
    """White's share of the eval bar, lichess-style."""
    return max(0.03, min(0.97, 0.5 + 0.5 * (2 / (1 + math.exp(-0.00368208 * cp)) - 1)))


# ----------------------------------------------------------------------------- drawing
def draw_board(im: Image.Image, pieces: dict[chess.Square, chess.Piece], moving: list[tuple[chess.Piece, tuple[float, float]]],
               fading: list[tuple[chess.Piece, chess.Square, float]], last: chess.Move | None, check_sq: chess.Square | None,
               hl_alpha: float) -> None:
    d = ImageDraw.Draw(im)
    for sq in chess.SQUARES:
        x, y = sq_xy(sq)
        d.rectangle([x, y, x + SQ, y + SQ], fill=LIGHT if (chess.square_file(sq) + chess.square_rank(sq)) % 2 else DARK)
    # coordinates
    for f in range(8):
        d.text((BX + f * SQ + SQ - 13, BY + BS - 18), "abcdefgh"[f], font=F_SM, fill=(90, 70, 50) if f % 2 == 0 else (240, 230, 210))
    for r in range(8):
        d.text((BX + 4, BY + (7 - r) * SQ + 3), str(r + 1), font=F_SM, fill=(240, 230, 210) if r % 2 == 0 else (90, 70, 50))
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(ov)
    if last is not None:
        for sq in (last.from_square, last.to_square):
            x, y = sq_xy(sq)
            od.rectangle([x, y, x + SQ, y + SQ], fill=(250, 204, 77, int(110 * hl_alpha)))
    if check_sq is not None:
        x, y = sq_xy(check_sq)
        g = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(g).ellipse([x - 6, y - 6, x + SQ + 6, y + SQ + 6], fill=(240, 60, 60, 200))
        ov = Image.alpha_composite(ov, g.filter(ImageFilter.GaussianBlur(10)))
    im.paste(ov, (0, 0), ov)
    for sq, p in pieces.items():
        im.paste(piece_img(p), sq_xy(sq), piece_img(p))
    for p, sq, a in fading:
        pi = piece_img(p).copy()
        pi.putalpha(pi.getchannel("A").point(lambda v: int(v * a)))
        im.paste(pi, sq_xy(sq), pi)
    for p, (x, y) in moving:
        im.paste(piece_img(p), (int(x), int(y)), piece_img(p))


def draw_eval_bar(im: Image.Image, share: float) -> None:
    d = ImageDraw.Draw(im)
    x0, y0, w = BX + BS + 18, BY, 16
    d.rounded_rectangle([x0, y0, x0 + w, y0 + BS], 8, fill=(40, 40, 46))
    wh = int(BS * share)
    d.rounded_rectangle([x0, y0 + BS - wh, x0 + w, y0 + BS], 8, fill=(235, 235, 235))
    d.line([(x0, y0 + BS // 2), (x0 + w, y0 + BS // 2)], fill=(120, 120, 120), width=1)


def pill(d: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, color: tuple, font=F_SM) -> int:
    tw = d.textlength(text, font=font)
    x, y = xy
    d.rounded_rectangle([x, y, x + tw + 22, y + 28], 14, fill=tuple(int(c * 0.22) for c in color))
    d.text((x + 11, y + 5), text, font=font, fill=color)
    return int(tw + 22)


def draw_panel(im: Image.Image, title: str, ply: int | None, san: str | None, mover: str, opp_label: str, probs: dict | None,
               info: dict | None, bar_t: float, moves: list[str], label_alpha: float, result_line: str | None = None) -> None:
    d = ImageDraw.Draw(im)
    d.text((PX, 56), title, font=F_H1, fill=FG)
    d.text((PX, 104), "TypeSafe's System One model. No lookahead, no reasoning:", font=F_H2, fill=DIM)
    d.text((PX, 128), "one Choice question over every legal move, ~200 ms per move.", font=F_H2, fill=DIM)
    # move card
    d.rounded_rectangle([PX, 176, W - 48, 296], 18, fill=(255, 255, 255, 10) if im.mode == "RGBA" else (26, 32, 45))
    if san is not None and ply is not None:
        num = f"{ply // 2 + 1}{'.' if ply % 2 == 0 else '...'}"
        col = GOLD if mover == "jev" else FG
        col = tuple(int(c * label_alpha + BG_BOT[i] * (1 - label_alpha)) for i, c in enumerate(col))
        d.text((PX + 24, 190), f"{num} {san}", font=F_SAN, fill=col)
        who = "Jev" if mover == "jev" else opp_label
        d.text((PX + 24, 256), f"{who} plays", font=F_TXT, fill=DIM)
        if info and info.get("forced_mate_by_code") and result_line is None:
            pill(d, (PX + 300, 214), "code played the mate (hard rule)", GREEN)
    else:
        d.text((PX + 24, 200), "Jev to move", font=F_SAN, fill=FG)
    # probability card
    y = 318
    if result_line is not None:
        y = 478  # below the poster headline and subline
        d.rounded_rectangle([PX, y, W - 48, y + 96], 18, fill=(26, 32, 45))
        d.text((PX + 24, y + 18), "Result", font=F_SM, fill=DIM)
        d.text((PX + 24, y + 44), result_line, font=F_TXT, fill=GOLD)
        probs = None
    else:
        d.rounded_rectangle([PX, y, W - 48, y + 262], 18, fill=(26, 32, 45))
    if mover == "jev" and probs:
        d.text((PX + 24, y + 16), "Jev's probability over legal moves", font=F_SM, fill=DIM)
        top = sorted(probs["probabilities"].items(), key=lambda kv: -kv[1])[:5]
        bw = W - 48 - PX - 200
        yy = y + 44
        for name, p in top:
            chosen = name.replace("#", "+") == (san or "").replace("#", "+")
            d.text((PX + 24, yy), name, font=F_MONO, fill=GOLD if chosen else FG)
            d.rounded_rectangle([PX + 118, yy + 4, PX + 118 + bw, yy + 18], 7, fill=(40, 47, 63))
            wv = max(6, int(bw * p * ease(bar_t)))
            d.rounded_rectangle([PX + 118, yy + 4, PX + 118 + wv, yy + 18], 7, fill=GOLD if chosen else TEAL)
            d.text((PX + 128 + bw, yy), f"{p * ease(bar_t):.2f}", font=F_MONO, fill=FG)
            yy += 30
        yy += 6
        x = PX + 24
        x += pill(d, (x, yy), f"confidence {probs['confidence']:.2f}", DIM) + 10
        if info and "cp_loss" in info:
            loss = info["cp_loss"]
            if loss == 0:
                pill(d, (x, yy), "Stockfish agrees: best move", GREEN)
            elif loss >= 200:
                pill(d, (x, yy), f"blunder: #{info['rank']} of {info['n_legal']}, −{loss} cp", RED)
            else:
                pill(d, (x, yy), f"#{info['rank']} of {info['n_legal']}, −{loss} cp", AMBER)
    elif mover == "opp" and san is not None:
        d.text((PX + 24, y + 16), f"{opp_label} replies", font=F_SM, fill=DIM)
        d.text((PX + 24, y + 48), "Stockfish 19, skill level 0, depth 1." if "Stockfish" in opp_label else "Uniformly random legal move.", font=F_TXT, fill=MUTED)
    # moves ticker
    tail = moves[-10:]
    start = len(moves) - len(tail)
    parts = [f"{(start + i) // 2 + 1}. {s}" if (start + i) % 2 == 0 else s for i, s in enumerate(tail)]
    line, lines = "", []
    for tok in parts:
        cand = (line + " " + tok).strip()
        if d.textlength(cand, font=F_MONO) > W - 48 - PX and line:
            lines.append(line); line = tok
        else:
            line = cand
    lines.append(line)
    for i, ln in enumerate(lines[-2:]):
        d.text((PX, 604 + 22 * i), ln, font=F_MONO, fill=DIM)
    d.text((PX, 676), "github.com/wondertwins/jev-benchmark", font=F_SM, fill=MUTED)


def card(text_big: str, text_small: str, alpha: float) -> Image.Image:
    im = BG_PLAIN.copy()
    d = ImageDraw.Draw(im)
    col = tuple(int(c * alpha + b * (1 - alpha)) for c, b in zip(FG, BG_BOT))
    col2 = tuple(int(c * alpha + b * (1 - alpha)) for c, b in zip(DIM, BG_BOT))
    lines = text_big.split("\n")
    y = H // 2 - 40 * len(lines) - 20
    for ln in lines:
        d.text(((W - d.textlength(ln, font=F_CARD)) // 2, y), ln, font=F_CARD, fill=col)
        y += 62
    for ln in text_small.split("\n"):
        d.text(((W - d.textlength(ln, font=F_TXT)) // 2, y + 10), ln, font=F_TXT, fill=col2)
        y += 30
    return im


def poster(base: Image.Image, headline: str, subline: str) -> Image.Image:
    """Dim a rendered game frame and stamp a large headline over it: this is the video's first frame,
    which X/Twitter uses as the thumbnail."""
    im = base.convert("RGBA")
    dim = Image.new("RGBA", (W, H), (6, 8, 12, 125))
    im = Image.alpha_composite(im, dim)
    d = ImageDraw.Draw(im)
    f_head, f_sub = _font(66, True), _font(28, True)
    lines = headline.split("\n")
    total = len(lines) * 76 + 50
    y = (H - total) // 2 - 10
    for ln in lines:
        w = d.textlength(ln, font=f_head)
        x = (W - w) // 2
        for dx, dy in ((3, 4), (-2, 2), (2, -2)):  # soft shadow
            d.text((x + dx, y + dy), ln, font=f_head, fill=(0, 0, 0, 170))
        d.text((x, y), ln, font=f_head, fill=(255, 255, 255, 255))
        y += 76
    w = d.textlength(subline, font=f_sub)
    d.rounded_rectangle([(W - w) // 2 - 22, y + 14, (W + w) // 2 + 22, y + 60], 23, fill=(250, 204, 77, 235))
    d.text(((W - w) // 2, y + 20), subline, font=f_sub, fill=(20, 16, 6, 255))
    return im.convert("RGB")


# ----------------------------------------------------------------------------- data
def load_probs(tag: str, level: str, filt: bool) -> dict[tuple[str, int], dict]:
    out: dict[tuple[str, int], dict] = {}
    for p in glob.glob(str(RUNS / "raw" / f"{tag}_*.json")):
        d = json.load(open(p))
        m = d.get("meta") or {}
        if m.get("exp") != "G" or "response" not in d or m.get("level", "rich") != level or bool(m.get("filter", False)) != filt:
            continue
        ans = d["response"]["answers"].get("move")
        if ans:
            out[(d["request"]["state"]["fen"], m["ply"])] = {"probabilities": ans["probabilities"], "confidence": ans["confidence"]}
    return out


# ----------------------------------------------------------------------------- render
def render(game: str, model: str, headline: str = "Can a model that can't think\nplay chess?", poster_seconds: float = 1.6) -> tuple[Path, Path]:
    global BG, BG_PLAIN
    BG = background()
    BG_PLAIN = background(glow=False)
    res = json.load(open(RUNS / "results" / f"G_game_vs_{game}_{model}.json"))
    opp = res.get("opponent", game)
    from .opponents import label as _lbl
    opp_label = {"random": "Random mover", "sf0": "Stockfish (skill 0)"}.get(opp) or _lbl(opp)
    title = f"Jev vs {opp_label}" if res.get("jev_color", "white") == "white" else f"{opp_label} vs Jev"
    level = res.get("level", "rich")
    sans = [t for t in res["pgn_moves"].split() if not t.endswith(".")]
    by_ply = {m["ply"]: m for m in res["jev_moves"]}
    probs = load_probs(model, level, bool(res.get("filter_blunders", False)))

    tmp = MEDIA / f"_v2_{game}"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    n = 0

    def emit(im: Image.Image) -> None:
        nonlocal n
        im.convert("RGB").save(tmp / f"{n:05d}.png", compress_level=1)
        n += 1

    # --- poster / thumbnail: the final position with Jev's last decision, under a big headline
    pre = chess.Board()
    last_mv, last_pr, last_info, last_ply = None, None, None, None
    for ply, san in enumerate(sans):
        fen_before = pre.fen()
        mv = pre.parse_san(san)
        is_jev = (ply % 2 == 0) == (res.get("jev_color", "white") == "white")
        if is_jev:
            last_mv, last_ply = mv, ply
            last_pr, last_info = probs.get((fen_before, ply)), by_ply.get(ply)
        pre.push(mv)
    s_ = res["summary"]
    jev_won = s_["result"] == ("1-0" if res.get("jev_color", "white") == "white" else "0-1")
    n_moves = len(sans) // 2 + len(sans) % 2
    forced = bool(last_info and last_info.get("forced_mate_by_code"))
    verb = "beats" if forced else "checkmates"
    subline = (f"Jev {verb} {opp_label} in {n_moves} moves" if jev_won and s_["termination"] == "CHECKMATE"
               else f"Jev vs {opp_label}")
    result_line = (f"Checkmate  ·  {s_['result']}  ·  {n_moves} moves" if s_["termination"] == "CHECKMATE"
                   else f"{s_['termination'].replace('_', ' ').title()}  ·  {s_['result']}  ·  {n_moves} moves")
    base = BG.copy()
    draw_board(base, dict(pre.piece_map()), [], [], last_mv, pre.king(pre.turn) if pre.is_check() else None, 1)
    draw_eval_bar(base, 0.97 if jev_won else 0.03)
    draw_panel(base, title, last_ply, sans[-1] if last_ply == len(sans) - 1 else None, "jev", opp_label, last_pr, last_info, 1, sans, 1,
               result_line=result_line)
    post = poster(base, headline, subline)
    post.save(MEDIA / f"v2_jev_vs_{game}_{model}_poster.png")
    for _ in range(int(FPS * poster_seconds)):
        emit(post)

    board = chess.Board()
    played: list[str] = []
    with open_engine() as eng:
        prev_share = eval_to_share(eval_cp(eng, board, 10))
        # opening frame
        im = BG.copy()
        draw_board(im, dict(board.piece_map()), [], [], None, None, 0)
        draw_eval_bar(im, prev_share)
        draw_panel(im, title, None, None, "jev", opp_label, None, None, 1, [], 1)
        for _ in range(FPS // 2):
            emit(im)
        for ply, san in enumerate(sans):
            fen_before = board.fen()
            mv = board.parse_san(san)
            mover = "jev" if (ply % 2 == 0) == (res.get("jev_color", "white") == "white") else "opp"
            info = by_ply.get(ply) if mover == "jev" else None
            pr = probs.get((fen_before, ply)) if mover == "jev" else None
            piece = board.piece_at(mv.from_square)
            captured_sq = None
            if board.is_capture(mv):
                captured_sq = mv.to_square if not board.is_en_passant(mv) else (mv.to_square + (-8 if board.turn == chess.WHITE else 8))
            captured = board.piece_at(captured_sq) if captured_sq is not None else None
            rook_mv = None
            if board.is_castling(mv):
                kf = chess.square_file(mv.to_square)
                r_from = chess.square(7 if kf == 6 else 0, chess.square_rank(mv.from_square))
                r_to = chess.square(5 if kf == 6 else 3, chess.square_rank(mv.from_square))
                rook_mv = (board.piece_at(r_from), r_from, r_to)
            static = dict(board.piece_map())
            static.pop(mv.from_square, None)
            if captured_sq is not None:
                static.pop(captured_sq, None)
            if rook_mv:
                static.pop(rook_mv[1], None)
            board.push(mv)
            played.append(san)
            new_share = eval_to_share(eval_cp(eng, board, 10)) if not board.is_game_over() else (0.97 if board.result() == "1-0" else 0.03 if board.result() == "0-1" else 0.5)
            check_sq = board.king(board.turn) if board.is_check() else None
            # slide
            for i in range(SLIDE):
                t = ease((i + 1) / SLIDE)
                im = BG.copy()
                fx, fy = sq_xy(mv.from_square); tx, ty = sq_xy(mv.to_square)
                moving = [(piece if not (mv.promotion and t > 0.85) else chess.Piece(mv.promotion, piece.color), (fx + (tx - fx) * t, fy + (ty - fy) * t))]
                if rook_mv:
                    rfx, rfy = sq_xy(rook_mv[1]); rtx, rty = sq_xy(rook_mv[2])
                    moving.append((rook_mv[0], (rfx + (rtx - rfx) * t, rfy + (rty - rfy) * t)))
                fading = [(captured, captured_sq, 1 - t)] if captured else []
                draw_board(im, static, moving, fading, mv, check_sq if t > 0.9 else None, t)
                draw_eval_bar(im, prev_share + (new_share - prev_share) * t)
                draw_panel(im, title, ply, san, mover, opp_label, pr, info, 0, played, t)
                emit(im)
            prev_share = new_share
            final_pieces = dict(board.piece_map())
            if mover == "jev":
                for i in range(BARS):
                    im = BG.copy()
                    draw_board(im, final_pieces, [], [], mv, check_sq, 1)
                    draw_eval_bar(im, new_share)
                    draw_panel(im, title, ply, san, mover, opp_label, pr, info, (i + 1) / BARS, played, 1)
                    emit(im)
            im = BG.copy()
            draw_board(im, final_pieces, [], [], mv, check_sq, 1)
            draw_eval_bar(im, new_share)
            draw_panel(im, title, ply, san, mover, opp_label, pr, info, 1, played, 1)
            for _ in range(HOLD_JEV if mover == "jev" else HOLD_OPP):
                emit(im)
    # end card
    s = res["summary"]
    jev_white = res.get("jev_color", "white") == "white"
    result = s["result"] if s["result"] != "unfinished" else (res.get("adjudicated_result") or "1/2-1/2")
    jev_won = result == ("1-0" if jev_white else "0-1")
    who = "Jev wins." if jev_won else "Jev loses." if result in ("1-0", "0-1") else "Draw."
    how = "Checkmate." if s["termination"] == "CHECKMATE" else "Adjudicated." if s["result"] == "unfinished" else s["termination"].replace("_", " ").title() + "."
    res_txt = f"{how} {who}"

    detail = (f"{len(sans) // 2 + len(sans) % 2} moves  ·  mean centipawn loss {s['jev_mean_cp_loss']}  ·  "
              f"{s['jev_blunders_200cp']} blunder(s)\ngithub.com/wondertwins/jev-benchmark")
    for i in range(int(FPS * 3.2)):
        emit(card(res_txt, detail, ease(min(1, i / (FPS * 0.6)))))

    mp4 = MEDIA / f"v2_jev_vs_{game}_{model}.mp4"
    gif = MEDIA / f"v2_jev_vs_{game}_{model}.gif"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", str(tmp / "%05d.png"),
                    "-vf", "format=yuv420p", "-c:v", "libx264", "-crf", "19", "-movflags", "+faststart", str(mp4)], check=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", str(tmp / "%05d.png"),
                    "-vf", f"fps=16,scale=800:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=192:stats_mode=diff[p];[s1][p]paletteuse=dither=bayer:bayer_scale=4",
                    "-loop", "0", str(gif)], check=True)
    shutil.rmtree(tmp)
    return gif, mp4


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", default="random", help="suffix of runs/results/G_game_vs_<suffix>_<model>.json")
    ap.add_argument("--model", default="jev-latest")
    ap.add_argument("--headline", default="Can a model that can't think\nplay chess?", help="poster headline; use \\n for a line break")
    ap.add_argument("--poster-seconds", type=float, default=1.6)
    a = ap.parse_args()
    g, m = render(a.game, a.model, a.headline.replace("\\n", "\n"), a.poster_seconds)
    print("poster:", MEDIA / f"v2_jev_vs_{a.game}_{a.model}_poster.png")
    print("gif:", g, f"{g.stat().st_size / 1e6:.1f} MB")
    print("mp4:", m, f"{m.stat().st_size / 1e6:.1f} MB")
