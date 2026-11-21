import os, hmac, time, secrets
from collections import defaultdict
from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from starlette.middleware.base import BaseHTTPMiddleware

SECRET=os.environ.get('SESSION_SECRET','')
PASSWORD=os.environ.get('ADMIN_PASSWORD','')
if len(SECRET)<32 or len(PASSWORD)<16:
    raise RuntimeError('Set SESSION_SECRET (32+ chars) and ADMIN_PASSWORD (16+ chars)')
signer=URLSafeTimedSerializer(SECRET,salt='jh3-session-v2')
attempts=defaultdict(list)
LOGIN_HTML='''<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>JH III Sign In</title><style>body{font:16px system-ui;background:#0b1220;color:#fff;display:grid;place-items:center;min-height:95vh;margin:0}form{width:min(90vw,360px);background:#142139;padding:25px;border-radius:14px}input,button{box-sizing:border-box;width:100%;padding:14px;margin:12px 0;border-radius:8px;font-size:16px}button{background:#e6b54a;border:0;font-weight:bold}input{background:#0b1220;color:white;border:1px solid #52617b}</style></head><body><form action="/login" method="post"><h2>JH III · Secure Sign In</h2><p>Enter your administrator password.</p><input name="password" type="password" autocomplete="current-password" required minlength="16"><button>Sign in</button></form></body></html>'''

class SecurityMiddleware(BaseHTTPMiddleware):
 async def dispatch(self,request:Request,call_next):
  path=request.url.path
  if path not in ('/login','/health'):
   try: signer.loads(request.cookies.get('jh3_session',''),max_age=43200)
   except (BadSignature,SignatureExpired):
    if path.startswith('/api/') or path=='/import':return JSONResponse({'detail':'Sign in required'},status_code=401)
    return RedirectResponse('/login',status_code=303)
  if request.method not in ('GET','HEAD','OPTIONS') and path not in ('/login',):
   origin=request.headers.get('origin')
   host=request.headers.get('host','')
   if origin and origin not in ('https://'+host,'http://'+host):return JSONResponse({'detail':'Origin rejected'},status_code=403)
   csrf=request.headers.get('x-csrf-token','')
   if not csrf or not hmac.compare_digest(csrf,request.cookies.get('jh3_csrf','')):
    return JSONResponse({'detail':'Invalid CSRF token'},status_code=403)
  response=await call_next(request)
  response.headers['X-Content-Type-Options']='nosniff'
  response.headers['X-Frame-Options']='DENY'
  response.headers['Referrer-Policy']='no-referrer'
  response.headers['Cache-Control']='no-store'
  response.headers['Content-Security-Policy']="default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
  response.headers['Strict-Transport-Security']='max-age=31536000; includeSubDomains'
  return response

def install_security(app):
 from fastapi import Form
 app.add_middleware(SecurityMiddleware)
 @app.get('/health')
 def health():return {'status':'ok'}
 @app.get('/login',response_class=HTMLResponse)
 def login_page():return LOGIN_HTML
 @app.post('/login')
 def login(request:Request,password:str=Form(...)):
  ip=request.client.host if request.client else 'unknown'
  current=time.monotonic(); attempts[ip]=[t for t in attempts[ip] if current-t<900]
  if len(attempts[ip])>=8:return HTMLResponse('Too many attempts. Try again later.',status_code=429)
  if not hmac.compare_digest(password,PASSWORD):
   attempts[ip].append(current)
   return HTMLResponse('Incorrect password. <a href="/login">Try again</a>',status_code=401)
  attempts[ip]=[]
  resp=RedirectResponse('/',status_code=303)
  resp.set_cookie('jh3_session',signer.dumps({'role':'admin'}),httponly=True,secure=True,samesite='strict',max_age=43200)
  resp.set_cookie('jh3_csrf',secrets.token_urlsafe(32),httponly=False,secure=True,samesite='strict',max_age=43200)
  return resp
 @app.post('/logout')
 def logout():
  resp=RedirectResponse('/login',status_code=303)
  resp.delete_cookie('jh3_session');resp.delete_cookie('jh3_csrf')
  return resp
