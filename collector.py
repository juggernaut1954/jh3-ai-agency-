"""Human-assisted Alabama HACR license collector. No CAPTCHA solving/bypass."""
import argparse, csv, json, re, time
from pathlib import Path
from playwright.sync_api import sync_playwright

URL='https://hacr.igovsolution.net/online/Lookups/Individual_Lookup.aspx'
FIELDS=['license_number','holder','license_type','status','issue_date','expiration_date','renewal_date','business_name','search_letter','page_number']
DATE=re.compile(r'^\d{1,2}/\d{1,2}/\d{4}$')

def extract_rows(page, letter, number):
    # Read table rows in the rendered page, never attempt to access protected endpoints.
    data=page.locator('table tr').evaluate_all('''els => els.map(tr => [...tr.querySelectorAll('td')].map(td => td.innerText.trim()))''')
    found=[]
    for cells in data:
        cells=[re.sub(r'\s+',' ',x).strip() for x in cells]
        # Expected: holder, license number, type, status, issued, expires, renewed, business
        for i in range(max(0,len(cells)-5)):
            if i+5>=len(cells): break
            if not re.fullmatch(r'(?:\d{4,}|I\d+)', cells[i+1], re.I): continue
            if not DATE.fullmatch(cells[i+4]) or not DATE.fullmatch(cells[i+5]): continue
            r={'holder':cells[i], 'license_number':cells[i+1], 'license_type':cells[i+2],
               'status':cells[i+3], 'issue_date':cells[i+4], 'expiration_date':cells[i+5],
               'renewal_date':cells[i+6] if len(cells)>i+6 and DATE.fullmatch(cells[i+6]) else '',
               'business_name':'', 'search_letter':letter,'page_number':number}
            business_idx=i+7 if r['renewal_date'] else i+6
            if business_idx<len(cells): r['business_name']=cells[business_idx]
            found.append(r)
            break
    return found

def save(path, rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    old=[]
    if path.exists():
        with path.open(newline='',encoding='utf-8-sig') as f: old=list(csv.DictReader(f))
    # One row per license ID; retain prior data if current extraction is less complete.
    by_id={r['license_number']:r for r in old if r.get('license_number')}
    for r in rows:
        key=r['license_number']
        if key not in by_id or sum(bool(x) for x in r.values())>=sum(bool(x) for x in by_id[key].values()):
            by_id[key]=r
    temp=path.with_suffix('.tmp')
    with temp.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=FIELDS,extrasaction='ignore');w.writeheader();w.writerows(by_id.values())
    temp.replace(path)
    return len(by_id)

def click_next(page):
    # ASP.NET sites may use text links or javascript postback pager controls.
    options=[page.get_by_role('link',name=re.compile(r'^(next|next page|>|»)$',re.I)),
             page.locator('a[title*="Next" i]'),page.locator('input[value*="Next" i]')]
    for loc in options:
        if loc.count() and loc.first.is_visible() and loc.first.is_enabled():
            loc.first.click(timeout=12000);return True
    return False

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--letter',default='B',help='Single last-name search letter')
    ap.add_argument('--out',default='alabama_licenses.csv')
    ap.add_argument('--max-pages',type=int,default=500)
    args=ap.parse_args()
    if not re.fullmatch('[A-Za-z]',args.letter): ap.error('--letter must be A-Z')
    letter=args.letter.upper(); path=Path(args.out)
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=False)
        context=browser.new_context(accept_downloads=False)
        page=context.new_page();page.goto(URL,wait_until='domcontentloaded',timeout=60000)
        print(f'In the opened browser, enter Last Name = {letter}, complete verification code, submit search.')
        input('Once page 1 results are visible, press ENTER here to begin collection... ')
        seen=set(); page_num=1
        while page_num<=args.max_pages:
            page.wait_for_timeout(900)
            rows=extract_rows(page,letter,page_num)
            if not rows:
                print('No recognizable result rows. Stopping safely; check table layout or verification.');break
            signature=tuple(r['license_number'] for r in rows)
            if signature in seen:
                print('Repeated page detected; stopping to prevent loop.');break
            seen.add(signature)
            total=save(path,rows)
            print(f'Page {page_num}: {len(rows)} rows extracted; {total} unique license IDs in {path}')
            before=page.locator('body').inner_text()[:1000]
            try:
                if not click_next(page):
                    print('No supported Next control detected. Check if numeric-only pagination is used.');break
                page.wait_for_timeout(1100)
                if 'verification code' in page.locator('body').inner_text().lower() and not extract_rows(page,letter,page_num+1):
                    input('Verification required. Complete it manually in browser and press ENTER... ')
            except Exception as e:
                print(f'Navigation paused: {e}. All previously collected pages are saved.');break
            page_num+=1
        print('Collection ended. Review CSV before importing into Agent 1.')
        input('Press ENTER to close browser... ')
        browser.close()
if __name__=='__main__':main()
