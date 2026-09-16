"""A reasonable non-AI heuristic to compare against: fuzzy name/role matching plus a few rules."""
from __future__ import annotations

import difflib
import re
from typing import Any

GROUP_WORDS = {"everyone", "everybody", "all of you", "you lot", "you all", "y'all", "all", "guys", "ladies", "gentlemen", "nobody move", "whoever"}
ROLE_SYNONYMS = {"innkeeper": {"innkeeper", "barkeep", "bartender", "landlady", "landlord"}, "guard": {"guard", "guards", "soldier", "officer"},
                 "merchant": {"merchant", "shopkeeper", "trader", "seller"}, "blacksmith": {"blacksmith", "smith"},
                 "healer": {"healer", "doctor", "medic"}, "dog": {"dog", "doggy", "boy", "pup"}}


def heuristic(present: list[tuple[str, str]], text: str, ctx: dict[str, Any] | None) -> dict[str, bool]:
    low = text.lower()
    words = re.findall(r"[a-z']+", low)
    out = {n: False for n, _ in present}
    if any(g in low for g in GROUP_WORDS):
        return {n: True for n, _ in present}
    for name, role in present:
        for w in words:
            w2 = w.rstrip("'s") if w.endswith("'s") else w
            if difflib.SequenceMatcher(None, w2, name.lower()).ratio() >= 0.8:
                out[name] = True
        if any(w in ROLE_SYNONYMS.get(role, {role}) for w in words):
            out[name] = True
    if not any(out.values()):
        if ctx and "you" in words and ctx.get("player_is_facing") in out:
            out[ctx["player_is_facing"]] = True
        elif ctx and ctx.get("player_was_last_talking_to") in out:
            out[ctx["player_was_last_talking_to"]] = True
    return out
