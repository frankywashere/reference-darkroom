import tempfile
import unittest
from pathlib import Path
from catalog import Catalog
from engine import path_id


class CatalogTests(unittest.TestCase):
    def test_remove_keeps_files_and_reimport_restores_library(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);store=Catalog(root/'index');p=store.create_empty('Keep me')
            path=store._path(p['id']);original=path.read_bytes()
            # Legacy copies must not make removed projects reappear.
            (store.directory/(p['id']+'.json')).write_bytes(original)
            store.forget(p['id'])
            self.assertEqual(Catalog(root/'index').listing(), [])
            self.assertEqual(path.read_bytes(), original)
            with self.assertRaises(ValueError):store.save_edits(p['id'],{},None)
            self.assertEqual(store.import_catalog(path)['id'], p['id'])
            self.assertEqual(len(store.listing()),1)

    def test_missing_catalog_recovery_preserves_memory_edits(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);store=Catalog(root/'index');source=root/'originals';source.mkdir()
            image=source/'a.RAF';image.write_bytes(b'raw original')
            p=store.create(source,'Recover me');key=p['assets'][0]['id'];path=store._path(p['id'])
            snapshot={**p,'photos':{key:{'rating':5,'recipe':{'exposure':1.2,'masks':[{'type':'brush','strokes':[{'points':[[.2,.4]]}]}]}}}}
            path.rename(path.with_suffix('.moved'))
            self.assertFalse(store.status(p['id'])['available'])
            with self.assertRaises(FileNotFoundError):store.save_edits(p['id'],snapshot['photos'],key)
            self.assertFalse(path.exists())
            restored=store.recover(snapshot)
            self.assertNotEqual(restored['id'],p['id'])
            self.assertEqual(restored['photos'],snapshot['photos'])
            self.assertEqual(image.read_bytes(),b'raw original')

    def test_locate_checks_identity_and_preserves_missing_references(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);store=Catalog(root/'index');p=store.create_empty('Moved');other=store.create_empty('Other')
            with self.assertRaises(ValueError):store.locate(p['id'],store._path(other['id']))
            path=store._path(p['id']);moved=root/'moved.json';path.rename(moved)
            with self.assertRaises(ValueError):store.locate(p['id'],moved,['new-photo'])
            self.assertTrue(store.locate(p['id'],moved)['available'])
            self.assertEqual(store._path(p['id']),moved.resolve())

    def test_trash_moves_only_managed_project_and_can_be_imported_after_restore(self):
        from unittest.mock import patch
        import shutil
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);store=Catalog(root/'index');p=store.create_empty('Trash me');path=store._path(p['id']);destination=root/'Trash';destination.mkdir()
            def fake_trash(args,**kwargs):
                self.assertEqual(args[0],'/usr/bin/trash');shutil.move(args[1],destination)
            with patch('catalog.subprocess.run',side_effect=fake_trash):store.trash_project(p['id'])
            self.assertFalse(path.exists());self.assertEqual(store.listing(),[])
            trashed=destination/'Trash me'/'catalog.darkroom.json'
            self.assertTrue(trashed.exists())
            imported=store.import_catalog(trashed)
            self.assertTrue(store._path(imported['id']).exists())

    def test_trash_refuses_referenced_originals_and_unmanaged_folders(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);store=Catalog(root/'index');p=store.create_empty('Original inside');folder=store._path(p['id']).parent
            (folder/'a.jpg').write_bytes(b'original');store.add(p['id'],folder)
            with patch('catalog.subprocess.run') as trash:
                with self.assertRaises(ValueError):store.trash_project(p['id'])
                trash.assert_not_called()
            self.assertTrue((folder/'a.jpg').exists())
            other=store.create_empty('Unmanaged');path=store._path(other['id']);moved=root/'catalog.darkroom.json';path.rename(moved);store.locate(other['id'],moved)
            with self.assertRaises(ValueError):store.trash_project(other['id'])

    def test_empty_projects_get_separate_named_folders(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            store = Catalog(root / 'index', root / 'Projects')
            one = store.create_empty('New shoot')
            two = store.create_empty('New shoot')
            a, b = store.open(one['id']), store.open(two['id'])
            self.assertEqual(a['files'], [])
            self.assertEqual(a['saved']['photos'], {})
            self.assertEqual(Path(a['catalog_path']).name, 'catalog.darkroom.json')
            self.assertNotEqual(a['project_folder'], b['project_folder'])
            self.assertTrue(Path(a['catalog_path']).is_file())

    def test_portable_catalog_reconnects_on_another_machine_without_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / 'originals'
            source.mkdir()
            (source / 'a.RAF').write_bytes(b'original camera bytes')
            first = Catalog(root / 'machine1' / 'index')
            p = first.create(source, 'Shoot')
            key = p['assets'][0]['id']
            edits = {key:{'rating':4,'recipe':{'exposure':.7,'crop':[.1,.2,.6,.7],'masks':[{'name':'Face','type':'brush','strokes':[{'points':[[.3,.4]]}]}]}}}
            first.save_edits(p['id'], edits, key)
            transfer = root / 'transfer.json'
            transfer.write_bytes(first._path(p['id']).read_bytes())
            moved = root / 'new-machine-originals'
            source.rename(moved)
            second = Catalog(root / 'machine2' / 'index')
            imported = second.import_catalog(transfer)
            opened = second.open(imported['id'])
            self.assertTrue(opened['files'][0]['missing'])
            self.assertEqual(opened['saved']['photos'], edits)
            self.assertEqual(second.reconnect(imported['id'], moved)['reconnected'], 1)
            restored = second.open(imported['id'])
            self.assertEqual(restored['saved']['photos'], edits)
            self.assertFalse(restored['files'][0]['missing'])
            again = second.import_catalog(transfer)
            self.assertNotEqual(again['id'], imported['id'])
            self.assertEqual(second.read(imported['id'])['photos'], edits)
            self.assertFalse(list(Path(restored['project_folder']).glob('*.RAF')))

    def test_legacy_catalog_migration_preserves_identity_and_recovery_file(self):
        with tempfile.TemporaryDirectory() as td:
            import json
            root = Path(td)
            store = Catalog(root / 'index')
            pid = 'a'*32
            legacy = {'id':pid,'name':'Legacy','source':'','roots':[],'assets':[],'photos':{},'selected':None}
            old = root / 'index' / f'{pid}.json'
            old.write_text(json.dumps(legacy))
            opened = store.open(pid)
            self.assertEqual(opened['project_id'], pid)
            self.assertTrue(old.is_file())
            self.assertNotEqual(Path(opened['catalog_path']), old)
            self.assertEqual(len(store.listing()), 1)

    def test_invalid_catalog_does_not_create_project(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            store = Catalog(root / 'index')
            bad = root / 'bad.json'
            bad.write_text('{"name":"bad","assets":[{}],"photos":{}}')
            with self.assertRaises(ValueError):
                store.import_catalog(bad)
            self.assertEqual(store.listing(), [])

    def test_brush_properties_survive_restart(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            folder = root / 'photos'
            folder.mkdir()
            (folder / 'a.jpg').write_bytes(b'image data')
            catalog = Catalog(root / 'catalog')
            project = catalog.create(folder, 'Brush test')
            key = project['assets'][0]['id']
            mask = {'type':'brush','name':'Face','enabled':False,'amount':45,'exposure':.3,'strokes':[{'points':[[.2,.4],[.3,.4]],'size':.1,'feather':65,'flow':50,'opacity':80,'erase':False}]}
            catalog.save_edits(project['id'], {key:{'recipe':{'masks':[mask]}}}, key)
            reopened = Catalog(root / 'catalog').open(project['id'])
            self.assertEqual(reopened['saved']['photos'][key]['recipe']['masks'][0], mask)

    def test_saved_edits_survive_restart_and_are_project_specific(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            folder = root / 'photos'
            folder.mkdir()
            (folder / 'a.jpg').write_bytes(b'image data')
            store = Catalog(root / 'catalog')
            first, second = store.create(folder, 'One'), store.create(folder, 'Two')
            key = first['assets'][0]['id']
            store.save_edits(first['id'], {key: {'rating': 5, 'recipe': {'exposure': .75, 'crop': [.1, .1, .8, .8]}}}, key)
            reopened = Catalog(root / 'catalog').open(first['id'])
            self.assertEqual(reopened['saved']['selected'], key)
            self.assertEqual(reopened['saved']['photos'][key]['recipe']['exposure'], .75)
            self.assertEqual(store.open(second['id'])['saved']['photos'], {})

    def test_move_rename_restart_preserves_edits(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            folder = root / 'shoot'
            folder.mkdir()
            photo = folder / 'a.RAF'
            photo.write_bytes(b'original raw bytes')
            store = Catalog(root / 'catalog')
            p = store.create(folder, 'Shoot', {'photos': {path_id(photo): {'recipe': {'exposure': 1.25, 'masks': [{'type': 'ellipse'}]}, 'rating': 4}}})
            asset = p['assets'][0]
            moved = root / 'renamed'
            folder.rename(moved)
            (moved / 'a.RAF').rename(moved / 'b.RAF')
            restored = Catalog(root / 'catalog').open(p['id'])
            self.assertEqual(restored['files'][0]['id'], asset['id'])
            self.assertEqual(restored['files'][0]['path'], str((moved / 'b.RAF').resolve()))
            self.assertEqual(restored['saved']['photos'][asset['id']]['recipe']['exposure'], 1.25)
            self.assertEqual((moved / 'b.RAF').read_bytes(), b'original raw bytes')

    def test_duplicate_content_is_not_silently_relinked(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / 'source'
            source.mkdir()
            photo = source / 'a.jpg'
            photo.write_bytes(b'photo')
            store = Catalog(root / 'catalog')
            p = store.create(source)
            photo.unlink()
            dest = root / 'destination'
            dest.mkdir()
            (dest / 'b.jpg').write_bytes(b'photo')
            (dest / 'c.jpg').write_bytes(b'photo')
            report = store.reconnect(p['id'], str(dest))
            self.assertEqual(report, {'reconnected': 0, 'ambiguous': 1, 'missing': 1})

    def test_same_name_different_content_not_relinked_and_import_deduplicated(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / 'source'
            source.mkdir()
            photo = source / 'a.jpg'
            photo.write_bytes(b'first')
            store = Catalog(root / 'catalog')
            p = store.create(source)
            self.assertEqual(len(store.add(p['id'], source)['assets']), 1)
            photo.unlink()
            dest = root / 'destination'
            dest.mkdir()
            (dest / 'a.jpg').write_bytes(b'other')
            self.assertEqual(store.reconnect(p['id'], str(dest))['reconnected'], 0)
