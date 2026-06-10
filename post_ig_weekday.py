"""
Delete old IG post and repost W22 weekday carousel with all 9 slides.
Uploads images to GitHub Pages (public tulsagays repo) for public URLs.
"""
import json, base64, time, sys, requests

# ── Config ────────────────────────────────────────────────────────────────────
META_CFG  = r'C:\Users\willi\.claude\tulsagays\meta_api_config.json'
GH_ENV    = r'C:\Users\willi\.credentials\github.env'
POST_DATA = r'C:\Users\willi\tulsagays\data\posts\2026-W22\weekday_post.json'
RESULTS   = r'C:\Users\willi\tulsagays\data\posts\2026-W22\post_results.json'

GRAPH_BASE = 'https://graph.facebook.com/v25.0'
GH_REPO    = 'DistrictOfRyan/tulsagays'
GH_BRANCH  = 'main'
GH_FOLDER  = 'data/posts/2026-W22'

# ── Load credentials ──────────────────────────────────────────────────────────
with open(META_CFG, encoding='utf-8') as f:
    meta = json.load(f)
TOKEN   = meta['page_access_token']
IG_ID   = meta['instagram_business_account_id']

GH_TOKEN = None
with open(GH_ENV) as f:
    for line in f:
        line = line.strip()
        if 'GITHUB_PAT=' in line:
            GH_TOKEN = line.split('=',1)[1].strip()
            break
if not GH_TOKEN:
    print('ERROR: GITHUB_PAT not found'); sys.exit(1)

# ── Load post data ─────────────────────────────────────────────────────────────
with open(POST_DATA, encoding='utf-8') as f:
    post = json.load(f)

CAPTION     = post['caption']
IMAGE_PATHS = post['image_paths']

# ── Step 1: Delete old IG post ─────────────────────────────────────────────────
with open(RESULTS, encoding='utf-8') as f:
    results = json.load(f)

old_ig_id = results.get('ig_post_id')
if old_ig_id:
    print(f'Deleting old IG post {old_ig_id}...')
    r = requests.delete(
        f'{GRAPH_BASE}/{old_ig_id}',
        params={'access_token': TOKEN}
    )
    resp = r.json()
    if resp.get('success') or resp.get('result') == 'true':
        print('  Deleted successfully.')
    else:
        print(f'  Delete response: {resp}')
        # Don't fail — post may already be gone
else:
    print('No old IG post ID found, skipping delete.')

# ── Step 2: Upload images to GitHub Pages ─────────────────────────────────────
print(f'\nUploading {len(IMAGE_PATHS)} images to GitHub...')
GH_HEADERS = {
    'Authorization': f'Bearer {GH_TOKEN}',
    'Accept': 'application/vnd.github.v3+json'
}

raw_urls = []
for i, local_path in enumerate(IMAGE_PATHS):
    filename = local_path.replace('\\', '/').split('/')[-1]
    repo_path = f'{GH_FOLDER}/{filename}'
    api_url   = f'https://api.github.com/repos/{GH_REPO}/contents/{repo_path}'

    with open(local_path, 'rb') as f:
        content_b64 = base64.b64encode(f.read()).decode('utf-8')

    # Check if file already exists (need SHA to update)
    sha = None
    check = requests.get(api_url, headers=GH_HEADERS, timeout=15)
    if check.status_code == 200:
        sha = check.json().get('sha')

    payload = {
        'message': f'Upload W22 weekday slide {i+1}',
        'content': content_b64,
        'branch': GH_BRANCH,
    }
    if sha:
        payload['sha'] = sha

    resp = requests.put(api_url, json=payload, headers=GH_HEADERS, timeout=60)
    if resp.status_code in (200, 201):
        raw_url = f'https://raw.githubusercontent.com/{GH_REPO}/{GH_BRANCH}/{repo_path}'
        raw_urls.append(raw_url)
        print(f'  [{i+1}/{len(IMAGE_PATHS)}] {filename} -> {raw_url}')
    else:
        print(f'  ERROR uploading {filename}: {resp.status_code} {resp.text[:200]}')
        sys.exit(1)

    time.sleep(0.5)  # Small delay between GitHub uploads

print(f'\nAll {len(raw_urls)} images uploaded.')

# ── Step 3: Create IG carousel containers ─────────────────────────────────────
print('\nCreating IG carousel containers...')
container_ids = []
for i, url in enumerate(raw_urls):
    r = requests.post(
        f'{GRAPH_BASE}/{IG_ID}/media',
        data={
            'image_url': url,
            'is_carousel_item': 'true',
            'access_token': TOKEN,
        }
    )
    resp = r.json()
    if 'id' in resp:
        container_ids.append(resp['id'])
        print(f'  [{i+1}/{len(raw_urls)}] container: {resp["id"]}')
    else:
        print(f'  ERROR creating container {i+1}: {resp}')
        sys.exit(1)
    time.sleep(2)

# ── Step 4: Create carousel container ─────────────────────────────────────────
print('\nCreating carousel container...')
r = requests.post(
    f'{GRAPH_BASE}/{IG_ID}/media',
    data={
        'media_type': 'CAROUSEL',
        'caption': CAPTION,
        'children': ','.join(container_ids),
        'access_token': TOKEN,
    }
)
carousel_resp = r.json()
print('Carousel container response:', json.dumps(carousel_resp, indent=2))

if 'id' not in carousel_resp:
    print('FAILED to create carousel container.')
    sys.exit(1)

carousel_id = carousel_resp['id']
print(f'Carousel container ID: {carousel_id}')

# ── Step 5: Publish ────────────────────────────────────────────────────────────
time.sleep(3)
print('\nPublishing carousel...')
r = requests.post(
    f'{GRAPH_BASE}/{IG_ID}/media_publish',
    data={
        'creation_id': carousel_id,
        'access_token': TOKEN,
    }
)
pub_resp = r.json()
print('Publish response:', json.dumps(pub_resp, indent=2))

if 'id' not in pub_resp:
    print('FAILED to publish.')
    sys.exit(1)

new_ig_id = pub_resp['id']
print(f'\nSUCCESS! New IG post ID: {new_ig_id}')

# ── Step 6: Save results ───────────────────────────────────────────────────────
results['ig_post_id']    = new_ig_id
results['ig_slides']     = len(IMAGE_PATHS)
results['ig_image_urls'] = raw_urls
results['note']          = f'IG reposted {__import__("datetime").datetime.now().isoformat()[:10]} with all {len(IMAGE_PATHS)} slides.'

with open(RESULTS, 'w', encoding='utf-8') as f:
    json.dump(results, f, indent=2, ensure_ascii=False)
print('Results saved.')
