"""Conservative public-web business research. No CAPTCHA bypass or invented contacts."""
import re, json, html, urllib.parse, urllib.request, xml.etree.ElementTree as ET
import unicodedata
from html.parser import HTMLParser
from datetime import datetime, timezone

UA='JH3AgencyResearch/1.0 (public business website review)'
BLOCK={'facebook.com','instagram.com','linkedin.com','yelp.com','yellowpages.com','angi.com','bbb.org','mapquest.com','google.com','bing.com','youtube.com','tiktok.com','nextdoor.com','chamberofcommerce.com','manta.com','homeadvisor.com','thumbtack.com','porch.com','buildzoom.com','reddit.com','hacr.alabama.gov','hacr.igovsolution.net'}
class Extract(HTMLParser):
 def __init__(self):super().__init__();self.links=[];self.text=[];self.title='';self._title=False;self.forms=0;self.meta=[]
 def handle_starttag(self,t,a):
  d=dict(a)
  if t=='a':self.links.append((d.get('href',''),d.get('aria-label','')))
  if t=='form':self.forms+=1
  if t=='title':self._title=True
  if t=='meta':self.meta.append(d)
 def handle_endtag(self,t):
  if t=='title':self._title=False
 def handle_data(self,data):
  if self._title:self.title+=data
  self.text.append(data)
def clean_url(url):
 """Remove invisible copy/paste characters and make a URL HTTP-safe."""
 if not isinstance(url,str):raise ValueError('Website URL must be text')
 url=''.join(c for c in url.strip() if unicodedata.category(c)!='Cf')
 parts=urllib.parse.urlsplit(url)
 if parts.scheme.lower() not in ('http','https') or not parts.hostname:
  raise ValueError('Website must be a valid http:// or https:// URL')
 if parts.username or parts.password:raise ValueError('Website URL cannot contain credentials')
 if any(c in parts.netloc for c in '\r\n\t '):raise ValueError('Invalid website host')
 try:
  host=parts.hostname.encode('idna').decode('ascii')
  port=parts.port
 except (UnicodeError,ValueError) as exc:raise ValueError('Invalid website host or port') from exc
 if ':' in host and not host.startswith('['):host='['+host+']'
 if port is not None:host+=':'+str(port)
 path=urllib.parse.quote(urllib.parse.unquote(parts.path),safe="/%:@!$&'()*+,;=-._~")
 query=urllib.parse.quote(urllib.parse.unquote(parts.query),safe="/%?:@!$&'()*+,;=-._~")
 return urllib.parse.urlunsplit((parts.scheme.lower(),host,path,query,''))
def fetch(url,limit=350000):
 url=clean_url(url)
 req=urllib.request.Request(url,headers={'User-Agent':UA,'Accept':'text/html,application/rss+xml,application/xml'})
 with urllib.request.urlopen(req,timeout=9) as r:
  typ=r.headers.get('Content-Type','')
  if not any(x in typ for x in ('text/html','xml','rss')):raise ValueError('Not an HTML page')
  return r.read(limit).decode('utf-8','replace'),r.geturl()
def domain(url):
 try:return (urllib.parse.urlparse(url).hostname or '').lower().removeprefix('www.')
 except Exception:return ''
# Search results are untrusted candidates, never verified business identities.
STOPWORDS={'llc','inc','corp','corporation','company','co','the','and','of','services','service','heating','cooling','air','conditioning','hvac','mechanical','contractors','contractor','dba'}
REJECT={'wikipedia.org','albright.edu','albrightsupply.com','albrightinternational.com'}
def tokens(s):
 return {x for x in re.findall(r'[a-z0-9]+',html.unescape(s).lower()) if len(x)>2 and x not in STOPWORDS}
def query_variants(name):
 clean=html.unescape(name).replace('&amp;','&').strip()
 alt=re.sub(r'\b(?:LLC|INC|CORP|CORPORATION)\b\.?','',clean,flags=re.I).strip(' ,.')
 return [f'"{clean}" "Alabama" HVAC',f'"{alt}" heating cooling Alabama',f'{alt} Alabama HVAC official website']
def candidate_score(name,title,url):
 host=domain(url)
 if not host or any(host==b or host.endswith('.'+b) for b in BLOCK|REJECT):return -100,['Excluded directory or unrelated site']
 name_tokens=tokens(name);found=tokens(title+' '+host.replace('.',' '))
 overlap=name_tokens & found
 # Never accept a single shared surname as evidence of company identity.
 if not overlap:return -100,['No distinctive company-name match']
 score=15*len(overlap)
 reasons=['Name tokens matched: '+', '.join(sorted(overlap))]
 title_lower=title.lower()
 if re.search(r'heat|cool|hvac|air condition|furnace|mechanical',title_lower+' '+host):score+=25;reasons.append('HVAC industry mentioned')
 if 'alabama' in title_lower or re.search(r'\b(?:al|birmingham|huntsville|mobile|montgomery|tuscaloosa)\b',title_lower):score+=15;reasons.append('Alabama geography mentioned')
 if len(overlap)<2 and len(name_tokens)>=2:score-=25;reasons.append('Insufficient company-name overlap')
 return score,reasons
