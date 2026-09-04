from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, quote_plus, quote
from pathlib import Path
from xml.etree import ElementTree as ET
from email.utils import parsedate_to_datetime
import urllib.request, json, os, time, hashlib, tempfile, threading, uuid, shutil, sqlite3, sqlite3
from datetime import datetime, timezone, timedelta

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
UPDATE_BASE = 'https://raw.githubusercontent.com/ant-system/ant-system/main/'
BUILD_FILE = ROOT / 'build.json'
BOOT_ID = uuid.uuid4().hex
YAHOO = 'https://query1.finance.yahoo.com/v8/finance/chart/{}?range={}&interval={}&includePrePost=true&events=div%2Csplits'

def val(q,k,i):
    a=q.get(k) or []
    return a[i] if i < len(a) else None

def fetch_json(url, timeout=12):
    req=urllib.request.Request(url,headers={'User-Agent':UA,'Accept':'application/json'})
    with urllib.request.urlopen(req,timeout=timeout) as r:
        return json.loads(r.read())

def fetch_bytes(url, timeout=15):
    req=urllib.request.Request(url,headers={
        'User-Agent':UA,
        'Accept':'*/*',
        'Cache-Control':'no-cache, no-store, max-age=0',
        'Pragma':'no-cache'
    })
    with urllib.request.urlopen(req,timeout=timeout) as r:
        return r.read()

def local_build():
    try: return json.loads(BUILD_FILE.read_text(encoding='utf-8')).get('build','0')
    except: return '0'

def remote_manifest():
    url=UPDATE_BASE+'manifest.json?ts='+str(time.time_ns())
    return json.loads(fetch_bytes(url).decode('utf-8'))

def check_update():
    m=remote_manifest(); cur=local_build(); latest=str(m.get('build','0'))
    return {'ok':True,'current':cur,'latest':latest,'update_available':cur != latest,'notes':m.get('notes',''),'published_at':m.get('published_at','')}

def apply_update():
    m=remote_manifest(); files=m.get('files') or []
    staged=[]; backups=[]
    try:
        for f in files:
            name=f.get('path','')
            if not name or '/' in name or '\\' in name or name.startswith('.'): raise RuntimeError('invalid update path')
            data=fetch_bytes(UPDATE_BASE+quote(name)+'?ts='+str(time.time_ns()))
            digest=hashlib.sha256(data).hexdigest()
            if digest != f.get('sha256'): raise RuntimeError('hash mismatch: '+name)
            tmp=ROOT/(name+'.antnew'); tmp.write_bytes(data); staged.append((tmp,ROOT/name))
        for _,dst in staged:
            if dst.exists():
                bak=ROOT/(dst.name+'.antbak')
                shutil.copy2(dst,bak); backups.append((bak,dst))
        for tmp,dst in staged: os.replace(tmp,dst)
    except Exception:
        for tmp,_ in staged:
            try:
                if tmp.exists(): tmp.unlink()
            except: pass
        for bak,dst in backups:
            try:
                if bak.exists(): shutil.copy2(bak,dst)
            except: pass
        raise
    names=[x[1].name for x in staged]
    restart_required=any(n in ('server.py','ANT_실행.bat') for n in names)
    return {'ok':True,'build':str(m.get('build','0')),'updated_files':names,'restart_required':restart_required,'boot_id':BOOT_ID}


