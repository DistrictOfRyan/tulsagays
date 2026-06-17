"""Auto-ingest inbound event tips (IG/FB DMs + comments) into the review queue.

The hands-off front half of the DM tip pipeline. Where tools/add_tip.py is the
paste-in door (you copy a DM in by hand), this tool pulls inbound messages itself
via scraper/dm_sources.py (official Graph API), keeps only the ones that look like
event tips, parses them, drafts site-voice copy, and lands each one REVIEW-READY in
the same data/event_tips_inbox.json queue add_tip.py uses.

It NEVER auto-publishes (William's standing review-first rule, 2026-06-06). Everything
stops at pending_review; you clear it with `python tools/add_tip.py approve <id>` (or a
Monday review session does). Standout tips also get a draft spotlight slide written to
the week's posts folder — a DRAFT only, never posted.

Voice copy: drafted through content.generator (the same enrichment the weekly pipeline
trusts), defaulting to the fast rule-based path so a scheduled run can never hang on a
nested claude CLI (see feedback_nested_claude_cli_prompt_size). Tips that only get the
rule-based placeholder are flagged needs_voice_polish:true so the review session rewrites
them in true RuPaul x Dolly voice before approval. Pass --llm-voice to use the real LLM
path in an interactive run.

Usage:
    python tools/ingest_dm_tips.py                 # live: collect, queue review-ready, notify
    python tools/ingest_dm_tips.py --dry-run       # collect + show, write nothing
    python tools/ingest_dm_tips.py --no-spotlight  # skip standout spotlight drafts
    python tools/ingest_dm_tips.py --channels fb_page_comments   # one channel
    python tools/ingest_dm_tips.py --selftest      # offline end-to-end test
"""

from __future__ import annotations

import os
import sys
import json
import argparse
import logging
from datetime import datetime, date as _date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from scraper import dm_sources
from scraper import dm_instagrapi
from tools import add_tip
from tools import enrich_tip_links

logger = logging.getLogger(__name__)

PENDING_ACTIONS = r"C:\Users\willi\.claude\pending-william-actions.md"
# Self-promo line appended to promoted-tip captions (William, 2026-06-17).
SELF_PROMO = "Find every Tulsa LGBTQ+ event any time at tulsagays.com 🏳️‍🌈"

# A message must smell like an event before it joins the queue — otherwise "love your
# page!" and "what time?" flood the reviewer. The review gate is still the real safety
# net, so this stays deliberately loose (a real date is the strongest single signal).
_EVENT_HINTS = (
    "join us", "come out", "tonight", "this week", "tomorrow", "tickets", "doors",
    "rsvp", "party", "drag", "show", "ball", "festival", "fundraiser", "market",
    "bingo", "happy hour", "dance", "live", "performance", "lineup", "presale",
    "celebration", "brunch", "mixer", "pride", "queer", "cabaret", "watch party",
    "fest", "pop up", "pop-up", "open mic", "karaoke", "trivia", "screening",
)
# Featurable = fun, one-off, inclusive. These keywords promote a tip to "high signal"
# (worth a standalone spotlight draft). Service/recurring words never qualify.
_FEATURABLE = (
    "drag", "ball", "pride", "queer", "cabaret", "festival", "fest", "party",
    "show", "performance", "brunch", "dance", "concert", "pop up", "pop-up",
)
_NEVER_FEATURE = (
    "aa meeting", "support group", "therapy", "clinic", "service", "worship",
    "bible", "recovery", "12 step", "12-step", "class", "rehearsal", "weekly",
)


import re as _re
# Word-boundary matcher so "show" doesn't fire inside "showing up" and "fest" doesn't
# fire inside "manifesto" — same lesson TulsaGays learned with "drag" / "dragon".
_HINT_RX = _re.compile(
    r"\b(" + "|".join(_re.escape(h) for h in _EVENT_HINTS) + r")\b", _re.I)


def looks_like_event_tip(text: str) -> bool:
    """Loose gate: a parseable date, or a word-boundary event-hint keyword. The review
    step is the real safety net, so this errs toward letting borderline tips through."""
    if not text or len(text.strip()) < 8:
        return False
    if add_tip.parse_date(text):
        return True
    return bool(_HINT_RX.search(text))


