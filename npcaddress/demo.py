"""Interactive playground: type what the player says, see who Jev thinks they're talking to.

  uv run python -m npcaddress.demo            # tavern scene
  uv run python -m npcaddress.demo square     # any scene name from dataset.SCENES

Type 'face Jeff' to set who the player is facing, 'scene forge' to switch scenes, 'quit' to exit.
Each utterance is one request; the last addressee is carried forward as conversation context.
"""
from __future__ import annotations

import os
import sys

from typesafe_sdk import TypeSafeClient

from .dataset import SCENES
from .questions import build_questions, build_state

BAR = "█"


def bar(p: float, width: int = 20) -> str:
    return BAR * round(p * width) + "·" * (width - round(p * width))


def main() -> None:
    if not os.environ.get("TYPESAFE_API_KEY"):
        raise SystemExit("TYPESAFE_API_KEY not set; run: set -a; source ~/.env; set +a")
    scene = sys.argv[1] if len(sys.argv) > 1 else "tavern"
    present = SCENES[scene]
    ctx: dict = {}
    client = TypeSafeClient()
    print(f"Scene '{scene}': " + ", ".join(f"{n} ({r})" for n, r in present))
    print("Say something. Commands: face <Name> | scene <name> | quit\n")
    while True:
        try:
            text = input("player> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not text or text.lower() in {"quit", "exit"}:
            break
        if text.lower().startswith("scene "):
            scene = text.split(None, 1)[1].strip(); present = SCENES[scene]; ctx = {}
            print("  now in", scene, ":", ", ".join(n for n, _ in present)); continue
        if text.lower().startswith("face "):
            ctx["player_is_facing"] = text.split(None, 1)[1].strip(); print("  facing", ctx["player_is_facing"]); continue
        variant = "clean" if any(c in text for c in ".,?!") else "stt"
        resp = client.system_one(build_state(present, text, ctx or None, variant), build_questions(present))
        addressed = []
        for n, r in present:
            p = resp.nouls[f"addr_{n}"].noul
            flag = "◄ listening" if p >= 0.5 else ""
            if p >= 0.5:
                addressed.append(n)
            print(f"  {n:8s} {bar(p)} {p:5.2f}  {flag}")
        print(f"  {'everyone':8s} {bar(resp.nouls['group_address'].noul)} {resp.nouls['group_address'].noul:5.2f}")
        print(f"  {'nobody':8s} {bar(resp.nouls['nobody'].noul)} {resp.nouls['nobody'].noul:5.2f}")
        i, a, u = resp.choices["intent"], resp.choices["attitude"], resp.scores["urgency"]
        print(f"  intent={i.choice} ({i.confidence:.2f})  attitude={a.choice}  urgency={u.score:.2f}/2  "
              f"primary={resp.choices['primary'].choice}  [{resp.usage.input_tokens} tokens]\n")
        if len(addressed) == 1:
            ctx["player_was_last_talking_to"] = addressed[0]
    client.close() if hasattr(client, "close") else None


if __name__ == "__main__":
    main()
