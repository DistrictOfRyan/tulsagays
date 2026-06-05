# TulsaGays — Reader Revenue Kit
# Built 2026-06-04 · Level 4 of nextlevel-tulsagays-revenue.md
# Why: the Nieman Lab 2025 report on LGBTQ media is blunt — corporate ad money is
# contracting (Gay Times lost 80% of advertisers). Reader revenue is the
# DEI-backlash-proof, recession-proof base. Even 100 supporters = $500/mo, sales-free.

---

## The product: "TulsaGays Supporter" — $5/month

A pay-what-you-can community-support tier. Not a paywall (the calendar stays free,
that's the mission), but a way for people who value it to keep it alive and unlock a
few extras.

### Supporter perks (all low-effort to deliver, high perceived value)
1. **The Saturday early drop** — supporters get the weekend preview a day early.
   (You already generate it; just send the supporter segment Friday.)
2. **"Skip the scroll" curated picks** — a short supporters-only "if you only do one
   thing this weekend" pick in each newsletter. One extra sentence you already think.
3. **Supporters' shout-out** — first name in a monthly "kept the lights on" thank-you
   (opt-in; anonymity-safe for them and you).
4. **Members' channel** — a Discord/Telegram for supporters to swap plans. (Optional;
   only if you want the community layer. Start without it.)

### Why $5 and pay-what-you-can
- $5 is an easy, no-think yes for a free thing people already love.
- Offer $5 / $10 / $25 tiers (same perks) so superfans can give more.
- One-time tips for people who won't subscribe ("buy us a coffee").

---

## Recommended platform: Ko-fi (BLOCKER — needs William to create the account)
- **Ko-fi** is the right fit: free, no monthly fee, supports both one-time tips and
  $5/mo memberships, takes 0% on Ko-fi Gold-free tier (just the payment-processor cut).
  Works anonymously under the TulsaGays brand (no personal name shown to supporters).
- Alternatives: Buy Me a Coffee (similar), Memberful (more powerful, costs more).
- **Setup (William, ~15 min):** create ko-fi.com/tulsagays → set a $5 monthly membership
  + tip jar → connect Stripe/PayPal (this is where the entity/payment decision matters,
  same as the sponsor rate card). Then paste the URL where this kit says `KOFI_URL`.

---

## Newsletter ask copy (drop one at the bottom of each weekly send — rotate)

**Ask A (value-first):**
> TulsaGays is free and always will be. If this list saves you a scroll every week,
> you can keep it going for the price of one drink a month. Become a Supporter →
> [KOFI_URL]

**Ask B (mission):**
> No corporate sponsor decides what's in this newsletter — our readers do. If you want
> it to stay that way, chip in $5/mo and get the weekend list a day early. [KOFI_URL]

**Ask C (light, occasional):**
> Like the list? Buy us a coffee and we'll keep finding every queer thing happening in
> Tulsa. [KOFI_URL]

---

## Deploy-ready "Support" section (paste into docs once KOFI_URL exists)

```html
<!-- TulsaGays Support block — drop above the footer on the homepage + newsletter page -->
<section class="support-block" style="max-width:640px;margin:2.5rem auto;padding:1.75rem;
     border:2px solid var(--berry,#b5179e);border-radius:14px;text-align:center;background:#fff">
  <h2 style="margin:0 0 .5rem;color:var(--berry,#b5179e)">Keep TulsaGays free</h2>
  <p style="margin:0 0 1rem;line-height:1.5">
    Every queer event in Tulsa, every week — no paywall, no corporate sponsor calling the
    shots. If it saves you a scroll, keep it alive for the price of one drink a month.
  </p>
  <a href="KOFI_URL" rel="nofollow"
     style="display:inline-block;padding:.7rem 1.4rem;background:var(--berry,#b5179e);
            color:#fff;border-radius:8px;font-weight:700;text-decoration:none">
    Become a Supporter — $5/mo
  </a>
  <p style="margin:.75rem 0 0;font-size:.85rem;opacity:.7">or leave a one-time tip · cancel anytime</p>
</section>
```
*Once `KOFI_URL` is live, tell me and I'll wire this into docs/index.html + the newsletter
template and verify it renders. Until then it's not deployed (no broken link shipped).*

---

## 30-day reader-revenue launch (once Ko-fi is live)
- **Week 1:** Ko-fi page live; Support block on homepage + newsletter; Ask A in the send.
- **Week 2:** Instagram Story: "we kept it free, here's how you keep it going" + link in bio.
- **Week 3:** first monthly "kept the lights on" thank-you to early supporters.
- **Week 4:** count supporters; if >20, add the Saturday early-drop perk.

## Target math
- 100 supporters @ $5 = **$500/mo** stable, sales-free, backlash-proof.
- Stacks on top of sponsor MRR (sponsor_pipeline.py) — different revenue, same audience.
- Combined with 8 sponsors (~$400/mo) -> ~$900/mo blended at Level 5.
