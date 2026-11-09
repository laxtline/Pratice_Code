"""Start the local compiler once and open it; optionally stop its server."""
from pathlib import Path
from urllib.request import Request, urlopen
import argparse
import json
import os
import subprocess
import sys
import time
import webbrowser

ROOT=Path(__file__).resolve().parent
URL='http://127.0.0.1:8000'

def running():
    try:
        with urlopen(URL+'/api/health',timeout=1) as response:
            return json.load(response).get('app')=='programiz-local'
    except Exception:
        return False

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--no-browser',action='store_true')
    parser.add_argument('--stop',action='store_true')
    args=parser.parse_args()
    if args.stop:
        if running():
            request=Request(URL+'/api/shutdown',data=b'{}',headers={'Content-Type':'application/json','X-Local-Compiler':'1'})
            with urlopen(request,timeout=5):
                pass
            print('Local compiler stopped.')
        else:
            print('Local compiler is not running.')
        sys.exit()
    if not running():
        (ROOT/'data').mkdir(exist_ok=True)
        with (ROOT/'data'/'server.log').open('ab') as log:
            process=subprocess.Popen([sys.executable,str(ROOT/'server.py')],cwd=ROOT,
                stdin=subprocess.DEVNULL,stdout=log,stderr=log,close_fds=True,
                creationflags=(subprocess.CREATE_NO_WINDOW|subprocess.CREATE_NEW_PROCESS_GROUP) if os.name=='nt' else 0,
                start_new_session=os.name!='nt')
        (ROOT/'data'/'server.pid').write_text(str(process.pid))
        for _ in range(50):
            if running():break
            if process.poll() is not None:
                raise SystemExit('Server could not start. Check data/server.log; another app may use port 8000.')
            time.sleep(.1)
        else:
            raise SystemExit('Server did not become ready. Check data/server.log.')
    print('Local compiler is running at '+URL)
    if not args.no_browser:
        webbrowser.open(URL+'/?lang=python',new=2)
