import csv, io, os, re, sqlite3, json
from datetime import datetime, timezone
from pathlib import Path
from fastapi import FastAPI, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from html import escape

ROOT=Path(__file__).parent
DB=Path(os.getenv('JH3_DB',str(ROOT/'agency.db')))
app=FastAPI(title='JH III Three-Agent Agency',version='1.0')

def connect():
 c=sqlite3.connect(DB);c.row_factory=sqlite3.Row;return c

def init():
 with connect() as c:
  c.executescript('''CREATE TABLE IF NOT EXISTS leads(id INTEGER PRIMARY KEY,name TEXT NOT NULL,industry TEXT NOT NULL,city TEXT DEFAULT '',state TEXT DEFAULT '',website TEXT DEFAULT '',email TEXT DEFAULT '',notes TEXT DEFAULT '',score INTEGER DEFAULT 0,status TEXT DEFAULT 'new',created TEXT NOT NULL);
  CREATE TABLE IF NOT EXISTS drafts(id INTEGER PRIMARY KEY,lead_id INTEGER NOT NULL,kind TEXT NOT NULL,subject TEXT DEFAULT '',body TEXT NOT NULL,status TEXT DEFAULT 'pending',created TEXT NOT NULL,FOREIGN KEY(lead_id) REFERENCES leads(id));
  CREATE TABLE IF NOT EXISTS replies(id INTEGER PRIMARY KEY,lead_id INTEGER NOT NULL,body TEXT NOT NULL,classification TEXT NOT NULL,reason TEXT NOT NULL,created TEXT NOT NULL);
  CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,event TEXT NOT NULL,details TEXT NOT NULL,created TEXT NOT NULL);''')
init()
def now():return datetime.now(timezone.utc).isoformat(timespec='seconds')
def audit(c,event,details):c.execute('INSERT INTO audit(event,details,created) VALUES(?,?,?)',(event,details,now()))
def lead_score(lead):
 industry=(lead['industry'] or '').lower();score=35 if any(x in industry for x in ('hvac','plumb','roof')) else 10
 score+=20 if lead['website'] else 0
 score+=20 if re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',lead['email'] or '') else 0
 score+=10 if lead['city'] and lead['state'] else 0
 score+=15 if len(lead['notes'] or '')>30 else 0
 return min(score,100)
def classify(msg):
 s=msg.lower()
 if re.search(r'\b(unsubscribe|remove me|stop emailing|do not contact|don.t contact)\b',s):return 'do_not_contact','Explicit opt-out'
 if re.search(r'\b(not interested|no thanks|no thank you|not for us)\b',s):return 'not_interested','Explicit rejection'
 if re.search(r'\b(price|pricing|cost|how much|demo|meeting|schedule|interested|tell me more|let.s talk|call me)\b',s):return 'interested','Possible commercial interest; human review required'
 if re.search(r'\b(out of office|automatic reply|away from the office)\b',s):return 'automatic','Likely automatic reply'
 return 'needs_review','No reliable intent signal; manual review'
def compose(lead,kind='initial',reply=''):
 name=lead['name'].strip();industry=lead['industry'].strip().lower();city=lead['city'].strip()
 segment='HVAC' if 'hvac' in industry else 'plumbing' if 'plumb' in industry else 'roofing' if 'roof' in industry else lead['industry'].strip()
 area=f' in {city}' if city else ''
 if kind=='initial':
  subject=f'Question about inquiry follow-up at {name}'
  body=(f'Hello {name} team,\n\nI work with {segment} businesses{area} on responding to new customer inquiries and keeping follow-ups organized. '
        'I do not know whether missed inquiries are a problem for your company, but I would be interested in learning how your team currently handles them.\n\n'
        'Would you be open to a short conversation to see whether an automated follow-up workflow would be useful?\n\n'
        'Best,\nJH III AI Revenue Agency\n\nIf you prefer no further outreach, reply “remove me.”')
 else:
  subject=f'Re: Inquiry follow-up at {name}'
  body=(f'Hello {name} team,\n\nThank you for your reply. I can outline a small pilot focused on inquiry response times and appointment requests. '
        'To see whether it fits, approximately how many new inquiries do you receive weekly, and which channels do they arrive through?\n\n'
        'I can send a brief workflow outline after that.\n\nBest,\nJH III AI Revenue Agency')
 return subject,body

def add_lead(c,data):
 d={k:str(data.get(k,'') or '').strip() for k in ['name','industry','city','state','website','email','notes']}
 if not d['name'] or not d['industry']:raise ValueError('name and industry required')
 if d['email'] and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',d['email']):raise ValueError('invalid email')
 score=lead_score(d)
 cur=c.execute('INSERT INTO leads(name,industry,city,state,website,email,notes,score,created) VALUES(?,?,?,?,?,?,?,?,?)',(*[d[k] for k in ['name','industry','city','state','website','email','notes']],score,now()))
 audit(c,'lead_created',f'{cur.lastrowid} score={score}')
 return cur.lastrowid
class LeadIn(BaseModel):
 name:str;industry:str;city:str='';state:str='';website:str='';email:str='';notes:str=''
