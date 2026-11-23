"""Apply to the exact deployed app.py/index.html in the current directory. Backups created."""
from pathlib import Path
import shutil
app=Path('app.py'); page=Path('index.html')
if not app.exists() or not page.exists():raise SystemExit('Run alongside app.py and index.html')
a=app.read_text(); h=page.read_text()
if "@app.post('/api/research/batch-step')" not in a:
 marker="@app.get('/api/research/export.csv')"
 if marker not in a:raise SystemExit('Missing expected research export route; no changes made')
 addition='''
# Bounded, human-review-first batch research. Never automatically creates sales leads.
class BatchResearchStep(BaseModel):
 offset:int=0
 limit:int=1

@app.post('/api/research/batch-step')
def research_batch_step(data:BatchResearchStep):
 from research import search_candidates, identity_evidence, audit_site, domain
 offset=max(0,min(data.offset,10000));limit=max(1,min(data.limit,2))
 with connect() as c:
  total=c.execute("SELECT COUNT(*) AS n FROM license_records WHERE status='ACTIVE' AND license_type='HVAC' AND LENGTH(TRIM(business_name))>2").fetchone()['n']
  rows=[dict(r) for r in c.execute("SELECT license_number,business_name FROM license_records WHERE status='ACTIVE' AND license_type='HVAC' AND LENGTH(TRIM(business_name))>2 ORDER BY id LIMIT ? OFFSET ?",(limit,offset))]
 results=[]
 for r in rows:
  item={'license_number':r['license_number'],'business_name':r['business_name'],'status':'NO_MATCH','website':'','phones':[],'emails':[],'evidence':[],'error':''}
  try:
   sites,warning=search_candidates(r['business_name'])
   if warning:item['error']=warning
   for site in sites[:3]:
    evidence=identity_evidence(r['business_name'],site['url'])
    if evidence.get('status')!='NEEDS_REVIEW' or not all(evidence.get(k) for k in ('name_match','industry_match','location_match')):continue
    try:report=audit_site(site['url'])
    except Exception as exc:
     item['error']='Website inspection failed: '+type(exc).__name__
     continue
    # Identity evidence is corroboration, not proof of license-holder ownership.
    item.update(status='REVIEW_REQUIRED',website=report['website'],phones=report['phones'],emails=report['emails'],evidence=evidence['reasons'],booking_links=report['booking_links'],findings=report['findings'],source_url=report['source_url'])
    break
  except Exception as exc:item['error']='Discovery unavailable: '+type(exc).__name__
  results.append(item)
 return {'offset':offset,'next_offset':offset+len(rows),'total':total,'results':results,'notice':'Automated corroboration only. Not independently verified until license-to-company ownership is checked by a human. No outreach or lead imports.'}

'''
 a=a.replace(marker,addition+marker,1)
if 'id="batch20Start"' not in h:
 marker='<button onclick="loadResearch()">Load active HVAC businesses</button>'
 if marker not in h:raise SystemExit('Missing expected dashboard research button; no changes made')
 h=h.replace(marker,marker+'<button id="batch20Start" onclick="startBatch20()">Research A-list automatically (up to 20 review candidates)</button><button class="secondary" onclick="stopBatch20()">Stop</button><p id="batch20Status" class="muted"></p><div id="batch20Results" class="scroll"></div>',1)
 marker='async function findResearch(i)'
 if marker not in h:raise SystemExit('Missing expected research JS; no changes made')
 js='''let batch20Running=false,batch20Items=[],batch20Offset=0;
function stopBatch20(){batch20Running=false;$('#batch20Status').textContent='Stopped. '+batch20Items.filter(x=>x.status==='REVIEW_REQUIRED').length+' review candidates; none automatically verified.';}
function renderBatch20(){let rows=batch20Items.filter(x=>x.status==='REVIEW_REQUIRED');$('#batch20Results').innerHTML='<h3>Review candidates ('+rows.length+'/20 target; 0 independently verified)</h3><p>Company ownership and contacts must be confirmed before outreach.</p><table><thead><tr><th>Company / license</th><th>Discovered website / public contact</th><th>Evidence</th></tr></thead><tbody>'+rows.map(x=>'<tr><td>'+safe(x.business_name)+'<br>'+safe(x.license_number)+'</td><td><a target="_blank" rel="noopener noreferrer" href="'+safe(x.website)+'">'+safe(x.website)+'</a><br>'+safe(x.phones.join(', '))+'<br>'+safe(x.emails.join(', '))+'</td><td>'+safe(x.evidence.join('; '))+'</td></tr>').join('')+'</tbody></table>';}
async function startBatch20(){if(batch20Running)return;batch20Running=true;batch20Items=[];batch20Offset=0;const button=$('#batch20Start');button.disabled=true;
 try{while(batch20Running){$('#batch20Status').textContent='Checking record '+(batch20Offset+1)+'; '+batch20Items.filter(x=>x.status==='REVIEW_REQUIRED').length+' review candidates found. Please keep this page open.';
 const response=await post('/api/research/batch-step',{offset:batch20Offset,limit:1});
 batch20Items.push(...response.results);batch20Offset=response.next_offset;renderBatch20();
 if(!response.results.length||batch20Offset>=response.total||batch20Items.filter(x=>x.status==='REVIEW_REQUIRED').length>=20)break;
 }
 $('#batch20Status').textContent='Finished/paused at '+batch20Offset+' records. '+batch20Items.filter(x=>x.status==='REVIEW_REQUIRED').length+' review candidates; 0 independently verified. No leads imported.';
 }catch(e){$('#batch20Status').textContent='Batch stopped at record '+batch20Offset+': '+e.message+'; review candidates retained on screen.';}
 finally{batch20Running=false;button.disabled=false;}}
'''
 h=h.replace(marker,js+marker,1)
shutil.copy2(app,'app.py.before_batch20');shutil.copy2(page,'index.html.before_batch20')
app.write_text(a);page.write_text(h)
print('Patched app.py and index.html; backups saved. Upload research.py from this package separately.')
