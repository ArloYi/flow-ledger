"""Cross-build the Windows x64 launcher and user-scoped setup executable."""
import argparse
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import zipfile
root=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--runtime',type=Path,required=True);p.add_argument('--go',default='go');p.add_argument('--icon',type=Path,required=True);p.add_argument('--output',type=Path,default=root/'dist');args=p.parse_args()
out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory() as temporary:
    temp=Path(temporary);code=temp/'code';shutil.copytree(root/'platforms/windows',code)
    app=temp/'payload';app.mkdir();(app/'resources').mkdir()
    env=dict(os.environ,GOOS='windows',GOARCH='amd64',CGO_ENABLED='0')
    def build(target,setup=False):
        flags='-H=windowsgui -s -w'+(' -X main.setup=true' if setup else '')
        subprocess.run([args.go,'build','-trimpath','-ldflags='+flags,'-o',str(target),'.'],cwd=code,env=env,check=True)
    (code/'payload.bin').write_bytes(b'placeholder');build(app/'FlowLedger.exe')
    shutil.copytree(args.runtime,app/'runtime')
    (app/'runtime/python313._pth').write_text('python313.zip\n.\n../resources\n',encoding='utf-8')
    for file in (root/'app/core').glob('*.py'):shutil.copy2(file,app/'resources'/file.name)
    shutil.copy2(root/'app/ui/index.html',app/'resources/index.html')
    png=args.icon.read_bytes();(app/'AppIcon.ico').write_bytes(struct.pack('<HHHBBBBHHII',0,1,1,0,0,0,0,1,32,len(png),22)+png)
    shutil.copytree(root/'third_party',app/'licenses');shutil.copy2(root/'LICENSE',app/'LICENSE')
    (app/'.flow-ledger-install').write_text('FlowLedger 1.5.0-beta.1\n')
    (app/'README.txt').write_text('流量手账 Windows x64 预览版\n双击 FlowLedger.exe 启动，托盘右键打开菜单。Windows 10/11，独立窗口使用系统 Edge；未安装 Edge 时使用默认浏览器。\n运行环境已随包携带，无需安装 Python。数据仅保存到当前用户本地目录。\n此版本无数字签名，Windows 可能提示未知发布者。\n',encoding='utf-8')
    archive=out/'FlowLedger-1.5.0-beta.1-Windows-x64-portable.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for file in sorted(app.rglob('*')):
            if file.is_file():z.write(file,file.relative_to(app).as_posix())
    shutil.copy2(archive,code/'payload.bin')
    build(out/'FlowLedger-1.5.0-beta.1-Windows-x64-Setup.exe',setup=True)
print('Windows installer and portable archive built')
