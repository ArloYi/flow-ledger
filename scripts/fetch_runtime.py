"""Fetch a pinned runtime; verify SHA-256 before extracting."""
import argparse
import hashlib
import json
from pathlib import Path
import tarfile
import tempfile
import urllib.request
import zipfile
root=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('platform',choices=['macos','windows']);p.add_argument('--dest',type=Path,required=True);a=p.parse_args()
name='python-mac.tar.gz' if a.platform=='macos' else 'python-win.zip'
entry=next(x for x in json.loads((root/'third_party/runtime-lock.json').read_text()) if x['name']==name)
with tempfile.TemporaryDirectory() as directory:
    file=Path(directory)/name
    with urllib.request.urlopen(entry['url'],timeout=60) as response,file.open('wb') as output:
        while chunk:=response.read(1024*1024):output.write(chunk)
    if hashlib.sha256(file.read_bytes()).hexdigest()!=entry['sha256']:raise SystemExit('Runtime checksum mismatch')
    a.dest.mkdir(parents=True,exist_ok=True)
    if name.endswith('.zip'):
        with zipfile.ZipFile(file) as archive:archive.extractall(a.dest)
    else:
        with tarfile.open(file) as archive:archive.extractall(a.dest,filter='data')
print('Verified runtime extracted')
