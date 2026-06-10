"""Post the W22 weekday carousel to the Tulsa Gays Facebook page."""
import json
import requests
import sys

# Load config
with open(r'C:\Users\willi\.claude\tulsagays\meta_api_config.json', encoding='utf-8') as f:
    cfg = json.load(f)

TOKEN = cfg['page_access_token']
PAGE_ID = cfg['page_id']
BASE = 'https://graph.facebook.com/v25.0'

# Load post data
with open(r'C:\Users\willi\tulsagays\data\posts\2026-W22\weekday_post.json', encoding='utf-8') as f:
    post_data = json.load(f)

CAPTION = post_data['caption']
IMAGE_PATHS = post_data['image_paths']

print(f'Uploading {len(IMAGE_PATHS)} images to Facebook page...')

photo_ids = []
for i, path in enumerate(IMAGE_PATHS):
    print(f'  [{i+1}/{len(IMAGE_PATHS)}] Uploading {path.split(chr(92))[-1]}...', flush=True)
    with open(path, 'rb') as img:
        r = requests.post(
            f'{BASE}/{PAGE_ID}/photos',
            data={'published': 'false', 'access_token': TOKEN},
            files={'source': (path.split('\\')[-1], img, 'image/png')}
        )
    resp = r.json()
    if 'id' in resp:
        photo_ids.append(resp['id'])
        print(f'    -> photo_id: {resp["id"]}')
    else:
        print(f'    ERROR: {resp}')
        sys.exit(1)

print(f'\nAll {len(photo_ids)} photos uploaded. Creating post...')

# Build attached_media list
attached_media = [{'media_fbid': pid} for pid in photo_ids]

r = requests.post(
    f'{BASE}/{PAGE_ID}/feed',
    json={
        'message': CAPTION,
        'attached_media': attached_media,
        'access_token': TOKEN
    }
)
resp = r.json()
print('Post response:', json.dumps(resp, indent=2))

if 'id' in resp:
    post_id = resp['id']
    print(f'\nSUCCESS! FB page post ID: {post_id}')
    # Save result
    try:
        with open(r'C:\Users\willi\tulsagays\data\posts\2026-W22\post_results.json', encoding='utf-8') as f:
            results = json.load(f)
    except Exception:
        results = {}
    results['fb_page_post_id'] = post_id
    results['fb_page_post_photos'] = photo_ids
    with open(r'C:\Users\willi\tulsagays\data\posts\2026-W22\post_results.json', 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print('Results saved.')
else:
    print('FAILED to create post.')
    sys.exit(1)
