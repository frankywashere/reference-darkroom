"""Install a user-supplied Nikon SDK locally; never commit Nikon's SDK files."""
import argparse
import io
import os
from pathlib import Path
import shutil
import subprocess
import zipfile

def unpack(archive, target, prefix):
    for info in archive.infolist():
        if not info.filename.startswith(prefix) or info.is_dir():
            continue
        relative=Path(info.filename)
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('Unsafe archive path')
        dest=target/relative
        dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_bytes(archive.read(info))

def install(source, data):
    root=Path(data).resolve()/'nikon'
    root.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(source) as sdk:
        unpack(sdk,root,'Module/Mac/HeaderFile/')
        binary=sdk.read('Module/Mac/BinaryFile/TestApp.zip')
        with zipfile.ZipFile(io.BytesIO(binary)) as runtime:
            unpack(runtime,root/'runtime','TestApp/')
    exe=root/'runtime/TestApp/TestApp/darkroom-nikon'
    profiles=Path.home()/'Library/Preferences/Nikon/NXTether'
    profiles.mkdir(parents=True,exist_ok=True)
    for name in ['DC_PTP_Config.config','MaidLayer.config','RangeValue.config']:
        src=exe.parent/name;dest=profiles/name
        if dest.exists() and dest.read_bytes()!=src.read_bytes():
            raise RuntimeError(f'Existing Nikon profile differs; kept it unchanged: {dest}')
        if not dest.exists():shutil.copy2(src,dest)
    compiler='/Library/Developer/CommandLineTools/usr/bin/clang++'
    headers=root/'Module/Mac/HeaderFile'
    bridge=Path(__file__).with_name('NikonBridge.mm')
    subprocess.run([compiler,'-std=c++17','-fobjc-arc','-mmacosx-version-min=13.0',
        '-isysroot','/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk',
        '-isystem','/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk/usr/include/c++/v1',
        '-I',str(headers),str(bridge),'-framework','Foundation','-framework','AppKit',
        '-framework','Carbon','-framework','CoreFoundation',
        '-Wl,-rpath,@executable_path/../Frameworks','-o',str(exe)],check=True)
    print(exe)
    return exe

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('sdk_zip');parser.add_argument('--data',default=str(Path(__file__).resolve().parent.parent/'photo_editor/editor_data'))
    args=parser.parse_args();install(args.sdk_zip,args.data)
