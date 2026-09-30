"""Persistent reference-only projects with stable asset IDs and safe relinking."""
import hashlib
import json
import os
import re
import subprocess
import threading
import uuid
from pathlib import Path

from engine import IMAGE_SUFFIXES, path_id


class Catalog:
    def __init__(self, directory, project_directory=None):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.project_directory = Path(project_directory or self.directory.parent / 'Project Library')

    def _locations(self):
        path = self.directory / '_locations.json'
        return json.loads(path.read_text()) if path.exists() else {}

    def _removed(self):
        path = self.directory / '_removed.json'
        return set(json.loads(path.read_text())) if path.exists() else set()

    def _set_removed(self, project_id, removed):
        ids = self._removed()
        ids.add(project_id) if removed else ids.discard(project_id)
        temporary = self.directory / '_removed.tmp'
        temporary.write_text(json.dumps(sorted(ids)))
        temporary.replace(self.directory / '_removed.json')

    def _register(self, project_id, path):
        locations = self._locations()
        locations[project_id] = str(path)
        temp = self.directory / '_locations.tmp'
        temp.write_text(json.dumps(locations, indent=2))
        temp.replace(self.directory / '_locations.json')

    def _path(self, project_id):
        if not project_id or any(c not in '0123456789abcdef' for c in project_id):
            raise ValueError('Invalid project ID')
        location = self._locations().get(project_id)
        return Path(location) if location else self.directory / (project_id + '.json')

    def read(self, project_id):
        if project_id in self._removed():
            raise ValueError('Project was removed from the library. Import its catalog to reopen it.')
        project = json.loads(self._path(project_id).read_text())
        if project.get('id') != project_id:
            raise ValueError('Catalog identity does not match this project')
        return project

    def write(self, project):
        if project['id'] in self._removed():
            raise ValueError('Project was removed from the library')
        path = self._path(project['id'])
        if not path.is_file():
            raise FileNotFoundError('Catalog disappeared. Locate it or save a recovery copy.')
        content = json.dumps(project, indent=2)
        if path.exists() and path.read_text() == content:
            return
        temporary = path.with_suffix('.tmp')
        with temporary.open('w') as stream:
            json.dump(project, stream, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        if not path.is_file():
            raise FileNotFoundError('Catalog disappeared during save. Save a recovery copy.')
        temporary.replace(path)

    def create_empty(self, name, parent=None):
        name = str(name or '').strip()
        if not name:
            raise ValueError('Enter a project name')
        base = Path(parent).expanduser().resolve() if parent else self.project_directory
        base.mkdir(parents=True, exist_ok=True)
        safe = re.sub(r'[^\w .-]', '_', name).strip(' .')[:100] or 'Untitled project'
        with self.lock:
            folder = base / safe
            number = 2
            while True:
                try:
                    folder.mkdir()
                    break
                except FileExistsError:
                    folder = base / f'{safe} ({number})'
                    number += 1
            p = {'format': 'reference-darkroom', 'version': 1, 'id': uuid.uuid4().hex,
                 'name': name, 'source': '', 'roots': [], 'assets': [], 'photos': {}, 'selected': None}
            path = folder / 'catalog.darkroom.json'
            # Publish in the local library only after the catalog exists.
            path.write_text(json.dumps(p, indent=2))
            (folder / '.darkroom-project').write_text(p['id'])
            self._register(p['id'], path)
            return p

    def ensure_folder(self, project_id):
        with self.lock:
            old_path = self._path(project_id)
            if old_path.parent != self.directory:
                marker = old_path.parent / '.darkroom-project'
                if old_path.is_file() and old_path.name == 'catalog.darkroom.json' and old_path.parent.parent == self.project_directory and not marker.exists():
                    marker.write_text(project_id)
                return old_path
            p = self.read(project_id)
            new = self.create_empty(p['name'])
            new_path = self._path(new['id'])
            p.update(format='reference-darkroom', version=1)
            new_path.write_text(json.dumps(p, indent=2))
            (new_path.parent / '.darkroom-project').write_text(project_id)
            locations = self._locations()
            locations.pop(new['id'])
            locations[project_id] = str(new_path)
            temp = self.directory / '_locations.tmp'
            temp.write_text(json.dumps(locations, indent=2))
            temp.replace(self.directory / '_locations.json')
            # Keep the legacy file as a recovery copy; the registry selects the new one.
            return new_path

    def import_catalog(self, filename):
        path = Path(filename).expanduser().resolve()
        if not path.is_file():
            raise ValueError('Choose a catalog JSON file')
        if path.stat().st_size > 100 * 1024 * 1024:
            raise ValueError('Catalog is larger than 100 MB')
        p = json.loads(path.read_text())
        if not isinstance(p, dict) or p.get('version', 1) != 1 or p.get('format', 'reference-darkroom') != 'reference-darkroom':
            raise ValueError('Unsupported catalog format or version')
        if not isinstance(p.get('name'), str) or not isinstance(p.get('assets'), list) or not isinstance(p.get('photos'), dict):
            raise ValueError('This file is not a project catalog')
        ids = set()
        for a in p['assets']:
            if not isinstance(a, dict) or not all(isinstance(a.get(k), str) for k in ('id', 'path', 'name', 'type', 'fingerprint')) or not isinstance(a.get('bytes'), int):
                raise ValueError('Invalid photo record in catalog')
            if a['id'] in ids or a['bytes'] < 0:
                raise ValueError('Invalid or duplicate photo record')
            ids.add(a['id'])
        for key, photo in p['photos'].items():
            if key not in ids or not isinstance(photo, dict) or not isinstance(photo.get('recipe', {}), dict):
                raise ValueError('Invalid photo settings in catalog')
        with self.lock:
            for project_id, location in self._locations().items():
                if Path(location).resolve() == path:
                    self._set_removed(project_id, False)
                    return self.read(project_id)
            # Never overwrite an existing project's edits when a copy has the same ID.
            new = self.create_empty(p['name'])
            p.update(id=new['id'], format='reference-darkroom', version=1)
            p['roots'] = []
            for a in p['assets']:
                source = Path(a['path']).expanduser()
                if not source.is_absolute():
                    source = path.parent / source
                a['path'] = str(source)
                try:
                    a['unverified'] = not (source.is_file() and self.fingerprint(source) == a['fingerprint'])
                except OSError:
                    a['unverified'] = True
                if not a['unverified'] and str(source.parent) not in p['roots']:
                    p['roots'].append(str(source.parent))
            p['source'] = p['roots'][0] if p['roots'] else ''
            p['selected'] = p.get('selected') if p.get('selected') in ids else None
            self.write(p)
            return p

    @staticmethod
    def fingerprint(path):
        # Size plus samples from three regions: bounded reads even for large RAFs.
        # Ambiguous matches are never automatically chosen.
        size = path.stat().st_size
        digest = hashlib.sha256(str(size).encode())
        with path.open('rb') as stream:
            for offset in sorted({0, max(0, size // 2 - 32768), max(0, size - 65536)}):
                stream.seek(offset)
                digest.update(stream.read(65536))
        return digest.hexdigest()

    def listing(self):
        with self.lock:
            result = []
            project_ids = {path.stem for path in self.directory.glob('*.json') if not path.name.startswith('_')}
            project_ids.update(self._locations())
            project_ids.difference_update(self._removed())
            for project_id in project_ids:
                try:
                    p = self.read(project_id)
                except (OSError, ValueError):
                    result.append({'id': project_id, 'name': self._path(project_id).parent.name + ' (catalog unavailable)', 'source': '', 'count': 0, 'missing': 0})
                    continue
                result.append({'id': p['id'], 'name': p['name'], 'source': p['source'],
                               'count': len(p['assets']),
                               'missing': sum(self._missing(a) for a in p['assets'])})
            return sorted(result, key=lambda p: p['name'].casefold())

    def status(self, project_id):
        with self.lock:
            path = self._path(project_id)
            try:
                self.read(project_id)
                return {'available': True, 'path': str(path)}
            except (OSError, ValueError) as exc:
                return {'available': False, 'path': str(path), 'detail': str(exc)}

    def forget(self, project_id):
        with self.lock:
            path = self._path(project_id)
            self._set_removed(project_id, True)
            return {'catalog_path': str(path)}

    def trash_project(self, project_id):
        with self.lock:
            path = self.ensure_folder(project_id)
            p = self.read(project_id)
            folder = path.parent.resolve()
            marker = folder / '.darkroom-project'
            if path.name != 'catalog.darkroom.json' or not marker.is_file() or marker.read_text() != project_id:
                raise ValueError('This folder is not a managed project folder. Use Remove from library instead.')
            if folder in (Path('/'), Path.home(), self.directory.resolve(), self.project_directory.resolve()):
                raise ValueError('Cannot trash this location')
            # A user may have manually placed originals inside a project folder.
            projects = [p]
            for location in self._locations().values():
                try:
                    projects.append(json.loads(Path(location).read_text()))
                except (ValueError, OSError):
                    continue
            for project in projects:
                for asset in project['assets']:
                    if Path(asset['path']).expanduser().resolve().is_relative_to(folder):
                        raise ValueError('This folder contains referenced originals. Use Remove from library instead.')
            subprocess.run(['/usr/bin/trash', str(folder)], check=True, timeout=30)
            self._set_removed(project_id, True)
            return {'folder': str(folder), 'recoverable': True}

    def locate(self, project_id, filename, asset_ids=None):
        with self.lock:
            path = Path(filename).expanduser().resolve()
            p = json.loads(path.read_text())
            if not isinstance(p, dict) or p.get('id') != project_id or not isinstance(p.get('assets'), list) or not isinstance(p.get('photos'), dict):
                raise ValueError('Choose the catalog for this same project. Use Import catalog for a different project.')
            if asset_ids and not set(asset_ids).issubset({a.get('id') for a in p['assets'] if isinstance(a, dict)}):
                raise ValueError('That catalog is missing photos in the open project. Save a recovery copy to preserve all current references and edits.')
            self._register(project_id, path)
            self._set_removed(project_id, False)
            return self.status(project_id)

    def recover(self, snapshot):
        if not isinstance(snapshot, dict) or not isinstance(snapshot.get('assets'), list) or not isinstance(snapshot.get('photos'), dict):
            raise ValueError('No valid project snapshot is available')
        ids = set()
        for a in snapshot['assets']:
            if not isinstance(a, dict) or not all(isinstance(a.get(k), str) for k in ('id','path','name','type','fingerprint')) or not isinstance(a.get('bytes'), int) or a['id'] in ids:
                raise ValueError('Invalid photo reference in recovery snapshot')
            ids.add(a['id'])
        if any(k not in ids or not isinstance(v, dict) or not isinstance(v.get('recipe', {}), dict) for k,v in snapshot['photos'].items()):
            raise ValueError('Invalid edits in recovery snapshot')
        with self.lock:
            p = self.create_empty(str(snapshot.get('name') or 'Project') + ' (Recovered)')
            p.update(assets=snapshot['assets'], photos=snapshot['photos'],
                     roots=sorted({str(Path(a['path']).parent) for a in snapshot['assets']}),
                     source=str(snapshot.get('source') or ''), selected=snapshot.get('selected') if snapshot.get('selected') in ids else None)
            self.write(p)
            return p

    def create(self, source, name=None, legacy=None):
        source = Path(source).expanduser().resolve()
        if not source.is_dir():
            raise ValueError('Choose an available photo folder')
        with self.lock:
            project = self.create_empty(name or source.name)
            return self.add(project['id'], str(source), legacy)

    def add(self, project_id, folder, legacy=None):
        root = Path(folder).expanduser().resolve()
        if not root.is_dir():
            raise ValueError('Folder is offline or missing')
        with self.lock:
            p = self.read(project_id)
            known = {a['path'] for a in p['assets']}
            legacy = legacy or {}
            for path in sorted(root.rglob('*')):
                if not path.is_file() or path.suffix.lower() not in IMAGE_SUFFIXES or str(path) in known:
                    continue
                stat = path.stat()
                asset_id = uuid.uuid4().hex
                p['assets'].append({'id': asset_id, 'path': str(path), 'name': path.name,
                                    'type': path.suffix[1:].upper(), 'bytes': stat.st_size,
                                    'fingerprint': self.fingerprint(path)})
                old_id = path_id(path)
                if old_id in legacy.get('photos', {}):
                    p['photos'][asset_id] = legacy['photos'][old_id]
                if old_id == legacy.get('selected'):
                    p['selected'] = asset_id
            if str(root) not in p['roots']:
                p['roots'].append(str(root))
            if not p['source']:
                p['source'] = str(root)
            self.write(p)
            return p

    def add_capture(self, project_id, filename, recipe, capture_id):
        """Register one SDK-confirmed capture atomically without rescanning a tree."""
        path = Path(filename).resolve()
        if not path.is_file() or path.suffix.lower() not in IMAGE_SUFFIXES:
            raise ValueError('Capture is not a supported photo')
        with self.lock:
            p = self.read(project_id)
            existing = next((a for a in p['assets'] if a['path'] == str(path)), None)
            if existing:
                return existing, p['photos'].get(existing['id']), False
            asset = {'id': uuid.uuid4().hex, 'path': str(path), 'name': path.name,
                     'type': path.suffix[1:].upper(), 'bytes': path.stat().st_size,
                     'fingerprint': self.fingerprint(path), 'capture_id': capture_id}
            photo = {'rating': 0, 'recipe': recipe}
            p['assets'].append(asset)
            p['photos'][asset['id']] = photo
            if str(path.parent) not in p['roots']:
                p['roots'].append(str(path.parent))
            if not p['source']:
                p['source'] = str(path.parent)
            self.write(p)
            return asset, photo, True

    def save_edits(self, project_id, photos, selected):
        with self.lock:
            p = self.read(project_id)
            ids = {a['id'] for a in p['assets']}
            p['photos'].update({k: v for k, v in photos.items() if k in ids})
            p['selected'] = selected if selected in ids else None
            self.write(p)

    def reconnect(self, project_id, folder=None):
        with self.lock:
            p = self.read(project_id)
            missing = [a for a in p['assets'] if self._missing(a)]
            roots = [Path(folder).expanduser().resolve()] if folder else [Path(r) for r in p['roots']]
            if folder and not roots[0].is_dir():
                raise ValueError('Search folder is offline or missing')
            # Nearby folder moves and renamed mounted volumes are common. Search
            # known roots/parents and matching paths on mounted volumes, not the Mac.
            if not folder:
                for root in list(roots):
                    if root.parent.is_dir() and root.parent != Path('/') and str(root.parent) != '/Volumes':
                        roots.append(root.parent)
                    parts = root.parts
                    if len(parts) > 3 and parts[1] == 'Volumes' and Path('/Volumes').exists():
                        for volume in Path('/Volumes').iterdir():
                            if not volume.is_symlink():
                                roots.append(volume.joinpath(*parts[3:]))
            sizes = {a['bytes'] for a in missing}
            candidates = {}
            seen = set()
            for root in roots:
                if not sizes or not root.is_dir():
                    continue
                for directory, dirs, files in os.walk(root):
                    dirs[:] = [d for d in dirs if not d.startswith('.')]
                    for name in files:
                        path = Path(directory) / name
                        if path in seen or path.suffix.lower() not in IMAGE_SUFFIXES:
                            continue
                        seen.add(path)
                        try:
                            if path.stat().st_size in sizes:
                                key = self.fingerprint(path)
                                candidates.setdefault(key, []).append(path)
                        except OSError:
                            continue
            reconnected, ambiguous = 0, 0
            for asset in missing:
                matches = candidates.get(asset['fingerprint'], [])
                if len(matches) == 1:
                    asset['path'] = str(matches[0])
                    asset['name'] = matches[0].name
                    asset.pop('unverified', None)
                    reconnected += 1
                    if str(matches[0].parent) not in p['roots']:
                        p['roots'].append(str(matches[0].parent))
                elif len(matches) > 1:
                    ambiguous += 1
            self.write(p)
            return {'reconnected': reconnected, 'ambiguous': ambiguous,
                    'missing': sum(self._missing(a) for a in p['assets'])}

    @staticmethod
    def _missing(asset):
        return asset.get('unverified', False) or not Path(asset['path']).is_file()

    def open(self, project_id):
        catalog_path = self.ensure_folder(project_id)
        report = self.reconnect(project_id)
        p = self.read(project_id)
        return {'project_id': p['id'], 'name': p['name'], 'source': p['source'],
                'catalog_path': str(catalog_path), 'project_folder': str(catalog_path.parent),
                'files': [{**a, 'missing': self._missing(a)} for a in p['assets']],
                'saved': {'photos': p['photos'], 'selected': p['selected']}, 'reconnect': report}
