"""Nikon camera process isolation and completed-capture catalog ingestion."""
from collections import deque
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import queue
import subprocess
import threading
import time
import uuid

from engine import DEFAULT_RECIPE, normalize_recipe

class TetherError(RuntimeError):
    pass

class NikonTether:
    def __init__(self, data, catalog):
        self.data = Path(data)
        self.catalog = catalog
        self.runtime = Path(os.environ.get('REFERENCE_DARKROOM_NIKON_RUNTIME', str(self.data/'nikon/runtime/TestApp/TestApp')))
        self.exe = self.runtime/'darkroom-nikon'
        self.frame = self.data/'nikon/live.jpg'
        self.lock = threading.RLock()
        self.command_lock = threading.RLock()
        self.process = None
        self.expected_stop = None
        self.ready = threading.Event()
        self.pending = {}
        self.events = deque(maxlen=200)
        self.sequence = 0
        self.session = None
        self.transfer_routes = deque()
        self.capture_routes = {}
        self.connected = False
        self.live = False
        self.devices = []
        self.settings = {}
        self.error = ''
        self.jobs = queue.Queue()
        self.closed = False
        self.worker = threading.Thread(target=self._ingest_loop, daemon=True)
        self.worker.start()

    def _event(self, kind, **data):
        with self.lock:
            self.sequence += 1
            self.events.append({'id': self.sequence, 'kind': kind,
                'time': datetime.now(timezone.utc).isoformat(), **data})

    def start(self):
        with self.lock:
            if self.process and self.process.poll() is None:
                return
            if not self.exe.is_file():
                raise TetherError('Nikon SDK is not installed. Run native/install_nikon_sdk.py with your Nikon SDK ZIP.')
            self.frame.parent.mkdir(parents=True, exist_ok=True)
            self.ready.clear()
            self.expected_stop = None
            self.error = ''
            self.frame.unlink(missing_ok=True)
            log = open(self.data/'nikon/bridge.log','ab')
            try:
                self.process = subprocess.Popen([str(self.exe), str(self.runtime/'TypeCommon Module.bundle'), str(self.frame)],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log, text=True, bufsize=1, cwd=self.runtime)
            finally:
                log.close()
            threading.Thread(target=self._read, args=(self.process,), daemon=True).start()
        if not self.ready.wait(20):
            self._terminate()
            raise TetherError('Nikon SDK did not initialize. Check the camera connection and bridge.log.')
        if self.error:
            raise TetherError(self.error)

    def _read(self, process):
        try:
            for line in process.stdout:
                try:
                    message = json.loads(line)
                except (ValueError, TypeError):
                    continue
                with self.lock:
                    if process is not self.process:
                        break
                    if message.get('id'):
                        waiter = self.pending.get(message['id'])
                        if waiter:
                            waiter.put(message)
                        continue
                    kind = message.get('event')
                    if kind == 'ready':
                        self.ready.set()
                    elif kind == 'fatal':
                        self.error = message.get('message', 'Nikon SDK stopped')
                        self.ready.set()
                    elif kind == 'capture_saved' and self.session:
                        self._capture_received(message.get('path',''))
                    elif kind == 'error' or (kind == 'shooting_result' and message.get('sdk_code',0)!=0):
                        self.error = message.get('message', f"Capture failed (Nikon code {message.get('sdk_code')}).")
                        self._event('error', message=self.error)
                    elif kind in ('devices_changed','settings_changed','live_changed','capture_complete','transfer'):
                        if kind=='transfer' and message.get('done')==0:
                            self._transfer_started()
                        self._event(kind, **{k:v for k,v in message.items() if k!='event'})
                        if kind=='devices_changed' and self.connected:
                            threading.Thread(target=self._check_presence,daemon=True).start()
        finally:
            with self.lock:
                if process is self.process:
                    self.connected = self.live = False
                    if not self.closed and process is not self.expected_stop:
                        self.error = self.error or 'Camera connection closed. Scan and connect again.'
                    self.ready.set()
                    for waiter in self.pending.values():
                        waiter.put({'sdk_code':-1,'message':self.error or 'Camera connection closed'})

    def command(self, op, **data):
        with self.command_lock:
            if self.closed:raise TetherError('Camera service has closed.')
            self.start()
            request_id = uuid.uuid4().hex
            waiter = queue.Queue()
            with self.lock:
                self.pending[request_id] = waiter
                process = self.process
            try:
                process.stdin.write(json.dumps({'id':request_id,'op':op,**data})+'\n')
                process.stdin.flush()
                reply = waiter.get(timeout=25)
                if reply.get('sdk_code',0)!=0:
                    raise TetherError(reply.get('message') or f"Nikon command failed (code {reply['sdk_code']}). Check the camera state and close other tether software.")
                with self.lock:
                    if 'live' in reply:self.live=reply['live']
                    if 'connected' in reply:self.connected=reply['connected']
                    if 'settings' in reply:self.settings=reply['settings']
                return reply
            except queue.Empty:
                self._terminate()
                raise TetherError('Camera command timed out. Scan and reconnect; a timed-out shutter command is never repeated automatically.')
            except (BrokenPipeError, OSError, ValueError) as error:
                raise TetherError('Camera connection closed. Scan and reconnect.') from error
            finally:
                with self.lock:self.pending.pop(request_id,None)

    def scan(self):
        reply = self.command('devices')
        with self.lock:self.devices=reply['devices']
        return self.status()

    def _check_presence(self):
        try:
            with self.command_lock:
                if not self.connected or self.closed or self.process is self.expected_stop:return
                data=self.command('devices')
                with self.lock:
                    self.devices=data['devices']
                    missing=self.connected and self.session and not any(d['id']==self.session['device_id'] for d in self.devices)
                if missing:
                    self._terminate()
                    with self.lock:
                        self.connected=self.live=False
                        self.error='Camera disconnected. Switch it on and scan to reconnect.'
                    self._event('error',message=self.error)
        except TetherError as error:
            self._event('error',message=str(error))

    def connect(self, project_id, device_id, destination=None, recipe=None, lossless=True):
        if self.connected:raise TetherError('Disconnect the current camera session first.')
        project = self.catalog.read(project_id)
        parent = Path(destination).expanduser().resolve() if destination else self.catalog.ensure_folder(project_id).parent/'Captures'
        parent.mkdir(parents=True, exist_ok=True)
        # Separate session folder prevents filename collisions across shoots.
        folder = parent/(datetime.now().strftime('%Y-%m-%d_%H-%M-%S')+'_'+uuid.uuid4().hex[:6])
        if len(str(folder).encode())>=255:raise TetherError('Choose a shorter capture folder path (Nikon limits it to 255 bytes).')
        folder.mkdir()
        with self.lock:
            self.transfer_routes.clear();self.capture_routes.clear()
            self.session={'id':uuid.uuid4().hex,'project_id':project_id,'project_name':project['name'],
                          'destination':str(folder),'device_id':device_id,'recipe':self.starting_recipe(recipe),'lossless':lossless}
            self.error=''
        try:
            self.command('connect',device_id=device_id,destination=str(folder),lossless=lossless)
        except Exception:
            with self.lock:self.session=None
            raise
        self._event('connected',message=f"Connected; photos save to {folder}")
        return self.status()

    def retarget(self, project_id):
        """Change catalog routing without interrupting the live camera session."""
        project=self.catalog.read(project_id)
        with self.command_lock, self.lock:
            if not self.connected or not self.session:return self.status()
            if self.session['project_id']==project_id:return self.status()
            self.session={**self.session,'project_id':project_id,'project_name':project['name']}
            self._event('target_changed',message=f"Future captures → {project['name']}")
            return self.status()

    def _transfer_started(self):
        with self.lock:
            if self.session:self.transfer_routes.append(deepcopy(self.session))

    def _capture_received(self, filename):
        with self.lock:
            route=self.transfer_routes.popleft() if self.transfer_routes else deepcopy(self.session)
            # The RAW/JPG siblings of one shot must stay in the same project.
            stem=Path(filename).stem
            if stem.rsplit('.',1)[-1].isdigit():stem=stem.rsplit('.',1)[0]
            key=(route['id'],stem)
            route=self.capture_routes.setdefault(key,route)
            if len(self.capture_routes)>256:self.capture_routes.pop(next(iter(self.capture_routes)))
            self.jobs.put((deepcopy(route),filename))
            self._event('transfer',message=f"Photo received; adding to {route['project_name']}…")

    @staticmethod
    def starting_recipe(recipe):
        # Spatial edits must not be pasted onto subjects in a new position.
        r=deepcopy(normalize_recipe(recipe or DEFAULT_RECIPE))
        for key in ['crop','crop_frame','crop_aspect','masks','clone_layers','rotation','straighten','flip_h','flip_v','camera_look']:
            r.pop(key,None)
        return {**deepcopy(DEFAULT_RECIPE),**r}

    def set_recipe(self, recipe):
        with self.lock:
            if not self.session:raise TetherError('Connect a camera first.')
            self.session['recipe']=self.starting_recipe(recipe)
        return self.status()

    def disconnect(self):
        with self.command_lock:
            try:
                if self.connected:self.command('disconnect')
            finally:
                self._terminate()
                with self.lock:self.connected=self.live=False
        self._event('disconnected',message='Camera disconnected. Completed captures remain in their project.')
        return self.status()

    def _terminate(self):
        with self.command_lock:self._terminate_locked()

    def _terminate_locked(self):
        with self.lock:
            process=self.process
            self.expected_stop=process
        if not process or process.poll() is not None:return
        try:
            process.stdin.close()
            process.wait(timeout=5)
        except (OSError,subprocess.TimeoutExpired):
            process.terminate()
            try:process.wait(timeout=3)
            except subprocess.TimeoutExpired:process.kill();process.wait()

    def _ingest_loop(self):
        while True:
            item=self.jobs.get()
            if item is None:self.jobs.task_done();return
            session,filename=item
            try:
                path=Path(filename).expanduser()
                if not path.is_absolute():path=Path(session['destination'])/path
                path=path.resolve()
                if not path.is_relative_to(Path(session['destination']).resolve()):
                    raise TetherError('Nikon reported a capture outside the session folder.')
                if path.suffix.lower() not in {'.nef','.jpg','.jpeg'}:
                    raise TetherError('Capture is not a NEF or JPG photo.')
                # ImageSaved means Nikon closed the file. Verify stable nonzero size
                # before fingerprinting, decoding, or publishing it to the catalog.
                previous=None;stable=0
                for _ in range(40):
                    stat=path.stat();key=(stat.st_size,stat.st_mtime_ns)
                    stable=stable+1 if key==previous and stat.st_size>0 else 0
                    if stable>=2:break
                    previous=key;time.sleep(.2)
                else:raise TetherError('Capture did not finish writing; it was not imported.')
                with path.open('rb') as f:
                    header=f.read(4)
                    if path.suffix.lower()=='.nef' and header not in (b'II*\x00',b'MM\x00*'):
                        raise TetherError('Incomplete or invalid NEF header; capture was not imported.')
                    if path.suffix.lower() in {'.jpg','.jpeg'}:
                        f.seek(-2,2)
                        if header[:2]!=b'\xff\xd8' or f.read()!=b'\xff\xd9':raise TetherError('Incomplete JPG; capture was not imported.')
                r=deepcopy(session['recipe'])
                if path.suffix.lower() in {'.jpg','.jpeg'}:r['camera_look_enabled']=False
                else:r['camera_look_enabled']=True
                asset,photo,added=self.catalog.add_capture(session['project_id'],path,r,uuid.uuid4().hex)
                if added:self._event('imported',project_id=session['project_id'],project_name=session.get('project_name', 'receiving project'),asset=asset,photo=photo)
            except Exception as error:
                self._event('error',message=str(error),path=filename)
                with self.lock:self.error=str(error)
            finally:self.jobs.task_done()

    def status(self, after=0):
        with self.lock:
            age=time.time()-self.frame.stat().st_mtime if self.frame.is_file() else None
            return {'installed':self.exe.is_file(),'connected':self.connected,'live':self.live,
                'devices':deepcopy(self.devices),'settings':deepcopy(self.settings),
                'session':deepcopy(self.session),'error':self.error,'frame_age':age,
                'pending':self.jobs.unfinished_tasks,'cursor':self.sequence,
                'events':[deepcopy(e) for e in self.events if e['id']>after]}

    def close(self):
        self.closed=True
        self._terminate()
        self.jobs.put(None)