PATCH_JS = r"""<script id="ant-runtime-patch">
(()=>{
 const sleep=ms=>new Promise(r=>setTimeout(r,ms));
 async function health(tries=8){let last=null;for(let i=0;i<tries;i++){try{let r=await fetch('/api/health?ts='+Date.now(),{cache:'no-store'});if(r.ok){let j=await r.json();if(j.ok)return j}}catch(e){last=e}await sleep(500+i*200)}throw last||new Error('health unavailable')}
 async function syncBuild(){try{let h=await health();let el=document.getElementById('buildLabel');if(el)el.textContent='Build '+h.build;let ss=document.getElementById('serverState');if(ss)ss.textContent='로컬 서버 정상';return h}catch(e){let ss=document.getElementById('serverState');if(ss)ss.textContent='서버 재연결 중';return null}}
 async function robustUpdate(){const b=document.getElementById('updateBtn');try{if(b)b.textContent='⏳ 확인 중';let r=await fetch('/api/update/check?ts='+Date.now(),{cache:'no-store'});let j=await r.json();if(!j.ok)throw Error(j.error||'업데이트 확인 실패');let bl=document.getElementById('buildLabel');if(bl)bl.textContent='Build '+j.current;if(!j.update_available){if(b)b.textContent='✓ 최신 Build';return}if(!confirm('Build '+j.latest+' 업데이트를 적용할까요?')){if(b)b.textContent='⬆ 업데이트 확인';return}if(b)b.textContent='⏳ 업데이트 적용 중';r=await fetch('/api/update/apply?ts='+Date.now(),{cache:'no-store'});j=await r.json();if(!j.ok)throw Error(j.error||'적용 실패');if(!j.restart_required){if(b)b.textContent='✓ 적용 완료';setTimeout(()=>location.reload(),600);return}if(b)b.textContent='↻ 서버 재시작 대기';const old=j.boot_id;await sleep(2500);for(let i=0;i<50;i++){try{let h=await health(1);if(h.boot_id&&h.boot_id!==old){location.reload();return}}catch(e){}await sleep(800)}if(b)b.textContent='⚠ 새로고침 필요'}catch(e){if(b)b.textContent='⚠ 업데이트 실패';if(window.log)log('UPDATE FAIL '+e.message)}}
 window.addEventListener('load',async()=>{await syncBuild();let b=document.getElementById('updateBtn');if(b)b.onclick=robustUpdate;await sleep(1800);let mp=document.getElementById('mprice');if(mp&&mp.textContent.trim()==='—'&&typeof window.refreshAll==='function'){try{await refreshAll()}catch(e){}}});
})();
</script>"""

def serve_index(handler):
    data=(ROOT/'index.html').read_text(encoding='utf-8')
    if 'id="ant-runtime-patch"' not in data:
        data=data.replace('</body>', PATCH_JS+'</body>')
    b=data.encode('utf-8')
    handler.send_response(200)
    handler.send_header('Content-Type','text/html; charset=utf-8')
    handler.send_header('Content-Length',str(len(b)))
    handler.end_headers()
    handler.wfile.write(b)

KST = timezone(timedelta(hours=9))

def kst_text(ts):
    if not ts: return ''
    return datetime.fromtimestamp(ts, KST).strftime('%Y-%m-%d %H:%M KST')

DB_FILE = ROOT / 'ant_market.db'

def latest_kis_tick(symbol):
    if not DB_FILE.exists(): return None
    con=None
    try:
        con=sqlite3.connect(str(DB_FILE), timeout=1)
        con.row_factory=sqlite3.Row
        r=con.execute(
            "SELECT received_at_utc,received_at_kst,source,market,symbol,exchange_time,price,change_pct,volume,cumulative_volume,ask1,bid1 "
            "FROM market_ticks WHERE symbol=? ORDER BY id DESC LIMIT 1", (symbol,)
        ).fetchone()
        if not r: return None
        d=dict(r)
        try:
            dt=datetime.fromisoformat(d['received_at_utc'].replace('Z','+00:00'))
            age=max(0.0,(datetime.now(timezone.utc)-dt.astimezone(timezone.utc)).total_seconds())
        except Exception:
            age=None
        d['age_sec']=age
        d['fresh']=bool(age is not None and age <= 120)
        return d
    except Exception:
        return None
    finally:
        if con:
            try: con.close()
            except Exception: pass


