"""Build the clean Facebook-group caption for the weekly blast.

Groups get a tightened, voice-correct version of the approved IG/FB caption:
  - harness/internal markers stripped (defense-in-depth; preflight also blocks)
  - em/en dashes replaced with commas (William's no-em-dash rule)
  - Instagram-only CTAs dropped ("tag who you're dragging...", "swipe...")
  - a tulsagays.com link line guaranteed (FB auto-renders the link card)
  - a clean Tulsa/OK hashtag set

Source of truth is data/posts/<week>/all_post.json (the approved caption),
so the group copy always tracks what was reviewed for IG/FB.
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# markers that must never reach a live post (mirror preflight_post.HARNESS_MARKERS)
_MARKER_RE = re.compile(
    r"\s*(?:SUPERVISOR_TASK_COMPLETE|SUPERVISOR:|TASK_COMPLETE|"
    r"system-reminder|As an AI|assistant:|<commentary>|tool_use|ANTHROPIC)\b.*$",
    re.IGNORECASE | re.DOTALL,
)
_DASHES = dict.fromkeys(map(ord, "—–‒―"), None)  # — – ‒ ―
_IG_ONLY_PREFIXES = ("tag ", "swipe", "double tap", "save this", "share this post")

_HASHTAGS = "#TulsaLGBTQ #TulsaPride #Tulsa #TulsaEvents #OklahomaLGBTQ"

_TULSAGAYS_LINE = "Full list at tulsagays.com."


def _current_week():
    """ISO week key like 2026-W23, matching the posts/ dir naming."""
    posts = ROOT / "data" / "posts"
    weeks = sorted(p.name for p in posts.glob("2*-W*") if p.is_dir())
    if not weeks:
        raise SystemExit("No data/posts/<week> dirs found.")
    return weeks[-1]


def _clean_dashes(text: str) -> str:
    # replace em/en dashes (with surrounding spaces) by a comma
    text = re.sub(r"\s*[—–‒―]\s*", ", ", text)
    return text.translate(_DASHES)


def build_group_caption(week=None) -> str:
    week = week or _current_week()
    cap_path = ROOT / "data" / "posts" / week / "all_post.json"
    if not cap_path.exists():
        raise SystemExit(f"missing {cap_path}")
    caption = json.loads(cap_path.read_text(encoding="utf-8")).get("caption", "")

    # 1) strip any leaked harness marker (and everything after it)
    caption = _MARKER_RE.split(caption)[0].rstrip()
    # 2) kill em/en dashes
    caption = _clean_dashes(caption)

    # 3) rebuild paragraph-by-paragraph, dropping IG-only CTAs and emoji-only lines
    out_paras = []
    for para in re.split(r"\n\s*\n", caption):
        p = para.strip()
        if not p:
            continue
        low = p.lower()
        if any(low.startswith(pre) for pre in _IG_ONLY_PREFIXES):
            continue
        # drop a pure-hashtag paragraph (we append a curated set)
        if p.replace("#", "").replace(" ", "").isalnum() and p.lstrip().startswith("#"):
            continue
        out_paras.append(p)

    body = "\n\n".join(out_paras).strip()

    # 4) guarantee the tulsagays.com link line (FB renders the card from it)
    if "tulsagays.com" not in body.lower():
        body += "\n\n" + _TULSAGAYS_LINE
    elif _TULSAGAYS_LINE.lower() not in body.lower():
        # there's a tulsagays.com mention but not our explicit CTA; leave as-is
        pass

    # 5) curated hashtags
    body = body.rstrip() + "\n\n" + _HASHTAGS

    # 6) collapse excess whitespace, normalize
    body = re.sub(r"[ \t]+\n", "\n", body)
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    return body


if __name__ == "__main__":
    wk = sys.argv[1] if len(sys.argv) > 1 else None
    cap = build_group_caption(wk)
    # ASCII-safe print for cp1252 consoles
    sys.stdout.buffer.write((cap + "\n").encode("utf-8", "replace"))
    # sanity flags
    assert "SUPERVISOR" not in cap, "marker leaked!"
    assert "—" not in cap, "em dash leaked!"
    assert "tulsagays.com" in cap.lower(), "missing tulsagays.com"
    sys.stderr.write(f"\n[ok] {len(cap)} chars, clean\n")