def is_high_signal(entry: dict) -> bool:
    """Worth a standalone spotlight draft: featurable keyword, a real in-future date,
    and no service/recurring red flag."""
    blob = f"{entry.get('name','')} {entry.get('raw_text','')}".lower()
    if any(bad in blob for bad in _NEVER_FEATURE):
        return False
    if not entry.get("date"):
        return False
    try:
        if datetime.strptime(entry["date"], "%Y-%m-%d").date() < _date.today():
            return False
    except ValueError:
        return False
    return any(k in blob for k in _FEATURABLE)


def draft_voice_copy(entry: dict, use_llm: bool = False) -> dict:
    """Draft short + long site-voice copy for a tip. Returns (possibly) updated entry
    with description / website_description filled and needs_voice_polish set.

    Defaults to the fast rule-based enrichment (no nested claude CLI -> can't hang a
    scheduled run). Rule-based output is a placeholder, so needs_voice_polish stays True
    until a review session rewrites it in true voice. --llm-voice flips on the real path.
    """
    if entry.get("description") and entry.get("website_description"):
        entry["needs_voice_polish"] = False
        return entry
    ev = {
        "name": entry.get("name", ""),
        "venue": entry.get("venue", ""),
        "date": entry.get("date", ""),
        "time": entry.get("time", ""),
        "description": entry.get("description", ""),
        "website_description": entry.get("website_description", ""),
    }
    prev_rule = os.environ.get("TULSAGAYS_RULE_ENRICH")
    prev_budget = os.environ.get("TULSAGAYS_ENRICH_BUDGET_S")
    try:
        from content import generator
        if not use_llm:
            os.environ["TULSAGAYS_RULE_ENRICH"] = "1"
        os.environ.setdefault("TULSAGAYS_ENRICH_BUDGET_S", "60")
        enriched = generator.enrich_event_descriptions([ev])[0]
        entry["description"] = (enriched.get("description") or "").strip()
        entry["website_description"] = (enriched.get("website_description") or "").strip()
        # Rule-based copy is a placeholder; only a real LLM draft clears the polish flag.
        entry["needs_voice_polish"] = not use_llm
    except Exception as e:  # never let copy-drafting kill the ingest
        logger.info("voice draft failed for %s: %s", entry.get("id"), e)
        entry["needs_voice_polish"] = True
    finally:
        _restore_env("TULSAGAYS_RULE_ENRICH", prev_rule)
        _restore_env("TULSAGAYS_ENRICH_BUDGET_S", prev_budget)
    return entry


def _restore_env(key, val):
    if val is None:
        os.environ.pop(key, None)
    else:
        os.environ[key] = val


def build_tip_entry(msg: dict, inbox: list, now: datetime) -> dict:
    """Turn a raw collector message into a pending_review queue entry (add_tip shape)."""
    parsed = add_tip.parse_tip(msg.get("text", ""))
    entry = {
        "id": add_tip._next_id(inbox),
        "status": "pending_review",
        "captured_at": now.strftime("%Y-%m-%d %H:%M"),
        "channel": msg.get("channel", ""),
        "submitted_by": msg.get("sender", ""),
        "image": "",
        "raw_text": msg.get("text", ""),
        **parsed,
        "priority": 2,
        # provenance so dedup + audit work and add_tip.py stays fully compatible
        "source_kind": msg.get("source_kind", ""),
        "permalink": msg.get("permalink", ""),
        "message_id": msg.get("message_id", ""),
        "auto_ingested": True,
        "needs_voice_polish": True,
    }
    # DM-only extras: flyers (a tip can carry MULTIPLE) + thread for the reply.
    flyers = msg.get("flyer_images") or []
    if flyers:
        entry["flyer_images"] = flyers          # ALL flyers noted, none dropped
        entry["image"] = flyers[0]              # add_tip shows the first
        entry["flyer_count"] = len(flyers)
        entry["needs_flyer_read"] = True        # a vision review fills fields from the art
    if msg.get("thread_id"):
        entry["thread_id"] = msg["thread_id"]
    return entry