def price_discovery_snapshot(fx_rate):
    if not DB_FILE.exists():
        return {'ok':False,'error':'ant_market.db missing'}
    con=sqlite3.connect(str(DB_FILE), timeout=3)
    con.row_factory=sqlite3.Row
    try:
        kr=[dict(r) for r in con.execute(
            "SELECT received_at_utc,price FROM market_ticks "
            "WHERE symbol='000660' AND market='NXT' AND price IS NOT NULL ORDER BY received_at_utc")]
        us=[dict(r) for r in con.execute(
            "SELECT received_at_utc,price FROM us_ticks "
            "WHERE symbol='SKHY' AND source='TIINGO' AND price IS NOT NULL ORDER BY received_at_utc")]
    finally:
        con.close()

    def pdt(s):
        d=datetime.fromisoformat(str(s).replace('Z','+00:00'))
        if d.tzinfo is None: d=d.replace(tzinfo=timezone.utc)
        return d.astimezone(KST).replace(second=0,microsecond=0)

    def bars(rows):
        g={}
        for r in rows:
            try: g[pdt(r['received_at_utc'])]=float(r['price'])
            except Exception: pass
        return g

    def corr(xs,ys):
        n=len(xs)
        if n<3:return None
        mx=sum(xs)/n; my=sum(ys)/n
        ax=[x-mx for x in xs]; ay=[y-my for y in ys]
        den=(sum(x*x for x in ax)*sum(y*y for y in ay))**0.5
        return sum(x*y for x,y in zip(ax,ay))/den if den else None

    def beta(xs,ys):
        n=len(xs)
        if n<3:return None
        mx=sum(xs)/n; my=sum(ys)/n
        den=sum((x-mx)**2 for x in xs)
        return sum((x-mx)*(y-my) for x,y in zip(xs,ys))/den if den else None

    kb,ub=bars(kr),bars(us)
    common=sorted(set(kb)&set(ub))
    if len(common)<3:
        return {'ok':False,'error':'insufficient overlap','common_minutes':len(common)}

    base=common[0]; latest=common[-1]
    series=[{
        'kst':m.isoformat(),
        'nxt':kb[m],
        'skhy':ub[m],
        'nxt_norm':kb[m]/kb[base]*100,
        'skhy_norm':ub[m]/ub[base]*100
    } for m in common]

    returns=[]; prev=None
    for m in common:
        if prev is not None and (m-prev).total_seconds()==60 and kb[prev] and ub[prev]:
            returns.append((m,kb[m]/kb[prev]-1,ub[m]/ub[prev]-1))
        prev=m

    windows={}
    for w in (5,15,30,60):
        rr=returns[-w:]
        if len(rr)>=3:
            x=[z[2] for z in rr]; y=[z[1] for z in rr]
            windows[str(w)]={'corr':corr(x,y),'beta':beta(x,y),'n':len(rr)}
        else:
            windows[str(w)]={'corr':None,'beta':None,'n':len(rr)}

    d={m:(rk,ru) for m,rk,ru in returns}
    lags=[]
    for lag in range(-5,6):
        pairs=[]
        for m,(rk,ru) in d.items():
            target=m+timedelta(minutes=lag)
            if target in d:pairs.append((ru,d[target][0]))
        if len(pairs)>=5:
            c=corr([x[0] for x in pairs],[x[1] for x in pairs])
            lags.append({'lag':lag,'corr':c,'n':len(pairs)})
    positive=[x for x in lags if x['corr'] is not None and x['corr']>0]
    bp=max(positive,key=lambda x:x['corr']) if positive else None
    lead=None
    if bp and bp['corr']>=0.30 and bp['n']>=15:
        lead={**bp,'meaning':'SKHY leads NXT' if bp['lag']>0 else ('NXT leads SKHY' if bp['lag']<0 else 'same-minute')}
    strongest=max(lags,key=lambda x:abs(x['corr'])) if lags else None

    nxt=kb[latest]; skhy=ub[latest]
    implied=discount=premium=None
    if fx_rate is not None:
        implied=skhy*10.0*fx_rate
        premium=(implied/nxt-1)*100
        discount=(1-nxt/implied)*100

    return {
        'ok':True,'fx_rate':fx_rate,'fx_mode':'snapshot' if fx_rate is not None else 'none',
        'adr_ratio':'10 ADS = 1 ordinary share',
        'overlap_start':base.isoformat(),'overlap_end':latest.isoformat(),
        'common_minutes':len(common),'paired_returns':len(returns),
        'latest':{'nxt':nxt,'skhy':skhy,'implied_krw':implied,'skhy_premium_pct':premium,'nxt_discount_pct':discount,
                  'nxt_norm':series[-1]['nxt_norm'],'skhy_norm':series[-1]['skhy_norm'],
                  'norm_gap_pp':series[-1]['skhy_norm']-series[-1]['nxt_norm']},
        'windows':windows,'lead_signal':lead,'strongest_relation':strongest,
        'series':series[-180:]
    }

