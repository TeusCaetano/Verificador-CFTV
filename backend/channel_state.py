"""Intelbras documented channel connection state, distinct from RTSP availability."""
import threading,time,hashlib
import xml.etree.ElementTree as ET
import httpx
from fastapi import HTTPException,Depends
from pydantic import BaseModel,Field
from sqlalchemy import String,Integer,select
from sqlalchemy.orm import Mapped,mapped_column

def parse_states(body):
 rows=body.get('states') if isinstance(body,dict) else None
 if not isinstance(rows,list) or not rows:raise ValueError('Invalid state list')
 out={}
 for row in rows:
  channel=row.get('channel');state=row.get('connectionState')
  if type(channel) is not int or not 0<=channel<256 or channel+1 in out:raise ValueError('Invalid channel')
  out[channel+1]='online' if state=='Connected' else 'offline' if state in ('Unconnect','Disable','UnInited','Empty','Hibernation') else 'unknown'
 return out
def parse_hikvision_states(content):
 """ISAPI InputProxy/channels/status: <InputProxyChannelStatus><id>1</id><online>true</online>."""
 if b'<!DOCTYPE' in content or b'<!ENTITY' in content:raise ValueError('Unsafe XML')
 try:root=ET.fromstring(content)
 except ET.ParseError:raise ValueError('Invalid XML')
 out={}
 for item in root.iter():
  if item.tag.rsplit('}',1)[-1]!='InputProxyChannelStatus':continue
  fields={child.tag.rsplit('}',1)[-1]:(child.text or '').strip() for child in item}
  if not fields.get('id','').isdigit() or not 0<int(fields['id'])<1025 or int(fields['id']) in out or fields.get('online') not in ('true','false'):raise ValueError('Invalid channel')
  out[int(fields['id'])]='online' if fields['online']=='true' else 'offline'
 if not out:raise ValueError('Invalid state list')
 return out
class Settings(BaseModel):
 enabled:bool=True
 web_port:int=Field(default=80,ge=1,le=65535)
 scheme:str=Field(default='http',pattern='^(http|https)$')

def configure(app,Base,Session,Camera,Connection,cipher,admin,authenticated,Audit):
 class RecorderStateSettings(Base):
  __tablename__='recorder_state_settings'
  key:Mapped[str]=mapped_column(String(120),primary_key=True)
  enabled:Mapped[int]=mapped_column(Integer,default=1)
  web_port:Mapped[int]=mapped_column(Integer,default=80)
  scheme:Mapped[str]=mapped_column(String(10),default='http')
 def key(c):return str(c.unit_id)+'|'+c.ip+'|'+str(c.port)
 cache={};locks={};lock=threading.Lock()
 @app.get('/api/cameras/{id}/recorder-status')
 def settings(id:int,user=Depends(authenticated)):
  with Session() as s:
   c=s.get(Camera,id)
   if not c:raise HTTPException(404,'Câmera não encontrada.')
   r=s.get(RecorderStateSettings,key(c))
   return {'enabled':bool(r.enabled) if r else False,'web_port':r.web_port if r else 80,'scheme':r.scheme if r else 'http'}
 @app.put('/api/cameras/{id}/recorder-status')
 def save(id:int,body:Settings,user=Depends(admin)):
  if body.enabled:
   result=read(id,body)
   if result is None or result.get('unavailable'):raise HTTPException(422,'A consulta de estado não foi confirmada nesta porta/protocolo/firmware. Configuração anterior preservada; use RTSP ou confira a porta web.')
  with Session.begin() as s:
   c=s.get(Camera,id);conn=s.get(Connection,id)
   if not c or not conn:raise HTTPException(404,'Dispositivo não encontrado.')
   if c.manufacturer not in ('Intelbras','Hikvision') or conn.device_type!='nvr':raise HTTPException(422,'Consulta de canais disponível para gravadores Intelbras e Hikvision.')
   k=key(c);r=s.get(RecorderStateSettings,k)
   if not r:r=RecorderStateSettings(key=k);s.add(r)
   r.enabled=int(body.enabled);r.web_port=body.web_port;r.scheme=body.scheme
   s.add(Audit(username=user['username'],action='recorder_state_settings_update',camera_id=id,timestamp=int(time.time())))
  with lock:cache.clear()
  return {'ok':True}
 def read(id,override=None):
  with Session() as s:
   c=s.get(Camera,id);conn=s.get(Connection,id)
   if not c or not conn or c.manufacturer not in ('Intelbras','Hikvision') or conn.device_type!='nvr':return None
   setting=override or s.get(RecorderStateSettings,key(c))
   if not setting or not setting.enabled:return None
   channel=c.channel;host='['+c.ip+']' if ':' in c.ip else c.ip
   hikvision=c.manufacturer=='Hikvision'
   url=f'{setting.scheme}://{host}:{setting.web_port}'+('/ISAPI/ContentMgmt/InputProxy/channels/status' if hikvision else '/cgi-bin/api/LogicDeviceManager/getCameraState')
   username=conn.username;password=cipher.decrypt(conn.password_encrypted.encode()).decode()
   k=hashlib.sha256((url+username+password).encode()).hexdigest()
  # One request shared by channels of the same recorder, including failed results.
  with lock:host_lock=locks.setdefault(k,threading.Lock())
  with host_lock:
   old=cache.get(k)
   if old and time.monotonic()-old[0]<30:states=old[1]
   else:
    try:
     with httpx.Client(timeout=httpx.Timeout(8,connect=4),trust_env=False,follow_redirects=False) as client:
      send=(lambda auth:client.get(url,auth=auth)) if hikvision else (lambda auth:client.post(url,json={'uniqueChannels':[-1]},auth=auth))
      r=send(httpx.DigestAuth(username,password))
      if r.status_code==401:r=send(httpx.BasicAuth(username,password))
      r.raise_for_status()
      if len(r.content)>1000000:raise ValueError('Too large')
      states=parse_hikvision_states(r.content) if hikvision else parse_states(r.json())
    except (httpx.HTTPError,ValueError):states=None
    cache[k]=(time.monotonic(),states)
  if states is None:return {'unavailable':True,'status':'unknown','video':False,'diagnostic':'Consulta de estado do NVD indisponível. Confira porta web, protocolo, credenciais e compatibilidade do firmware.'}
  if channel not in states:return {'unavailable':True,'status':'unknown','diagnostic':'Canal ausente na consulta de estado; usando teste RTSP.'}
  state=states[channel]
  return {'status':state,'video':False,'network':True,'diagnostic':'Estado do canal informado pelo gravador: '+('câmera conectada; imagem útil não validada.' if state=='online' else 'câmera sem conexão ativa.' if state=='offline' else 'conexão em andamento ou estado inconclusivo.')}
 return read
