"""Conservative public-web business research for JH III Agent 1.

Search candidates are not verified businesses. No CAPTCHA bypass, invented contacts,
email sending, or automatic lead import. Standard-library only.
"""
import re
import json
import html
import urllib.parse
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
import unicodedata
import ipaddress
import socket
from html.parser import HTMLParser
from datetime import datetime, timezone

UA = 'JH3AgencyResearch/1.1 (public business website review)'
BLOCK = {
    'facebook.com', 'instagram.com', 'linkedin.com', 'yelp.com',
    'yellowpages.com', 'angi.com', 'bbb.org', 'mapquest.com',
    'google.com', 'bing.com', 'youtube.com', 'tiktok.com',
    'nextdoor.com', 'chamberofcommerce.com', 'manta.com',
    'homeadvisor.com', 'thumbtack.com', 'porch.com', 'buildzoom.com',
    'reddit.com', 'hacr.alabama.gov', 'hacr.igovsolution.net',
}
REJECT = {'wikipedia.org', 'albright.edu', 'albrightsupply.com', 'albrightinternational.com'}
STOPWORDS = {
    'llc', 'inc', 'corp', 'corporation', 'company', 'co', 'the', 'and',
    'of', 'services', 'service', 'heating', 'cooling', 'air', 'conditioning',
    'hvac', 'mechanical', 'contractors', 'contractor', 'dba', 'pros', 'associated', 'advanced', 'central', 'general', 'quality', 'best', 'professional',
}
HVAC_RE = re.compile(r'heat(?:ing)?|cool(?:ing)?|hvac|air[ -]?condition|furnace|mechanical|refrigerat', re.I)
AL_RE = re.compile(r'\balabama\b|\bAL\s*\d{5}\b|\bbirmingham\b|\bhuntsville\b|\bmontgomery\b|\btuscaloosa\b|\bmobile,?\s*al\b', re.I)


