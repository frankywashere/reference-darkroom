"""Disposable, versioned screen previews; never stores or modifies originals."""
import hashlib
import io
import json
import threading
import uuid
from pathlib import Path
from PIL import Image, ImageOps
from engine import embedded_thumbnail, jpeg_bytes, normalize_recipe


class PreviewCache:
    def __init__(self, root, renderer_version, budget=2 * 1024**3):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True)
        self.version=renderer_version;self.budget=budget;self.lock=threading.RLock()

    def key(self,path,recipe=None):
        source=Path(path).expanduser().resolve();s=source.stat()
        value=[str(source),s.st_size,s.st_mtime_ns,self.version,
               normalize_recipe(recipe) if recipe is not None else 'camera']
        return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()

    def file(self,key):
        if len(key)!=64 or any(c not in '0123456789abcdef' for c in key):
            raise ValueError('Invalid preview key')
        return self.root/(key+'.jpg')

    def get(self,key):
        with self.lock:
            p=self.file(key)
            if not p.exists():return None
            p.touch();return p.read_bytes()

    def put(self,key,payload):
        if len(payload)>24*1024**2:raise ValueError('Preview payload too large')
        with Image.open(io.BytesIO(payload)) as im:
            if im.width*im.height>2560**2:raise ValueError('Preview dimensions too large')
            image=ImageOps.exif_transpose(im).convert('RGB');image.thumbnail((2560,2560))
            encoded=jpeg_bytes(image,93)
        with self.lock:
            path=self.file(key);tmp=self.root/(uuid.uuid4().hex+'.tmp')
            try:tmp.write_bytes(encoded);tmp.replace(path)
            finally:tmp.unlink(missing_ok=True)
            files=sorted(self.root.glob('*.jpg'),key=lambda p:p.stat().st_mtime_ns)
            total=sum(p.stat().st_size for p in files)
            for p in files:
                if total<=self.budget:break
                if p==path:continue
                total-=p.stat().st_size;p.unlink()

    def lookup(self,path,recipe):
        key=self.key(path,recipe);cached=self.get(key)
        if cached:return cached,'edited',key
        camera_key=self.key(path);camera=self.get(camera_key)
        if camera is None:
            camera=jpeg_bytes(embedded_thumbnail(path,1800),93)
            self.put(camera_key,camera)
        return camera,'camera',key