def make_spotlight_draft(entry: dict, week_key: str, posts_root: str) -> str:
    """Render a DRAFT spotlight slide + caption for a standout tip. Returns path or ''.
    Never posts — just leaves files for the reviewer."""
    try:
        from content.image_maker import make_engagement_slide
    except Exception as e:
        logger.info("spotlight import failed: %s", e)
        return ""
    week_dir = os.path.join(posts_root, week_key)
    os.makedirs(week_dir, exist_ok=True)
    headline = entry.get("name") or "Tulsa, mark your calendar"
    body = (entry.get("description")
            or "A community tip worth leaving the house for. Details on the site.")
    try:
        img = make_engagement_slide(headline, body, post_type="spotlight")
        img = _add_promo_footer(img)        # self-promo band (William, 2026-06-17)
        img_path = os.path.join(week_dir, f"spotlight_tip_{entry['id']}.png")
        img.save(img_path)
        cap_path = os.path.join(week_dir, f"spotlight_tip_{entry['id']}.caption.txt")
        with open(cap_path, "w", encoding="utf-8") as f:
            f.write(_spotlight_caption(entry))
        return img_path
    except Exception as e:
        logger.info("spotlight render failed for %s: %s", entry.get("id"), e)
        return ""


def _add_promo_footer(img):
    """Draw a tulsagays.com self-promo band across the bottom of a spotlight slide.
    Best-effort: if fonts/helpers aren't importable, returns the image unchanged."""
    try:
        from PIL import ImageDraw
        from content.image_maker import _font, NEON_PINK, BG, SIZE
    except Exception:
        return img
    try:
        w, h = img.size
        draw = ImageDraw.Draw(img)
        band_h = 56
        draw.rectangle([0, h - band_h, w, h], fill=NEON_PINK)
        text = "FIND EVERY TULSA GAY EVENT  →  TULSAGAYS.COM"
        f = _font("segoe-semi", 26)
        try:
            tw = draw.textlength(text, font=f)
        except Exception:
            tw = len(text) * 13
        draw.text(((w - tw) // 2, h - band_h + 14), text, font=f, fill=BG)
    except Exception:
        return img
    return img


def _spotlight_caption(entry: dict) -> str:
    bits = [entry.get("name", "").strip()]
    when = " ".join(x for x in (entry.get("date", ""), entry.get("time", "")) if x).strip()
    if when:
        bits.append(when)
    if entry.get("venue"):
        bits.append(entry["venue"].strip())
    if entry.get("description"):
        bits.append(entry["description"].strip())
    bits.append("")
    bits.append(SELF_PROMO)                       # self-promo in the caption too
    bits.append("(DRAFT spotlight — review before posting.)")
    return "\n".join(b for b in bits if b is not None)


def ingest(channels=None, dry_run=False, spotlight=True, use_llm=False,
           now=None, inbox_path=None, state_path=None, posts_root=None,
           notify=True, collect_fn=None, include_dms=True, autoreply=True,
           enrich_links=True, dm_read_fn=None, dm_client_fn=None, autoreply_fn=None):
    """End-to-end: collect (official API + instagrapi DMs) -> gate -> parse ->
    enrich from linked sites -> draft -> queue review-ready -> spotlight -> auto-reply.

    The *_fn params let the selftest inject stubs. Returns a summary dict.
    """
    now = now or datetime.now()
    inbox_path = inbox_path or add_tip.INBOX_FILE
    state_path = state_path or dm_sources.STATE_FILE
    posts_root = posts_root or os.path.join(config.DATA_DIR, "posts")
    collect_fn = collect_fn or dm_sources.collect_all
    dm_read_fn = dm_read_fn or dm_instagrapi.read_dm_tips
    dm_client_fn = dm_client_fn or dm_instagrapi.get_client
    autoreply_fn = autoreply_fn or dm_instagrapi.send_confirmations

    state = dm_sources._load_state(state_path)
    messages, status = collect_fn(channels=channels, state=state)

    # Instagram DMs come via instagrapi (official API can't read them until App Review).
    # Degrades silently if the session is invalid — never blocks the official channels.
    dm_client = None
    if include_dms:
        dm_client = dm_client_fn()
        dm_msgs, dm_err = dm_read_fn(dm_client, set(state.get("seen_ids", [])))
        status["ig_dm"] = dm_err or f"ok ({len(dm_msgs)} new)"
        messages = list(messages) + list(dm_msgs)

    inbox = add_tip._load(inbox_path, [])
    seen_keys = {add_tip._norm_key(e.get("name"), e.get("date")) for e in inbox}
    seen_msg_ids = {e.get("message_id") for e in inbox if e.get("message_id")}

    queued, skipped_chatter, skipped_dup, spotlights = [], 0, 0, []
    newly_seen, source_suggested = [], []

    for msg in messages:
        mid = msg.get("message_id", "")
        newly_seen.append(mid)  # mark seen regardless so we don't re-evaluate chatter
        # A flyer-only DM (image, no text) is still a tip — don't drop it as chatter.
        if not looks_like_event_tip(msg.get("text", "")) and not msg.get("flyer_images"):
            skipped_chatter += 1
            continue
        if mid in seen_msg_ids:
            skipped_dup += 1
            continue
        entry = build_tip_entry(msg, inbox, now)
        if enrich_links and not dry_run:
            try:
                entry = enrich_tip_links.enrich_tip(entry)
                if entry.get("source_suggested"):
                    source_suggested.extend(entry["source_suggested"])
            except Exception as e:
                logger.info("link enrich failed for %s: %s", entry.get("id"), e)
        key = add_tip._norm_key(entry.get("name"), entry.get("date"))
        if entry.get("name") and entry.get("date") and key in seen_keys:
            skipped_dup += 1
            continue
        # Append first so _next_id stays unique across this run (even in dry-run,
        # where we never persist). Drafting + spotlight are live-run only.
        inbox.append(entry)
        seen_keys.add(key)
        seen_msg_ids.add(mid)
        if not dry_run:
            entry = draft_voice_copy(entry, use_llm=use_llm)
            if spotlight and is_high_signal(entry):
                path = make_spotlight_draft(entry, config.current_week_key(), posts_root)
                if path:
                    entry["spotlight_draft"] = path
                    spotlights.append(entry["id"])
        queued.append(entry)

    # Auto-reply (guardrailed) to DM submitters whose tip we just queued.
    autoreply_result = None
    if autoreply and not dry_run:
        dm_tips = [e for e in queued if e.get("source_kind") == "ig_dm" and e.get("thread_id")]
        if dm_tips:
            autoreply_result = autoreply_fn(dm_client, dm_tips)

    if not dry_run:
        add_tip._save(inbox_path, inbox)
        existing = set(state.get("seen_ids", []))
        state["seen_ids"] = list(state.get("seen_ids", [])) + [
            m for m in newly_seen if m and m not in existing]
        state["last_run"] = now.strftime("%Y-%m-%d %H:%M")
        state["last_status"] = status
        dm_sources._save_state(state, state_path)

    summary = {
        "collected": len(messages),
        "queued": len(queued),
        "queued_ids": [e["id"] for e in queued],
        "skipped_chatter": skipped_chatter,
        "skipped_dup": skipped_dup,
        "spotlight_drafts": spotlights,
        "flyers_captured": sum(len(e.get("flyer_images") or []) for e in queued),
        "source_candidates_suggested": source_suggested,
        "autoreply": autoreply_result,
        "needs_polish": [e["id"] for e in queued if e.get("needs_voice_polish")],
        "channel_status": status,
        "dry_run": dry_run,
    }
    if notify and not dry_run and queued:
        _notify(summary, queued)
    return summary


def _notify(summary: dict, queued: list):
    """Append a one-tap review nudge to pending-william-actions.md (the documented
    task-output channel). The scheduled Claude session relays it to Telegram."""
    try:
        lines = [
            f"\n## [{datetime.now():%Y-%m-%d %H:%M}] TulsaGays: {len(queued)} new event tip(s) auto-ingested (review-ready)",
        ]
        for e in queued:
            when = e.get("date") or "????-??-??"
            sp = "  [spotlight draft]" if e.get("spotlight_draft") else ""
            polish = "  (needs voice polish)" if e.get("needs_voice_polish") else ""
            lines.append(f"- `{e['id']}` {when} {(e.get('name') or '(no name)')[:60]} "
                         f"via {e.get('source_kind','')}{sp}{polish}")
        lines.append("- Review: `python tools/add_tip.py review <id>` then `approve <id>` "
                     "(write the site-voice copy first).")
        with open(PENDING_ACTIONS, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    except OSError as e:
        logger.info("notify append failed: %s", e)


# ── selftest ──────────────────────────────────────────────────────────────────

def _selftest():
    import tempfile

    assert looks_like_event_tip("Drag brunch Sun June 22 at Inner Circle, $15")
    assert looks_like_event_tip("Pride party this Saturday, doors 8pm")
    assert not looks_like_event_tip("love your page!!")
    assert not looks_like_event_tip("hi")

    d = tempfile.mkdtemp()
    inbox_p = os.path.join(d, "inbox.json")
    state_p = os.path.join(d, "state.json")
    posts_p = os.path.join(d, "posts")
    add_tip._save(inbox_p, [])

    canned = [
        dm_sources._msg("ig", "ig_messages", "m1",
                        "Hey! Sapphic Drag Brunch at Inner Circle Sun June 28 2026 "
                        "from 12:00pm-2:00pm, tix https://x.co/t", "@friend", "t1"),
        dm_sources._msg("fb", "fb_page_comments", "m2",
                        "omg love this page", "Some Fan", "t2"),
        dm_sources._msg("ig", "ig_comments", "m3",
                        "Weekly AA meeting every Monday 7pm at the center", "@bot", "t3"),
    ]

    def fake_collect(channels=None, state=None, **kw):
        seen = set((state or {}).get("seen_ids", []))
        new = [m for m in canned if m["message_id"] not in seen]
        return new, {"ig_messages": "ok", "fb_page_comments": "ok", "ig_comments": "ok"}

    # voice drafting offline: stub generator so no network/CLI
    import content.generator as gen
    orig = gen.enrich_event_descriptions
    gen.enrich_event_descriptions = lambda evs: [
        {**e, "description": "Test short pitch.",
         "website_description": "Test long copy for the site."} for e in evs]
    try:
        s = ingest(dry_run=False, spotlight=True, use_llm=False,
                   now=datetime(2026, 6, 17, 9, 0),
                   inbox_path=inbox_p, state_path=state_p, posts_root=posts_p,
                   notify=False, collect_fn=fake_collect,
                   include_dms=False, enrich_links=False, autoreply=False)
    finally:
        gen.enrich_event_descriptions = orig

    assert s["collected"] == 3, s
    assert s["queued"] == 1, s                      # only the drag brunch is an event tip
    # "love this page" (no date, no hint) and the AA-meeting comment (no parseable
    # date, no event-hint keyword) both fail the loose gate -> chatter.
    assert s["skipped_chatter"] == 2, s
    inbox = add_tip._load(inbox_p, [])
    drag = next(e for e in inbox if "Drag Brunch" in (e.get("name") or ""))
    assert drag["date"] == "2026-06-28", drag
    assert drag["description"], drag
    assert drag["message_id"] == "m1", drag
    assert drag["channel"] == "ig", drag

    # idempotency: a second run with the same canned messages queues nothing new
    s2 = ingest(dry_run=False, spotlight=True, use_llm=False,
                now=datetime(2026, 6, 17, 9, 5),
                inbox_path=inbox_p, state_path=state_p, posts_root=posts_p,
                notify=False, collect_fn=fake_collect,
                include_dms=False, enrich_links=False, autoreply=False)
    assert s2["queued"] == 0, s2
    assert s2["collected"] == 0, s2                 # state filtered them all out

    # high-signal gate: drag brunch yes; AA/weekly no
    assert is_high_signal({"name": "Drag Brunch", "raw_text": "drag brunch",
                           "date": "2026-12-01"})
    assert not is_high_signal({"name": "AA Meeting", "raw_text": "weekly aa meeting",
                               "date": "2026-12-01"})
    assert not is_high_signal({"name": "Old Party", "raw_text": "party",
                               "date": "2020-01-01"})  # past date

    # ── DM channel + multi-flyer + link-enrich + guardrailed auto-reply (stubbed) ──
    d2 = tempfile.mkdtemp()
    inbox_p2 = os.path.join(d2, "inbox.json")
    state_p2 = os.path.join(d2, "state.json")
    add_tip._save(inbox_p2, [])

    def empty_collect(channels=None, state=None, **kw):
        return [], {}

    # one DM tip carrying TWO flyers + a venue link
    dm_messages = [{
        "channel": "ig", "source_kind": "ig_dm", "message_id": "ig_dm:thr1:mm1",
        "text": "Drag Night at The Tulsan Fri June 19 2026 9pm — flyers attached, "
                "more at https://thetulsan.com/events/drag",
        "sender": "thetulsan", "ts": "t", "permalink": "",
        "flyer_images": ["/tmp/flyer_a.jpg", "/tmp/flyer_b.jpg"], "thread_id": "thr1",
    }]

    def fake_dm_read(client, seen):
        return [m for m in dm_messages if m["message_id"] not in seen], ""

    reply_calls = {"sent": 0, "tips": None}

    def fake_autoreply(client, tips, **kw):
        reply_calls["tips"] = tips
        reply_calls["sent"] = len(tips)
        return {"sent": len(tips), "skipped": 0}

    page_html = ("<html><script type=\"application/ld+json\">"
                 "{\"@type\":\"Event\",\"name\":\"Drag Night\",\"startDate\":\"2026-06-19T21:00:00\","
                 "\"location\":{\"name\":\"The Tulsan\"}}</script></html>")

    import content.generator as gen2
    orig2 = gen2.enrich_event_descriptions
    gen2.enrich_event_descriptions = lambda evs: [
        {**e, "description": "Sickening drag, darling.", "website_description": "Long copy."}
        for e in evs]
    orig_fetch = enrich_tip_links.fetch_page
    enrich_tip_links.fetch_page = lambda url: page_html
    # point source-candidate writes at a temp file so the test doesn't touch real data
    cand_p = os.path.join(d2, "cands.json")
    orig_enrich = enrich_tip_links.enrich_tip
    enrich_tip_links.enrich_tip = lambda e, **kw: orig_enrich(
        e, fetcher=lambda u: page_html, candidates_path=cand_p)
    try:
        sd = ingest(dry_run=False, spotlight=True, use_llm=False,
                    now=datetime(2026, 6, 17, 10, 0),
                    inbox_path=inbox_p2, state_path=state_p2,
                    posts_root=os.path.join(d2, "posts"), notify=False,
                    collect_fn=empty_collect, include_dms=True, enrich_links=True,
                    autoreply=True, dm_read_fn=fake_dm_read,
                    dm_client_fn=lambda: "FAKE_CLIENT", autoreply_fn=fake_autoreply)
    finally:
        gen2.enrich_event_descriptions = orig2
        enrich_tip_links.fetch_page = orig_fetch
        enrich_tip_links.enrich_tip = orig_enrich

    assert sd["queued"] == 1, sd
    assert sd["flyers_captured"] == 2, sd                  # BOTH flyers noted
    assert sd["channel_status"].get("ig_dm", "").startswith("ok"), sd
    dmtip = add_tip._load(inbox_p2, [])[0]
    assert dmtip["flyer_count"] == 2 and dmtip["needs_flyer_read"], dmtip
    assert dmtip["date"] == "2026-06-19", dmtip            # link-enrich filled the date
    assert reply_calls["sent"] == 1, reply_calls           # auto-reply fired once for the DM tip
    assert sd["source_candidates_suggested"], sd           # /events link -> source candidate

    print("ingest_dm_tips selftest: passed (gate + parse + draft + queue + dedup/state + "
          "high-signal + DM/multi-flyer + link-enrich + guardrailed auto-reply)")
    return 0


def main(argv=None):
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser(description="Auto-ingest inbound event tips (review-first).")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="collect + show, write nothing")
    ap.add_argument("--no-spotlight", dest="spotlight", action="store_false",
                    help="don't draft spotlight slides for standout tips")
    ap.add_argument("--llm-voice", dest="use_llm", action="store_true",
                    help="draft copy via the real LLM path (interactive only; can be slow)")
    ap.add_argument("--channels", nargs="*", default=None,
                    help=f"subset of {dm_sources.ALL_CHANNELS}")
    args = ap.parse_args(argv)
    if args.selftest:
        return _selftest()
    summary = ingest(channels=args.channels, dry_run=args.dry_run,
                     spotlight=args.spotlight, use_llm=args.use_llm)
    # ensure_ascii=True so emoji in comment-derived names can't crash a cp1252 console
    # (the inbox JSON itself is still written with ensure_ascii=False / full unicode).
    print(json.dumps(summary, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
