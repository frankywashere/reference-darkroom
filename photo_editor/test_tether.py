import tempfile
import unittest
from pathlib import Path
from PIL import Image
from catalog import Catalog
from tether import NikonTether

class TetherTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.catalog=Catalog(self.root/'catalog',self.root/'projects')
        self.project=self.catalog.create_empty('Tether test')
        self.tether=NikonTether(self.root/'data',self.catalog)

    def tearDown(self):
        self.tether.close();self.tether.worker.join(timeout=3)
        self.temp.cleanup()

    def test_presence_check_does_not_restart_disconnected_helper(self):
        def unexpected(*args, **kwargs):raise AssertionError('Disconnected helper restarted')
        self.tether.command=unexpected
        self.tether._check_presence()

    def test_closed_service_rejects_commands(self):
        from tether import TetherError
        self.tether.closed=True
        with self.assertRaises(TetherError):self.tether.command('devices')

    def session(self):
        folder=self.root/'captures';folder.mkdir(exist_ok=True)
        return {'id':'test-session','project_id':self.project['id'],'project_name':self.project['name'],
                'destination':str(folder),'recipe':self.tether.starting_recipe({'exposure':.7})}

    def test_switch_routes_future_captures_and_keeps_live_session(self):
        self.tether.session=self.session();self.tether.connected=True;self.tether.live=True
        second=self.catalog.create_empty('Second project')
        old_destination=self.tether.session['destination']
        self.tether.retarget(second['id'])
        file=Path(old_destination)/'new.jpg';Image.new('RGB',(20,20)).save(file)
        self.tether._transfer_started();self.tether._capture_received(file.name);self.tether.jobs.join()
        self.assertTrue(self.tether.live);self.assertTrue(self.tether.connected)
        self.assertEqual(self.tether.session['destination'],old_destination)
        self.assertEqual(len(self.catalog.read(second['id'])['assets']),1)
        self.assertEqual(len(self.catalog.read(self.project['id'])['assets']),0)

    def test_switch_during_transfer_keeps_old_route_and_recipe(self):
        self.tether.session=self.session();self.tether.connected=True
        second=self.catalog.create_empty('Second project')
        self.tether._transfer_started();self.tether.retarget(second['id'])
        file=Path(self.tether.session['destination'])/'old.jpg';Image.new('RGB',(20,20)).save(file)
        self.tether._capture_received(file.name);self.tether.jobs.join()
        self.assertEqual(len(self.catalog.read(self.project['id'])['assets']),1)
        self.assertEqual(len(self.catalog.read(second['id'])['assets']),0)

    def test_raw_jpg_siblings_keep_same_project_when_switching(self):
        self.tether.session=self.session();self.tether.connected=True
        second=self.catalog.create_empty('Second project')
        root=Path(self.tether.session['destination'])
        raw=root/'DSC_001.001.nef';raw.write_bytes(b'II*\x00'+b'0'*100)
        jpg=root/'DSC_001.001.jpg';Image.new('RGB',(20,20)).save(jpg)
        self.tether._transfer_started();self.tether._capture_received(raw.name)
        self.tether.retarget(second['id']);self.tether._transfer_started();self.tether._capture_received(jpg.name)
        self.tether.jobs.join()
        self.assertEqual(len(self.catalog.read(self.project['id'])['assets']),2)
        self.assertEqual(len(self.catalog.read(second['id'])['assets']),0)

    def test_completed_capture_is_deduplicated_and_keeps_recipe(self):
        session=self.session();file=Path(session['destination'])/'shot.jpg'
        Image.new('RGB',(30,20),'red').save(file)
        for name in [str(file),file.name]:self.tether.jobs.put((session,name))
        self.tether.jobs.join()
        project=self.catalog.read(self.project['id'])
        self.assertEqual(len(project['assets']),1)
        self.assertEqual(project['photos'][project['assets'][0]['id']]['recipe']['exposure'],.7)
        self.assertFalse(project['photos'][project['assets'][0]['id']]['recipe']['camera_look_enabled'])
        self.assertEqual(sum(e['kind']=='imported' for e in self.tether.events),1)

    def test_incomplete_and_outside_files_are_not_imported(self):
        session=self.session();bad=Path(session['destination'])/'bad.jpg';bad.write_bytes(b'\xff\xd8bad')
        outside=self.root/'outside.jpg';Image.new('RGB',(20,20)).save(outside)
        for file in [bad,outside]:self.tether.jobs.put((session,str(file)))
        self.tether.jobs.join()
        self.assertEqual(self.catalog.read(self.project['id'])['assets'],[])
        self.assertEqual(sum(e['kind']=='error' for e in self.tether.events),2)

    def test_recipe_transfers_global_look_without_spatial_edits(self):
        r=self.tether.starting_recipe({'exposure':1.2,'crop':[.2,.2,.3,.3],
            'masks':[{'type':'brush'}],'clone_layers':[{'name':'Clone'}],'rotation':90})
        self.assertEqual(r['exposure'],1.2)
        self.assertEqual(r['crop'],[0,0,1,1]);self.assertEqual(r['masks'],[])
        self.assertEqual(r['clone_layers'],[]);self.assertEqual(r['rotation'],0)

if __name__=='__main__':unittest.main()
