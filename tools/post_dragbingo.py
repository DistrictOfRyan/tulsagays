# -*- coding: utf-8 -*-
"""Post the Drag Bingo promo to TulsaGays FB (and prep IG). One-off."""
import os, sys, json, urllib.request, urllib.parse, mimetypes

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "posts", "dragbingo-2026-06-14")
CFG = json.load(open(os.path.join(ROOT, "meta_api_config.json")))
PAGE_ID = CFG["page_id"]
IG_ID = CFG["instagram_business_account_id"]
GRAPH = "https://graph.facebook.com/v25.0"

def load_token():
    t = os.environ.get("TULSAGAYS_PAGE_ACCESS_TOKEN")
    if t:
        return t.strip()
    envf = os.path.join(ROOT, ".env")
    if os.path.exists(envf):
        for line in open(envf, encoding="utf-8"):
            if line.strip().startswith("TULSAGAYS_PAGE_ACCESS_TOKEN"):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    sys.exit("NO TOKEN")

TOKEN = load_token()

def post_fb_photo(img_path, caption):
    url = f"{GRAPH}/{PAGE_ID}/photos"
    boundary = "----tgbingo"
    parts = []
    def field(name, val):
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{val}\r\n".encode("utf-8"))
    field("access_token", TOKEN)
    field("caption", caption)
    field("published", "true")
    with open(img_path, "rb") as f:
        img = f.read()
    parts.append((f"--{boundary}\r\nContent-Disposition: form-data; name=\"source\"; filename=\"bingo.png\"\r\nContent-Type: image/png\r\n\r\n").encode("utf-8"))
    parts.append(img)
    parts.append(f"\r\n--{boundary}--\r\n".encode("utf-8"))
    body = b"".join(parts)
    req = urllib.request.Request(url, data=body, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)

def _get(url):
    with urllib.request.urlopen(url, timeout=120) as r:
        return json.load(r)

def _post(url, data):
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(url, data=body)
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)

def post_ig(image_url, caption):
    cont = _post(f"{GRAPH}/{IG_ID}/media",
                 {"image_url": image_url, "caption": caption, "access_token": TOKEN})
    cid = cont["id"]
    pub = _post(f"{GRAPH}/{IG_ID}/media_publish",
                {"creation_id": cid, "access_token": TOKEN})
    return pub

if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "fb"
    if action == "fb":
        cap = open(os.path.join(OUT, "fb_caption.txt"), encoding="utf-8").read()
        try:
            res = post_fb_photo(os.path.join(OUT, "dragbingo_feed_1080.png"), cap)
            print("FB_OK", json.dumps(res))
        except urllib.error.HTTPError as e:
            print("FB_ERR", e.code, e.read().decode())
    elif action == "ig":
        image_url = sys.argv[2]
        cap = open(os.path.join(OUT, "ig_caption.txt"), encoding="utf-8").read()
        try:
            res = post_ig(image_url, cap)
            print("IG_OK", json.dumps(res))
        except urllib.error.HTTPError as e:
            print("IG_ERR", e.code, e.read().decode())