class ReplyIn(BaseModel):
 lead_id:int;body:str
@app.post('/api/leads')
def api_lead(data:LeadIn):
 try:
  with connect() as c:return {'id':add_lead(c,data.model_dump())}
 except ValueError as e:raise HTTPException(400,str(e))
@app.get('/api/leads')
def api_leads():
 with connect() as c:return [dict(r) for r in c.execute('SELECT * FROM leads ORDER BY score DESC,id DESC')]
@app.post('/api/leads/{lead_id}/draft')
def make_draft(lead_id:int):
 with connect() as c:
  lead=c.execute('SELECT * FROM leads WHERE id=?',(lead_id,)).fetchone()
  if not lead:raise HTTPException(404,'Lead not found')
  if lead['status']=='do_not_contact':raise HTTPException(409,'Opted out')
  subject,body=compose(lead)
  cur=c.execute('INSERT INTO drafts(lead_id,kind,subject,body,created) VALUES(?,?,?,?,?)',(lead_id,'initial',subject,body,now()))
  audit(c,'draft_created',str(cur.lastrowid));return {'id':cur.lastrowid,'subject':subject,'body':body,'status':'pending'}
@app.get('/api/drafts')
def api_drafts():
 with connect() as c:return [dict(r) for r in c.execute('SELECT d.*,l.name,l.email FROM drafts d JOIN leads l ON l.id=d.lead_id ORDER BY d.id DESC')]
@app.post('/api/drafts/{draft_id}/approve')
def approve(draft_id:int):
 with connect() as c:
  row=c.execute('SELECT d.*,l.status AS lead_status FROM drafts d JOIN leads l ON l.id=d.lead_id WHERE d.id=?',(draft_id,)).fetchone()
  if not row:raise HTTPException(404,'Draft not found')
  if row['lead_status']=='do_not_contact':raise HTTPException(409,'Lead opted out')
  if row['status']!='pending':raise HTTPException(409,'Not pending')
  c.execute('UPDATE drafts SET status=? WHERE id=?',('approved',draft_id));audit(c,'draft_approved',str(draft_id))
 return {'status':'approved','note':'Approved for manual sending; no email was sent'}
@app.post('/api/replies')
def api_reply(data:ReplyIn):
 with connect() as c:
  lead=c.execute('SELECT * FROM leads WHERE id=?',(data.lead_id,)).fetchone()
  if not lead:raise HTTPException(404,'Lead not found')
  if not data.body.strip():raise HTTPException(400,'Empty reply')
  label,reason=classify(data.body)
  cur=c.execute('INSERT INTO replies(lead_id,body,classification,reason,created) VALUES(?,?,?,?,?)',(data.lead_id,data.body,label,reason,now()))
  c.execute('UPDATE leads SET status=? WHERE id=?',(label,data.lead_id))
  if label=='interested':
   subject,body=compose(lead,'reply',data.body)
   c.execute('INSERT INTO drafts(lead_id,kind,subject,body,created) VALUES(?,?,?,?,?)',(data.lead_id,'reply',subject,body,now()))
  if label=='do_not_contact':
   c.execute("UPDATE drafts SET status='blocked' WHERE lead_id=? AND status IN ('pending','approved')",(data.lead_id,))
  audit(c,'reply_classified',f'{cur.lastrowid} {label}')
 return {'classification':label,'reason':reason,'follow_up_drafted':label=='interested'}
@app.get('/api/replies')
def api_replies():
 with connect() as c:return [dict(r) for r in c.execute('SELECT r.*,l.name FROM replies r JOIN leads l ON l.id=r.lead_id ORDER BY r.id DESC')]
@app.get('/api/audit')
def api_audit():
 with connect() as c:return [dict(r) for r in c.execute('SELECT * FROM audit ORDER BY id DESC LIMIT 100')]
@app.get('/api/export.csv')
def export_csv():
 with connect() as c:rows=[dict(r) for r in c.execute('SELECT * FROM leads ORDER BY id')]
 output=io.StringIO();writer=csv.DictWriter(output,fieldnames=['id','name','industry','city','state','website','email','notes','score','status','created']);writer.writeheader();writer.writerows(rows)
 return StreamingResponse(iter([output.getvalue()]),media_type='text/csv',headers={'Content-Disposition':'attachment; filename=leads.csv'})
@app.post('/import')
async def import_csv(file:UploadFile=File(...)):
 raw=await file.read()
 if len(raw)>2_000_000:raise HTTPException(413,'CSV too large')
 try:rows=list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))
 except Exception:raise HTTPException(400,'Invalid CSV')
 count=0;errors=[]
 with connect() as c:
  for i,row in enumerate(rows[:1000],2):
   try:add_lead(c,row);count+=1
   except ValueError as e:errors.append(f'Row {i}: {e}')
 return {'imported':count,'errors':errors[:20]}
@app.get('/',response_class=HTMLResponse)
def home():return (ROOT/'index.html').read_text()

# Secure browser sessions, request validation and response headers.
from security import install_security
install_security(app)
