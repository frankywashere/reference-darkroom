import io
import tempfile
import time
import unittest
from pathlib import Path
from PIL import Image
from catalog import Catalog
from preview_cache import PreviewCache
from import_jobs import ImportJobs


class ScreenPreviewTests(unittest.TestCase):
    def test_persistent_preview_and_invalidation(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'source.png';Image.new('RGB',(2400,1600),'red').save(p)
            c=PreviewCache(Path(td)/'cache','v1');r={'exposure':1}
            data,kind,key=c.lookup(p,r)
            self.assertEqual(kind,'camera');self.assertEqual(Image.open(io.BytesIO(data)).size,(1800,1200))
            c.put(key,data)
            self.assertEqual(PreviewCache(c.root,'v1').lookup(p,r)[1],'edited')
            self.assertNotEqual(c.key(p,{'exposure':2}),key)
            self.assertNotEqual(PreviewCache(c.root,'v2').key(p,r),key)
            Image.new('RGB',(2401,1600),'blue').save(p)
            self.assertNotEqual(c.key(p,r),key)
            with self.assertRaises(ValueError):c.put('../escape',data)


class ImportProgressTests(unittest.TestCase):
    def test_batches_preserve_edits_and_cancel(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);photos=root/'photos';photos.mkdir()
            for i in range(30):Image.new('RGB',(16,12),'red').save(photos/f'{i:02}.jpg')
            catalog=Catalog(root/'registry',root/'projects');p=catalog.create_empty('QA')
            jobs=ImportJobs(catalog);job={'id':'test','project_id':p['id'],'folder':str(photos),'status':'running','phase':'scanning','found':0,'done':0,'total':None,'added':0,'assets':[],'errors':[],'cancel':False};jobs.jobs['test']=job
            original=catalog.fingerprint;calls=0
            def fingerprint(path):
                nonlocal calls
                calls+=1
                if calls==2:
                    first=catalog.read(p['id'])['assets'][0]['id']
                    catalog.save_edits(p['id'],{first:{'rating':5,'recipe':{'exposure':1}}},first)
                return original(path)
            catalog.fingerprint=fingerprint;jobs.run('test',photos)
            saved=catalog.read(p['id']);self.assertEqual(len(saved['assets']),30)
            self.assertEqual(saved['photos'][saved['selected']]['rating'],5)
            self.assertEqual(jobs.snapshot('test')['status'],'complete')
            # A duplicate import is a no-op.
            job.update(assets=[],added=0,status='running',cancel=False);jobs.run('test',photos)
            self.assertEqual(jobs.snapshot('test')['added'],0)
            empty=catalog.create_empty('Cancel');job.update(project_id=empty['id'],assets=[],added=0,status='running',cancel=True)
            jobs.run('test',photos);self.assertEqual(jobs.snapshot('test')['status'],'cancelled')
            self.assertEqual(catalog.read(empty['id'])['assets'],[])
            jobs.pool.shutdown()
