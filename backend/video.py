import asyncio
import os, time, secrets, socket, subprocess, json, re, threading
from urllib.parse import quote, urljoin, urlsplit
import hashlib,hmac
import logging
from concurrent.futures import ThreadPoolExecutor
from cryptography.fernet import Fernet
import httpx
from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel, Field
from fastapi.responses import Response
from backend.live_preparation import Preparations,probe_codec
from sqlalchemy import String, Integer, select, func, Index
from sqlalchemy.orm import Mapped, mapped_column

def configure(app, Base, Session, Camera, Audit, User, authenticated, admin, tokens):
    class Connection(Base):
        __tablename__='camera_connections'
        id: Mapped[int]=mapped_column(primary_key=True)
        device_type: Mapped[str]=mapped_column(String(20),default='nvr')
        username: Mapped[str]=mapped_column(String(100),default='')
        password_encrypted: Mapped[str]=mapped_column(String(1000),default='')
        stream: Mapped[str]=mapped_column(String(20),default='secondary')
        path: Mapped[str]=mapped_column(String(500),default='')
        status: Mapped[str]=mapped_column(String(20),default='unknown')
        checked_at: Mapped[int]=mapped_column(Integer,default=0)
        diagnostic: Mapped[str]=mapped_column(String(300),default='Não verificada')
    class StatusEvent(Base):
        __tablename__='camera_status_events'
        id: Mapped[int]=mapped_column(primary_key=True)
        camera_id: Mapped[int]=mapped_column(Integer,index=True)
        name: Mapped[str]=mapped_column(String(100))
        previous: Mapped[str]=mapped_column(String(20))
        status: Mapped[str]=mapped_column(String(20))
        timestamp: Mapped[int]=mapped_column(Integer,index=True)
        diagnostic: Mapped[str]=mapped_column(String(300))
    class Observation(Base):
        __tablename__='camera_observations'
        id: Mapped[int]=mapped_column(primary_key=True)
        camera_id: Mapped[int]=mapped_column(Integer,index=True)
        timestamp: Mapped[int]=mapped_column(Integer,index=True)
        valid_until: Mapped[int]=mapped_column(Integer,index=True)
        status: Mapped[str]=mapped_column(String(20))
    observation_index=Index("ix_observations_camera_time_id",Observation.camera_id,Observation.timestamp,Observation.id)
    class ConnectionRevision(Base):
        __tablename__='camera_connection_revisions'
        id:Mapped[int]=mapped_column(primary_key=True)
        version:Mapped[int]=mapped_column(Integer,default=0)
        free:Mapped[int]=mapped_column(Integer,default=0)
        signature:Mapped[str]=mapped_column(String(64),default="")
    interval=max(30,int(os.environ.get('MONITOR_INTERVAL','60')))
    workers=max(1,min(32,int(os.environ.get('MONITOR_WORKERS','16'))))
    per_recorder=max(1,min(workers,int(os.environ.get('MONITOR_PER_RECORDER','2'))))
    stable_interval=max(interval,int(os.environ.get('MONITOR_STABLE_INTERVAL','120')))
    deep_interval=max(60,int(os.environ.get('MONITOR_DEEP_INTERVAL','900')))
    ttl=max(180,stable_interval*3)
    deep_at={}
    enabled=os.environ.get('MONITOR_ENABLED','true').lower()=='true'
    stop_event=threading.Event()
    monitor_state={'enabled':enabled,'running':False,'interval':interval,'stable_interval':stable_interval,'workers':workers,'per_recorder':per_recorder,'stale':0,'oldest_check_seconds':0,'last_cycle':0,'in_progress':0,'configured':0,'last_error':None}
    monitor_thread=None
    key=os.environ.get('CAMERA_KEY','')
    if not key: raise RuntimeError('Execute configurar.ps1 para gerar CAMERA_KEY.')
    cipher=Fernet(key.encode())
    live_evidence={};evidence_lock=threading.Lock()
    tickets={}; config_lock=threading.Lock(); probe_slots=threading.BoundedSemaphore(workers+2)
    media_client=httpx.Client(timeout=25,follow_redirects=True,trust_env=False,limits=httpx.Limits(max_connections=40,max_keepalive_connections=20))
    api_base=os.environ.get('MEDIA_API','http://video:9997')
    hls_base=os.environ.get('MEDIA_HLS','http://video:8888')
    from backend.transcoding import Converters
    converters=Converters(limit=max(1,min(4,int(os.environ.get('TRANSCODE_MAX','2')))))
    codec_cache={}
    live_slots=threading.BoundedSemaphore(2)
    preparations=Preparations()
    from backend.alerts import configure_alerts
    alert_probe,alert_reset,start_alerts,stop_alerts=configure_alerts(app,Base,Session,Camera,User,Audit,authenticated,Connection,stable_interval)
    from backend.channel_state import configure as configure_channel_state
    recorder_state=configure_channel_state(app,Base,Session,Camera,Connection,cipher,admin,authenticated,Audit)
    mode_table=Base.metadata.tables['channel_modes']
    def is_free(id,session=None):
        if session is not None:return bool(session.scalar(select(mode_table.c.is_free).where(mode_table.c.id==id)))
        with Session() as s:return is_free(id,s)
    def free_ids():
        with Session() as s:return set(s.scalars(select(mode_table.c.id).where(mode_table.c.is_free==1)))
    def save_config(session,camera,body):
        record=session.get(Connection,camera.id)
        if not record: record=Connection(id=camera.id);session.add(record)
        revision=session.get(ConnectionRevision,camera.id)
        old_password=cipher.decrypt(record.password_encrypted.encode()).decode() if record.password_encrypted else ''
        signature=hmac.new(key.encode(),json.dumps([camera.ip,camera.port,camera.channel,camera.manufacturer,body.device_type,body.username,body.stream,body.rtsp_path,body.password or old_password,bool(body.is_free)],ensure_ascii=False).encode(),hashlib.sha256).hexdigest()
        if revision and revision.signature==signature:return
        if not revision:revision=ConnectionRevision(id=camera.id,version=0,free=0);session.add(revision)
        revision.version=(revision.version or 0)+1;revision.free=int(body.is_free);revision.signature=signature
        record.device_type=body.device_type;record.username=body.username;record.stream=body.stream;record.path=body.rtsp_path
        if body.password: record.password_encrypted=cipher.encrypt(body.password.encode()).decode()
        converters.remove(camera.id);codec_cache.pop(camera.id,None);deep_at.pop(camera.id,None)
        with evidence_lock:live_evidence.pop(camera.id,None)
        for ticket,item in list(tickets.items()):
            if item['camera_id']==camera.id:tickets.pop(ticket,None)
        alert_reset(session,camera.id)
        now=int(time.time())
        session.add(Observation(camera_id=camera.id,timestamp=now,valid_until=now+ttl,status='unknown'))
        record.status='unknown';record.checked_at=0;record.diagnostic='Configuração alterada. Teste a conexão.'
    def data(r,free=False):
        if not r:return {'device_type':'nvr','username':'','has_password':False,'stream':'secondary','rtsp_path':'','status':'unknown','checked_at':0,'diagnostic':'Preencha as credenciais para iniciar o monitoramento.'}
        expired=time.time()-r.checked_at>ttl
        return {'device_type':r.device_type,'username':r.username,'has_password':bool(r.password_encrypted),'stream':r.stream,'rtsp_path':r.path,'is_free':free,'status':'free' if free else ('unknown' if expired and r.status!='offline' else r.status),'last_status':r.status,'verification_stale':expired,'checked_at':r.checked_at,'diagnostic':'Canal livre. Monitoramento e alertas desativados.' if free else ('Verificação vencida. Último resultado: '+r.status+'. Aguardando nova verificação.' if expired and r.checked_at else r.diagnostic)}
    def config_data(id):
        with Session() as s:return data(s.get(Connection,id),is_free(id,s))
    def all_configs():
        with Session() as s:
            free=set(s.scalars(select(mode_table.c.id).where(mode_table.c.is_free==1)))
            return {r.id:data(r,r.id in free) for r in s.scalars(select(Connection))}
    def source_snapshot(id):
        with Session() as s:
            c=s.get(Camera,id);r=s.get(Connection,id)
            if not c:raise HTTPException(404,'Câmera inexistente.')
            if is_free(id,s):raise HTTPException(409,'Canal livre. Reative o canal para testar ou abrir o vídeo.')
            if not r or not r.username or not r.password_encrypted:raise HTTPException(422,'Preencha usuário e senha do equipamento e salve o cadastro.')
            password=cipher.decrypt(r.password_encrypted.encode()).decode()
            channel=c.channel if r.device_type=='nvr' else 1
            path=r.path or (f'/cam/realmonitor?channel={channel}&subtype={0 if r.stream=="primary" else 1}' if c.manufacturer=='Intelbras' else f'/Streaming/Channels/{channel}{"01" if r.stream=="primary" else "02"}')
            host=f'[{c.ip}]' if ':' in c.ip else c.ip
            rev=s.get(ConnectionRevision,id)
            return f'rtsp://{quote(r.username,safe="")}:{quote(password,safe="")}@{host}:{c.port}{path}',c.ip,c.port,rev.version if rev else 0
    def source(id):return source_snapshot(id)[:3]
    def gateway(id):
        name=f'cam{id}'
        url,_,_=source(id)
        try:
            with config_lock,httpx.Client(timeout=12) as client:
                body={'source':url,'sourceOnDemand':True,'rtspTransport':'tcp','sourceOnDemandStartTimeout':'20s','sourceOnDemandCloseAfter':'10s'}
                current=client.get(api_base+'/v3/config/paths/get/'+name)
                if current.status_code==200:
                    old=current.json()
                    if old.get('source')!=url:
                        result=client.patch(api_base+'/v3/config/paths/patch/'+name,json=body)
                        result.raise_for_status()
                elif current.status_code==404:
                    client.post(api_base+'/v3/config/paths/add/'+name,json=body).raise_for_status()
                else: current.raise_for_status()
        except httpx.HTTPError:raise HTTPException(502,'Gateway de vídeo indisponível. Verifique o serviço video.')
        return name
    @app.post('/api/cameras/{id}/test')
    def test(id:int,user=Depends(admin),quick:bool=False):
        started=time.monotonic()
        url,ip,port,revision=source_snapshot(id)
        if not probe_slots.acquire(blocking=False):raise HTTPException(429,'Há testes em andamento. Tente novamente.')
        try:
            channel_result=recorder_state(id)
            state_fallback=bool(channel_result and channel_result.get('unavailable'))
            if state_fallback:channel_result=None
            try:
                if channel_result:raise StopIteration
                with socket.create_connection((ip,port),timeout=2 if quick else 5):pass
            except StopIteration:
                result=channel_result
            except OSError:
                result={'status':'offline','network':False,'video':False,'diagnostic':'IP/porta sem conexão a partir do servidor. Verifique VPN, porta e firewall.'}
            else:
                try:
                    from backend.probe import probe_video,fast_probe_video,describe_probe
                    result=None
                    if quick and time.monotonic()-deep_at.get(id,float('-inf'))<deep_interval:
                        result=describe_probe(url)
                        if result['status']=='unknown':result=None
                    if result is None:
                        result=fast_probe_video(url) if quick else probe_video(url)
                        if result.get('status')=='online':deep_at[id]=time.monotonic()
                except (OSError,ValueError):raise HTTPException(503,'Ferramenta de teste de vídeo indisponível.')
            if state_fallback:result['diagnostic']='Consulta de estado do NVD indisponível; resultado obtido por RTSP. '+result['diagnostic']
            if result['status']!='online':deep_at.pop(id,None)
            if result.get('needs_slow'):return result
            with Session.begin() as s:
                camera=s.get(Camera,id,with_for_update=True);r=s.get(Connection,id)
                if not r or not camera:raise HTTPException(404,'Dispositivo removido durante a verificação.')
                current_revision=s.get(ConnectionRevision,id)
                if (current_revision.version if current_revision else 0)!=revision:raise HTTPException(409,'Configuração alterada durante o teste; resultado antigo descartado.')
                if is_free(id,s):raise HTTPException(409,'Canal marcado como livre durante a verificação.')
                with evidence_lock:evidence=live_evidence.get(id)
                if not channel_result and result['status']!='online' and evidence and evidence['revision']==revision and evidence['at']>=started and time.monotonic()-evidence['at']<15:
                    result={'status':'online','network':True,'video':True,'diagnostic':'Vídeo recebido pela reprodução ativa durante esta verificação. Imagem útil da câmera física não validada.'}
                if r.status!=result['status']:
                    s.add(StatusEvent(camera_id=id,name=camera.name,previous=r.status,status=result['status'],timestamp=int(time.time()),diagnostic=result['diagnostic']))
                now=int(time.time())
                previous=s.scalar(select(Observation).where(Observation.camera_id==id).order_by(Observation.timestamp.desc(),Observation.id.desc()).limit(1))
                if previous and previous.status==result['status'] and previous.valid_until>=now:
                    previous.valid_until=now+ttl
                else:s.add(Observation(camera_id=id,timestamp=now,valid_until=now+ttl,status=result['status']))
                r.status=result['status'];r.checked_at=int(time.time());r.diagnostic=result['diagnostic']
            if result.get('codec'):codec_cache[id]=(hashlib.sha256(url.encode()).hexdigest(),result['codec'],time.monotonic())
            alert_probe(id,result['status'])
            result['checked_at']=int(time.time())
            return result
        finally:probe_slots.release()
    def monitor():
        monitor_state['running']=True
        due={};streak={};pending={};slow_pending={};slow_queue={};rows=[];ids=[];rows_expire=0
        try:
            with ThreadPoolExecutor(max_workers=workers,thread_name_prefix='camera-probe') as pool,ThreadPoolExecutor(max_workers=2,thread_name_prefix='camera-retry') as retry_pool:
                while not stop_event.is_set():
                    try:
                        for future,id in list(pending.items()):
                            if not future.done():continue
                            retry_soon=False;outcome={}
                            try:
                                outcome=future.result()
                                if outcome.get('needs_slow'):slow_queue.setdefault(id,time.monotonic())
                            except HTTPException as e:
                                retry_soon=e.status_code==429
                                if e.status_code not in [404,409,422,429]:monitor_state['last_error']='Falha interna em uma verificação.'
                            except Exception:monitor_state['last_error']='Falha interna em uma verificação.'
                            streak[id]=streak.get(id,0)+1 if outcome.get('status')=='online' else 0
                            due[id]=time.monotonic()+(2 if retry_soon else stable_interval if streak[id]>=2 else interval)
                            pending.pop(future,None)
                        for future,id in list(slow_pending.items()):
                            if future.done():
                                try:future.result()
                                except Exception:monitor_state['last_error']='Falha em confirmação lenta.'
                                due[id]=time.monotonic()+interval
                                slow_pending.pop(future,None)
                        if time.monotonic()>=rows_expire:
                          with Session() as s:
                            raw=s.execute(select(Connection.id,Camera.ip,Camera.port,Connection.checked_at).join(Camera,Camera.id==Connection.id).where(Connection.username!='',Connection.password_encrypted!='',~Connection.id.in_(select(mode_table.c.id).where(mode_table.c.is_free==1)))).all()
                            rows=[(id,(ip,port),checked) for id,ip,port,checked in raw]
                            ids=[id for id,host,checked in rows]
                          rows_expire=time.monotonic()+2
                        eligible=set(ids)
                        due={k:v for k,v in due.items() if k in eligible};streak={k:v for k,v in streak.items() if k in eligible}
                        slow_queue={id:queued for id,queued in slow_queue.items() if id in eligible}
                        busy=set(pending.values())|set(slow_pending.values())
                        from backend.scheduling import select_ready
                        hosts={id:host for id,host,checked in rows}
                        for id in sorted(slow_queue,key=slow_queue.get):
                            if len(slow_pending)>=2:break
                            if id in busy or sum(hosts.get(i)==hosts[id] for i in busy)>=max(1,per_recorder-1):continue
                            slow_pending[retry_pool.submit(test,id,{'username':'monitor','role':'admin'})]=id
                            slow_queue.pop(id,None);busy.add(id)
                        for id in select_ready(rows,due,busy,time.monotonic(),workers+2,per_recorder)[:max(0,workers-len(pending))]:
                            pending[pool.submit(test,id,{'username':'monitor','role':'admin'},True)]=id

                        now=int(time.time());ages=[max(0,now-checked) for id,host,checked in rows if checked]
                        stale=sum(1 for id,host,checked in rows if not checked or now-checked>ttl)
                        monitor_state.update(last_cycle=now,in_progress=len(pending),slow_in_progress=len(slow_pending),slow_waiting=len(slow_queue),configured=len(ids),stale=stale,oldest_check_seconds=max(ages,default=0))
                    except Exception:
                        monitor_state['last_error']='Falha ao consultar a fila de monitoramento.'
                        logging.getLogger('scheffer.monitor').warning('Falha na fila de monitoramento; nova tentativa em breve.')
                    stop_event.wait(1)
        finally:monitor_state['running']=False
    def start_monitor():
        nonlocal monitor_thread,media_client
        if media_client.is_closed:media_client=httpx.Client(timeout=25,follow_redirects=True,trust_env=False,limits=httpx.Limits(max_connections=40,max_keepalive_connections=20))
        observation_index.create(Session.kw["bind"],checkfirst=True)
        # Seed revisions for pre-upgrade devices without changing their status.
        with Session.begin() as session:
            existing=set(session.scalars(select(ConnectionRevision.id)))
            free=set(session.scalars(select(mode_table.c.id).where(mode_table.c.is_free==1)))
            for record,camera in session.execute(select(Connection,Camera).join(Camera,Camera.id==Connection.id)):
                if camera.id in existing:continue
                password=cipher.decrypt(record.password_encrypted.encode()).decode() if record.password_encrypted else ''
                signature=hmac.new(key.encode(),json.dumps([camera.ip,camera.port,camera.channel,camera.manufacturer,record.device_type,record.username,record.stream,record.path,password,camera.id in free],ensure_ascii=False).encode(),hashlib.sha256).hexdigest()
                session.add(ConnectionRevision(id=camera.id,version=0,free=int(camera.id in free),signature=signature))
        converters.start()
        start_alerts()
        if enabled:
            stop_event.clear();monitor_thread=threading.Thread(target=monitor,name='camera-monitor',daemon=True);monitor_thread.start()
    def stop_monitor():
        converters.stop()
        stop_alerts()
        stop_event.set()
        if monitor_thread:monitor_thread.join(timeout=25)
        media_client.close()
    @app.get('/api/monitor')
    def monitor_info(user=Depends(authenticated)):return dict(monitor_state)
    @app.get('/api/events')
    def events(user=Depends(authenticated)):
        with Session() as s:
            return [{k:getattr(e,k) for k in ['id','camera_id','name','previous','status','timestamp','diagnostic']} for e in s.scalars(select(StatusEvent).order_by(StatusEvent.id.desc()).limit(200))]
    @app.get('/api/overview')
    def overview(user=Depends(authenticated)):
        now=time.time()
        with Session() as s:
            registered=s.scalar(select(func.count(User.id)))
            changes=s.scalar(select(func.count(StatusEvent.id)).where(StatusEvent.timestamp>=now-86400))
            offline_changes=s.scalar(select(func.count(StatusEvent.id)).where(StatusEvent.timestamp>=now-86400,StatusEvent.status=='offline'))
            latest=dict(s.execute(select(StatusEvent.camera_id,func.max(StatusEvent.timestamp)).where(StatusEvent.status=='offline').group_by(StatusEvent.camera_id)).all())
            free=set(s.scalars(select(mode_table.c.id).where(mode_table.c.is_free==1)))
            configs={r.id:data(r,r.id in free) for r in s.scalars(select(Connection))}
            devices=list(s.scalars(select(Camera)))
        offline_recent=offline_old=offline_unknown=0
        for c in devices:
            if configs.get(c.id,{}).get('status')!='offline':continue
            changed=latest.get(c.id)
            if changed is None:offline_unknown+=1
            elif now-changed>=72*3600:offline_old+=1
            else:offline_recent+=1
        users={t['username'] for t in tokens.values() if t['expires']>now and now-t.get('last_seen',0)<60}
        free=free_ids()
        views=sum(1 for t in tickets.values() if t['camera_id'] not in free and t['expires']>now and t['session'] in tokens.values() and t['session']['expires']>now and now-t.get('last_request',0)<30)
        return {'free_channels':len(free),'registered_users':registered,'online_users':len(users),'live_views':views,'status_changes_24h':changes,'offline_changes_24h':offline_changes,'offline_recent':offline_recent,'offline_old':offline_old,'offline_unknown':offline_unknown,'device_types':{'nvr':sum(1 for c in devices if configs.get(c.id,{}).get('device_type')=='nvr'),'camera':sum(1 for c in devices if configs.get(c.id,{}).get('device_type')=='camera'),'unknown':sum(1 for c in devices if c.id not in configs)}}
    @app.get('/api/dashboard')
    def dashboard(hours:int=24,manufacturer:str='',camera_id:int=0,user=Depends(authenticated)):
        if hours not in [24,168,720]:raise HTTPException(422,'Selecione 24h, 7 dias ou 30 dias.')
        if manufacturer not in ['', 'Intelbras','Hikvision']:raise HTTPException(422,'Fabricante inválido.')
        from backend.analytics import aggregate
        end=int(time.time());start=end-hours*3600
        with Session() as s:
            query=select(Camera)
            if manufacturer:query=query.where(Camera.manufacturer==manufacturer)
            if camera_id:query=query.where(Camera.id==camera_id)
            devices=list(s.scalars(query))
            free=set(s.scalars(select(mode_table.c.id).where(mode_table.c.is_free==1)))
            configs={r.id:data(r,r.id in free) for r in s.scalars(select(Connection))}
            cams=[{'id':c.id,'name':c.name,'manufacturer':c.manufacturer,'unit_id':c.unit_id,'status':configs.get(c.id,{}).get('status','unknown'),'checked_at':configs.get(c.id,{}).get('checked_at',0)} for c in devices]
            cams=[c for c in cams if c["status"]!="free"]
            ids=[c["id"] for c in cams]
            from backend.analytics import compact_observations
            samples=s.scalars(select(Observation).where(Observation.camera_id.in_(ids),Observation.valid_until>start,Observation.timestamp<=end).order_by(Observation.camera_id,Observation.timestamp,Observation.id).execution_options(yield_per=2000)) if ids else []
            observations=compact_observations(({'id':r.id,'camera_id':r.camera_id,'timestamp':r.timestamp,'valid_until':r.valid_until,'status':r.status} for r in samples),start,end)
        return aggregate(cams,observations,start,end)
    @app.delete('/api/cameras/{id}')
    def remove_camera(id:int,user=Depends(admin)):
        with Session.begin() as s:
            camera=s.get(Camera,id)
            if not camera:raise HTTPException(404,'Dispositivo inexistente.')
            s.add(Audit(username=user['username'],action=('delete: '+camera.name)[:100],camera_id=id,timestamp=int(time.time())))
            r=s.get(Connection,id)
            if r:s.delete(r)
            app.state.delete_inventory(s,id)
            s.execute(mode_table.delete().where(mode_table.c.id==id))
            s.delete(camera)
        for key,item in list(tickets.items()):
            if item['camera_id']==id:tickets.pop(key,None)
        converters.remove(id);codec_cache.pop(id,None)
        cleanup=True
        try:
            response=httpx.delete(api_base+f'/v3/config/paths/delete/cam{id}',timeout=10)
            cleanup=response.status_code in [200,404]
        except httpx.HTTPError:cleanup=False
        return {'removed':True,'gateway_cleaned':cleanup}
    def prepare_live(id,user,cancel,client_key):
        deadline=time.monotonic()+4
        while not live_slots.acquire(timeout=0.1):
            if cancel.is_set():raise HTTPException(409,'Abertura cancelada.')
            if time.monotonic()>deadline:raise HTTPException(429,'Há vídeos sendo preparados. Tente novamente em alguns segundos.')
        try:
            url,_,_,revision=source_snapshot(id)
            signature=hashlib.sha256(url.encode()).hexdigest()
            cached=codec_cache.get(id)
            if cached and cached[0]==signature and time.monotonic()-cached[2]<180:codec=cached[1]
            else:
                try:codec=probe_codec(url,cancel)
                except (OSError,ValueError):raise HTTPException(503,'Não foi possível identificar o codec do vídeo.')
                codec_cache[id]=(signature,codec,time.monotonic())
            if cancel.is_set():raise HTTPException(409,'Abertura cancelada.')
            if codec=='h264':converters.remove(id);name=gateway(id);converted=False
            elif codec in ('hevc','h265','mjpeg'):
                name=f'cam{id}h264';converted=True
                def prepare():
                    try:
                        with config_lock,httpx.Client(timeout=12) as client:
                            current=client.get(api_base+'/v3/config/paths/get/'+name)
                            if current.status_code==404:client.post(api_base+'/v3/config/paths/add/'+name,json={'source':'publisher'}).raise_for_status()
                            else:current.raise_for_status()
                    except httpx.HTTPError:raise HTTPException(502,'Gateway de conversão indisponível.')
                converters.ensure(id,url,'rtsp://video:8554/'+name,prepare)
            else:raise HTTPException(422,'Codec não suportado para visualização: '+str(codec))
        finally:live_slots.release()
        now=time.time()
        for k in list(tickets):
            if tickets[k]['expires']<now:tickets.pop(k,None)
        ticket=secrets.token_urlsafe(32)
        tickets[ticket]={'client_key':client_key,'created':now,'name':name,'camera_id':id,'revision':revision,'converted':converted,'username':user['username'],'expires':now+3600,'session':user,'assets':{'index.m3u8':hls_base+'/'+name+'/index.m3u8'}}
        return {'url':f'/api/live/{ticket}/index.m3u8','expires_in':3600,'transport':'HLS','converted':converted}
    def release_client(client_key,user):
        preparations.cancel((user['username'],client_key))
        removed=[]
        for key,item in list(tickets.items()):
            if item.get('client_key')==client_key and item['session'] is user:
                removed.append(item['camera_id']);tickets.pop(key,None)
        for id in set(removed):
            others=any(t['camera_id']==id and t['session'] in tokens.values() and t['expires']>time.time() and time.time()-t.get('last_request',t.get('created',0))<45 for t in list(tickets.values()))
            if not others:
                converters.remove(id)
                with evidence_lock:live_evidence.pop(id,None)
    @app.post('/api/live-cancel')
    def cancel_live(request:Request,user=Depends(authenticated)):
        client_key=request.headers.get('X-Video-Client','')[:100]
        if client_key:release_client(client_key,user)
        return {'ok':True}
    @app.post('/api/cameras/{id}/live')
    async def live(id:int,request:Request,user=Depends(authenticated)):
        client_key=request.headers.get('X-Video-Client','')[:100] or secrets.token_urlsafe(12)
        await asyncio.to_thread(release_client,client_key,user)
        key=(user['username'],client_key);cancel=preparations.begin(key)
        task=asyncio.create_task(asyncio.to_thread(prepare_live,id,user,cancel,client_key))
        try:
            while not task.done():
                await asyncio.wait({task},timeout=0.1)
                if await request.is_disconnected():cancel.set()
            result=await task
            if cancel.is_set():
                tickets.pop(result['url'].split('/')[-2],None)
                raise HTTPException(409,'Abertura cancelada.')
            return result
        finally:preparations.finish(key,cancel)
    class LiveConfirmationInput(BaseModel):
        ticket:str=Field(min_length=20,max_length=100,pattern=r'^[A-Za-z0-9_-]+$')
    @app.post('/api/live-confirm')
    def confirm_live(body:LiveConfirmationInput,request:Request,user=Depends(authenticated)):
        item=tickets.get(body.ticket);now=int(time.time())
        if not item or item['expires']<now:raise HTTPException(409,'Reprodução encerrada ou expirada.')
        if item['session'] is not user or item['client_key']!=request.headers.get('X-Video-Client',''):
            raise HTTPException(403,'A reprodução pertence a outra sessão.')
        if time.monotonic()-item.get('media_at',float('-inf'))>15:
            return {'confirmed':False,'reason':'Aguardando dados recentes de vídeo pelo gateway.'}
        id=item['camera_id']
        with Session.begin() as session:
            camera=session.get(Camera,id,with_for_update=True);record=session.get(Connection,id)
            revision=session.get(ConnectionRevision,id)
            if not camera or not record:raise HTTPException(404,'Dispositivo removido.')
            if is_free(id,session):raise HTTPException(409,'Canal livre. Reprodução não confirma monitoramento.')
            if (revision.version if revision else 0)!=item['revision']:
                raise HTTPException(409,'Configuração mudou. Abra novamente o vídeo.')
            if record.status=='offline' and record.diagnostic.startswith('Estado do canal informado pelo gravador:'):
                return {'confirmed':False,'reason':'O gravador informou câmera desconectada; reprodução não substitui esse diagnóstico.'}
            # A delivered media fragment and browser playback progress are required;
            # a ticket, playlist, init MP4, codec detection or click is insufficient.
            diagnostic='Vídeo recebido e reproduzido pelo player. Stream disponível; imagem útil da câmera física não validada.'
            if record.status=='online' and now-record.checked_at<30:
                checked=record.checked_at;diagnostic=record.diagnostic
            else:
                if record.status!='online':session.add(StatusEvent(camera_id=id,name=camera.name,previous=record.status,status='online',timestamp=now,diagnostic=diagnostic))
                previous=session.scalar(select(Observation).where(Observation.camera_id==id).order_by(Observation.timestamp.desc(),Observation.id.desc()).limit(1))
                if previous and previous.status=='online' and previous.valid_until>=now:previous.valid_until=now+ttl
                else:session.add(Observation(camera_id=id,timestamp=now,valid_until=now+ttl,status='online'))
                record.status='online';record.checked_at=now;record.diagnostic=diagnostic;checked=now
        with evidence_lock:live_evidence[id]={'revision':item['revision'],'at':time.monotonic()}
        alert_probe(id,'online')
        return {'confirmed':True,'camera_id':id,'status':'online','checked_at':checked,'diagnostic':diagnostic}
    def media_fragment(payload,asset):
        if asset.endswith('.ts'):return len(payload)>=188 and payload[0]==0x47
        if not asset.endswith(('.mp4','.m4s')):return False
        offset=0;moof=mdat=False
        while offset+8<=len(payload):
            size=int.from_bytes(payload[offset:offset+4],'big');kind=payload[offset+4:offset+8];header=8
            if size==1:
                if offset+16>len(payload):return False
                size=int.from_bytes(payload[offset+8:offset+16],'big');header=16
            elif size==0:size=len(payload)-offset
            if size<header or offset+size>len(payload):return False
            moof=moof or kind==b'moof';mdat=mdat or (kind==b'mdat' and size>header)
            offset+=size
        return moof and mdat
    @app.get('/api/live/{ticket}/{asset}')
    def proxy(ticket:str,asset:str):
        item=tickets.get(ticket)
        if not item or item['expires']<time.time() or item['session']['expires']<time.time() or item['session'] not in tokens.values():raise HTTPException(401,'Sessão de vídeo expirada. Abra a câmera novamente.')
        if is_free(item['camera_id']):tickets.pop(ticket,None);raise HTTPException(409,'Canal livre. Vídeo desativado.')
        if not re.fullmatch(r'[A-Za-z0-9_-]+\.(m3u8|mp4|m4s|ts)',asset):raise HTTPException(400,'Recurso inválido.')
        target=item['assets'].get(asset)
        if not target:raise HTTPException(404,'Recurso de vídeo desconhecido.')
        if item['converted']:converters.touch(item['camera_id'])
        try:
            r=media_client.get(target)
        except httpx.HTTPError:raise HTTPException(502,'Sem resposta do gateway. Verifique VPN e stream.')
        if r.status_code==200:item['last_request']=time.time();item['session']['last_seen']=time.time()
        if r.status_code!=200:raise HTTPException(502,'Vídeo ainda indisponível. Verifique cadastro, codec e conexão.')
        if urlsplit(str(r.url)).netloc!=urlsplit(hls_base).netloc:raise HTTPException(502,'Redirecionamento inesperado do gateway.')
        if asset.endswith('.m3u8'):
            def reference(uri):
                absolute=urljoin(str(r.url),uri)
                parsed=urlsplit(absolute)
                if parsed.netloc!=urlsplit(hls_base).netloc or not parsed.path.startswith('/'+item['name']+'/'):raise HTTPException(502,'Referência de vídeo inesperada.')
                suffix=parsed.path.rsplit('.',1)[-1]
                if suffix not in ['m3u8','mp4','m4s','ts']:raise HTTPException(502,'Formato de segmento não suportado.')
                local=hashlib.sha256(absolute.encode()).hexdigest()[:24]+'.'+suffix
                item['assets'][local]=absolute
                return '/api/live/'+ticket+'/'+local
            lines=[]
            for line in r.text.splitlines():
                if line and not line.startswith('#'):line=reference(line.strip())
                elif 'URI="' in line:line=re.sub(r'URI="([^"]+)"',lambda m:'URI="'+reference(m[1])+'"',line)
                lines.append(line)
            return Response('\n'.join(lines)+'\n',media_type='application/vnd.apple.mpegurl',headers={'Cache-Control':'no-store','Referrer-Policy':'no-referrer'})
        if media_fragment(r.content,asset) and target!=item.get('last_media_asset'):
            item['last_media_asset']=target;item['media_at']=time.monotonic()
            with evidence_lock:
                evidence=live_evidence.get(item['camera_id'])
                if evidence and evidence['revision']==item['revision']:evidence['at']=item['media_at']
        return Response(r.content,media_type=r.headers.get('content-type','application/octet-stream'),headers={'Cache-Control':'no-store','Referrer-Policy':'no-referrer'})
    return save_config,config_data,all_configs,start_monitor,stop_monitor
