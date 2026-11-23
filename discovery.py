"""Human-reviewed OpenStreetMap discovery. No database writes or emails.

Public Overpass instances are best-effort, not a guaranteed commercial SLA.
"""
import json
import ipaddress
import socket
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse
import logging
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)
OVERPASS_URLS = (
    'https://ovp.dresel.systems/api-na/interpreter',
    'https://overpass.private.coffee/api/interpreter',
    'https://overpass-api.de/api/interpreter',
)
USER_AGENT = 'JHIII-Agent1-Discovery/0.3 (manual research; contact: info@jh3mining.com)'
MARKETS = {
    'huntsville-al': {'label': 'Huntsville, Alabama', 'bbox': (34.60, -86.80, 34.85, -86.45)},
    'nw-arkansas': {'label': 'Northwest Arkansas', 'bbox': (36.00, -94.30, 36.45, -93.95)},
    'greenville-sc': {'label': 'Greenville, South Carolina', 'bbox': (34.75, -82.55, 34.98, -82.25)},
}
INDUSTRIES = {
    'hvac': {'label': 'HVAC', 'filters': [('craft', 'hvac'), ('craft', 'air_conditioning'), ('craft', 'heating'), ('shop', 'hvac')]},
    'plumbing': {'label': 'Plumbing', 'filters': [('craft', 'plumber'), ('shop', 'plumbing')]},
    'roofing': {'label': 'Roofing', 'filters': [('craft', 'roofer'), ('shop', 'roofing')]},
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
    # Retrieve all matched records; limit is applied after filtering and deduplication.
    return '[out:json][timeout:18];\n(\n' + '\n'.join(clauses) + '\n);\nout center tags;' 

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
    phone = (tags.get('contact:phone') or tags.get('phone') or '').strip()[:80]
    return {'name':name[:250], 'industry':INDUSTRIES[industry]['label'],
            'city':city[:120], 'state':state, 'website':website, 'email':email, 'phone':phone,
            'source':source, 'source_type':'OpenStreetMap',
            'notes':f'Public OSM listing: {source}. Phone: {phone or "not listed"}. Contact information unverified.'}

def _fetch(url, payload):
    req = Request(url, data=payload,
                  headers={'User-Agent': USER_AGENT,
                           'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'},
                  method='POST')
    with urlopen(req, timeout=20) as response:
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
    # Prefer records with useful contact details, without inventing missing information.
    results.sort(key=lambda c: (bool(c['website']) + bool(c['email']) + bool(c['phone'])), reverse=True)
    _cache[key] = (time.monotonic(), results)
    return results[:limit]


class _ContactParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.emails = []
        self.phones = []
        self.contact_links = []
    def handle_starttag(self, tag, attrs):
        if tag != 'a':
            return
        href = dict(attrs).get('href', '')
        if href.lower().startswith('mailto:'):
            self.emails.append(href[7:].split('?')[0])
        elif href.lower().startswith('tel:'):
            self.phones.append(href[4:].split('?')[0])
        elif 'contact' in href.lower() and len(self.contact_links) < 3:
            self.contact_links.append(href)

def _public_website(url):
    """Reject local/private destinations before any request; do not follow redirects."""
    parsed = urlparse(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None, 443):
        return False
    host = parsed.hostname.lower().rstrip('.')
    if host in ('localhost',) or host.endswith(('.local', '.internal', '.localhost')):
        return False
    try:
        addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        return bool(addresses) and all(ipaddress.ip_address(x[4][0]).is_global for x in addresses)
    except (OSError, ValueError):
        return False

def enrich_website(candidate):
    """Opt-in bounded public website lookup. Does not guess addresses or verify deliverability.

    Caller should only pass candidates returned by discover(); not arbitrary URLs.
    """
    result = dict(candidate)
    url = result.get('website') or ''
    if not url or not _public_website(url):
        result['enrichment_status'] = 'no_safe_https_website'
        return result
    try:
        # Disable redirects to avoid a public URL redirecting to an internal address.
        from urllib.request import build_opener, HTTPRedirectHandler
        class NoRedirect(HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None
        opener = build_opener(NoRedirect())
        req = Request(url, headers={'User-Agent': USER_AGENT, 'Accept': 'text/html'})
        with opener.open(req, timeout=5) as response:
            if 'text/html' not in response.headers.get('Content-Type', '').lower():
                result['enrichment_status'] = 'not_html'
                return result
            raw = response.read(100_001)
            if len(raw) > 100_000:
                result['enrichment_status'] = 'page_too_large'
                return result
            page = _ContactParser()
            page.feed(raw.decode('utf-8', errors='replace'))
        if not result.get('email'):
            for email in page.emails:
                if re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
                    result['email'] = email[:250]
                    result['notes'] += f' Email listed on business homepage: {url}.'
                    break
        if not result.get('phone') and page.phones:
            result['phone'] = page.phones[0][:80]
            result['notes'] += f' Phone listed on business homepage: {url}.'
        result['enrichment_status'] = 'homepage_checked'
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
        logger.info('Website enrichment skipped (%s)', type(exc).__name__)
        result['enrichment_status'] = 'website_unavailable'
    return result

def enrich_cached(market, industry, source):
    """Only enrich a candidate produced by this server's recent discovery cache."""
    if market not in MARKETS or industry not in INDUSTRIES:
        raise ValueError('Unsupported market or industry')
    cached = _cache.get((market, industry))
    if not cached or time.monotonic() - cached[0] > CACHE_SECONDS:
        raise ValueError('Search results expired; run discovery again')
    for candidate in cached[1]:
        if candidate['source'] == source:
            return enrich_website(candidate)
    raise ValueError('Candidate not found in recent search')
