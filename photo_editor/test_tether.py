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

    def add_shot(self, name, exposure=0):
        file=Path(self.tether.session['destination'])/name;Image.new('RGB',(20,20)).save(file)
        return self.catalog.add_capture(self.project['id'],file,{'exposure':exposure},name)[0]

    def test_auto_look_defaults_on_and_latest_edits_reach_next_capture(self):
        self.assertTrue(self.tether.auto_look)
        self.tether.session=self.session();self.tether.connected=True
        old=self.add_shot('old.jpg');latest=self.add_shot('latest.jpg')
        photos={latest['id']:{'recipe':{'exposure':1.4,'contrast':30,'crop':[.1,.1,.8,.8],'rotation':90,'masks':[{'type':'brush'}],'clone_layers':[{'name':'Clone'}]}}}
        self.catalog.save_edits(self.project['id'],photos,latest['id'])
        self.tether.sync_saved_edits(self.project['id'],photos,latest['id'])
        r=self.tether.session['recipe'];self.assertEqual(r['exposure'],1.4);self.assertEqual(r['contrast'],30)
        self.assertEqual(r['crop'],[0,0,1,1]);self.assertEqual(r['rotation'],0);self.assertEqual(r['masks'],[]);self.assertEqual(r['clone_layers'],[])
        file=Path(self.tether.session['destination'])/'incoming.jpg';Image.new('RGB',(20,20)).save(file)
        self.tether._transfer_started();self.tether._capture_received(file.name);self.tether.jobs.join()
        p=self.catalog.read(self.project['id']);self.assertEqual(p['photos'][p['assets'][-1]['id']]['recipe']['exposure'],1.4)
        self.assertEqual(p['photos'][old['id']]['recipe']['exposure'],0)

    def test_auto_look_ignores_edits_to_older_shots(self):
        self.tether.session=self.session();self.tether.connected=True
        old=self.add_shot('old.jpg');self.add_shot('new.jpg')
        self.tether.sync_saved_edits(self.project['id'],{old['id']:{'recipe':{'exposure':4}}},old['id'])
        self.assertEqual(self.tether.session['recipe']['exposure'],.7)

    def test_auto_look_off_preserves_manual_look_and_preference(self):
        self.tether.session=self.session();self.tether.connected=True;latest=self.add_shot('new.jpg')
        self.tether.set_auto_look(False)
        self.tether.sync_saved_edits(self.project['id'],{latest['id']:{'recipe':{'exposure':4}}},latest['id'])
        self.assertEqual(self.tether.session['recipe']['exposure'],.7)
        other=NikonTether(self.root/'data',self.catalog)
        try:self.assertFalse(other.auto_look)
        finally:other.close();other.worker.join(timeout=3)

    def test_latest_raw_jpg_pair_can_sync_either_version(self):
        self.tether.session=self.session();self.tether.connected=True
        raw=Path(self.tether.session['destination'])/'DSC_001.001.nef';raw.write_bytes(b'II*\x00')
        asset=self.catalog.add_capture(self.project['id'],raw,{'exposure':0},'raw')[0]
        self.add_shot('DSC_001.001.jpg')
        self.tether.sync_saved_edits(self.project['id'],{asset['id']:{'recipe':{'exposure':2}}},asset['id'])
        self.assertEqual(self.tether.session['recipe']['exposure'],2)

    def test_enabling_auto_look_uses_latest_even_when_browsing_older(self):
        self.tether.session=self.session();self.tether.connected=True
        old=self.add_shot('old.jpg',4);latest=self.add_shot('new.jpg',1.2)
        self.catalog.save_edits(self.project['id'],{},old['id'])
        self.tether.set_auto_look(False);self.tether.set_auto_look(True)
        self.assertEqual(self.tether.session['recipe']['exposure'],1.2)

    def test_incoming_raw_preserves_camera_tone_toggle(self):
        session=self.session();session['recipe']['camera_look_enabled']=False
        file=Path(session['destination'])/'new.nef';file.write_bytes(b'II*\x00'+b'0'*100)
        self.tether.jobs.put((session,file.name));self.tether.jobs.join()
        p=self.catalog.read(self.project['id'])
        self.assertFalse(p['photos'][p['assets'][0]['id']]['recipe']['camera_look_enabled'])

if __name__=='__main__':unittest.main()
