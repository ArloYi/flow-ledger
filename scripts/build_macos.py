"""Build an Apple Silicon app and drag-to-install DMG with a bundled runtime."""
import argparse
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import tempfile
root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('--runtime',type=Path,required=True);parser.add_argument('--output',type=Path,default=root/'dist');args=parser.parse_args()
out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
app=out/'流量手账.app';contents=app/'Contents';resources=contents/'Resources'
if app.exists():shutil.rmtree(app)
(contents/'MacOS').mkdir(parents=True);resources.mkdir()
def run(*command):subprocess.run([str(c) for c in command],check=True)
run('xcrun','swiftc',root/'platforms/macos/App.swift','-o',contents/'MacOS/NetworkMeter','-framework','AppKit','-framework','WebKit','-O','-target','arm64-apple-macos13.0','-debug-prefix-map',str(root)+'=.','-module-cache-path',out/'.swift-cache')
with tempfile.TemporaryDirectory() as temp:
    temp=Path(temp);run('xcrun','swiftc',root/'platforms/macos/Icon.swift','-o',temp/'make-icon');run(temp/'make-icon',temp/'AppIcon.iconset');run('iconutil','-c','icns',temp/'AppIcon.iconset','-o',resources/'AppIcon.icns')
    shutil.copy2(temp/'AppIcon.iconset/icon_256x256.png',out/'AppIcon.png')
for file in (root/'app/core').glob('*.py'):shutil.copy2(file,resources/file.name)
shutil.copy2(root/'app/ui/index.html',resources/'index.html')
shutil.copytree(args.runtime,resources/'runtime',symlinks=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
for folder in ['include','share/man']:
    path=resources/'runtime'/folder
    if path.exists():shutil.rmtree(path)
shutil.copytree(root/'third_party',resources/'licenses')
shutil.copy2(root/'LICENSE',resources/'LICENSE')
info={'CFBundleExecutable':'NetworkMeter','CFBundleIdentifier':'local.arlo.network-meter','CFBundleName':'流量手账','CFBundleDisplayName':'流量手账','CFBundlePackageType':'APPL','CFBundleShortVersionString':'1.5.0','CFBundleVersion':'8','CFBundleIconFile':'AppIcon','LSMinimumSystemVersion':'13.0','LSUIElement':True,'NSHighResolutionCapable':True,'NSAppTransportSecurity':{'NSAllowsLocalNetworking':True}}
(contents/'Info.plist').write_bytes(plistlib.dumps(info))
# Sign nested native code before the outer application. No Developer ID is available.
for file in sorted((resources/'runtime').rglob('*')):
    if not file.is_file() or file.is_symlink():continue
    with file.open('rb') as stream:magic=stream.read(4)
    if magic in (b'\xcf\xfa\xed\xfe',b'\xce\xfa\xed\xfe',b'\xca\xfe\xba\xbe'):
        run('codesign','--force','--sign','-',file)
run('codesign','--force','--sign','-',app)
run('codesign','--verify','--deep','--strict',app)
with tempfile.TemporaryDirectory() as temp:
    image=Path(temp);shutil.copytree(app,image/app.name,symlinks=True);(image/'Applications').symlink_to('/Applications')
    (image/'安装说明.txt').write_text('流量手账 1.5 预览版\n\n将应用拖到 Applications 后打开。需要 Apple Silicon Mac、macOS 13 或更高版本。\n运行时已随包携带，无需安装 Python。菜单栏点击可打开主界面。\n升级前请退出旧版本；真实流量数据存放在用户 Application Support 中，不包含在安装包。\n此版本未经过 Developer ID 签名与公证，macOS 可能阻止运行。\n卸载时退出应用、关闭菜单中的登录启动，再将应用移入废纸篓；历史数据默认保留。\n',encoding='utf-8')
    dmg=out/'FlowLedger-1.5.0-beta.1-macOS-arm64.dmg'
    if dmg.exists():dmg.unlink()
    run('hdiutil','create','-volname','流量手账','-srcfolder',image,'-ov','-format','UDZO',dmg)
print(dmg)
