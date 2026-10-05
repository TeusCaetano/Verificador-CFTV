import os, hashlib, secrets, hmac, time
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, IPvAnyAddress, model_validator
from sqlalchemy import create_engine, String, Float, Integer, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

class Base(DeclarativeBase): pass
class Unit(Base):
    __tablename__='units'
    id: Mapped[int]=mapped_column(primary_key=True)
    name: Mapped[str]=mapped_column(String(100))
    lat: Mapped[float]=mapped_column(Float)
    lng: Mapped[float]=mapped_column(Float)
class User(Base):
    __tablename__='users'
    id: Mapped[int]=mapped_column(primary_key=True)
    username: Mapped[str]=mapped_column(String(80),unique=True)
    password_hash: Mapped[str]=mapped_column(String(200))
    role: Mapped[str]=mapped_column(String(20))
class Camera(Base):
    __tablename__='cameras'
    id: Mapped[int]=mapped_column(primary_key=True)
    name: Mapped[str]=mapped_column(String(100))
    manufacturer: Mapped[str]=mapped_column(String(30))
    model: Mapped[str]=mapped_column(String(80))
    ip: Mapped[str]=mapped_column(String(50))
    port: Mapped[int]=mapped_column(Integer)
    channel: Mapped[int]=mapped_column(Integer)
    lat: Mapped[float]=mapped_column(Float)
    lng: Mapped[float]=mapped_column(Float)
    unit_id: Mapped[int]=mapped_column(Integer)
class ChannelMode(Base):
    __tablename__="channel_modes"
    id: Mapped[int]=mapped_column(primary_key=True)
    is_free: Mapped[int]=mapped_column(Integer,default=0)
class Audit(Base):
    __tablename__='audit'
    id: Mapped[int]=mapped_column(primary_key=True)
    username: Mapped[str]=mapped_column(String(80))
    action: Mapped[str]=mapped_column(String(100))
    camera_id: Mapped[int]=mapped_column(Integer)
    timestamp: Mapped[int]=mapped_column(Integer)

engine=create_engine(os.environ.get('DATABASE_URL','postgresql+psycopg://scheffer:change-me@db/scheffer'),pool_pre_ping=True)
Session=sessionmaker(engine)
tokens={}
def password_hash(password):
    salt=secrets.token_hex(16)
    return salt+':'+hashlib.pbkdf2_hmac('sha256',password.encode(),salt.encode(),300000).hex()
def verify(password,stored):
    salt,digest=stored.split(':')
    return hmac.compare_digest(digest,hashlib.pbkdf2_hmac('sha256',password.encode(),salt.encode(),300000).hex())
@asynccontextmanager
async def lifespan(app):
    Base.metadata.create_all(engine)
    with Session.begin() as s:
        if not s.scalar(select(User).where(User.username=='admin')):
            password=os.environ.get('ADMIN_PASSWORD','')
            if len(password)<12: raise RuntimeError('Defina ADMIN_PASSWORD com pelo menos 12 caracteres.')
            s.add(User(username='admin',password_hash=password_hash(password),role='admin'))
        if not s.get(Unit,1): s.add(Unit(id=1,name='Três Lagoas',lat=-13.2582793655,lng=-58.7325993091))
    migrate_inventory()
    start_monitor()
    try: yield
    finally: stop_monitor()
app=FastAPI(title='Scheffer — etapa 8',lifespan=lifespan)
def authenticated(authorization: str=Header(default='')):
    token=authorization.removeprefix('Bearer ')
    item=tokens.get(token)
    if not item or item['expires']<time.time():
        tokens.pop(token,None)
        raise HTTPException(401,'Faça login novamente.')
    item['last_seen']=time.time()
    return item
def admin(user=Depends(authenticated)):
    if user['role']!='admin': raise HTTPException(403,'Ação permitida somente ao administrador.')
    return user
class Login(BaseModel):
    username:str=Field(max_length=80)
    password:str=Field(max_length=200)
