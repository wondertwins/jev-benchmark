"""Run the addressee benchmark: uv run python -m npcaddress.run [--model jev-latest] [--variants clean,stt,stt_misheard]"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

from jevcommon.client import JevClient

from .baseline import heuristic
from .dataset import ITEMS, VARIANTS, Item, transcript
from .questions import request_for

RUNS = Path(__file__).resolve().parent.parent / "runs"


async def run_variant(client: JevClient, items: list[Item], variant: str) -> list[dict[str, Any]]:
    async def one(item: Item) -> dict[str, Any]:
        state, qs = request_for(item, variant)
        resp = await client.ask(state, qs, meta={"exp": "npc", "variant": variant, "item": item.id})
        names = [n for n, _ in item.present]
        row: dict[str, Any] = {"item": item.id, "variant": variant, "scene": item.scene, "text": transcript(item, variant),
                               "category": item.category, "ambiguous": item.ambiguous, "truth": {n: n in item.addressed for n in names},
                               "truth_group": item.group, "truth_nobody": item.nobody, "truth_intent": item.intent,
                               "baseline": heuristic(item.present, transcript(item, variant), item.ctx)}
        if resp is None:
            row["error"] = True
            return row
        row["pred"] = {n: round(resp.nouls[f"addr_{n}"].noul, 3) for n in names}
        row["group"] = round(resp.nouls["group_address"].noul, 3)
        row["nobody"] = round(resp.nouls["nobody"].noul, 3)
        row["intent"] = resp.choices["intent"].choice
        row["intent_conf"] = round(resp.choices["intent"].confidence, 3)
        row["urgency"] = round(resp.scores["urgency"].score, 2)
        row["attitude"] = resp.choices["attitude"].choice
        row["primary"] = resp.choices["primary"].choice
        row["primary_conf"] = round(resp.choices["primary"].confidence, 3)
        row["input_tokens"] = resp.usage.input_tokens
        return row
    return list(await asyncio.gather(*(one(it) for it in items)))


def prf(pairs: list[tuple[bool, bool]]) -> dict[str, float]:
    tp = sum(p and t for p, t in pairs); fp = sum(p and not t for p, t in pairs); fn = sum(t and not p for p, t in pairs)
    prec = tp / (tp + fp) if tp + fp else 0.0; rec = tp / (tp + fn) if tp + fn else 0.0
    return {"precision": round(prec, 3), "recall": round(rec, 3), "f1": round(2 * prec * rec / (prec + rec), 3) if prec + rec else 0.0,
            "accuracy": round(statistics.mean(p == t for p, t in pairs), 3)}


def metrics(rows: list[dict[str, Any]], thr: float = 0.5) -> dict[str, Any]:
    ok = [r for r in rows if "pred" in r]
    strict = [r for r in ok if not r["ambiguous"]]
    jev_pairs = [(r["pred"][n] >= thr, r["truth"][n]) for r in strict for n in r["truth"]]
    base_pairs = [(r["baseline"][n], r["truth"][n]) for r in strict for n in r["truth"]]
    exact_jev = statistics.mean(all((r["pred"][n] >= thr) == r["truth"][n] for n in r["truth"]) for r in strict)
    exact_base = statistics.mean(all(r["baseline"][n] == r["truth"][n] for n in r["truth"]) for r in strict)
    brier = statistics.mean((r["pred"][n] - float(r["truth"][n])) ** 2 for r in strict for n in r["truth"])
    by_cat: dict[str, dict[str, Any]] = {}
    cats = defaultdict(list)
    for r in strict:
        cats[r["category"]].append(r)
    for c, rs in sorted(cats.items()):
        by_cat[c] = {"n": len(rs),
                     "jev_exact": round(statistics.mean(all((r["pred"][n] >= thr) == r["truth"][n] for n in r["truth"]) for r in rs), 2),
                     "baseline_exact": round(statistics.mean(all(r["baseline"][n] == r["truth"][n] for n in r["truth"]) for r in rs), 2)}
    intent_acc = statistics.mean(r["intent"] == r["truth_intent"] for r in ok)
    nobody = prf([(r["nobody"] >= thr, r["truth_nobody"]) for r in ok])
    group = prf([(r["group"] >= thr, r["truth_group"]) for r in ok])
    # primary Choice on single-addressee, non-group items
    single = [r for r in strict if sum(r["truth"].values()) == 1 and not r["truth_group"]]
    primary_acc = statistics.mean(r["primary"] == next(n for n, v in r["truth"].items() if v) for r in single) if single else None
    nobody_choice = [r for r in ok if r["truth_nobody"]]
    primary_nobody = statistics.mean(r["primary"] == "nobody" for r in nobody_choice) if nobody_choice else None
    amb = [r for r in ok if r["ambiguous"]]
    return {"n_utterances": len(ok), "n_strict": len(strict), "n_addressee_decisions": len(jev_pairs),
            "jev_per_npc": prf(jev_pairs), "baseline_per_npc": prf(base_pairs),
            "jev_exact_set_accuracy": round(exact_jev, 3), "baseline_exact_set_accuracy": round(exact_base, 3), "jev_brier": round(brier, 3),
            "nobody_noul": nobody, "group_noul": group, "intent_accuracy": round(intent_acc, 3),
            "primary_choice_accuracy_single_addressee": round(primary_acc, 3) if primary_acc is not None else None,
            "primary_choice_says_nobody_when_nobody": round(primary_nobody, 3) if primary_nobody is not None else None,
            "by_category": by_cat,
            "ambiguous_items": [{"text": r["text"], "truth": r["truth"], "pred": r["pred"]} for r in amb],
            "mean_input_tokens": round(statistics.mean(r["input_tokens"] for r in ok))}


def report(all_results: dict[str, Any], model: str) -> str:
    L = [f"# Jev addressee detection for speech-to-text NPC dialogue — model `{model}`", "",
         f"{len(ITEMS)} hand-labeled utterances in a fantasy village with 2 to 5 NPCs within earshot. For each NPC, one Noul asks whether "
         "the player is speaking to them. Ground truth is my labeling; 4 arguable items are excluded from strict metrics and listed separately. "
         "Baseline = fuzzy name/role matching + group words + facing/last-speaker fallback.", "",
         "## Per-NPC 'is being spoken to' decisions", "",
         "| transcript variant | decisions | Jev F1 | Jev precision | Jev recall | baseline F1 | Jev exact-set acc | baseline exact-set acc | Jev Brier |",
         "|---|---|---|---|---|---|---|---|---|"]
    for v, m in all_results.items():
        j, b = m["jev_per_npc"], m["baseline_per_npc"]
        L.append(f"| {v} | {m['n_addressee_decisions']} | **{j['f1']}** | {j['precision']} | {j['recall']} | {b['f1']} | "
                 f"**{m['jev_exact_set_accuracy']}** | {m['baseline_exact_set_accuracy']} | {m['jev_brier']} |")
    L += ["", "Exact-set = every NPC in the scene classified correctly for that utterance.", "",
          "## Other judgments (same request)", "",
          "| variant | nobody Noul F1 | group Noul F1 | intent accuracy (7 classes) | primary-addressee Choice acc (single-addressee items) | Choice says 'nobody' when nobody | mean input tokens |",
          "|---|---|---|---|---|---|---|"]
    for v, m in all_results.items():
        L.append(f"| {v} | {m['nobody_noul']['f1']} | {m['group_noul']['f1']} | {m['intent_accuracy']} | "
                 f"{m['primary_choice_accuracy_single_addressee']} | {m['primary_choice_says_nobody_when_nobody']} | {m['mean_input_tokens']} |")
    L += ["", "## By category (exact-set accuracy, Jev vs baseline)", "", "| category | n | " + " | ".join(f"{v} Jev / base" for v in all_results) + " |",
          "|---|---|" + "---|" * len(all_results)]
    cats = sorted({c for m in all_results.values() for c in m["by_category"]})
    for c in cats:
        cells = []
        for v, m in all_results.items():
            d = m["by_category"].get(c)
            cells.append(f"{d['jev_exact']} / {d['baseline_exact']}" if d else "–")
        n = next(m["by_category"][c]["n"] for m in all_results.values() if c in m["by_category"])
        L.append(f"| {c} | {n} | " + " | ".join(cells) + " |")
    first = next(iter(all_results.values()))
    if first["ambiguous_items"]:
        L += ["", "## Arguable items (clean variant), excluded from strict metrics", ""]
        for a in first["ambiguous_items"]:
            L.append(f"- \"{a['text']}\"  truth {a['truth']}  → Jev {a['pred']}")
    return "\n".join(L)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="jev-latest")
    ap.add_argument("--variants", default=",".join(VARIANTS))
    ap.add_argument("--concurrency", type=int, default=6)
    args = ap.parse_args()
    if not os.environ.get("TYPESAFE_API_KEY"):
        raise SystemExit("TYPESAFE_API_KEY not set")
    variants = [v.strip() for v in args.variants.split(",")]
    all_results: dict[str, Any] = {}
    rows_out: dict[str, Any] = {}
    async with JevClient(model=args.model, concurrency=args.concurrency, tag=f"npc_{args.model}") as client:
        for v in variants:
            rows = await run_variant(client, ITEMS, v)
            rows_out[v] = rows
            all_results[v] = metrics(rows)
            m = all_results[v]
            print(f"{v}: Jev F1 {m['jev_per_npc']['f1']} (baseline {m['baseline_per_npc']['f1']}), exact-set {m['jev_exact_set_accuracy']} "
                  f"(baseline {m['baseline_exact_set_accuracy']}), intent {m['intent_accuracy']}, nobody F1 {m['nobody_noul']['f1']}")
        print("usage:", client.usage.summary())
    (RUNS / "results").mkdir(parents=True, exist_ok=True)
    (RUNS / "results" / f"NPC_addressee_{args.model}.json").write_text(json.dumps({"summary": all_results, "rows": rows_out}, indent=1))
    rep = report(all_results, args.model)
    (RUNS / f"REPORT_npc_addressee_{args.model}.md").write_text(rep)
    print(rep)


if __name__ == "__main__":
    asyncio.run(main())
