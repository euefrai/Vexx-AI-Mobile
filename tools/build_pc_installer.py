"""Build a self-contained, per-user Windows installer from public source only.

No operator settings, local Python installation or private data are packaged.
Pinned vendor downloads are hash checked; Microsoft's bootstrapper must be signed.
"""
import argparse
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import uuid
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from pc_companion import __version__
from pc_companion.release import bundle


def download(url, destination, expected=None):
    destination=Path(destination)
    if not destination.exists():
        temp=destination.with_suffix(destination.suffix+'.part')
        with urllib.request.urlopen(url,timeout=90) as response, temp.open('wb') as output:
            if response.status!=200:raise RuntimeError('Vendor download failed')
            shutil.copyfileobj(response,output)
        digest=hashlib.sha256(temp.read_bytes()).hexdigest()
        if expected and digest!=expected:raise ValueError('Vendor download checksum mismatch')
        temp.replace(destination)
    digest=hashlib.sha256(destination.read_bytes()).hexdigest()
    if expected and digest!=expected:raise ValueError('Cached download checksum mismatch')
    return digest


def run(command, **kwargs):
    result=subprocess.run([str(c) for c in command],timeout=600,stdout=subprocess.PIPE,
                   stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0,**kwargs)
    if result.returncode:
        print(result.stdout.decode('utf-8',errors='replace')[-12000:],flush=True)
        result.check_returncode()


def main():
    sys.stdout.reconfigure(errors='replace')
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',default=str(ROOT/'output/windows-installer'))
    parser.add_argument('--iscc')
    args=parser.parse_args()
    if os.name!='nt':raise SystemExit('Windows is required to compile this installer.')
    output=Path(args.output).resolve();output.mkdir(parents=True,exist_ok=True)
    cache=output/'cache';cache.mkdir(exist_ok=True)
    build=output/('build-'+__version__+'-'+uuid.uuid4().hex[:8]);build.mkdir()
    payload=build/'payload';payload.mkdir()
    pins=json.loads((ROOT/'installer/sources.json').read_text('utf-8'))
    print('Preparing bundled Python '+pins['python']['version']+'...',flush=True)
    archive=cache/'python.tar.gz'
    download(pins['python']['url'],archive,pins['python']['sha256'])
    with tarfile.open(archive,'r:gz') as source:source.extractall(build/'python-extracted',filter='data')
    shutil.move(str(build/'python-extracted/python'),str(payload/'runtime'))
    python=payload/'runtime/python.exe'
    run([python,'-c','import sqlite3; c=sqlite3.connect(":memory:"); c.execute("CREATE VIRTUAL TABLE t USING fts5(name, tokenize=trigram)")'])
    wheels=cache/('wheels-'+hashlib.sha256((ROOT/'pc_companion/requirements.txt').read_bytes()).hexdigest()[:12])
    wheels.mkdir(exist_ok=True)
    print('Collecting application dependencies for offline installation...',flush=True)
    run([python,'-m','pip','wheel','--disable-pip-version-check','--prefer-binary',
         '-r',ROOT/'pc_companion/requirements.txt','--wheel-dir',wheels])
    shutil.copytree(wheels,payload/'wheels')
    with zipfile.ZipFile(io.BytesIO(bundle())) as source:source.extractall(payload/'source')
    shutil.copy2(ROOT/'installer/bootstrap.py',payload/'bootstrap.py')
    # Reuse the existing application asset, without an image-generation dependency.
    from PIL import Image
    Image.open(ROOT/'public/icon-512.png').convert('RGBA').save(payload/'VexxPC.ico',format='ICO',sizes=[(16,16),(32,32),(48,48),(64,64),(256,256)])
    webview=cache/'MicrosoftEdgeWebview2Setup.exe'
    webview_hash=download(pins['webview2']['url'],webview)
    # Never execute or distribute a bootstrapper that failed vendor signature validation.
    signature_check=build/'verify-signature.ps1'
    signature_check.write_text("param([string]$Path)\nImport-Module \"$PSHOME\\Modules\\Microsoft.PowerShell.Security\\Microsoft.PowerShell.Security.psd1\" -ErrorAction Stop\n$s=Get-AuthenticodeSignature -LiteralPath $Path\nif($s.Status -ne 'Valid' -or $s.SignerCertificate.Subject -notmatch 'Microsoft'){exit 1}\n",'utf-8')
    run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',signature_check,'-Path',webview])
    shutil.copy2(webview,payload/webview.name)
    compiler=Path(args.iscc) if args.iscc else cache/'inno/ISCC.exe'
    if not compiler.is_file():
        compiler=cache/'inno/ISCC.exe'
        if not compiler.is_file():
            print('Preparing Inno Setup compiler...',flush=True)
            setup=cache/'inno-setup.exe';download(pins['inno']['url'],setup,pins['inno']['sha256'])
            run([setup,'/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/CURRENTUSER','/NOICONS',
                 '/DIR='+str(compiler.parent)])
    print('Compiling Vexx PC '+__version__+' installer...',flush=True)
    run([compiler,'/Qp','/DPayloadDir='+str(payload),'/DAppVersion='+__version__,
         '/DOutputDir='+str(output),ROOT/'installer/vexx-pc.iss'])
    executable=output/('Vexx-PC-Setup-'+__version__+'.exe')
    digest=hashlib.sha256(executable.read_bytes()).hexdigest()
    (output/'SHA256SUMS').write_text(digest+'  '+executable.name+'\n','utf-8')
    record={'version':__version__,'file':executable.name,'size':executable.stat().st_size,'sha256':digest,
            'bundled_python':pins['python']['version'],'webview2_bootstrapper_sha256':webview_hash,
            'payload':str(payload),'wheels':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in wheels.glob('*.whl')}}
    (output/'build.json').write_text(json.dumps(record,indent=2),'utf-8')
    print(json.dumps({k:record[k] for k in ('version','file','size','sha256')}),flush=True)


if __name__=='__main__':main()