class CameraInput(BaseModel):
    name:str=Field(min_length=1,max_length=100)
    manufacturer:str=Field(pattern='^(Intelbras|Hikvision)$')
    model:str=Field(default='',max_length=80)
    ip:IPvAnyAddress
    port:int=Field(ge=1,le=65535)
    channel:int=Field(ge=1,le=256)
    lat:float=Field(ge=-90,le=90)
    lng:float=Field(ge=-180,le=180)
    unit_id:int=Field(default=1,ge=1)
    sector_id:int=Field(default=0,ge=0)
    recorder_name:str=Field(default="",max_length=100)
    is_free:bool=False
    device_type:str=Field(default='nvr',pattern='^(nvr|camera)$')
    username:str=Field(default='',max_length=100)
    password:str=Field(default='',max_length=200)
    stream:str=Field(default='secondary',pattern='^(primary|secondary)$')
    rtsp_path:str=Field(default='',max_length=500,pattern=r'^(/[^\s@#]*)?$')
    @model_validator(mode="after")
    def normalize(self):
        self.name=self.name.strip();self.model=self.model.strip();self.recorder_name=self.recorder_name.strip()
        if not self.name:raise ValueError("Informe o nome do dispositivo.")
        if self.device_type=="camera":self.channel=1;self.recorder_name=""
        return self
class UserInput(BaseModel):
    username:str=Field(min_length=3,max_length=80,pattern='^[a-zA-Z0-9_.-]+$')
    password:str=Field(min_length=12,max_length=200)
    role:str=Field(pattern='^(admin|operator|viewer)$')
def serialize(c,configs=None,metadata=None):
    conf=(configs.get(c.id) if configs is not None else None) or connection_data(c.id)
    meta=(metadata if metadata is not None else inventory_metadata()).get(c.id,{})
    return {k:getattr(c,k) for k in ['id','name','manufacturer','model','ip','port','channel','lat','lng','unit_id']}|conf|meta
@app.get('/api/health')
def health():
    with Session() as s: s.execute(select(Unit.id).limit(1))
    return {'status':'ok','stage':8}
@app.post('/api/login')
def login(body:Login):
    with Session() as s:
        user=s.scalar(select(User).where(User.username==body.username))
        if not user or not verify(body.password,user.password_hash): raise HTTPException(401,'Usuário ou senha inválidos.')
        token=secrets.token_urlsafe(32)
        tokens[token]={'username':user.username,'role':user.role,'expires':time.time()+28800,'last_seen':time.time()}
        return {'token':token,'username':user.username,'role':user.role}
@app.post('/api/logout')
def logout(authorization: str=Header(default=''),user=Depends(authenticated)):
    tokens.pop(authorization.removeprefix('Bearer '),None)
    return {'ok':True}
@app.get('/api/units')
def units(user=Depends(authenticated)):
    with Session() as s: return [{'id':u.id,'name':u.name,'lat':u.lat,'lng':u.lng} for u in s.scalars(select(Unit))]
@app.get('/api/cameras')
def cameras(user=Depends(authenticated)):
    configs=all_connections();metadata=inventory_metadata()
    with Session() as s: return [serialize(c,configs,metadata) for c in s.scalars(select(Camera).order_by(Camera.id))]
def store_camera(s,body,id,user):
    verify_inventory(s,body,id)
    data=body.model_dump(exclude={'device_type','username','password','stream','rtsp_path','sector_id','recorder_name','is_free'});data['ip']=str(body.ip)
    camera=s.get(Camera,id,with_for_update=True) if id else Camera()
    if camera is None:raise HTTPException(404,'Câmera inexistente.')
    for k,v in data.items():setattr(camera,k,v)
    s.add(camera);s.flush()
    mode=s.get(ChannelMode,camera.id)
    if not mode:mode=ChannelMode(id=camera.id);s.add(mode)
    mode.is_free=int(body.is_free)
    s.flush()
    save_inventory(s,camera,body);save_connection(s,camera,body)
    s.add(Audit(username=user['username'],action='update' if id else 'create',camera_id=camera.id,timestamp=int(time.time())))
    return camera.id

def save_camera(body,id,user):
    try:
        with Session.begin() as s:camera_id=store_camera(s,body,id,user)
    except IntegrityError:raise HTTPException(409,'Este IP, porta, tipo e canal já estão cadastrados na unidade.')
    with Session() as s:return serialize(s.get(Camera,camera_id))
