from pathlib import Path
import subprocess, sys, time, webbrowser, urllib.request

ROOT=Path(__file__).resolve().parent
URL='http://127.0.0.1:8765'

def healthy():
    try:
        with urllib.request.urlopen(URL+'/api/health',timeout=.7) as r:
            return r.status==200
    except: return False

def main():
    opened=False
    while True:
        if healthy():
            if not opened:
                webbrowser.open(URL); opened=True
            time.sleep(1); continue
        p=subprocess.Popen([sys.executable,str(ROOT/'server.py')],cwd=str(ROOT))
        for _ in range(30):
            if healthy():
                if not opened: webbrowser.open(URL); opened=True
                break
            if p.poll() is not None: break
            time.sleep(.2)
        code=p.wait()
        if code not in (42,0): time.sleep(2)
        else: time.sleep(.4)

if __name__=='__main__': main()
