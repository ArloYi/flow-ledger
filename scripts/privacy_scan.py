"""Fail on private runtime files or known personal strings. Never prints matches."""
import argparse
import json
from pathlib import Path
import re
import sys
import zipfile
import io
parser=argparse.ArgumentParser();parser.add_argument('root',type=Path);parser.add_argument('--known-private',type=Path);parser.add_argument('--source',action='store_true');args=parser.parse_args()
known=json.loads(args.known_private.read_text()) if args.known_private else []
needles=[text.encode(encoding) for text in known for encoding in ('utf-8','utf-16-le') if text]
patterns=[('private-key',re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----')),('github-token',re.compile(rb'gh[pousr]_[A-Za-z0-9]{30,}')),('cloud-key',re.compile(rb'AKIA[0-9A-Z]{16}')),('personal-home',re.compile(rb'/Users/[^/\s\x00]{1,80}/(?:Documents|Desktop|Library|\.codex)/'))]
issues=[];checked=0

def scan(name,data,depth=0):
    global checked
    checked+=1
    for index,needle in enumerate(needles):
        if needle in data:issues.append({'path':name,'rule':'known-private-value'}) ;break
    for label,pattern in patterns:
        if pattern.search(data):issues.append({'path':name,'rule':label})
    if depth<2 and data[:4]==b'PK\x03\x04':
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                for info in archive.infolist():
                    if not info.is_dir():scan(name+'!/'+info.filename,archive.read(info),depth+1)
        except zipfile.BadZipFile:issues.append({'path':name,'rule':'invalid-archive'})

for file in sorted(args.root.rglob('*')):
    if not file.is_file() or file.is_symlink():continue
    path=file.relative_to(args.root)
    if '.git' in path.parts:continue
    if args.source and any(p in ('dist','.build','local-archive','backups','__pycache__') for p in path.parts):continue
    if file.suffix.lower() in ('.sqlite','.sqlite3','.db','.log') or '.data' in path.parts or file.name.startswith('.env'):
        issues.append({'path':str(path),'rule':'private-runtime-file'})
    scan(str(path),file.read_bytes())
print(json.dumps({'files_and_archive_entries_checked':checked,'issues':issues},ensure_ascii=False,indent=2))
sys.exit(bool(issues))