@app.post('/api/cameras',status_code=201)
def create_camera(body:CameraInput,user=Depends(admin)): return save_camera(body,None,user)
@app.put('/api/cameras/{id}')
def update_camera(id:int,body:CameraInput,user=Depends(admin)): return save_camera(body,id,user)
@app.get('/api/audit')
def audit(user=Depends(admin)):
    with Session() as s: return [{'username':a.username,'action':a.action,'camera_id':a.camera_id,'timestamp':a.timestamp} for a in s.scalars(select(Audit).order_by(Audit.id.desc()).limit(200))]
@app.post('/api/users',status_code=201)
def create_user(body:UserInput,user=Depends(admin)):
    with Session.begin() as s:
        if s.scalar(select(User).where(User.username==body.username)): raise HTTPException(409,'Usuário já existe.')
        s.add(User(username=body.username,password_hash=password_hash(body.password),role=body.role))
    return {'username':body.username,'role':body.role}
from backend.video import configure
save_connection,connection_data,all_connections,start_monitor,stop_monitor=configure(app,Base,Session,Camera,Audit,User,authenticated,admin,tokens)
from backend.inventory import configure_inventory
inventory_metadata,verify_inventory,save_inventory,migrate_inventory,delete_inventory=configure_inventory(app,Base,Session,Camera,Unit,Audit,CameraInput,authenticated,admin,store_camera)
app.state.delete_inventory=delete_inventory
class ChannelModeInput(BaseModel):
    is_free:bool
@app.patch('/api/cameras/{id}/channel-mode')
def change_channel_mode(id:int,body:ChannelModeInput,user=Depends(admin)):
    with Session() as s:
        camera=s.get(Camera,id)
        if not camera:raise HTTPException(404,'Dispositivo inexistente.')
        values=serialize(camera)
    values['is_free']=body.is_free
    values['password']=''
    return save_camera(CameraInput.model_validate(values),id,user)
class CameraPositionInput(BaseModel):
    lat:float=Field(ge=-90,le=90)
    lng:float=Field(ge=-180,le=180)
    sector_id:int=Field(default=0,ge=0)
@app.patch('/api/cameras/{id}/position')
def position_camera(id:int,body:CameraPositionInput,user=Depends(admin)):
    # Moving a pin must not reset connection state, credentials or alert streaks.
    with Session.begin() as s:
        camera=s.get(Camera,id)
        if not camera:raise HTTPException(404,'Dispositivo inexistente.')
        values=serialize(camera)|body.model_dump()
        validated=CameraInput.model_validate(values)
        verify_inventory(s,validated,id)
        camera.lat=body.lat;camera.lng=body.lng
        save_inventory(s,camera,validated)
        s.add(Audit(username=user['username'],action='position_update',camera_id=id,timestamp=int(time.time())))
    with Session() as s:return serialize(s.get(Camera,id))
@app.get('/api/maps-config')
def maps_config(user=Depends(authenticated)):
    return {'google_api_key': os.getenv('GOOGLE_MAPS_API_KEY', '').strip()}

from backend.discovery import configure_discovery
configure_discovery(app,admin)

import threading,asyncio
snapshot_lock=threading.Lock()
snapshot_cache={}
def invalidate_snapshot():
    with snapshot_lock:snapshot_cache.clear()
@app.middleware('http')
async def refresh_snapshot_after_write(request,call_next):
    response=await call_next(request)
    if request.method in ('POST','PUT','PATCH','DELETE') and response.status_code<400:
        await asyncio.to_thread(invalidate_snapshot)
    return response
@app.get('/api/snapshot')
def snapshot(state_filter:str='active',user=Depends(authenticated)):
    with snapshot_lock:
        cached=snapshot_cache.get(state_filter)
        if cached and time.monotonic()-cached[0]<3:return cached[1]
        endpoints={r.path:r.endpoint for r in app.routes if hasattr(r,'endpoint') and 'GET' in getattr(r,'methods',set())}
        result={key:endpoints['/api/'+key](user=user) for key in ('units','sectors','cameras','overview','monitor','events','maintenance')}
        result['alerts']=endpoints['/api/alerts'](state_filter=state_filter,user=user)
        snapshot_cache.clear();snapshot_cache[state_filter]=(time.monotonic(),result)
        return result

app.mount('/',StaticFiles(directory=str(Path(__file__).parent.parent/'frontend'),html=True),name='frontend')
