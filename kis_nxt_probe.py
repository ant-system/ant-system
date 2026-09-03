from __future__ import annotations
import getpass, json, sqlite3, subprocess, sys, time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
DB = ROOT / 'ant_market.db'
REST = 'https://openapi.koreainvestment.com:9443'
WS = 'ws://ops.koreainvestment.com:21000'
TR_ID = 'H0NXCNT0'  # KIS official: domestic stock realtime execution price (NXT)
SYMBOL = '000660'    # SK hynix
KST = timezone(timedelta(hours=9))
COLS = [
'MKSC_SHRN_ISCD','STCK_CNTG_HOUR','STCK_PRPR','PRDY_VRSS_SIGN','PRDY_VRSS','PRDY_CTRT',
'WGHN_AVRG_STCK_PRC','STCK_OPRC','STCK_HGPR','STCK_LWPR','ASKP1','BIDP1','CNTG_VOL','ACML_VOL',
'ACML_TR_PBMN','SELN_CNTG_CSNU','SHNU_CNTG_CSNU','NTBY_CNTG_CSNU','CTTR','SELN_CNTG_SMTN',
'SHNU_CNTG_SMTN','CNTG_CLS_CODE','SHNU_RATE','PRDY_VOL_VRSS_ACML_VOL_RATE','OPRC_HOUR',
'OPRC_VRSS_PRPR_SIGN','OPRC_VRSS_PRPR','HGPR_HOUR','HGPR_VRSS_PRPR_SIGN','HGPR_VRSS_PRPR',
'LWPR_HOUR','LWPR_VRSS_PRPR_SIGN','LWPR_VRSS_PRPR','BSOP_DATE','NEW_MKOP_CLS_CODE','TRHT_YN',
'ASKP_RSQN1','BIDP_RSQN1','TOTAL_ASKP_RSQN','TOTAL_BIDP_RSQN','VOL_TNRT',
'PRDY_SMNS_HOUR_ACML_VOL','PRDY_SMNS_HOUR_ACML_VOL_RATE','HOUR_CLS_CODE','MRKT_TRTM_CLS_CODE','VI_STND_PRC']

def approval(appkey: str, secret: str) -> str:
    body=json.dumps({'grant_type':'client_credentials','appkey':appkey,'secretkey':secret}).encode()
    req=Request(REST+'/oauth2/Approval',data=body,headers={'content-type':'application/json'},method='POST')
    with urlopen(req,timeout=15) as r:
        data=json.loads(r.read().decode())
    key=data.get('approval_key')
    if not key: raise RuntimeError('approval_key 발급 실패: '+str(data))
    return key

def ensure_ws():
    try:
        import websocket
        return websocket
    except ImportError:
        print('[준비] websocket-client 설치 중...')
        subprocess.check_call([sys.executable,'-m','pip','install','websocket-client'])
        import websocket
        return websocket

def init_db():
    con=sqlite3.connect(DB)
    con.execute('''CREATE TABLE IF NOT EXISTS market_ticks(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      received_at_utc TEXT NOT NULL,
      received_at_kst TEXT NOT NULL,
      source TEXT NOT NULL,
      market TEXT NOT NULL,
      symbol TEXT NOT NULL,
      exchange_time TEXT,
      price REAL NOT NULL,
      change_pct REAL,
      volume REAL,
      cumulative_volume REAL,
      ask1 REAL,
      bid1 REAL,
      raw TEXT NOT NULL
    )''')
    con.execute('CREATE INDEX IF NOT EXISTS idx_ticks_symbol_time ON market_ticks(symbol, received_at_utc)')
    con.commit(); return con

def fnum(x):
    try: return float(x)
    except: return None

def main():
    print('A.N.T KIS NXT 실시간 수신 검증 - SK하이닉스(000660)')
    print('APP Key/Secret은 화면 입력에만 사용하며 파일/DB에 저장하지 않습니다.')
    appkey=input('KIS 실전 APP Key: ').strip()
    secret=getpass.getpass('KIS 실전 APP Secret: ').strip()
    if not appkey or not secret: raise SystemExit('Key/Secret이 비어 있습니다.')
    print('[1/3] WebSocket approval_key 발급...')
    akey=approval(appkey,secret)
    print('[OK] approval_key 발급 성공')
    websocket=ensure_ws()
    con=init_db()
    sub=json.dumps({'header':{'approval_key':akey,'custtype':'P','tr_type':'1','content-type':'utf-8'},'body':{'input':{'tr_id':TR_ID,'tr_key':SYMBOL}}})
    count=0
    def on_open(ws):
        print('[2/3] KIS 실전 WebSocket 연결 성공')
        ws.send(sub)
        print('[3/3] H0NXCNT0 / 000660 NXT 구독 요청 완료 - 체결 대기 중...')
    def on_message(ws,msg):
        nonlocal count
        if msg.startswith('0|'):
            parts=msg.split('|',3)
            if len(parts)<4 or parts[1] != TR_ID: return
            vals=parts[3].split('^')
            d={COLS[i]: vals[i] if i < len(vals) else '' for i in range(len(COLS))}
            price=fnum(d['STCK_PRPR'])
            if price is None: return
            now=datetime.now(timezone.utc); kst=now.astimezone(KST)
            con.execute('''INSERT INTO market_ticks(received_at_utc,received_at_kst,source,market,symbol,exchange_time,price,change_pct,volume,cumulative_volume,ask1,bid1,raw)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''',(
                now.isoformat(timespec='milliseconds'),kst.isoformat(timespec='milliseconds'),'KIS','NXT',SYMBOL,
                d['STCK_CNTG_HOUR'],price,fnum(d['PRDY_CTRT']),fnum(d['CNTG_VOL']),fnum(d['ACML_VOL']),
                fnum(d['ASKP1']),fnum(d['BIDP1']),parts[3]))
            con.commit(); count+=1
            print(f"[{kst.strftime('%H:%M:%S.%f')[:-3]} KST] NXT 000660 {price:,.0f}원  등락 {fnum(d['PRDY_CTRT']) or 0:+.2f}%  체결량 {fnum(d['CNTG_VOL']) or 0:,.0f}  저장 #{count}")
        elif msg.startswith('{'):
            try:
                j=json.loads(msg); h=j.get('header',{}); b=j.get('body',{})
                code=b.get('rt_cd')
                text=b.get('msg1') or b.get('msg_cd') or ''
                if code is not None: print(f"[KIS] tr_id={h.get('tr_id','')} rt_cd={code} {text}")
            except Exception: pass
    def on_error(ws,err): print('[WebSocket ERROR]',err)
    def on_close(ws,status,msg): print(f'[WebSocket 종료] status={status} {msg or ""}')
    app=websocket.WebSocketApp(WS,on_open=on_open,on_message=on_message,on_error=on_error,on_close=on_close)
    try: app.run_forever(ping_interval=30,ping_timeout=10)
    except KeyboardInterrupt: print('\n사용자 종료')
    finally: con.close(); print('저장 DB:',DB)

if __name__=='__main__': main()
