"""Publish this project's releases; GCM credentials stay in memory."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

REPO='laxtline/Pratice_Code'
ROOT='/repos/'+REPO

def credential():
    result=subprocess.run(['git','credential','fill'],input='protocol=https\nhost=github.com\nusername=laxtline\n\n',text=True,capture_output=True,
        env=dict(os.environ,GIT_TERMINAL_PROMPT='0',GCM_INTERACTIVE='never'))
    fields=dict(line.split('=',1) for line in result.stdout.splitlines() if '=' in line)
    if not fields.get('password'):raise RuntimeError('No saved GitHub sign-in is available.')
    return fields['password']

def api(token,path,method='GET',data=None,file=None):
    headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28','User-Agent':'LocalCodeCompilerPublisher'}
    body=None;stream=None
    if file:
        file=Path(file);stream=file.open('rb');body=stream
        headers.update({'Content-Type':'application/octet-stream','Content-Length':str(file.stat().st_size)})
    elif data is not None:body=json.dumps(data).encode();headers['Content-Type']='application/json'
    try:
        with urllib.request.urlopen(urllib.request.Request(path if path.startswith('https://') else 'https://api.github.com'+path,
            data=body,headers=headers,method=method),timeout=180) as response:
            raw=response.read();return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as error:
        raise RuntimeError('GitHub HTTP '+str(error.code)+': '+error.read().decode(errors='replace')[:1000]) from None
    finally:
        if stream:stream.close()

def get_release(token,tag):
    try:return api(token,ROOT+'/releases/tags/'+tag)
    except RuntimeError as error:
        if 'HTTP 404' not in str(error):raise
        matches=[r for r in api(token,ROOT+'/releases?per_page=100') if r['tag_name']==tag]
        return matches[0] if len(matches)==1 else None

def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['create','upload','publish','status','runs'])
    parser.add_argument('--tag',default='v1.2.0');parser.add_argument('--sha');parser.add_argument('--notes');parser.add_argument('--file')
    args=parser.parse_args();token=credential()
    if args.action=='create':
        current=get_release(token,args.tag)
        if current:
            print(json.dumps({'existing':True,'id':current['id'],'draft':current['draft']}));return
        if not args.sha or not args.notes:raise RuntimeError('--sha and --notes required')
        result=api(token,ROOT+'/releases','POST',{'tag_name':args.tag,'target_commitish':args.sha,
            'name':'Local Code Compiler '+args.tag.lstrip('v')+' — Output zoom and no word wrap',
            'body':Path(args.notes).read_text(encoding='utf-8'),'draft':True,'prerelease':False})
        print(json.dumps({k:result.get(k) for k in ['id','tag_name','draft','html_url']}))
    elif args.action=='upload':
        current=get_release(token,args.tag);file=Path(args.file);digest='sha256:'+hashlib.sha256(file.read_bytes()).hexdigest()
        if not current:raise RuntimeError('Create the release first.')
        for asset in current['assets']:
            if asset['name']==file.name:
                if asset.get('digest')==digest:print(json.dumps({'existing':True,'name':file.name}));return
                raise RuntimeError('A different asset with this name already exists.')
        result=api(token,current['upload_url'].split('{')[0]+'?name='+urllib.parse.quote(file.name),'POST',file=file)
        if result.get('digest') and result['digest']!=digest:raise RuntimeError('Release checksum mismatch.')
        print(json.dumps({k:result.get(k) for k in ['name','size','state','digest']}))
    elif args.action=='publish':
        current=get_release(token,args.tag);assets={a['name']:a for a in current['assets']}
        required=['Local-Code-Compiler-Setup.exe','Local-Code-Compiler.exe','Local-Code-Compiler-Windows-x64.zip','SHA256SUMS.txt']
        if any(name not in assets or assets[name]['state']!='uploaded' for name in required):raise RuntimeError('Downloads are not all ready.')
        result=api(token,ROOT+'/releases/'+str(current['id']),'PATCH',{'draft':False,'make_latest':'true'})
        print(json.dumps({k:result.get(k) for k in ['tag_name','draft','html_url','published_at']}))
    elif args.action=='status':
        current=get_release(token,args.tag)
        print(json.dumps({'release':{k:current.get(k) for k in ['tag_name','draft','target_commitish','html_url']} if current else None,
            'assets':[{k:a.get(k) for k in ['name','size','digest','browser_download_url']} for a in current['assets']] if current else []}))
    else:
        print(json.dumps({'runs':[{k:r.get(k) for k in ['id','name','head_sha','event','status','conclusion','html_url']} for r in api(token,ROOT+'/actions/runs?per_page=5')['workflow_runs']]}))

if __name__=='__main__':
    try:main()
    except Exception as error:print(str(error),file=sys.stderr);sys.exit(1)
