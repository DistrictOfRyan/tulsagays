# TulsaGays Sponsor Outreach Templates
*Anonymous TulsaGays brand voice. Lead with "we send queer Tulsa to your door," never a personal name. DRAFTS — do not auto-send; William approves the first batch, then the fleet can run the sequence.*
*Best first ask for a small business: Community ($25/mo) or an à la carte IG spotlight ($75). Save Pride ($400) for bars/clinics with real budgets.*

---

## Email 1 — Cold (bars / high-intent venues)
**Subject:** Your events, in front of every queer Tulsan looking for plans

Hey [Venue],

We run TulsaGays.com, the one place that lists every LGBTQ+ event in Tulsa each week, plus a newsletter and @tulsagays on Instagram. Nearly half our traffic is people actively searching "gay Tulsa events," so it's exactly the crowd you want walking through your door on a slow Tuesday.

Your drag nights, karaoke, and theme nights are already the kind of thing we feature. We'd love to make [Venue] a Featured Partner so you're on the site, in the newsletter, and getting a monthly IG shoutout, all written in our voice (the fun kind people actually screenshot).

Founding-partner rates start at $25/mo and an IG spotlight runs $75. Want the one-pager? Happy to send it over.

See you out there,
The TulsaGays team

---

## Email 2 — Cold (community businesses: cafes, shops, clinics, services)
**Subject:** Put [Business] in front of Tulsa's queer community, every week

Hi [Business],

We're TulsaGays.com, Tulsa's weekly guide to every LGBTQ+ event in town. Our readers are queer Tulsans (and regional folks from Dallas and OKC) figuring out where to go, eat, and spend, and a lot of them would love a place like [Business] that gets them.

For $25/mo you'd be in our business directory with a warm write-up, cross-promoted on social, and tagged when it fits. Featured Partners ($150/mo) also get a monthly newsletter mention and an Instagram shoutout. It's the most targeted local audience you can reach, and every dollar goes to a queer-run community project.

Can I send the one-page media kit? No contracts, cancel anytime.

Warmly,
The TulsaGays team

---

## Email 3 — Follow-up (5-7 days after, if no reply)
**Subject:** Re: [previous subject]

Just floating this back to the top, [Name]. Quick recap: TulsaGays puts [Business] in front of the queer Tulsans actively looking for where to go, from $25/mo, no contract.

If now's not the time, totally fine, want me to circle back before Pride season instead? And if you'd rather start tiny, a single $75 Instagram spotlight is a great way to test it.

The TulsaGays team

---

## Email 4 — Partner ask (OKEQ / nonprofits, cross-promo not a sale)
**Subject:** Cross-promo? TulsaGays + [Org]

Hi [Org],

We run TulsaGays.com and we already list a lot of [Org]'s events. We'd love a simple cross-promo: we keep featuring your programming (free, always), and you point folks who ask "where do I find queer events" our way. No money, just two queer projects making each other stronger. Open to it?

The TulsaGays team

---

## Instagram DM version (short, for @-only businesses)
Hey! We run @tulsagays, the weekly guide to every LGBTQ+ event in Tulsa. We'd love to feature [Venue] to the exact crowd looking for plans. Founding-partner spots start at $25/mo and a single spotlight post is $75. Want the details? 🌈

---

## Fulfillment (what happens when someone says yes)
1. Add them to `data/featured_partners.json` (active: true, correct tier), run `python tools/inject_featured_partners.py` → they appear in the directory.
2. Newsletter mention: add to the Tuesday Kit send. IG shoutout: schedule via the posting pipeline.
3. Payment: send them the Ko-fi/Stripe link (see the monetization runbook) — recurring for monthly tiers.
4. Log the deal + monthly amount so we track real revenue.
