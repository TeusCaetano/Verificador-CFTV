import time, threading, logging
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import String, Integer, select, func
from sqlalchemy.orm import Mapped, mapped_column

class Treatment(BaseModel):
    acknowledge: bool=False
    owner: str=Field(default='',max_length=80)
    note: str=Field(default='',max_length=1000)
class MaintenanceInput(BaseModel):
    minutes: int=Field(ge=0,le=10080)
    reason: str=Field(min_length=1,max_length=300)

def configure_alerts(app,Base,Session,Camera,User,Audit,authenticated,Connection,interval):
    class Alert(Base):
        __tablename__='device_alerts'
        id: Mapped[int]=mapped_column(primary_key=True)
        camera_id: Mapped[int]=mapped_column(Integer,index=True)
        name: Mapped[str]=mapped_column(String(100))
        kind: Mapped[str]=mapped_column(String(20))
        state: Mapped[str]=mapped_column(String(20),default='open')
        opened_at: Mapped[int]=mapped_column(Integer)
        resolved_at: Mapped[int]=mapped_column(Integer,default=0)
        resolution: Mapped[str]=mapped_column(String(100),default='')
        owner: Mapped[str]=mapped_column(String(80),default='')
        acknowledged_by: Mapped[str]=mapped_column(String(80),default='')
    class AlertNote(Base):
        __tablename__='device_alert_notes'
        id: Mapped[int]=mapped_column(primary_key=True)
        alert_id: Mapped[int]=mapped_column(Integer,index=True)
        username: Mapped[str]=mapped_column(String(80))
        text: Mapped[str]=mapped_column(String(1200))
        timestamp: Mapped[int]=mapped_column(Integer)
    class AlertState(Base):
        __tablename__='device_alert_state'
        id: Mapped[int]=mapped_column(primary_key=True)
        failures: Mapped[int]=mapped_column(Integer,default=0)
        since: Mapped[int]=mapped_column(Integer)
        maintenance_until: Mapped[int]=mapped_column(Integer,default=0)
        reason: Mapped[str]=mapped_column(String(300),default='')
    lock=threading.RLock();stop=threading.Event();thread=None
    def state(s,id,now):
        r=s.info["states"].get(id) if "states" in s.info else s.get(AlertState,id)
        if not r:r=AlertState(id=id,failures=0,since=now,maintenance_until=0,reason='');s.add(r);s.flush()
        if "states" in s.info:s.info["states"][id]=r
        return r
    def active(s,id):
        if "active_alerts" in s.info:return [a for a in s.info["active_alerts"].get(id,[]) if a.state!="resolved"]
        return list(s.scalars(select(Alert).where(Alert.camera_id==id,Alert.state!='resolved')))
    def close(s,id,now,reason,kind=None):
        for a in active(s,id):
            if kind is None or a.kind==kind:a.state='resolved';a.resolved_at=now;a.resolution=reason
    def opening(s,c,kind,now):
        if not any(a.kind==kind for a in active(s,c.id)):s.add(Alert(camera_id=c.id,name=c.name,kind=kind,state='open',opened_at=now))
    modes=Base.metadata.tables["channel_modes"]
    def probe(id,status):
        now=int(time.time())
        with lock,Session.begin() as s:
            c=s.get(Camera,id)
            if not c:return
            r=state(s,id,now)
            if s.scalar(select(modes.c.is_free).where(modes.c.id==id)):
                r.failures=0;close(s,id,now,"Canal livre");return
            if status in ('online','offline'):close(s,id,now,'Verificação retomada','unverified')
            if r.maintenance_until>now:r.failures=0;return
            if status=='online':r.failures=0;close(s,id,now,'Stream disponível','offline')
            elif status=='offline':
                r.failures+=1
                if r.failures>=3:opening(s,c,'offline',now)
    def reset(id,reason='Cadastro alterado'):
        with lock,Session.begin() as s:
            now=int(time.time());r=state(s,id,now);r.failures=0;r.since=now;close(s,id,now,reason)
    def sweep():
        now=int(time.time());ttl=max(180,interval*3)
        with lock,Session.begin() as s:
            devices=list(s.scalars(select(Camera)));ids={c.id for c in devices}
            s.info['states']={r.id:r for r in s.scalars(select(AlertState))}
            s.info['active_alerts']={}
            for a in s.scalars(select(Alert).where(Alert.state!='resolved')):
                s.info['active_alerts'].setdefault(a.camera_id,[]).append(a)
                if a.camera_id not in ids:a.state='resolved';a.resolved_at=now;a.resolution='Dispositivo removido'
            configs={r.id:r for r in s.scalars(select(Connection))}
            free=set(s.scalars(select(modes.c.id).where(modes.c.is_free==1)))
            for c in devices:
                r=state(s,c.id,now);cfg=configs.get(c.id)
                if c.id in free:
                    r.failures=0;close(s,c.id,now,"Canal livre");continue
                if r.maintenance_until>now:continue
                if r.maintenance_until:
                    r.maintenance_until=0;r.failures=0;r.since=now
                last=max(r.since,cfg.checked_at if cfg else 0)
                if now-last>ttl:
                    r.failures=0;opening(s,c,'unverified',now)
    def worker():
        while not stop.is_set():
            try:sweep()
            except Exception:logging.getLogger('scheffer.alerts').exception('Falha ao avaliar alertas')
            stop.wait(10)
    def start():
        nonlocal thread
        sweep();stop.clear();thread=threading.Thread(target=worker,daemon=True,name='device-alerts');thread.start()
    def finish():
        stop.set()
        if thread:thread.join(timeout=12)
    def operator(user):
        if user['role'] not in ['admin','operator']:raise HTTPException(403,'Ação permitida a administrador ou operador.')
    @app.get('/api/alerts')
    def listing(state_filter:str='active',user=Depends(authenticated)):
        if state_filter not in ['active','resolved','all']:raise HTTPException(422,'Filtro inválido')
        sweep()
        with Session() as s:
            q=select(Alert)
            if state_filter=='active':q=q.where(Alert.state!='resolved')
            if state_filter=='resolved':q=q.where(Alert.state=='resolved')
            rows=list(s.scalars(q.order_by(Alert.id.desc()).limit(200)))
            notes={}
            if rows:
                for n in s.scalars(select(AlertNote).where(AlertNote.alert_id.in_([a.id for a in rows])).order_by(AlertNote.id)):
                    notes.setdefault(n.alert_id,[]).append({'username':n.username,'text':n.text,'timestamp':n.timestamp})
            recurring=list(s.execute(select(Alert.camera_id,func.count(Alert.id)).where(Alert.kind=='offline',Alert.opened_at>=time.time()-30*86400).group_by(Alert.camera_id).having(func.count(Alert.id)>=2)).all())
            summary={'recurring_devices':len(recurring),'open':s.scalar(select(func.count(Alert.id)).where(Alert.state!='resolved')),'acknowledged':s.scalar(select(func.count(Alert.id)).where(Alert.state=='acknowledged')),'maintenance':s.scalar(select(func.count(AlertState.id)).join(Camera,Camera.id==AlertState.id).where(AlertState.maintenance_until>time.time()))}
            return {'summary':summary,'rows':[{k:getattr(a,k) for k in ['id','camera_id','name','kind','state','opened_at','resolved_at','resolution','owner','acknowledged_by']}|{'notes':notes.get(a.id,[])} for a in rows]}
    @app.post('/api/alerts/{id}/treat')
    def treat(id:int,body:Treatment,user=Depends(authenticated)):
        operator(user)
        with lock,Session.begin() as s:
            a=s.get(Alert,id)
            if not a:raise HTTPException(404,'Alerta inexistente')
            if a.state=='resolved':raise HTTPException(409,'Alerta já resolvido')
            if body.owner and not s.scalar(select(User).where(User.username==body.owner,User.role.in_(['admin','operator']))):raise HTTPException(422,'Responsável deve ser administrador ou operador cadastrado')
            a.owner=body.owner
            if body.acknowledge:a.state='acknowledged';a.acknowledged_by=user['username']
            now=int(time.time());text=('Reconhecido. ' if body.acknowledge else '')+'Responsável: '+(body.owner or 'não atribuído')+'. '+body.note.strip()
            s.add(AlertNote(alert_id=id,username=user['username'],text=text,timestamp=now))
            s.add(Audit(username=user['username'],action='alert_treat',camera_id=a.camera_id,timestamp=now))
        return {'ok':True}
    @app.get('/api/alert-operators')
    def operators(user=Depends(authenticated)):
        with Session() as s:return list(s.scalars(select(User.username).where(User.role.in_(['admin','operator'])).order_by(User.username)))
    @app.get('/api/maintenance')
    def maintenance(user=Depends(authenticated)):
        with Session() as s:return [{'camera_id':r.id,'until':r.maintenance_until,'reason':r.reason} for r in s.scalars(select(AlertState).join(Camera,Camera.id==AlertState.id).where(AlertState.maintenance_until>time.time()))]
    @app.post('/api/cameras/{id}/maintenance')
    def change_maintenance(id:int,body:MaintenanceInput,user=Depends(authenticated)):
        operator(user)
        with lock,Session.begin() as s:
            if not s.get(Camera,id):raise HTTPException(404,'Dispositivo inexistente')
            if not body.reason.strip():raise HTTPException(422,'Informe o motivo')
            now=int(time.time());r=state(s,id,now);r.maintenance_until=now+body.minutes*60 if body.minutes else 0;r.reason=body.reason.strip();r.failures=0;r.since=now
            close(s,id,now,'Manutenção programada' if body.minutes else 'Manutenção encerrada')
            s.add(Audit(username=user['username'],action='maintenance_start' if body.minutes else 'maintenance_end',camera_id=id,timestamp=now))
        return {'ok':True}
    def changed(s,id):
        now=int(time.time());r=state(s,id,now);r.failures=0;r.since=now;close(s,id,now,'Canal livre' if s.scalar(select(modes.c.is_free).where(modes.c.id==id)) else 'Cadastro alterado')
    return probe,changed,start,finish
