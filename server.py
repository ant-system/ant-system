from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, quote_plus, quote
from pathlib import Path
from xml.etree import ElementTree as ET
from email.utils import parsedate_to_datetime
import urllib.request, json, os, time, hashlib, tempfile, threading
from datetime import datetime, timezone, timedelta

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
UPDATE_BASE = 'https://raw.githubusercontent.com/ant-system/ant-system/main/'
BUILD_FILE = ROOT / 'build.json'
YAHOO = 'https://query1.finance.yahoo.com/v8/finance/chart/{}?range={}&interval={}&includePrePost=true&events=div%2Csplits'

def val(q,k,i):
    a=q.get(k) or []
    return a[i] if i < len(a) else None

def fetch_json(url, timeout=12):
    req=urllib.request.Request(url,headers={'User-Agent':UA,'Accept':'application/json'})
    with urllib.request.urlopen(req,timeout=timeout) as r:
        return json.loads(r.read())

def fetch_bytes(url, timeout=15):
    req=urllib.request.Request(url,headers={'User-Agent':UA,'Accept':'*/*'})
    with urllib.request.urlopen(req,timeout=timeout) as r:
        return r.read()

def local_build():
    try: return json.loads(BUILD_FILE.read_text(encoding='utf-8')).get('build','0')
    except: return '0'

def remote_manifest():
    return json.loads(fetch_bytes(UPDATE_BASE+'manifest.json').decode('utf-8'))

def check_update():
    m=remote_manifest(); cur=local_build(); latest=str(m.get('build','0'))
    return {'ok':True,'current':cur,'latest':latest,'update_available':cur != latest,'notes':m.get('notes',''),'published_at':m.get('published_at','')}

def apply_update():
    m=remote_manifest(); files=m.get('files') or []
    staged=[]
    for f in files:
        name=f.get('path','')
        if not name or '/' in name or '\\' in name or name.startswith('.'): raise RuntimeError('invalid update path')
        data=fetch_bytes(UPDATE_BASE+quote(name))
        digest=hashlib.sha256(data).hexdigest()
        if digest != f.get('sha256'): raise RuntimeError('hash mismatch: '+name)
        tmp=ROOT/(name+'.antnew'); tmp.write_bytes(data); staged.append((tmp,ROOT/name))
    for tmp,dst in staged: os.replace(tmp,dst)
    return {'ok':True,'build':str(m.get('build','0')),'updated_files':[x[1].name for x in staged]}

KST = timezone(timedelta(hours=9))

def kst_text(ts):
    if not ts: return ''
    return datetime.fromtimestamp(ts, KST).strftime('%Y-%m-%d %H:%M KST')

def google_news(query, limit=30, max_age_min=1440):
    # Google News is discovery-only; enforce freshness locally and in the search query.
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
        if p.path=='/api/health':
            return self.json({'ok':True,'server':'ANT local proxy','time':int(time.time()),'build':local_build()})
        if p.path=='/api/update/check':
            try: return self.json(check_update())
            except Exception as e: return self.json({'ok':False,'error':str(e)},502)
        if p.path=='/api/update/apply':
            try:
                result=apply_update(); self.json(result)
                threading.Timer(1.0, lambda: os._exit(42)).start()
                return
            except Exception as e: return self.json({'ok':False,'error':str(e)},502)
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
                return self.json({'ok':True,'symbol':symbol,'rows':rows,'meta':result.get('meta',{}),'fetched_at':int(time.time())})
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
