"""Conservative public-web business research. No CAPTCHA bypass or invented contacts."""
import re, json, html, urllib.parse, urllib.request, xml.etree.ElementTree as ET
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
def fetch(url,limit=350000):
 req=urllib.request.Request(url,headers={'User-Agent':UA,'Accept':'text/html,application/rss+xml,application/xml'})
 with urllib.request.urlopen(req,timeout=9) as r:
  typ=r.headers.get('Content-Type','')
  if not any(x in typ for x in ('text/html','xml','rss')):raise ValueError('Not an HTML page')
  return r.read(limit).decode('utf-8','replace'),r.geturl()
def domain(url):
 try:return (urllib.parse.urlparse(url).hostname or '').lower().removeprefix('www.')
 except Exception:return ''
def search_candidates(name):
 """Best-effort free public RSS lookup; unavailable is a normal result."""
 query=urllib.parse.quote('"'+name+'" Alabama HVAC heating cooling official website')
 try:
  body,_=fetch('https://www.bing.com/search?format=rss&q='+query,150000)
  root=ET.fromstring(body)
  out=[]
  for item in root.findall('.//item')[:12]:
   url=item.findtext('link','').strip();host=domain(url)
   if not url.startswith('https://') or not host or any(host==b or host.endswith('.'+b) for b in BLOCK):continue
   out.append({'url':url,'title':item.findtext('title','')[:180]})
  return out[:6],None
 except Exception as e:return [],'Public search unavailable; supply and verify a company website manually.'
def audit_site(url):
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
