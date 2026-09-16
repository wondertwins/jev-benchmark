"""Aggregate runs/results/*.json into a Markdown report: uv run python -m jevchess.report [model]"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

RESULTS = Path(__file__).resolve().parent.parent / "runs" / "results"

from .experiments import spearman  # noqa: E402


def load(model: str) -> dict[str, dict]:
    out = {}
    for p in sorted(RESULTS.glob(f"*_{model}.json")):
        if p.name[:2] not in {"A_", "B_", "C_", "D_", "E_", "F_", "G_"}:
            continue  # other benchmarks (e.g. NPC addressee) live in their own report
        out[p.name[: -len(f"_{model}.json")]] = json.loads(p.read_text())
    return out


def fmt(v) -> str:
    if v is None:
        return "–"
    if isinstance(v, float):
        return f"{v:.3g}" if abs(v) < 10 else f"{v:.0f}"
    return str(v)


def main() -> None:
    model = sys.argv[1] if len(sys.argv) > 1 else "jev-latest"
    R = load(model)
    lines = [f"# Jev chess experiments — model `{model}`", ""]

    move_exps = [(k, v) for k, v in R.items() if k.startswith(("A_", "B_", "C_"))]
    if move_exps:
        lines += ["## Move selection vs Stockfish (depth 12), realistic middlegame positions", "",
                  "| method | state | n | mean cp loss | median | % best move | % top-3 | % blunders ≥200cp | random-move baseline cp loss | mean confidence |",
                  "|---|---|---|---|---|---|---|---|---|---|"]
        for k, v in move_exps:
            s = v["summary"]
            method = {"A": "Choice over all legal moves", "B": "Score per move, argmax", "C": "Choice piece → Choice square"}[k[0]]
            lines.append(f"| {method} | {v.get('level')} | {s.get('n')} | {fmt(s.get('mean_cp_loss'))} | {fmt(s.get('median_cp_loss'))} | "
                         f"{fmt(s.get('pct_best_move'))} | {fmt(s.get('pct_top3'))} | {fmt(s.get('pct_blunder_200cp'))} | "
                         f"{fmt(s.get('random_baseline_mean_cp_loss'))} | {fmt(s.get('mean_confidence'))} |")
        for k, v in move_exps:
            s = v["summary"]
            if s.get("mean_spearman_move_scores_vs_stockfish") is not None:
                lines.append(f"\nB: mean Spearman correlation between Jev's per-move scores and Stockfish move values: "
                             f"**{s['mean_spearman_move_scores_vs_stockfish']}** (0 = no relationship, 1 = identical ranking).")
            if s.get("mean_cp_loss_locked_in_by_piece_choice") is not None:
                lines.append(f"\nC: choosing the piece first already locks in a mean cp loss of "
                             f"**{s['mean_cp_loss_locked_in_by_piece_choice']}** (best move available with that piece).")
        lines.append("")

    ev = [(k, v) for k, v in R.items() if k.startswith("E_")]
    if ev:
        lines += ["## Mate-in-one puzzles (Choice over legal moves; '#' hidden as '+')", "",
                  "| state | n | found mate | random baseline | prob. mass on mating moves |", "|---|---|---|---|---|"]
        for k, v in ev:
            s = v["summary"]
            lines.append(f"| {v['level']} | {s['n']} | {fmt(s['accuracy'])} | {fmt(s['random_baseline'])} | {fmt(s['mean_prob_mass_on_mating_moves'])} |")
        lines.append("")

    if "D_perception" in R:
        s = R["D_perception"]["summary"]
        lines += [f"## Board perception (Nouls on ASCII board, n={s['n']})", "",
                  "| question | accuracy @0.5 | Brier | positive rate | majority baseline |", "|---|---|---|---|---|"]
        for k in ["in_check", "mate_in_one", "free_capture", "own_piece_hanging", "can_castle"]:
            d = s[k]
            lines.append(f"| {k} | {fmt(d['accuracy'])} | {fmt(d['brier'])} | {fmt(d['positive_rate'])} | {fmt(d['majority_baseline'])} |")
        lines.append(f"| more_material (Choice white/black/equal) | {fmt(s['more_material']['accuracy'])} | – | – | – |")
        lines.append("")

    if "F_eval_score" in R:
        s = R["F_eval_score"]["summary"]
        lines += [f"## Position evaluation (7-level Score vs Stockfish depth 14, n={s['n']})", "",
                  f"- Spearman vs Stockfish centipawns: **{fmt(s['spearman_vs_stockfish'])}**",
                  f"- Exact bucket accuracy: {fmt(s['exact_bucket_accuracy'])}; within one bucket: {fmt(s['within_one_bucket'])}",
                  f"- Who-is-better accuracy (white / equal / black): {fmt(s['who_is_better_accuracy'])} "
                  f"(always-'equal' baseline {fmt(s['always_equal_baseline'])})", ""]

    games = [(k, v) for k, v in R.items() if k.startswith("G_")]
    if games:
        lines += ["## Full games (Choice over legal moves)", "",
                  "| opponent | Jev plays | state | code filter | Jev result | termination | moves | Jev mean cp loss | Jev % best | Jev blunders |",
                  "|---|---|---|---|---|---|---|---|---|---|"]
        for k, v in games:
            s = v["summary"]
            jw = v.get("jev_color", "white") == "white"
            result = s["result"] if s["result"] != "unfinished" else (v.get("adjudicated_result") or
                     ("1-0" if (s.get("final_eval_cp_white") or 0) > 300 else "0-1" if (s.get("final_eval_cp_white") or 0) < -300 else "1/2-1/2"))
            outcome = "draw" if result == "1/2-1/2" else ("**win**" if result == ("1-0" if jw else "0-1") else "loss")
            term = s["termination"].lower() if s["result"] != "unfinished" else f"adjudicated at {s['final_eval_cp_white']} cp"
            lines.append(f"| {v['opponent']} | {'white' if jw else 'black'} | {v.get('level', 'rich')} | {'yes' if v.get('filter_blunders') else 'no'} | "
                         f"{outcome} | {term} | {(s['plies'] + 1) // 2} | {fmt(s['jev_mean_cp_loss'])} | {fmt(s['jev_pct_best_move'])} | {s['jev_blunders_200cp']} |")
        for k, v in games:
            lines += ["", f"**vs {v['opponent']}** ({v.get('level', 'rich')}{', filter' if v.get('filter_blunders') else ''}, Jev {v.get('jev_color', 'white')}): `{v['pgn_moves']}`"]
        lines.append("")

    # --- confidence vs blunders, on the best configuration
    rich = R.get("A_move_choice_rich")
    if rich:
        rows = [r for r in rich["rows"] if r.get("cp_loss") is not None]
        lo = [r for r in rows if r["confidence"] < 0.25]; hi = [r for r in rows if r["confidence"] >= 0.25]
        def _s(rs):
            if not rs: return "n=0"
            return (f"n={len(rs)}, mean cp loss {statistics.mean(r['cp_loss'] for r in rs):.0f}, blunders "
                    f"{sum(r['cp_loss'] >= 200 for r in rs)}, best-move {100 * sum(r['cp_loss'] == 0 for r in rs) / len(rs):.0f}%")
        lines += [f"## Does confidence predict blunders? (rich-state Choice, n={len(rows)})", "",
                  f"- confidence < 0.25: {_s(lo)}", f"- confidence ≥ 0.25: {_s(hi)}",
                  f"- Spearman(confidence, cp loss) = {spearman([r['confidence'] for r in rows], [r['cp_loss'] for r in rows])} "
                  f"(negative = higher confidence, smaller loss)", ""]
    # --- model comparison on the rich configuration, across every model with results on disk
    models = sorted({p.name.split("_rich_")[1][:-5] for p in RESULTS.glob("A_move_choice_rich_*.json")})
    if len(models) > 1:
        lines += ["## Model comparison on the best configuration (rich state)", "",
                  "| model | A: mean cp loss | A: median | A: % best | A: % top-3 | A: % blunders | E: mate found |", "|---|---|---|---|---|---|---|"]
        for m in models:
            a = json.loads((RESULTS / f"A_move_choice_rich_{m}.json").read_text())["summary"]
            ep = RESULTS / f"E_mate_in_one_rich_{m}.json"
            e = json.loads(ep.read_text())["summary"]["accuracy"] if ep.exists() else None
            lines.append(f"| {m} | {a['mean_cp_loss']} | {a['median_cp_loss']} | {a['pct_best_move']} | {a['pct_top3']} | {a['pct_blunder_200cp']} | {fmt(e)} |")
        lines.append("")
    # --- tokens per request, from the rows themselves
    tok = []
    for k, v in R.items():
        ts = [r["input_tokens"] for r in v.get("rows", []) if r.get("input_tokens")]
        if ts:
            tok.append((k, v.get("level"), round(statistics.mean(ts))))
    if tok:
        lines += ["## Input tokens per request", "", "| experiment | state | mean input tokens |", "|---|---|---|"]
        lines += [f"| {k} | {lvl or '–'} | {t:,} |" for k, lvl, t in tok]
        lines.append("")
    out = RESULTS.parent / f"REPORT_chess_{model}.md"
    out.write_text("\n".join(lines))
    print("\n".join(lines))
    print(f"\n(written to {out})")


if __name__ == "__main__":
    main()