def google_news(query, limit=30, max_age_min=1440):
    fresh_query = query + (' when:1h' if max_age_min <= 60 else ' when:1d')
    url='https://news.google.com/rss/search?q='+quote_plus(fresh_query)+'&hl=ko&gl=KR&ceid=KR:ko'
    req=urllib.request.Request(url,headers={'User-Agent':UA,'Accept':'application/rss+xml, application/xml, text/xml'})
    with urllib.request.urlopen(req,timeout=12) as r:
        xml=r.read()
    root=ET.fromstring(xml)
    out=[]
    for item in root.findall('.//item')[:limit]:
        title=(item.findtext('title') or '').strip()
        link=(item.findtext('link') or '').strip()
        pub=(item.findtext('pubDate') or '').strip()
        source=''
        src=item.find('source')
        if src is not None and src.text: source=src.text.strip()
        ts=None
        try: ts=int(parsedate_to_datetime(pub).timestamp())
        except: pass
        if ts is None: continue
        age_min=max(0,int((time.time()-ts)/60))
        if age_min > max_age_min: continue
        out.append({'title':title,'link':link,'pubDate':kst_text(ts),'ts':ts,'source':source,'kst':kst_text(ts),'age_min':age_min})
    out.sort(key=lambda x:x['ts'], reverse=True)
    return out[:limit]

SCAN_GROUPS = [
 ('전쟁·중동','이란 전쟁 호르무즈 미국 미사일 드론 속보'),
 ('금리·Fed','미국 연준 Fed 금리 국채 긴급'),
 ('유가','WTI 브렌트 유가 급등 급락 호르무즈'),
 ('미국선물','나스닥 선물 S&P500 선물 급락 급등'),
 ('일본·엔','BOJ 일본 금리 엔화 캐리 트레이드'),
 ('중국','중국 증시 경기 부동산 위안화'),
 ('한국시장','코스피 외국인 기관 프로그램 매도 선물'),
 ('반도체','엔비디아 마이크론 SK하이닉스 삼성전자 반도체 HBM'),
 ('이차전지','삼성SDI 이수스페셜티케미컬 전고체 ESS')
]