class Extract(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.text = []
        self.title = ''
        self._title = False
        self.forms = 0
        self.meta = []

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if tag == 'a':
            self.links.append((d.get('href', ''), d.get('aria-label', '')))
        if tag == 'form':
            self.forms += 1
        if tag == 'title':
            self._title = True
        if tag == 'meta':
            self.meta.append(d)

    def handle_endtag(self, tag):
        if tag == 'title':
            self._title = False

    def handle_data(self, data):
        if self._title:
            self.title += data
        self.text.append(data)


def clean_url(url):
    """Normalize a public HTTP(S) URL, rejecting credentials and malformed hosts."""
    if not isinstance(url, str):
        raise ValueError('Website URL must be text')
    url = ''.join(c for c in url.strip() if unicodedata.category(c) != 'Cf')
    parts = urllib.parse.urlsplit(url)
    if parts.scheme.lower() not in ('http', 'https') or not parts.hostname:
        raise ValueError('Website must be a valid http:// or https:// URL')
    if parts.username or parts.password:
        raise ValueError('Website URL cannot contain credentials')
    if any(c in parts.netloc for c in '\r\n\t '):
        raise ValueError('Invalid website host')
    try:
        host = parts.hostname.encode('idna').decode('ascii')
        port = parts.port
    except (UnicodeError, ValueError) as exc:
        raise ValueError('Invalid website host or port') from exc
    if ':' in host and not host.startswith('['):
        host = '[' + host + ']'
    if port is not None:
        host += ':' + str(port)
    path = urllib.parse.quote(urllib.parse.unquote(parts.path), safe="/%:@!$&'()*+,;=-._~")
    query = urllib.parse.quote(urllib.parse.unquote(parts.query), safe="/%?:@!$&'()*+,;=-._~")
    return urllib.parse.urlunsplit((parts.scheme.lower(), host, path, query, ''))


def domain(url):
    try:
        return (urllib.parse.urlsplit(url).hostname or '').lower().removeprefix('www.')
    except (ValueError, TypeError):
        return ''


def _blocked(host, blocked):
    return any(host == item or host.endswith('.' + item) for item in blocked)


def _public_host(url):
    """Deny private/internal IPs, local hostnames and non-web ports."""
    parts = urllib.parse.urlsplit(clean_url(url))
    host = parts.hostname
    if not host or host.lower() == 'localhost' or host.lower().endswith(('.localhost', '.local', '.internal')):
        raise ValueError('Non-public website host blocked')
    if parts.port not in (None, 80, 443):
        raise ValueError('Non-standard website port blocked')
    try:
        ip = ipaddress.ip_address(host)
        if not ip.is_global:
            raise ValueError('Non-public website address blocked')
        return
    except ValueError as exc:
        # A valid IP which is not global must be rejected; otherwise resolve DNS.
        try:
            ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            raise exc
    addresses = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    if not addresses:
        raise ValueError('Website DNS returned no addresses')
    for addr in addresses:
        ip = ipaddress.ip_address(addr[4][0])
        if not ip.is_global:
            raise ValueError('Non-public website address blocked')


class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _public_host(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(url, limit=350000):
    """Fetch only public HTTP(S) HTML/XML, validating every redirect target.

    DNS rebinding between resolution and connection is not fully eliminated by
    urllib; for hostile internet-wide crawling use network-level egress controls.
    """
    url = clean_url(url)
    _public_host(url)
    req = urllib.request.Request(url, headers={
        'User-Agent': UA,
        'Accept': 'text/html,application/rss+xml,application/xml',
    })
    opener = urllib.request.build_opener(_SafeRedirect())
    with opener.open(req, timeout=9) as response:
        final = clean_url(response.geturl())
        _public_host(final)
        content_type = response.headers.get('Content-Type', '').lower()
        if not any(x in content_type for x in ('text/html', 'xml', 'rss')):
            raise ValueError('Not an HTML/XML page')
        return response.read(limit).decode('utf-8', 'replace'), final


def tokens(value):
    return {
        term for term in re.findall(r'[a-z0-9]+', html.unescape(value).lower())
        if len(term) > 2 and term not in STOPWORDS
    }


def query_variants(name):
    clean = html.unescape(name).replace('&amp;', '&').strip()
    alt = re.sub(r'\b(?:LLC|INC|CORP|CORPORATION)\b\.?', '', clean, flags=re.I).strip(' ,.')
    return list(dict.fromkeys([
        f'"{clean}" Alabama',
        f'"{alt}" HVAC Alabama',
        f'"{alt}" official website',
    ]))


def candidate_score(name, title, url):
    """Rank plausible sites, never declare identity verification from search alone."""
    host = domain(url)
    if not host:
        return -100, ['Invalid website host']
    if _blocked(host, BLOCK | REJECT):
        return -100, ['Directory, social network or excluded site']
    wanted = tokens(name)
    found = tokens(title + ' ' + host.replace('.', ' '))
    overlap = wanted & found
    if not overlap:
        return 0, ['No distinctive company-name term in result title/domain']
    score = 20 * len(overlap)
    reasons = ['Matching name terms: ' + ', '.join(sorted(overlap))]
    if HVAC_RE.search(title + ' ' + host):
        score += 20
        reasons.append('HVAC industry signal in search result')
    if AL_RE.search(title):
        score += 10
        reasons.append('Alabama location signal in search result')
    if len(overlap) >= 2:
        score += 20
        reasons.append('Multiple distinctive name terms matched')
    if len(wanted) >= 2 and len(overlap) == 1:
        reasons.append('Only one distinctive name term matched; requires stronger site evidence')
    if not HVAC_RE.search(title + ' ' + host):
        return -100, ['No HVAC evidence in search title/domain']
    if len(wanted) >= 2 and len(overlap) < 2:
        return 0, ['Insufficient distinctive name overlap']
    return score, reasons


def search_candidates_detailed(name):
    """Return candidate sites plus useful counts and safe rejection samples."""
    out = {}
    diagnostics = {
        'queries': [], 'raw_results': 0, 'https_results': 0,
        'excluded': 0, 'low_score': 0, 'candidate_count': 0,
        'provider_errors': [], 'rejection_reasons': {}, 'rejection_samples': [],
    }
    for query in query_variants(name):
        item = {'query': query, 'result_count': 0, 'error': None}
        try:
            body, _ = fetch('https://www.bing.com/search?format=rss&q=' + urllib.parse.quote(query), 150000)
            root = ET.fromstring(body)
            entries = root.findall('.//item')[:15]
            item['result_count'] = len(entries)
            diagnostics['raw_results'] += len(entries)
            for entry in entries:
                url = entry.findtext('link', '').strip()
                title = html.unescape(entry.findtext('title', ''))[:180]
                if not url.startswith('https://'):
                    continue
                diagnostics['https_results'] += 1
                score, reasons = candidate_score(name, title, url)
                if score < 0:
                    diagnostics['excluded'] += 1
                    reason = reasons[0]
                elif score < 20:
                    diagnostics['low_score'] += 1
                    reason = reasons[0] if reasons else 'Insufficient search-result evidence'
                else:
                    host = domain(url)
                    previous = out.get(host)
                    if previous is None or score > previous['match_score']:
                        out[host] = {
                            'url': url, 'title': title, 'match_score': score,
                            'match_status': 'NEEDS_REVIEW', 'reasons': reasons,
                        }
                    continue
                diagnostics['rejection_reasons'][reason] = diagnostics['rejection_reasons'].get(reason, 0) + 1
                if len(diagnostics['rejection_samples']) < 8:
                    diagnostics['rejection_samples'].append({
                        'title': title, 'url': url, 'reason': reason,
                    })
        except Exception as exc:
            item['error'] = type(exc).__name__
            diagnostics['provider_errors'].append(type(exc).__name__)
        diagnostics['queries'].append(item)
    candidates = sorted(out.values(), key=lambda x: -x['match_score'])[:6]
    diagnostics['candidate_count'] = len(candidates)
    if len(diagnostics['provider_errors']) == len(diagnostics['queries']):
        status = 'SEARCH_UNAVAILABLE'
    elif not diagnostics['raw_results']:
        status = 'NO_SEARCH_RESULTS'
    elif not candidates:
        status = 'NO_CONFIDENT_MATCH'
    else:
        status = 'CANDIDATES_FOUND'
    return {'status': status, 'candidates': candidates, 'diagnostics': diagnostics}


def search_candidates(name):
    result = search_candidates_detailed(name)
    warning = 'Search provider unavailable for one or more queries' if result['diagnostics']['provider_errors'] else None
    return result['candidates'], warning


def _same_site(a, b):
    return domain(a) == domain(b)


def _business_identity(name, url, title, text):
    wanted = tokens(name)
    observed = tokens(title + ' ' + domain(url).replace('.', ' ') + ' ' + text[:12000])
    overlap = wanted & observed
    industry = bool(HVAC_RE.search(text))
    location = bool(AL_RE.search(text))
    strong_name = len(overlap) >= 2 or (
        len(wanted) == 1 and len(overlap) == 1 and len(next(iter(wanted))) >= 6
    )
    reasons = []
    if overlap:
        reasons.append('Company-name terms on site: ' + ', '.join(sorted(overlap)))
    if industry:
        reasons.append('HVAC trade found on website')
    if location:
        reasons.append('Alabama geography found on website')
    if not strong_name:
        reasons.append('Business name insufficiently corroborated')
    if not industry:
        reasons.append('HVAC services not corroborated')
    if not location:
        reasons.append('Alabama location not corroborated')
    # No auto-VERIFIED: public license-to-website linkage needs separate evidence.
    return {
        'status': 'NEEDS_REVIEW' if strong_name and industry and location else 'UNCONFIRMED',
        'reasons': reasons, 'name_match': strong_name,
        'industry_match': industry, 'location_match': location,
    }


def _site_pages(body, base_url):
    parser = Extract()
    parser.feed(body)
    candidates = []
    for href, label in parser.links:
        if not href:
            continue
        url = urllib.parse.urljoin(base_url, href)
        if not _same_site(base_url, url):
            continue
        path = urllib.parse.urlsplit(url).path.lower()
        if re.search(r'contact|about|location|service-area', path + ' ' + label.lower()):
            candidates.append(url)
    return list(dict.fromkeys(candidates))[:2]


def identity_evidence(name, url):
    """Review homepage and up to two same-domain contact/about pages."""
    try:
        url = clean_url(url)
        if _blocked(domain(url), BLOCK | REJECT):
            return {'status': 'REJECTED', 'reasons': ['Excluded directory or social site']}
        body, final = fetch(url, 250000)
        if not _same_site(url, final):
            return {
                'status': 'NEEDS_REVIEW',
                'reasons': ['Redirected to different domain'],
                'requested_url': url, 'final_url': final,
            }
        parser = Extract()
        parser.feed(body)
        content = html.unescape(re.sub(r'\s+', ' ', ' '.join(parser.text)))[:20000]
        inspected = [final]
        for extra in _site_pages(body, final):
            if extra == final:
                continue
            try:
                extra_body, extra_final = fetch(extra, 150000)
                if not _same_site(final, extra_final):
                    continue
                extra_parser = Extract()
                extra_parser.feed(extra_body)
                content += ' ' + html.unescape(' '.join(extra_parser.text))[:12000]
                inspected.append(extra_final)
            except Exception:
                continue
        evidence = _business_identity(name, final, parser.title, parser.title + ' ' + content)
        evidence.update({
            'requested_url': url, 'final_url': final,
            'pages_inspected': inspected,
        })
        return evidence
    except Exception as exc:
        return {
            'status': 'UNCONFIRMED',
            'reasons': ['Website could not be checked: ' + type(exc).__name__],
        }


_PLACEHOLDER_USERS = {'user', 'example', 'test', 'name', 'yourname', 'email', 'username', 'admin@example', 'john.doe', 'jane.doe'}
_PLACEHOLDER_DOMAINS = {'example.com', 'example.org', 'example.net', 'domain.com', 'test.com', 'localhost', 'email.com'}


def _realistic_email(value, site_host):
    value = value.strip().lower().strip('.,;:')
    if '@' not in value:
        return False
    local, host = value.rsplit('@', 1)
    if host in _PLACEHOLDER_DOMAINS or local in _PLACEHOLDER_USERS:
        return False
    if any(x in local for x in ('placeholder', 'your-email', 'youremail', 'sample')):
        return False
    if host.endswith(('.png', '.jpg', '.webp', '.svg', '.gif')):
        return False
    return True


def _booking_link(href, label, site_host):
    host = domain(href)
    if _blocked(host, {'facebook.com', 'instagram.com', 'linkedin.com', 'youtube.com', 'tiktok.com'}):
        return False
    parsed = urllib.parse.urlsplit(href)
    route = urllib.parse.unquote(parsed.path + ' ' + parsed.query).lower()
    return bool(re.search(r'(?:^|[\W_])(book(?:ing)?|schedul(?:e|ing)|appointment|request[\W_]*service)(?:$|[\W_])', route + ' ' + label.lower()))


def qualify_candidates(name, license_number, license_status='ACTIVE', max_candidates=6):
    if license_status.upper() != 'ACTIVE':
        return {'license_number': license_number, 'status': 'INELIGIBLE_LICENSE', 'candidates': []}
    candidates, error = search_candidates(name)
    reviewed = []
    for candidate in candidates[:max_candidates]:
        evidence = identity_evidence(name, candidate['url'])
        reviewed.append({**candidate, 'identity': evidence})
    return {
        'license_number': license_number, 'business_name': name,
        'status': 'REVIEW_REQUIRED', 'candidates': reviewed,
        'search_warning': error,
    }


def audit_site(url):
    """Inspect public homepage only; no unsupported marketing-performance claims."""
    url = clean_url(url)
    body, final = fetch(url)
    if not _same_site(url, final):
        raise ValueError('Website redirected to a different domain; review manually')
    parser = Extract()
    parser.feed(body)
    text = re.sub(r'\s+', ' ', ' '.join(parser.text))
    emails = sorted(set(x.lower() for x in re.findall(r'\b[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}\b', body, re.I)))
    emails = [e for e in emails if _realistic_email(e, domain(final))][:8]
    phones = sorted(set(re.findall(r'(?<!\d)(?:\+1[\s.\-]?)?\(?\d{3}\)?[\s.\-]\d{3}[\s.\-]\d{4}(?!\d)', text)))[:8]
    links = [(urllib.parse.urljoin(final, u), label) for u, label in parser.links if u]
    social = {
        key: sorted(set(u for u, _ in links if _blocked(domain(u), {key + '.com'})))[:3]
        for key in ('facebook', 'instagram', 'linkedin', 'youtube', 'tiktok')
    }
    booking = list(dict.fromkeys(u for u, label in links if _booking_link(u, label, domain(final))))[:5]
    contact = list(dict.fromkeys(u for u, label in links if re.search(r'contact|quote|estimate', urllib.parse.urlsplit(u).path + ' ' + label, re.I)))[:5]
    signals = {
        'contact_form': parser.forms > 0,
        'booking_link': bool(booking), 'contact_link': bool(contact),
        'mobile_viewport': bool(re.search(r'name=["\']viewport', body, re.I)),
        'structured_data': bool(re.search(r'application/ld\+json', body, re.I)),
        'social_profiles_linked': sum(bool(v) for v in social.values()),
        'phone_published': bool(phones), 'email_published': bool(emails),
    }
    findings = []
    if not booking:
        findings.append('No booking link detected on homepage; check contact and scheduling pages manually')
    if not parser.forms:
        findings.append('No HTML form detected on homepage; embedded widgets or other pages may exist')
    if not phones:
        findings.append('No phone number detected on homepage; inspect contact page')
    if not any(social.values()):
        findings.append('No social profile links detected on homepage; this does not prove inactivity')
    return {
        'website': final, 'page_title': parser.title[:180],
        'phones': phones, 'emails': emails, 'social': social,
        'booking_links': booking, 'contact_links': contact,
        'signals': signals, 'findings': findings,
        'checked_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'source_url': final,
        'scope': 'homepage only; public contacts unverified; no Google review, ad-spend, call-answering or revenue verification',
    }


# Four-category online presence discovery (no paid API).
"""Evidence-first business presence classification; no paid APIs or fabricated matches."""
import re, html, urllib.parse, xml.etree.ElementTree as ET


SOCIAL={'facebook.com','instagram.com','linkedin.com','tiktok.com','youtube.com','nextdoor.com'}
DIRECTORY={'yelp.com','yellowpages.com','bbb.org','angi.com','manta.com','chamberofcommerce.com','mapquest.com','buildzoom.com','homeadvisor.com','thumbtack.com','porch.com','google.com'}
EXCLUDE={'bing.com','wikipedia.org','merriam-webster.com','dictionary.cambridge.org','microsoft.com','support.microsoft.com','associatedbank.com','reddit.com','amazon.com'}
GENERIC={'advanced','associated','central','general','american','united','quality','best','first','professional','total','all','solutions','services','service','group','holding','holdings','property','management','company','inc','llc','corp','the','and','of','alabama','heating','cooling','air','conditioning','mechanical','contractor','contractors','hvac','pros','electric'}

def kind(url):
 host=domain(url)
 if not host or any(host==x or host.endswith('.'+x) for x in EXCLUDE):return 'excluded'
 if any(host==x or host.endswith('.'+x) for x in SOCIAL):return 'social'
 if any(host==x or host.endswith('.'+x) for x in DIRECTORY):return 'directory'
 return 'website'

def identity_terms(name):
 return {w for w in tokens(name) if w not in GENERIC}

def name_support(name,title,url):
 wanted=identity_terms(name)
 observed=set(re.findall(r'[a-z0-9]+',html.unescape(title+' '+urllib.parse.unquote(urllib.parse.urlsplit(url).path)+' '+domain(url)).lower()))
 if not wanted:return False, 'Business name too generic to verify from search title'
 if len(wanted)==1:return next(iter(wanted)) in observed, 'Distinctive name term in listing' if wanted<=observed else 'Distinctive name term missing'
 matched=wanted & observed
 return len(matched)>=2 or (len(matched)==1 and len(wanted)==2 and max(map(len,matched))>=7), 'Name terms: '+', '.join(sorted(matched))

def search_queries(name):
 cleaned=re.sub(r'\b(?:LLC|INC|CORP|CORPORATION)\b\.?','',name,flags=re.I).strip(' ,.')
 return [f'"{cleaned}" Alabama HVAC', f'"{cleaned}" Alabama Facebook Yelp heating cooling']

def discover_presence(name,license_number):
 results={};diagnostics={'queries':[],'raw_results':0,'provider_errors':[],'excluded':0,'name_mismatch':0}
 for query in search_queries(name):
  try:
   raw,_=fetch('https://www.bing.com/search?format=rss&q='+urllib.parse.quote(query),150000)
   entries=ET.fromstring(raw).findall('.//item')[:15]
   diagnostics['raw_results']+=len(entries)
   diagnostics['queries'].append({'query':query,'results':len(entries)})
   for e in entries:
    url=e.findtext('link','').strip();title=html.unescape(e.findtext('title',''))[:200]
    category=kind(url)
    if category=='excluded' or not url.startswith('https://'):
     diagnostics['excluded']+=1;continue
    matches,reason=name_support(name,title,url)
    if not matches:
     diagnostics['name_mismatch']+=1;continue
    # A search result is only a candidate, never independently verified.
    if url not in results:results[url]={'url':url,'title':title,'kind':category,'status':'CANDIDATE','reasons':[reason],'source':'Bing search result'}
  except Exception as exc:
   diagnostics['provider_errors'].append(type(exc).__name__)
 candidates=list(results.values())[:10]
 websites=[x for x in candidates if x['kind']=='website'][:2]
 for item in websites:
  evidence=identity_evidence(name,item['url'])
  item['identity']=evidence
  item['status']='REVIEW_REQUIRED' if evidence['status']=='NEEDS_REVIEW' else 'UNCONFIRMED'
 # Social/directory listing pages are not reliably readable by automated clients.
 # Keep these as review candidates; never claim verified business identity.
 for item in candidates:
  if item['kind']!='website':item['reasons'].append('Search title only; open listing to verify Alabama HVAC identity')
 reviewed=[x for x in candidates if x['kind']=='website' and x['status']=='REVIEW_REQUIRED']
 if reviewed:classification='OFFICIAL_WEBSITE_CANDIDATE'
 elif any(x['kind']=='social' for x in candidates):classification='SOCIAL_MEDIA_CANDIDATE'
 elif any(x['kind']=='directory' for x in candidates):classification='DIRECTORY_CANDIDATE'
 else:classification='IDENTITY_UNCONFIRMED'
 return {'license_number':license_number,'business_name':name,'classification':classification,'presence':candidates,'diagnostics':diagnostics,'verified':False,'notice':'Candidate classification, not independent verification. Review source before importing.'}
