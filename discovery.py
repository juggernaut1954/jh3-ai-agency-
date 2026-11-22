"""Small, human-reviewed OSM discovery adapter. No database writes or emails."""
import json
import re
import time
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from urllib.error import HTTPError, URLError

OVERPASS_URL = 'https://overpass-api.de/api/interpreter'
USER_AGENT = 'JHIII-Agent1-Discovery/0.1 (manual research; contact: info@jh3mining.com)'
# Bounding boxes: south, west, north, east. Approximate metro search windows.
MARKETS = {
    'huntsville-al': {'label': 'Huntsville, Alabama', 'bbox': (34.60, -86.80, 34.85, -86.45)},
    'nw-arkansas': {'label': 'Northwest Arkansas', 'bbox': (36.00, -94.30, 36.45, -93.95)},
    'greenville-sc': {'label': 'Greenville, South Carolina', 'bbox': (34.75, -82.55, 34.98, -82.25)},
}
# Only supported OSM tag/value combinations are queried. Additional industries
# can be added without changing the API or dashboard.
INDUSTRIES = {
    'hvac': {'label': 'HVAC', 'filters': [('craft', 'hvac'), ('craft', 'air_conditioning')]},
    'plumbing': {'label': 'Plumbing', 'filters': [('craft', 'plumber')]},
    'roofing': {'label': 'Roofing', 'filters': [('craft', 'roofer')]},
    'electrician': {'label': 'Electrician', 'filters': [('craft', 'electrician')]},
    'landscaping': {'label': 'Landscaping', 'filters': [('craft', 'gardener'), ('craft', 'landscaper')]},
    'auto_repair': {'label': 'Auto repair', 'filters': [('shop', 'car_repair')]},
    'dentist': {'label': 'Dentist', 'filters': [('amenity', 'dentist')]},
    'restaurant': {'label': 'Restaurant', 'filters': [('amenity', 'restaurant')]},
}
_cache = {}
CACHE_SECONDS = 900

class DiscoveryError(Exception):
    pass

def _query(market, industry):
    bbox = ','.join(str(v) for v in MARKETS[market]['bbox'])
    clauses = []
    for key, value in INDUSTRIES[industry]['filters']:
        clauses.append(f'  nwr["{key}"="{value}"]({bbox});')
    return '[out:json][timeout:18];\n(\n' + '\n'.join(clauses) + '\n);\nout center tags 120;'

def _website(tags):
    for key in ('website', 'contact:website'):
        val = (tags.get(key) or '').strip()
        if val and re.match(r'^https?://', val, re.I):
            return val[:500]
        if val and re.match(r'^[a-z0-9.-]+\.[a-z]{2,}(/.*)?$', val, re.I):
            return 'https://' + val[:492]
    return ''

def _candidate(item, market, industry):
    tags = item.get('tags') or {}
    name = (tags.get('name') or '').strip()
    if not name:
        return None
    osm_type, osm_id = item.get('type'), item.get('id')
    if osm_type not in ('node', 'way', 'relation') or not isinstance(osm_id, int):
        return None
    city = (tags.get('addr:city') or MARKETS[market]['label'].split(',')[0]).strip()
    state = {'huntsville-al':'Alabama', 'nw-arkansas':'Arkansas', 'greenville-sc':'South Carolina'}[market]
    # Northwest Arkansas is regional: never pretend every listing is in a city named 'Northwest Arkansas'.
    if market == 'nw-arkansas' and not tags.get('addr:city'):
        city = ''
    website = _website(tags)
    email = (tags.get('contact:email') or tags.get('email') or '').strip()[:250]
    if email and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
        email = ''
    source = f'https://www.openstreetmap.org/{osm_type}/{osm_id}'
    return {'name':name[:250], 'industry':INDUSTRIES[industry]['label'],
            'city':city[:120], 'state':state, 'website':website, 'email':email,
            'source':source, 'source_type':'OpenStreetMap',
            'notes':f'Public OSM listing: {source}. Contact information unverified.'}

def discover(market, industry, limit=20):
    if market not in MARKETS or industry not in INDUSTRIES:
        raise ValueError('Unsupported market or industry')
    if not isinstance(limit, int) or not 1 <= limit <= 50:
        raise ValueError('Limit must be between 1 and 50')
    key = (market, industry)
    cached = _cache.get(key)
    if cached and time.monotonic() - cached[0] < CACHE_SECONDS:
        results = cached[1]
    else:
        payload = urlencode({'data':_query(market, industry)}).encode('utf-8')
        req = Request(OVERPASS_URL, data=payload,
                      headers={'User-Agent':USER_AGENT, 'Content-Type':'application/x-www-form-urlencoded; charset=UTF-8'},
                      method='POST')
        try:
            with urlopen(req, timeout=23) as response:
                if response.status != 200:
                    raise DiscoveryError('Public data service unavailable; try later')
                raw = response.read(2_000_001)
                if len(raw) > 2_000_000:
                    raise DiscoveryError('Public data response too large')
                body = json.loads(raw)
        except (HTTPError, URLError, TimeoutError, ValueError, OSError) as exc:
            raise DiscoveryError('Public data service unavailable or rate-limited; try later') from exc
        results = []
        seen = set()
        for item in body.get('elements', []):
            c = _candidate(item, market, industry)
            if c and c['source'] not in seen:
                seen.add(c['source'])
                results.append(c)
        _cache[key] = (time.monotonic(), results)
    return results[:limit]