class H(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Cache-Control','no-store')
        super().end_headers()

    def json(self,obj,status=200):
        b=json.dumps(obj,ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length',str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        p=urlparse(self.path)
        if p.path in ('/','/index.html'):
            return serve_index(self)
        if p.path=='/api/health':
            return self.json({'ok':True,'server':'ANT local proxy','time':int(time.time()),'build':local_build(),'boot_id':BOOT_ID,'kst':kst_text(int(time.time()))})
        if p.path=='/api/update/check':
            try: return self.json(check_update())
            except Exception as e: return self.json({'ok':False,'error':str(e)},502)
        if p.path=='/api/update/apply':
            try:
                result=apply_update(); self.json(result)
                if result.get('restart_required'):
                    threading.Timer(2.2, lambda: os._exit(42)).start()
                return
            except Exception as e: return self.json({'ok':False,'error':str(e)},502)
        if p.path=='/api/live/quote':
            q=parse_qs(p.query); symbol=q.get('symbol',[''])[0]
            if not symbol: return self.json({'ok':False,'error':'symbol required'},400)
            tick=latest_kis_tick(symbol)
            return self.json({'ok':True,'symbol':symbol,'available':bool(tick),'tick':tick,'server_kst':kst_text(int(time.time()))})
        if p.path=='/api/kis/nxt/latest':
            qs=parse_qs(p.query); symbol=qs.get('symbol',['000660'])[0]
            if symbol != '000660': return self.json({'ok':False,'error':'only 000660 is enabled in this test'},400)
            db=ROOT/'ant_market.db'
            try:
                con=sqlite3.connect(str(db)); con.row_factory=sqlite3.Row
                row=con.execute('SELECT received_at_utc,received_at_kst,source,market,symbol,exchange_time,price,change_pct,volume,cumulative_volume,ask1,bid1 FROM market_ticks WHERE symbol=? ORDER BY received_at_utc DESC LIMIT 1',(symbol,)).fetchone(); con.close()
                if not row: return self.json({'ok':True,'symbol':symbol,'tick':None,'live':False})
                d=dict(row)
                try:
                    stamp=str(d.get('received_at_utc') or '').replace('Z','+00:00'); dt=datetime.fromisoformat(stamp)
                    if dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
                    age=max(0.0,(datetime.now(timezone.utc)-dt.astimezone(timezone.utc)).total_seconds())
                except Exception: age=None
                return self.json({'ok':True,'symbol':symbol,'tick':d,'age_sec':age,'live':age is not None and age <= 120})
            except Exception as e: return self.json({'ok':False,'symbol':symbol,'error':str(e)},500)

        if p.path=='/api/price_discovery':
            qs=parse_qs(p.query)
            raw=(qs.get('fx') or [''])[0].strip().replace(',','')
            fx=None
            if raw:
                try:
                    fx=float(raw)
                    if not (500 < fx < 3000): raise ValueError()
                except Exception:
                    return self.json({'ok':False,'error':'invalid USD/KRW snapshot rate'},400)
            try: return self.json(price_discovery_snapshot(fx))
            except Exception as e: return self.json({'ok':False,'error':str(e)},500)
        if p.path=='/api/chart':
            q=parse_qs(p.query)
            symbol=q.get('symbol',[''])[0]; rng=q.get('range',['5d'])[0]; interval=q.get('interval',['5m'])[0]
            if not symbol: return self.json({'ok':False,'error':'symbol required'},400)
            try:
                url=YAHOO.format(quote(symbol,safe=''),quote(rng),quote(interval))
                data=fetch_json(url)
                result=(data.get('chart',{}).get('result') or [None])[0]
                if not result: raise RuntimeError(str(data.get('chart',{}).get('error')))
                ts=result.get('timestamp') or []; ind=result.get('indicators',{})
                q0=(ind.get('quote') or [{}])[0]
                ac=(ind.get('adjclose') or [{}])[0].get('adjclose') or q0.get('close') or []
                rows=[]
                for i,t in enumerate(ts):
                    c=ac[i] if i < len(ac) else None
                    if c is None: continue
                    rows.append({'t':t,'o':val(q0,'open',i),'h':val(q0,'high',i),'l':val(q0,'low',i),'c':c,'v':val(q0,'volume',i)})
                return self.json({'ok':True,'symbol':symbol,'rows':rows,'meta':result.get('meta',{}),'fetched_at':int(time.time()),'last_data_at_kst':kst_text(rows[-1]['t']) if rows else ''})
            except Exception as e:
                return self.json({'ok':False,'symbol':symbol,'error':str(e)},502)
        if p.path=='/api/news':
            qs=parse_qs(p.query); q=qs.get('q',['증시 속보'])[0]
            try: window=max(10,min(1440,int(qs.get('window',['1440'])[0])))
            except: window=1440
            try: return self.json({'ok':True,'query':q,'window_min':window,'items':google_news(q,40,window),'scanned_at':int(time.time()),'scanned_at_kst':kst_text(int(time.time()))})
            except Exception as e: return self.json({'ok':False,'error':str(e),'items':[]},502)
        if p.path=='/api/news_scan':
            try:
                qs=parse_qs(p.query)
                try: window=max(10,min(1440,int(qs.get('window',['30'])[0])))
                except: window=30
                items=[]; seen=set(); now=int(time.time())
                for cat,q in SCAN_GROUPS:
                    for x in google_news(q,12,window):
                        if x['title'] in seen: continue
                        seen.add(x['title']); x['category']=cat
                        age=(now-(x['ts'] or now))/60
                        score=max(0,60-age)
                        low=x['title'].lower()
                        for kw in ['속보','긴급','공격','미사일','전쟁','급락','급등','매도','금리','호르무즈','fomc','fed']:
                            if kw in low: score += 12
                        x['score']=round(score,1); items.append(x)
                items.sort(key=lambda x:(x.get('score',0),x.get('ts') or 0),reverse=True)
                return self.json({'ok':True,'items':items[:80],'window_min':window,'scanned_at':now,'scanned_at_kst':kst_text(now)})
            except Exception as e:
                return self.json({'ok':False,'error':str(e),'items':[]},502)
        return super().do_GET()

if __name__=='__main__':
    port=int(os.environ.get('ANT_PORT','8765'))
    print(f'A.N.T Market Control V1.0 -> http://127.0.0.1:{port}')
    ThreadingHTTPServer(('127.0.0.1',port),H).serve_forever()