def register_tether(app, data, catalog):
    from fastapi import HTTPException
    from pydantic import BaseModel, Field
    from fastapi.responses import Response
    tether=NikonTether(data,catalog)

    class ConnectRequest(BaseModel):
        project_id:str
        device_id:int=Field(ge=0)
        destination:str|None=None
        recipe:dict|None=None
        lossless:bool=True
    class CaptureRequest(BaseModel):
        autofocus:bool=True
    class TargetRequest(BaseModel):
        project_id:str
    class LiveRequest(BaseModel):
        enabled:bool
    class RecipeRequest(BaseModel):
        recipe:dict
    class SettingRequest(BaseModel):
        key:str
        index:int=Field(ge=0,le=10000)
    def call(fn,*args,**kwargs):
        try:return fn(*args,**kwargs)
        except (TetherError,ValueError,OSError) as error:raise HTTPException(409,str(error)) from error
    @app.get('/api/tether/status')
    def status(after:int=0):return tether.status(after)
    @app.post('/api/tether/scan')
    def scan():return call(tether.scan)
    @app.post('/api/tether/connect')
    def connect(req:ConnectRequest):return call(tether.connect,req.project_id,req.device_id,req.destination,req.recipe,req.lossless)
    @app.post('/api/tether/disconnect')
    def disconnect():return call(tether.disconnect)
    @app.post('/api/tether/target')
    def target(req:TargetRequest):return call(tether.retarget,req.project_id)
    @app.post('/api/tether/live')
    def live(req:LiveRequest):return call(tether.command,'live_start' if req.enabled else 'live_stop')
    @app.post('/api/tether/capture')
    def capture(req:CaptureRequest):return call(tether.command,'capture',autofocus=req.autofocus)
    @app.get('/api/tether/settings')
    def settings():return call(tether.command,'settings')
    @app.post('/api/tether/setting')
    def setting(req:SettingRequest):return call(tether.command,'setting',key=req.key,index=req.index)
    @app.post('/api/tether/recipe')
    def recipe(req:RecipeRequest):return call(tether.set_recipe,req.recipe)
    @app.get('/api/tether/frame')
    def frame():
        if not tether.live or not tether.frame.is_file() or time.time()-tether.frame.stat().st_mtime>3:
            raise HTTPException(404,'Waiting for a current live-view frame')
        return Response(tether.frame.read_bytes(),media_type='image/jpeg',headers={'Cache-Control':'no-store'})
    @app.on_event('shutdown')
    def shutdown():tether.close()
    return tether
