"""
TulsaGays follower-growth DISCOVERY (read-only).

Uses the @tulsagays instagrapi session to read followers of seed LGBTQ accounts,
drops anyone @tulsagays already follows, scores for "real local LGBTQ person"
signals, and prints a JSON shortlist. Does NOT follow anyone — discovery only.

Authenticated calls are kept low on purpose (session validate + my following +
2 seed follower pages). Bio/location enrichment uses the auth-free public
web-profile endpoint for only the top shortlist to avoid rate limits.
"""
import json, sys, time, re
from pathlib import Path

SETTINGS_FILE = Path.home() / ".credentials" / "ig_settings_tulsagays.json"
SELF = "tulsagays"

# Seed accounts to mine (followers of these = likely local LGBTQ people)
SEEDS = ["qwc_tul", "blackqueertulsa", "clubmajestictulsa"]

# Tulsa-metro location signal words for bio matching
LOCAL_RE = re.compile(
    r"\b(tulsa|broken arrow|bixby|jenks|owasso|sand springs|sapulpa|claremore|"
    r"\bokla?\b|oklahoma|918|t[\- ]?town|green country)\b", re.I)
LGBTQ_RE = re.compile(
    r"(gay|queer|lesbian|trans|nonbinary|non-binary|enby|bi\b|pan\b|drag|pride|"
    r"lgbtq|\bthey/them\b|\bhe/him\b|\bshe/her\b|🏳️‍🌈|🏳️‍⚧️|💅|👑)", re.I)
# Brand / org / out-of-scope filters on username or name
BRAND_RE = re.compile(
    r"(official|store|shop|boutique|salon|studio|bar\b|club\b|llc|inc\b|co\.|"
    r"realty|realtor|photography|fitness|church|ministry|news|magazine|podcast|"
    r"foundation|nonprofit|collective|society|league|chamber|university|college)", re.I)


def client():
    from instagrapi import Client
    cl = Client()
    cl.load_settings(str(SETTINGS_FILE))
    cl.get_timeline_feed()  # validate session (raises if dead)
    return cl


def public_profile(username):
    """Auth-free web-profile JSON: bio + name + private flag. None on failure."""
    import urllib.request
    url = f"https://www.instagram.com/api/v1/users/web_profile_info/?username={username}"
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
                      "AppleWebKit/605.1.15",
        "x-ig-app-id": "936619743392459",
    })
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            u = json.loads(r.read())["data"]["user"]
        return {
            "biography": u.get("biography", "") or "",
            "full_name": u.get("full_name", "") or "",
            "is_private": u.get("is_private", False),
            "followers": u.get("edge_followed_by", {}).get("count", 0),
            "follows": u.get("edge_follow", {}).get("count", 0),
        }
    except Exception as e:
        return None


def main():
    cl = client()
    my_id = cl.user_id_from_username(SELF)
    print(f"[ok] session valid; @{SELF} id={my_id}", file=sys.stderr)

    already = set()
    for uid, u in cl.user_following(my_id).items():
        already.add(u.username.lower())
    print(f"[ok] @{SELF} already follows {len(already)}", file=sys.stderr)

    # Collect candidate UserShorts from seed followers
    seen = {}
    for seed in SEEDS:
        try:
            sid = cl.user_id_from_username(seed)
            followers = cl.user_followers(sid, amount=60)
        except Exception as e:
            print(f"[warn] seed @{seed} failed: {type(e).__name__}: {e}", file=sys.stderr)
            time.sleep(3)
            continue
        for uid, u in followers.items():
            un = u.username.lower()
            if un in already or un == SELF or un in seen:
                continue
            seen[un] = {
                "username": u.username,
                "full_name": u.full_name or "",
                "is_private": bool(u.is_private),
                "seed": seed,
            }
        print(f"[ok] seed @{seed}: +{len(followers)} followers scanned, "
              f"pool now {len(seen)}", file=sys.stderr)
        time.sleep(2)

    # First-pass score on username + full_name (no extra calls)
    def prescore(c):
        s = 0
        name = c["full_name"]
        un = c["username"]
        blob = f"{name} {un}"
        if BRAND_RE.search(blob):
            s -= 3
        if LGBTQ_RE.search(blob):
            s += 2
        # a human-looking full name (has a space, letters) is a good sign
        if name and " " in name.strip() and re.search(r"[A-Za-z]", name):
            s += 1
        return s

    ranked = sorted(seen.values(), key=prescore, reverse=True)
    # Enrich top ~18 with public bio to confirm local + LGBTQ, keep auth calls at 0 here
    enriched = []
    for c in ranked[:18]:
        prof = public_profile(c["username"])
        time.sleep(1.2)
        if not prof:
            continue
        bio = prof["biography"]
        c.update(prof)
        local = bool(LOCAL_RE.search(bio)) or bool(LOCAL_RE.search(prof["full_name"]))
        lgbtq = bool(LGBTQ_RE.search(bio)) or bool(LGBTQ_RE.search(prof["full_name"]))
        brand = bool(BRAND_RE.search(bio))
        # Final confidence
        score = 0
        score += 3 if local else 0
        score += 2 if lgbtq else 0
        score -= 3 if brand else 0
        score += 1 if (prof["full_name"] and " " in prof["full_name"].strip()) else 0
        # reasonable human follower range, not a mega-brand
        if 30 <= prof["followers"] <= 8000:
            score += 1
        c["local_signal"] = local
        c["lgbtq_signal"] = lgbtq
        c["score"] = score
        enriched.append(c)

    enriched.sort(key=lambda x: x["score"], reverse=True)
    out = {
        "self": SELF,
        "already_following_count": len(already),
        "pool_scanned": len(seen),
        "shortlist": enriched,
    }
    Path("scripts/discover_results.json").write_text(
        json.dumps(out, indent=2), encoding="utf-8")
    print(f"[ok] wrote {len(enriched)} enriched candidates to "
          f"scripts/discover_results.json", file=sys.stderr)
    # Compact top view to stdout
    for c in enriched[:10]:
        print(f"  score={c['score']:>2}  @{c['username']:<22} "
              f"local={int(c['local_signal'])} lgbtq={int(c['lgbtq_signal'])} "
              f"priv={int(c['is_private'])} flwr={c['followers']:<5} "
              f"| {c['full_name'][:28]} | seed={c['seed']}")


if __name__ == "__main__":
    main()
