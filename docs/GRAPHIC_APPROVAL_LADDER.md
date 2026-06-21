# Graphic Approval — the Ladder to the Ceiling

Trigger: 2026-06-20, a cheap "boxes with X's" (tofu) weekend graphic shipped to
IG/FB. William: *"I need a better graphic approval process. Set this in place and
then take it to the ceiling through the ladder process."*

The ceiling: **it is structurally impossible for a cheap or broken graphic to
reach the public.** Every graphic is born clean, proven clean by machine, seen by
a human, and leaves an honest audit trail.

---

## The ladder (each rung a real jump, not a tweak)

### Rung 0 — the failure state (what shipped the tofu)
Graphics auto-posted from a static asset. No machine QA, no human eyes. A muddy
rainbow background with `.notdef` tofu boxes around "TulsaGays.com" went live.
**Status: this is what we are climbing away from.**

### Rung 1 — machine catches the obvious garbage ✅ DONE (2026-06-20)
`tools/detect_tofu.py` + `tools/graphic_qa.py`: hard, deterministic, free checks
on the EXACT bytes that will post — tofu/.notdef glyphs, blank/single-color
canvas, too-small resolution, broken aspect ratio. Any fail → BLOCK.
Wired into `tulsagays-saturday-preview` STEP 5 (`preflight_image.preflight`).
*Verified:* `detect_tofu` flags the live tofu fixture, passes the clean one.

### Rung 2 — reusable assets must be registered ✅ DONE (2026-06-20)
`data/approved_assets.json` records sha256 + who/when. A reusable brand asset
(e.g. `docs/assets/weekend-preview-bg.png`) must hash-match a registry entry to
post; change the bytes → must be re-approved. The old broken asset was never
registered, so this layer alone would have stopped it.

### Rung 3 — a HUMAN actually sees it ✅ DONE (2026-06-20, this session)
The gap rung 1–2 left: a *script* could write `approved_by: William` without
William ever laying eyes on the image. Automated QA cannot judge "this looks
cheap" — only a person can.
- `tools/request_visual_approval.py` — gate + notify. Auto-QA fail → block, never
  bother William. Auto-QA pass → Telegram the ACTUAL IMAGE to William with the
  caption + a one-tap `[STOP: <key>]` / `[APPROVE-GFX: <key>]`, under his chosen
  "auto + veto window" model (2026-06-08).
- `relay-notifications.py` now does `sendPhoto` (was text-only), so the graphic
  reaches his phone.
- Honesty fix: registry method is now `auto-veto-window (image shown, no STOP)`
  or `human-telegram` — scripts can no longer impersonate William's sign-off.
*Verified:* `request_visual_approval.py selftest` — tofu blocked at request,
clean → pending eyes-on, window-elapsed → auto-approve. ALL PASS.

### Rung 4 — every graphic-posting path uses the gate ✅ DONE (2026-06-21)
Rather than wire each *task* one-by-one (bypassable the moment a new task posts
an image), the gate was pushed DOWN into the low-level posting **primitives** so
it is structurally impossible to post an unchecked image from any caller:
- `posting/facebook.py` (`post_to_page` → single, carousel, `_upload_photo`)
- `posting/instagram.py` (`post_carousel`, `post_single_image`)
- `posting/group_post.py` (`post_to_group`)
- `posting/group_blast.py` (`run` — gates all 9 slides once before the group loop)

All four route through the single chokepoint `preflight_image.gate_images()`
(→ `graphic_qa` + `detect_tofu`), fail-CLOSED on a real block, fail-OPEN only if
the gate tooling itself is unavailable (a tooling bug can never silently kill
every post). The high-level paths (`post_weekly.py`, `social_lib.py`, the
Saturday SKILL) were already gated; this closes the low-level bypass.
*Decision RESOLVED (William 2026-06-21):* keep **auto-gate + Telegram preview w/
veto window** everywhere (including the Monday carousel) — visibility + quality
control with zero mandatory taps; silence ships, one `STOP` holds.
*Verified:* each primitive blocks the known-bad tofu image and passes the clean
one; full regression suite green.

### Rung 5 — born clean (kill the root cause) ⏳ QUEUED
QA is a net; the real win is graphics that can't be born dirty. In
`content/image_maker.py`: route EVERY emoji through the color emoji font
(`segoe-emoji`, `embedded_color=True`) or strip it — never let a brand font try
to draw an emoji (that is what bakes tofu). Add a generation-time assert that
re-runs `detect_tofu` on each slide before it is saved, failing the build loudly
instead of shipping quietly. Then QA almost never has anything to catch.

### Rung 6 / the ceiling — the self-defending graphic factory ⏳ QUEUED
Born-clean generation + machine QA + human eyes + honest audit, plus:
weekly auto-regeneration of stable assets (no asset silently rots), a contact
sheet of the week's graphics in one approval message, and a regression fixture
for every past failure (the tofu pair is the first). Nothing cheap can ship
because every layer would have to fail at once.

---

## Where we are now
Rungs 0→4 climbed and verified (4 completed 2026-06-21 via /cockpit). The gate is
now structurally un-bypassable at the posting-primitive level, the framing
decision is resolved (auto + veto window everywhere), and the ceiling's
regression-fixture layer is seeded: `tests/test_pipeline.py::test_graphic_gate`
locks in that the detector catches the original tofu pair AND that every
primitive both defines and calls the gate (so the call site can't be silently
deleted). The live website asset is clean + registered; every posting path now
QA's the exact bytes and shows William new/changed graphics first.

Remaining (queued, not move-week-urgent):
- **Rung 5 (born clean):** add a generation-time `detect_tofu` assert inside
  `content/image_maker.py` per-slide save so a dirty slide fails the build loudly.
  (`gen_weekend_preview_bg.py` already routes emoji through the color font + gates.)
- **Rung 6 (factory):** the weekly contact sheet (`graphic_contact_sheet.py`,
  already generating `_APPROVAL_contact_sheet.png`) folded into ONE weekly approval
  message; weekly auto-regen of stable assets so none silently rots.
