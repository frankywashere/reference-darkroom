"""Progressive, cancellable reference imports. Fingerprinting never holds the catalog lock."""
import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from engine import IMAGE_SUFFIXES


class ImportJobs:
    def __init__(self,catalog):
        self.catalog=catalog;self.lock=threading.RLock();self.jobs={};self.pool=ThreadPoolExecutor(max_workers=1)

    def start(self,project_id,folder):
        root=Path(folder).expanduser().resolve()
        if not root.is_dir():raise ValueError('Folder is offline or missing')
        self.catalog.read(project_id)
        with self.lock:
            if any(j['project_id']==project_id and j['status']=='running' for j in self.jobs.values()):raise ValueError('An import is already running for this project')
            # Completed status records are disposable; bound session memory.
            for old in list(self.jobs):
                if len(self.jobs)<30:break
                if self.jobs[old]['status']!='running':self.jobs.pop(old)
            key=uuid.uuid4().hex
            self.jobs[key]={'id':key,'project_id':project_id,'folder':str(root),'status':'running','phase':'scanning','found':0,'done':0,'total':None,'added':0,'assets':[],'errors':[],'cancel':False}
        self.pool.submit(self.run,key,root);return {'job_id':key}

    def snapshot(self,key):
        with self.lock:
            j=self.jobs[key];return {**j,'assets':list(j['assets']),'errors':list(j['errors'])}

    def cancel(self,key):
        with self.lock:self.jobs[key]['cancel']=True
        return self.snapshot(key)

    def run(self,key,root):
        def update(**kw):
            with self.lock:self.jobs[key].update(kw)
        def cancelled():
            with self.lock:return self.jobs[key]['cancel']
        j=self.snapshot(key);project=j['project_id'];pending=[]
        def commit():
            if not pending:return
            with self.catalog.lock:
                p=self.catalog.read(project);known={a['path'] for a in p['assets']}
                batch=[a for a in pending if a['path'] not in known];p['assets'].extend(batch)
                if str(root) not in p['roots']:p['roots'].append(str(root))
                if not p['source']:p['source']=str(root)
                self.catalog.write(p)
            with self.lock:self.jobs[key]['assets'].extend(batch);self.jobs[key]['added']+=len(batch)
            pending.clear()
        try:
            with self.catalog.lock:known={a['path'] for a in self.catalog.read(project)['assets']}
            paths=[]
            def scan_error(exc):
                with self.lock:self.jobs[key]['errors'].append(str(exc))
            for directory,dirs,files in os.walk(root,onerror=scan_error):
                if cancelled():break
                dirs[:]=sorted(d for d in dirs if not d.startswith('.'))
                for name in sorted(files):
                    if cancelled():break
                    p=Path(directory)/name
                    if p.suffix.lower() in IMAGE_SUFFIXES and str(p) not in known:paths.append(p)
                    update(found=len(paths))
            update(phase='adding',total=len(paths))
            for i,path in enumerate(paths):
                if cancelled():break
                try:
                    s=path.stat();fingerprint=self.catalog.fingerprint(path)
                    after=path.stat()
                    if (s.st_size,s.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):raise ValueError(f'File changed during import: {path.name}')
                    pending.append({'id':uuid.uuid4().hex,'path':str(path),'name':path.name,'type':path.suffix[1:].upper(),'bytes':s.st_size,'fingerprint':fingerprint})
                except (OSError,ValueError) as exc:scan_error(exc)
                if len(pending)>=12 or i==0:commit()
                update(done=i+1)
            if not cancelled():commit()
            update(status='cancelled' if cancelled() else 'complete',phase='finished')
        except Exception as exc:
            with self.lock:self.jobs[key]['errors'].append(str(exc))
            update(status='failed',phase='finished')
