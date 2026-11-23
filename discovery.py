"""Human-reviewed OpenStreetMap discovery. No database writes or emails.

Public Overpass instances are best-effort, not a guaranteed commercial SLA.
"""
import json
import logging
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)
OVERPASS_URLS = (
    'https://overpass-api.de/api/interpreter',
    'https://overpass.kumi.systems/api/interpreter',
)
USER_AGENT = 'JHIII-Agent1-Discovery/0.2 (manual research; contact: info@jh3mining.com)'
MARKETS = {
    'huntsville-al': {'label': 'Huntsville, Alabama', 'bbox': (34.60, -86.80, 34.85, -86.45)},
    'nw-arkansas': {'label': 'Northwest Arkansas', 'bbox': (36.00, -94.30, 36.45, -93.95)},
    'greenville-sc': {'label': 'Greenville, South Carolina', 'bbox': (34.75, -82.55, 34.98, -82.25)},
}
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
_failure_until = 0.0
COOLDOWN_SECONDS = 60

class DiscoveryError(Exception):
    pass

def _query(market, industry):
    bbox = ','.join(str(v) for v in MARKETS[market]['bbox'])
    clauses = [f'  nwr["{key}"="{value}"]({bbox});'
               for key, value in INDUSTRIES[industry]['filters']]
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

def _fetch(url, payload):
    req = Request(url, data=payload,
                  headers={'User-Agent': USER_AGENT,
                           'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'},
                  method='POST')
    with urlopen(req, timeout=25) as response:
        if response.status != 200:
            raise DiscoveryError(f'Upstream HTTP {response.status}')
        raw = response.read(2_000_001)
        if len(raw) > 2_000_000:
            raise DiscoveryError('Upstream response exceeded 2 MB')
        body = json.loads(raw)
        if not isinstance(body, dict) or not isinstance(body.get('elements'), list):
            raise DiscoveryError('Invalid upstream response structure')
        return body

def discover(market, industry, limit=20):
    global _failure_until
    if market not in MARKETS or industry not in INDUSTRIES:
        raise ValueError('Unsupported market or industry')
    if not isinstance(limit, int) or not 1 <= limit <= 50:
        raise ValueError('Limit must be between 1 and 50')
    key = (market, industry)
    cached = _cache.get(key)
    if cached and time.monotonic() - cached[0] < CACHE_SECONDS:
        return cached[1][:limit]
    if time.monotonic() < _failure_until:
        raise DiscoveryError('Public data service temporarily unavailable; wait one minute before retrying')

    payload = urlencode({'data': _query(market, industry)}).encode('utf-8')
    body = None
    for url in OVERPASS_URLS:
        try:
            body = _fetch(url, payload)
            logger.info('Discovery provider succeeded: %s', url)
            break
        except HTTPError as exc:
            logger.warning('Discovery provider HTTP %s: %s', exc.code, url)
            if exc.code in (429, 403):
                # Respect throttling/denial rather than switching providers to evade it.
                _failure_until = time.monotonic() + COOLDOWN_SECONDS
                raise DiscoveryError('Public data provider refused or rate-limited the request; retry later') from exc
        except (URLError, TimeoutError, OSError, ValueError, DiscoveryError) as exc:
            logger.warning('Discovery provider failed (%s): %s: %s',
                           type(exc).__name__, url, str(exc)[:250])
    if body is None:
        _failure_until = time.monotonic() + COOLDOWN_SECONDS
        raise DiscoveryError('Public data service unavailable; check Render logs for provider details')

    results = []
    seen = set()
    for item in body['elements']:
        if not isinstance(item, dict):
            continue
        candidate = _candidate(item, market, industry)
        if candidate and candidate['source'] not in seen:
            seen.add(candidate['source'])
            results.append(candidate)
    _cache[key] = (time.monotonic(), results)
    return results[:limit]
