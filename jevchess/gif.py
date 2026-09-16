"""Animate one of Jev's recorded games as a GIF (and MP4 if ffmpeg is present).

  uv run --group media python -m jevchess.gif --game random
  uv run --group media python -m jevchess.gif --game sf0

Each frame: the board after the move, and for Jev's moves the probability
distribution it returned over the legal moves (top 5), its confidence, and the
Stockfish centipawn loss of the move it picked. Requires the `media` dependency
group (pillow, cairosvg) and the raw request logs in runs/raw/.
"""
from __future__ import annotations

import argparse
import glob
import io
import json
import shutil
import subprocess
from pathlib import Path

import cairosvg
import chess
import chess.svg
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "runs"
MEDIA = RUNS / "media"

W, H = 960, 540
BOARD = 468
BG = (15, 17, 21)
FG = (235, 236, 240)
DIM = (140, 145, 160)
ACCENT = (86, 204, 194)     # teal bars
GOLD = (245, 197, 66)       # Jev's chosen move
RED = (232, 93, 93)
GREEN = (92, 200, 120)


def font(size: int, bold: bool = False, mono: bool = False) -> ImageFont.FreeTypeFont:
    cands = ["/System/Library/Fonts/Menlo.ttc"] if mono else (
        ["/System/Library/Fonts/Supplemental/Arial Bold.ttf"] if bold else ["/System/Library/Fonts/Supplemental/Arial.ttf"])
    cands += ["/System/Library/Fonts/Helvetica.ttc", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
    for c in cands:
        try:
            return ImageFont.truetype(c, size)
        except OSError:
            continue
    return ImageFont.load_default()


F_TITLE, F_SUB, F_BIG, F_TXT, F_SMALL, F_MONO = font(26, True), font(15), font(34, True), font(18), font(14), font(15, mono=True)


def load_probabilities(tag: str) -> dict[str, dict]:
    """fen -> {'probabilities': {...}, 'confidence': x} for every recorded game request."""
    out: dict[str, dict] = {}
    for p in glob.glob(str(RUNS / "raw" / f"{tag}_*.json")):
        d = json.load(open(p))
        if (d.get("meta") or {}).get("exp") != "G" or "response" not in d:
            continue
        if "move" not in d["response"].get("answers", {}):
            continue
        ans = d["response"]["answers"]["move"]
        out[d["request"]["state"]["fen"]] = {"probabilities": ans["probabilities"], "confidence": ans["confidence"]}
    return out


def board_png(board: chess.Board, lastmove: chess.Move | None) -> Image.Image:
    check_sq = board.king(board.turn) if board.is_check() else None
    svg = chess.svg.board(board, lastmove=lastmove, check=check_sq, size=BOARD, coordinates=True,
                          colors={"square light": "#e9e4d6", "square dark": "#7f9a75", "margin": "#0f1115",
                                  "coord": "#c8ccd6", "square light lastmove": "#f6e7a0", "square dark lastmove": "#c9b95a"})
    return Image.open(io.BytesIO(cairosvg.svg2png(bytestring=svg.encode()))).convert("RGB")


def frame(board: chess.Board, lastmove: chess.Move | None, ply: int, san: str | None, mover: str, opponent_label: str,
          jev_info: dict | None, probs: dict | None, moves_so_far: list[str], final: str | None = None) -> Image.Image:
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    im.paste(board_png(board, lastmove), (28, (H - BOARD) // 2))
    x0 = 28 + BOARD + 36
    d.text((x0, 26), "Jev (White) vs " + opponent_label, font=F_TITLE, fill=FG)
    d.text((x0, 60), "TypeSafe's System One model, no lookahead.", font=F_SUB, fill=DIM)
    d.text((x0, 80), "Each turn: one Choice question over every legal move.", font=F_SUB, fill=DIM)

    if final:
        head, _, rest = final.partition("|")
        d.text((x0, 118), head, font=F_BIG, fill=GOLD)
        d.text((x0, 162), rest, font=F_TXT, fill=FG)
        y = 200
    elif san is None:
        d.text((x0, 120), "Move 1. Jev to play.", font=F_BIG, fill=FG)
        y = 175
    else:
        move_no = ply // 2 + 1
        who = "Jev plays" if mover == "jev" else f"{opponent_label} plays"
        d.text((x0, 112), f"{move_no}{'.' if mover == 'jev' else '...'} {san}", font=F_BIG, fill=GOLD if mover == "jev" else FG)
        d.text((x0, 152), who, font=F_TXT, fill=DIM)
        y = 190

    if mover == "jev" and jev_info and jev_info.get("forced_mate_by_code") and not final:
        d.text((x0, y), "Code found a checkmate and played it (hard rule)", font=F_SMALL, fill=GREEN)
        y += 26
    if mover == "jev" and probs and not final:
        d.text((x0, y), "Jev's probability over legal moves (top 5)", font=F_SMALL, fill=DIM)
        y += 22
        top = sorted(probs["probabilities"].items(), key=lambda kv: -kv[1])[:5]
        bar_w = W - x0 - 150
        for name, p in top:
            chosen = name.replace("#", "+") == (san or "").replace("#", "+")
            d.text((x0, y), name, font=F_MONO, fill=GOLD if chosen else FG)
            d.rectangle([x0 + 78, y + 3, x0 + 78 + bar_w, y + 15], fill=(35, 38, 46))
            d.rectangle([x0 + 78, y + 3, x0 + 78 + max(2, int(bar_w * p)), y + 15], fill=GOLD if chosen else ACCENT)
            d.text((x0 + 86 + bar_w, y), f"{p:.2f}", font=F_MONO, fill=FG)
            y += 24
        y += 6
        conf = probs["confidence"]
        d.text((x0, y), f"confidence {conf:.2f}   ·   {jev_info['n_legal']} legal moves", font=F_SMALL, fill=DIM)
        y += 22
        if jev_info and "cp_loss" in jev_info:
            loss = jev_info["cp_loss"]
            verdict = "Stockfish agrees: best move" if loss == 0 else f"Stockfish: ranked #{jev_info['rank']}, lost {loss} cp"
            if loss >= 200:
                verdict += "  (blunder)"
            d.text((x0, y), verdict, font=F_SMALL, fill=GREEN if loss == 0 else (RED if loss >= 200 else FG))
            y += 26
    # move list (last 8 plies)
    y = max(y, H - 112)
    d.text((x0, y), "Moves", font=F_SMALL, fill=DIM)
    tail = moves_so_far[-8:]
    start = len(moves_so_far) - len(tail)
    parts = []
    for i, s in enumerate(tail):
        k = start + i
        parts.append(f"{k // 2 + 1}. {s}" if k % 2 == 0 else s)
    line, lines = "", []
    for tok in parts:
        cand = (line + " " + tok).strip()
        if d.textlength(cand, font=F_MONO) > W - x0 - 24 and line:
            lines.append(line); line = tok
        else:
            line = cand
    lines.append(line)
    for i, ln in enumerate(lines[-2:]):
        d.text((x0, y + 20 + 19 * i), ln, font=F_MONO, fill=FG)
    d.text((x0, H - 28), "github.com/wondertwins/jev-benchmark", font=F_SMALL, fill=DIM)
    return im


def render(game: str, model: str, jev_ms: int, opp_ms: int, hold_ms: int) -> tuple[Path, Path | None]:
    res = json.load(open(RUNS / "results" / f"G_game_vs_{game}_{model}.json"))
    opp = res.get("opponent", game)
    opponent_label = {"random": "random mover", "sf0": "Stockfish (skill 0)"}.get(opp, opp)
    if res.get("level") == "tactical":
        opponent_label += "  ·  tactical facts"
    sans = [tok for tok in res["pgn_moves"].split() if not tok.endswith(".")]
    jev_by_ply = {m["ply"]: m for m in res["jev_moves"]}
    probs_by_fen = load_probabilities(model)

    board = chess.Board()
    frames: list[Image.Image] = []
    durations: list[int] = []
    frames.append(frame(board, None, 0, None, "jev", opponent_label, None, None, []))
    durations.append(1400)
    played: list[str] = []
    for ply, san in enumerate(sans):
        fen_before = board.fen()
        mv = board.parse_san(san)
        mover = "jev" if (ply % 2 == 0) == (res.get("jev_color", "white") == "white") else "opp"
        board.push(mv)
        played.append(san)
        info = jev_by_ply.get(ply) if mover == "jev" else None
        probs = probs_by_fen.get(fen_before) if mover == "jev" else None
        frames.append(frame(board, mv, ply, san, mover, opponent_label, info, probs, played))
        durations.append(jev_ms if mover == "jev" else opp_ms)
    s = res["summary"]
    jev_white = res.get("jev_color", "white") == "white"
    jev_won = s["result"] == ("1-0" if jev_white else "0-1")
    outcome = {"1-0": f"Checkmate. Jev {'wins' if jev_won else 'loses'} 1-0", "0-1": f"Checkmate. Jev {'wins' if jev_won else 'loses'} 0-1",
               "1/2-1/2": "Draw"}.get(s["result"], s["result"])
    if s["termination"] != "CHECKMATE" and s["result"] in ("1-0", "0-1"):
        outcome = f"{s['termination'].title()}. {s['result']}"
    final_text = f"{outcome.split('.')[0]}.|{outcome.split('. ', 1)[-1] if '. ' in outcome else ''} in {len(sans) // 2 + len(sans) % 2} moves"
    frames.append(frame(board, mv, len(sans) - 1, None, "jev", opponent_label, None, None, played, final=final_text))
    durations.append(hold_ms)

    MEDIA.mkdir(parents=True, exist_ok=True)
    gif = MEDIA / f"jev_vs_{game}_{model}.gif"
    pal = [f.quantize(colors=160, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE) for f in frames]
    pal[0].save(gif, save_all=True, append_images=pal[1:], duration=durations, loop=0, optimize=True)

    mp4 = None
    if shutil.which("ffmpeg"):
        tmp = MEDIA / f"_frames_{game}"
        tmp.mkdir(exist_ok=True)
        # ffmpeg concat demuxer honours per-frame durations
        lst = tmp / "list.txt"
        lines = []
        for i, (f, ms) in enumerate(zip(frames, durations)):
            p = tmp / f"{i:04d}.png"
            f.save(p)
            lines += [f"file '{p.name}'", f"duration {ms / 1000:.3f}"]
        lines.append(f"file '{(tmp / f'{len(frames) - 1:04d}.png').name}'")
        lst.write_text("\n".join(lines))
        mp4 = MEDIA / f"jev_vs_{game}_{model}.mp4"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-vf", "fps=30,format=yuv420p",
                        "-c:v", "libx264", "-crf", "20", "-movflags", "+faststart", str(mp4)], check=True)
        shutil.rmtree(tmp)
    return gif, mp4


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", default="random", help="suffix of a runs/results/G_game_vs_<suffix>_<model>.json file")
    ap.add_argument("--model", default="jev-latest")
    ap.add_argument("--jev-ms", type=int, default=1000)
    ap.add_argument("--opp-ms", type=int, default=450)
    ap.add_argument("--hold-ms", type=int, default=3000)
    a = ap.parse_args()
    g, m = render(a.game, a.model, a.jev_ms, a.opp_ms, a.hold_ms)
    print("gif:", g, f"{g.stat().st_size / 1e6:.1f} MB")
    if m:
        print("mp4:", m, f"{m.stat().st_size / 1e6:.1f} MB")