def search_candidates(name):
 """Multi-query discovery with conservative rejection; candidates always need identity verification."""
 out={};errors=[]
 for query in query_variants(name):
  try:
   body,_=fetch('https://www.bing.com/search?format=rss&q='+urllib.parse.quote(query),150000)
   root=ET.fromstring(body)
   for item in root.findall('.//item')[:15]:
    url=item.findtext('link','').strip();title=html.unescape(item.findtext('title',''))[:180]
    if not url.startswith('https://'):continue
    score,reasons=candidate_score(name,title,url)
    if score<30:continue
    host=domain(url)
    previous=out.get(host)
    if previous is None or score>previous['match_score']:
     out[host]={'url':url,'title':title,'match_score':score,'match_status':'NEEDS_REVIEW','reasons':reasons}
  except Exception:errors.append('Public search source unavailable for one query')
 candidates=sorted(out.values(),key=lambda x:-x['match_score'])[:6]
 return candidates,('Some public searches were unavailable.' if errors else None)

def identity_evidence(name,url):
 """Fetch homepage and classify cautiously; no automated VERIFIED status."""
 host=domain(url)
 if not host or any(host==b or host.endswith('.'+b) for b in BLOCK|REJECT):
  return {'status':'REJECTED','reasons':['Unrelated or directory domain']}
 try:
  body,final=fetch(url,250000)
  if domain(final)!=host:return {'status':'NEEDS_REVIEW','reasons':['Redirected to another domain']}
  parser=Extract();parser.feed(body)
  content=' '.join(parser.text)[:60000]
  content=html.unescape(re.sub(r'\s+',' ',content))
  hay=(parser.title+' '+content[:12000]).lower()
  name_tokens=tokens(name)
  title_tokens=tokens(parser.title+' '+host.replace('.',' '))
  overlap=name_tokens & title_tokens
  industry=bool(re.search(r'heat|cool|hvac|air condition|furnace|mechanical|refrigerat',hay))
  geography=bool(re.search(r'\balabama\b|\bAL\s*\d{5}\b|\bbirmingham\b|\bhuntsville\b|\bmobile,?\s*al\b|\bmontgomery\b',hay,re.I))
  reasons=[]
  if overlap:reasons.append('Name matched in page title or domain: '+', '.join(sorted(overlap)))
  if industry:reasons.append('HVAC-related services mentioned on homepage')
  if geography:reasons.append('Alabama location signal on homepage')
  if not industry or not overlap:return {'status':'REJECTED','reasons':reasons+['Missing company-name or HVAC evidence']}
  return {'status':'NEEDS_REVIEW','reasons':reasons+(['Alabama location not confirmed'] if not geography else [])}
 except Exception:
  return {'status':'NEEDS_REVIEW','reasons':['Homepage could not be independently checked']}

def audit_site(url):
 url=clean_url(url)
 if not url.startswith('https://') and not url.startswith('http://'):raise ValueError('Website must start with http:// or https://')
 p=urllib.parse.urlparse(url)
 if not p.hostname or p.username or p.password:raise ValueError('Invalid website URL')
 # prevent private/internal network access; hostname check is supplemented by redirect checks
 import socket,ipaddress
 for addr in socket.getaddrinfo(p.hostname,None):
  ip=ipaddress.ip_address(addr[4][0])
  if not ip.is_global:raise ValueError('Private or non-public website address blocked')
 body,final=fetch(url)
 if domain(final)!=domain(url):raise ValueError('Website redirected to a different domain; review manually')
 parser=Extract();parser.feed(body)
 text=' '.join(parser.text);text=re.sub(r'\s+',' ',text)
 emails=sorted(set(x.lower() for x in re.findall(r'\b[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}\b',body,re.I)))
 emails=[e for e in emails if not e.endswith(('.png','.jpg','.webp','.svg'))][:8]
 phones=sorted(set(re.findall(r'(?<!\d)(?:\+1[\s.\-]?)?\(?\d{3}\)?[\s.\-]\d{3}[\s.\-]\d{4}(?!\d)',text)))[:8]
 links=[urllib.parse.urljoin(final,u) for u,_ in parser.links if u]
 social={k:sorted(set(u for u in links if k+'.com' in domain(u)))[:3] for k in ('facebook','instagram','linkedin','youtube','tiktok')}
 booking=[u for u in links if re.search(r'book|schedul|appointment|request.service',u,re.I)][:5]
 contact=[u for u in links if re.search(r'contact|quote|estimate',u,re.I)][:5]
 signals={'contact_form':parser.forms>0,'booking_link':bool(booking),'contact_link':bool(contact),'mobile_viewport':bool(re.search(r'name=["\']viewport',body,re.I)),'structured_data':bool(re.search(r'application/ld\+json',body,re.I)),'social_profiles_linked':sum(bool(v) for v in social.values()),'phone_published':bool(phones),'email_published':bool(emails)}
 findings=[]
 if not booking:findings.append('No booking link detected on homepage; check contact and scheduling pages manually')
 if not parser.forms:findings.append('No HTML form detected on homepage; embedded widgets or other pages may exist')
 if not phones:findings.append('No phone number detected on homepage; inspect contact page')
 if not social or not any(social.values()):findings.append('No social profile links detected on homepage; this does not prove inactivity')
 return {'website':final,'page_title':parser.title[:180],'phones':phones,'emails':emails,'social':social,'booking_links':booking,'contact_links':contact,'signals':signals,'findings':findings,'checked_at':datetime.now(timezone.utc).isoformat(timespec='seconds'),'source_url':final,'scope':'homepage only; no Google review, ad-spend, call-answering or revenue verification'}
