"""Organization and atomic, previewed inventory registration."""
import base64,csv,io,ipaddress,secrets,threading,time,zipfile
from fastapi import Depends,HTTPException
from fastapi.responses import Response
from pydantic import BaseModel,Field,ValidationError
from sqlalchemy import String,Integer,select
from sqlalchemy.orm import Mapped,mapped_column
from sqlalchemy.exc import IntegrityError

class UnitInput(BaseModel):
    name:str=Field(min_length=1,max_length=100)
    lat:float=Field(ge=-90,le=90)
    lng:float=Field(ge=-180,le=180)
class UnitLocationInput(BaseModel):
    lat:float=Field(ge=-90,le=90,allow_inf_nan=False)
    lng:float=Field(ge=-180,le=180,allow_inf_nan=False)
    camera_scope:str=Field(default='center',pattern='^(none|center|all)$')
class SectorInput(BaseModel):
    name:str=Field(min_length=1,max_length=100)
    unit_id:int=Field(default=0,ge=0)
class BatchInput(BaseModel):
    device:dict
    channels:list[int]=Field(min_length=1,max_length=256)
    prefix:str=Field(min_length=1,max_length=90)
    free_channels:list[int]=Field(default_factory=list,max_length=256)
class ImportInput(BaseModel):
    format:str=Field(pattern='^(csv|xlsx)$')
    content:str=Field(max_length=2800000)
    defaults:dict=Field(default_factory=dict)
class CommitInput(BaseModel):
    token:str=Field(min_length=1,max_length=100)

COLUMNS=['nome','fabricante','modelo','tipo','ip','porta','canal','unidade','setor','gravador','latitude','longitude','usuario','senha','stream','caminho_rtsp']


def configure_inventory(app,Base,Session,Camera,Unit,Audit,CameraInput,authenticated,admin,store_camera):
    class Sector(Base):
        __tablename__='inventory_sectors'
        id:Mapped[int]=mapped_column(primary_key=True)
        name:Mapped[str]=mapped_column(String(100))
        unit_id:Mapped[int]=mapped_column(Integer,index=True)
    class UnitSector(Base):
        __tablename__='inventory_unit_sectors'
        unit_id:Mapped[int]=mapped_column(Integer,primary_key=True)
        sector_id:Mapped[int]=mapped_column(Integer,primary_key=True)
    class CameraInventory(Base):
        __tablename__='camera_inventory'
        id:Mapped[int]=mapped_column(primary_key=True)
        sector_id:Mapped[int]=mapped_column(Integer,default=0,index=True)
        recorder_name:Mapped[str]=mapped_column(String(100),default='')
        source_key:Mapped[str|None]=mapped_column(String(200),unique=True,nullable=True)
    def source_key(body):
        return '|'.join(map(str,[body.unit_id,str(ipaddress.ip_address(str(body.ip))),body.port,body.device_type,body.channel if body.device_type=='nvr' else 1]))
    def migrate():
        # Only adds side tables; original device rows and credentials stay intact.
        with Session.begin() as s:
            # Idempotent migration: canonical global sector names and unit links.
            canonical={}
            for x in list(s.scalars(select(Sector).order_by(Sector.id))):
                key=x.name.strip().casefold()
                target=canonical.get(key)
                if target is None:canonical[key]=x;target=x
                if x.unit_id and not s.get(UnitSector,(x.unit_id,target.id)):
                    s.add(UnitSector(unit_id=x.unit_id,sector_id=target.id));s.flush()
                if x.id!=target.id:
                    for m in s.scalars(select(CameraInventory).where(CameraInventory.sector_id==x.id)):m.sector_id=target.id
                    for link in list(s.scalars(select(UnitSector).where(UnitSector.sector_id==x.id))):
                        if not s.get(UnitSector,(link.unit_id,target.id)):s.add(UnitSector(unit_id=link.unit_id,sector_id=target.id));s.flush()
                        s.delete(link)
                    s.delete(x)
                else:x.unit_id=0;x.name=x.name.strip()
            connection=Base.metadata.tables['camera_connections']
            existing={m.id:m for m in s.scalars(select(CameraInventory))}
            occupied={m.source_key for m in existing.values() if m.source_key}
            types=dict(s.execute(select(connection.c.id,connection.c.device_type)).all())
            for c in s.scalars(select(Camera).order_by(Camera.id)):
                if c.id in existing:continue
                key='|'.join(map(str,[c.unit_id,str(ipaddress.ip_address(c.ip)),c.port,types.get(c.id,'nvr'),c.channel if types.get(c.id,'nvr')=='nvr' else 1]))
                s.add(CameraInventory(id=c.id,sector_id=0,recorder_name='',source_key=None if key in occupied else key));occupied.add(key)
    def metadata():
        with Session() as s:
            sectors={x.id:x.name for x in s.scalars(select(Sector))}
            units={x.id:x.name for x in s.scalars(select(Unit))}
            return {c.id:{'unit_name':units.get(c.unit_id,''),'sector_id':m.sector_id if m else 0,'sector_name':sectors.get(m.sector_id,'') if m else '', 'recorder_name':m.recorder_name if m else ''} for c,m in s.execute(select(Camera,CameraInventory).outerjoin(CameraInventory,CameraInventory.id==Camera.id)).all()}
    def verify(s,body,id=None):
        if body.unit_id and not s.get(Unit,body.unit_id):raise HTTPException(422,'Unidade inexistente.')
        if body.sector_id:
            sector=s.get(Sector,body.sector_id)
            if not sector or not s.get(UnitSector,(body.unit_id,body.sector_id)):raise HTTPException(422,'Setor não pertence à unidade selecionada.')
        key=source_key(body);current=s.get(CameraInventory,id) if id else None
        if current and current.source_key==key:return key
        connection=Base.metadata.tables['camera_connections']
        for c,dtype in s.execute(select(Camera,connection.c.device_type).outerjoin(connection,connection.c.id==Camera.id).where(Camera.unit_id==body.unit_id,Camera.port==body.port)).all():
            if c.id==id:continue
            old='|'.join(map(str,[c.unit_id,str(ipaddress.ip_address(c.ip)),c.port,dtype or 'nvr',c.channel if (dtype or 'nvr')=='nvr' else 1]))
            if old==key:raise HTTPException(409,f'Duplicado: dispositivo "{c.name}" já usa este IP, porta, tipo e canal na unidade.')
        return key
    def save_metadata(s,camera,body):
        key=verify(s,body,camera.id)
        m=s.get(CameraInventory,camera.id)
        if not m:m=CameraInventory(id=camera.id);s.add(m)
        m.sector_id=body.sector_id;m.recorder_name=body.recorder_name.strip();m.source_key=key
    def delete_metadata(s,id):
        m=s.get(CameraInventory,id)
        if m:s.delete(m)
    @app.get('/api/sectors')
    def sectors(user=Depends(authenticated)):
        with Session() as s:
            links={}
            for sector_id,unit_id in s.execute(select(UnitSector.sector_id,UnitSector.unit_id)):links.setdefault(sector_id,[]).append(unit_id)
            return [{'id':x.id,'name':x.name,'unit_ids':links.get(x.id,[])} for x in s.scalars(select(Sector).order_by(Sector.name))]
    @app.post('/api/units',status_code=201)
    def create_unit(body:UnitInput,user=Depends(admin)):
        with Session.begin() as s:
            name=body.name.strip()
            if not name:raise HTTPException(422,'Informe o nome.')
            if any(u.name.casefold()==name.casefold() for u in s.scalars(select(Unit))):raise HTTPException(409,'Unidade já cadastrada.')
            u=Unit(name=name,lat=body.lat,lng=body.lng);s.add(u);s.flush()
            s.add(Audit(username=user['username'],action='unit_create: '+name[:80],camera_id=0,timestamp=int(time.time())))
            return {'id':u.id,'name':u.name,'lat':u.lat,'lng':u.lng}
    @app.patch('/api/units/{unit_id}/location')
    def update_unit_location(unit_id:int,body:UnitLocationInput,user=Depends(admin)):
        with Session.begin() as s:
            u=s.get(Unit,unit_id)
            if not u:raise HTTPException(404,'Unidade não encontrada.')
            old_lat,old_lng=u.lat,u.lng
            affected=0
            for c in s.scalars(select(Camera).where(Camera.unit_id==unit_id)):
                at_center=abs(c.lat-old_lat)<=0.000001 and abs(c.lng-old_lng)<=0.000001
                if body.camera_scope=='all' or (body.camera_scope=='center' and at_center):
                    c.lat=body.lat;c.lng=body.lng;affected+=1
                    s.add(Audit(username=user['username'],action='unit_position_update',camera_id=c.id,timestamp=int(time.time())))
            u.lat=body.lat;u.lng=body.lng
            s.add(Audit(username=user['username'],action='unit_location_update: '+str(unit_id)+' '+body.camera_scope+' '+str(affected),camera_id=0,timestamp=int(time.time())))
        return {'ok':True,'updated_cameras':affected}
    @app.post('/api/sectors',status_code=201)
    def create_sector(body:SectorInput,user=Depends(admin)):
        with Session.begin() as s:
            if body.unit_id and not s.get(Unit,body.unit_id):raise HTTPException(422,'Unidade inexistente.')
            name=body.name.strip()
            if not name:raise HTTPException(422,'Informe o nome.')
            if any(x.name.casefold()==name.casefold() for x in s.scalars(select(Sector))):raise HTTPException(409,'Setor já cadastrado no catálogo global.')
            x=Sector(name=name,unit_id=0);s.add(x);s.flush()
            if body.unit_id:s.add(UnitSector(unit_id=body.unit_id,sector_id=x.id))
            s.add(Audit(username=user['username'],action='sector_create: '+name[:80],camera_id=0,timestamp=int(time.time())))
            return {'id':x.id,'name':x.name,'unit_ids':[body.unit_id] if body.unit_id else []}
    @app.delete('/api/sectors/{sector_id}')
    def remove_sector(sector_id:int,user=Depends(admin)):
        with Session.begin() as s:
            x=s.get(Sector,sector_id)
            if not x:raise HTTPException(404,'Setor não encontrado.')
            if s.scalar(select(CameraInventory.id).where(CameraInventory.sector_id==sector_id).limit(1)) is not None:
                raise HTTPException(409,'Este setor possui dispositivos. Altere o setor deles antes de excluir.')
            if s.scalar(select(UnitSector.unit_id).where(UnitSector.sector_id==sector_id).limit(1)) is not None:
                raise HTTPException(409,'Este setor está vinculado a unidades. Desvincule primeiro.')
            s.add(Audit(username=user['username'],action='sector_delete: '+x.name[:80],camera_id=0,timestamp=int(time.time())))
            s.delete(x)
        return {'ok':True}
    @app.delete('/api/units/{unit_id}')
    def remove_unit(unit_id:int,user=Depends(admin)):
        with Session.begin() as s:
            x=s.get(Unit,unit_id)
            if not x:raise HTTPException(404,'Unidade não encontrada.')
            if s.scalar(select(Camera.id).where(Camera.unit_id==unit_id).limit(1)) is not None:
                raise HTTPException(409,'Esta unidade possui dispositivos. Altere a unidade deles antes de excluir.')
            if s.scalar(select(UnitSector.sector_id).where(UnitSector.unit_id==unit_id).limit(1)) is not None:
                raise HTTPException(409,'Esta unidade possui setores. Desvincule os setores primeiro.')
            s.add(Audit(username=user['username'],action='unit_delete: '+x.name[:80],camera_id=0,timestamp=int(time.time())))
            s.delete(x)
        return {'ok':True}
    @app.put('/api/units/{unit_id}/sectors/{sector_id}')
    def link_sector(unit_id:int,sector_id:int,user=Depends(admin)):
        with Session.begin() as s:
            if not s.get(Unit,unit_id) or not s.get(Sector,sector_id):raise HTTPException(404,'Unidade ou setor inexistente.')
            if not s.get(UnitSector,(unit_id,sector_id)):
                s.add(UnitSector(unit_id=unit_id,sector_id=sector_id))
                s.add(Audit(username=user['username'],action=f'sector_link: {unit_id}/{sector_id}',camera_id=0,timestamp=int(time.time())))
        return {'ok':True}
    @app.delete('/api/units/{unit_id}/sectors/{sector_id}')
    def unlink_sector(unit_id:int,sector_id:int,user=Depends(admin)):
        with Session.begin() as s:
            link=s.get(UnitSector,(unit_id,sector_id))
            if not link:raise HTTPException(404,'Vínculo não encontrado.')
            if s.scalar(select(Camera.id).join(CameraInventory,CameraInventory.id==Camera.id).where(Camera.unit_id==unit_id,CameraInventory.sector_id==sector_id).limit(1)) is not None:
                raise HTTPException(409,'Há dispositivos neste setor da unidade. Altere o setor deles antes de desvincular.')
            s.delete(link)
            s.add(Audit(username=user['username'],action=f'sector_unlink: {unit_id}/{sector_id}',camera_id=0,timestamp=int(time.time())))
        return {'ok':True}
    jobs={};lock=threading.RLock()
    def preview(rows,user):
        if not rows or len(rows)>1000:raise HTTPException(422,'Informe de 1 a 1.000 dispositivos por lote.')
        with lock:
            for k in list(jobs):
                if jobs[k]["session"] is user:jobs.pop(k)
        parsed=[];result=[];seen=set()
        with Session() as s:
            for number,row in enumerate(rows,1):
                errors=[];camera=None
                try:
                    camera=CameraInput.model_validate(row);key=source_key(camera)
                    if key in seen:errors.append('Duplicado dentro deste lote.')
                    seen.add(key)
                    verify(s,camera)
                    if not camera.username or not camera.password:errors.append('Informe usuário e senha para o novo dispositivo.')
                except ValidationError as e:
                    errors += [str(x['loc'][0])+': '+x['msg'] for x in e.errors()]
                except HTTPException as e:errors.append(e.detail)
                if errors:parsed.append(None)
                else:parsed.append(camera)
                result.append({'row':number,'name':str(row.get('name',''))[:100],'ip':str(row.get('ip',''))[:50],'channel':str(row.get('channel',''))[:20],'unit_id':camera.unit_id if camera else 0,'sector_id':camera.sector_id if camera else 0,'recorder_name':camera.recorder_name if camera else '', 'is_free':camera.is_free if camera else False,'errors':errors})
        valid=sum(1 for p in parsed if p is not None);token=None
        if valid==len(rows):
            with lock:
                now=time.time()
                for k in list(jobs):
                    if jobs[k]['expires']<now:jobs.pop(k)
                # Keep one preview per session; changing data invalidates the previous preview.
                for k in list(jobs):
                    if jobs[k]['session'] is user:jobs.pop(k)
                if len(jobs)>=20:raise HTTPException(429,'Há muitos lotes pendentes. Tente novamente em alguns minutos.')
                token=secrets.token_urlsafe(32);jobs[token]={'session':user,'expires':now+900,'rows':parsed}
        return {'token':token,'rows':result,'valid':valid,'invalid':len(rows)-valid,'total':len(rows),'expires_seconds':900 if token else 0}
    @app.post('/api/inventory/batch-preview')
    def batch_preview(body:BatchInput,user=Depends(admin)):
        if any(type(ch) is not int or ch<1 or ch>256 for ch in body.channels):raise HTTPException(422,'Canais devem ser inteiros de 1 a 256.')
        if len(set(body.channels))!=len(body.channels):raise HTTPException(422,'Selecione cada canal uma única vez.')
        if any(ch not in body.channels for ch in body.free_channels):raise HTTPException(422,'Canal livre deve estar na seleção de canais.')
        if body.device.get('rtsp_path'):raise HTTPException(422,'Cadastro em lote usa o caminho padrão por canal. Para caminho personalizado, cadastre individualmente.')
        return preview([body.device|{'name':body.prefix.strip()+f'-CAM{ch:02d}','channel':ch,'device_type':'nvr','is_free':ch in body.free_channels} for ch in body.channels],user)
    def file_rows(body):
        try:raw=base64.b64decode(body.content,validate=True)
        except Exception:raise HTTPException(422,'Arquivo inválido.')
        if len(raw)>2_000_000:raise HTTPException(413,'Arquivo excede 2 MB.')
        if body.format=='csv':
            try:text=raw.decode('utf-8-sig')
            except UnicodeDecodeError:
                try:text=raw.decode('cp1252')
                except UnicodeDecodeError:raise HTTPException(422,'CSV deve usar UTF-8 ou Windows-1252.')
            try:
                dialect=csv.Sniffer().sniff(text[:8192],delimiters=';,\t');values=[]
                for row in csv.reader(io.StringIO(text),dialect):
                    if len(values)>=1002:raise HTTPException(422,'Limite de 1.000 dispositivos por lote.')
                    values.append(row)
            except csv.Error:raise HTTPException(422,'CSV inválido. Use o modelo disponível.')
        else:
            try:
                with zipfile.ZipFile(io.BytesIO(raw)) as z:
                    if sum(i.file_size for i in z.infolist())>20_000_000:raise ValueError('xlsx grande')
                from openpyxl import load_workbook
                wb=load_workbook(io.BytesIO(raw),read_only=True,data_only=False);ws=wb.active
                if ws.max_column>16 or ws.max_row>1001:raise ValueError("Dimensões excedidas")
                values=[]
                for row in ws.iter_rows(values_only=True):
                    if len(values)>=1002:raise ValueError('muitas linhas')
                    values.append(list(row))
                wb.close()
            except Exception:raise HTTPException(422,'Excel inválido ou excede os limites. Use até 1.000 dispositivos na primeira aba.')
        if not values:raise HTTPException(422,'Arquivo vazio.')
        headers=[str(v or '').strip().lower() for v in values[0]]
        if len(set(headers))!=len(headers) or any(h not in COLUMNS for h in headers):raise HTTPException(422,'Cabeçalhos inválidos ou repetidos. Use o modelo disponível.')
        if not {'nome','fabricante','ip','porta','canal'}<=set(headers):raise HTTPException(422,'Colunas obrigatórias: nome, fabricante, ip, porta e canal.')
        rows=[]
        for row in values[1:]:
            if not any(v is not None and str(v).strip() for v in row):continue
            if len(row)>len(headers) and any(v is not None and str(v).strip() for v in row[len(headers):]):raise HTTPException(422,'Há valores sem cabeçalho no arquivo.')
            rows.append({h:row[i] if i<len(row) and row[i] is not None else '' for i,h in enumerate(headers)})
            if len(rows)>1000:raise HTTPException(422,'Limite de 1.000 dispositivos por lote.')
        return rows
    @app.post('/api/inventory/import-preview')
    def import_preview(body:ImportInput,user=Depends(admin)):
        raw_rows=file_rows(body);rows=[]
        with Session() as s:
            units=list(s.scalars(select(Unit)));sectors=list(s.scalars(select(Sector)));links={(x.unit_id,x.sector_id) for x in s.scalars(select(UnitSector))}
            for raw in raw_rows:
                row=dict(body.defaults)
                for col,key in {'nome':'name','fabricante':'manufacturer','modelo':'model','tipo':'device_type','ip':'ip','porta':'port','canal':'channel','gravador':'recorder_name','latitude':'lat','longitude':'lng','usuario':'username','senha':'password','stream':'stream','caminho_rtsp':'rtsp_path'}.items():
                    value=raw.get(col,'')
                    if value!='':row[key]=value
                row['device_type']={'gravador':'nvr','camera':'camera','câmera':'camera'}.get(str(row.get('device_type','nvr')).strip().lower(),row.get('device_type','nvr'))
                unit=raw.get('unidade','')
                if str(unit).strip():
                    matches=[u for u in units if u.name.casefold()==str(unit).strip().casefold() or str(u.id)==str(unit).strip()]
                    row['unit_id']=matches[0].id if len(matches)==1 else -1
                uid=row.get('unit_id',1);sector=raw.get('setor','')
                if str(sector).strip():
                    matches=[x for x in sectors if (uid,x.id) in links and (x.name.casefold()==str(sector).strip().casefold() or str(x.id)==str(sector).strip())]
                    row['sector_id']=matches[0].id if len(matches)==1 else -1
                u=next((u for u in units if u.id==uid),None)
                if u:row.setdefault('lat',u.lat);row.setdefault('lng',u.lng)
                rows.append(row)
        return preview(rows,user)
    @app.post('/api/inventory/commit',status_code=201)
    def commit(body:CommitInput,user=Depends(admin)):
        with lock:
            job=jobs.get(body.token)
            if not job or job['session'] is not user or job['expires']<time.time():raise HTTPException(409,'Prévia vencida ou inválida. Valide o lote novamente.')
            try:
                with Session.begin() as s:
                    ids=[store_camera(s,r,None,user) for r in job['rows']]
            except IntegrityError:raise HTTPException(409,'Um dispositivo foi cadastrado durante a importação. Valide novamente. Nenhum item deste lote foi salvo.')
            jobs.pop(body.token,None)
            return {'created':len(ids),'ids':ids}
    @app.get('/api/inventory/template/{format}')
    def template(format:str,user=Depends(authenticated)):
        if format=='csv':
            out=io.StringIO();csv.writer(out,delimiter=';').writerow(COLUMNS)
            return Response(('\ufeff'+out.getvalue()).encode('utf-8'),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="modelo-dispositivos.csv"'})
        if format=='xlsx':
            from openpyxl import Workbook
            wb=Workbook();ws=wb.active;ws.title='Dispositivos';ws.append(COLUMNS);ws.freeze_panes='A2';ws.auto_filter.ref='A1:P1'
            for col in ws.columns:ws.column_dimensions[col[0].column_letter].width=22
            out=io.BytesIO();wb.save(out)
            return Response(out.getvalue(),media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={'Content-Disposition':'attachment; filename="modelo-dispositivos.xlsx"'})
        raise HTTPException(422,'Formato inválido.')
    return metadata,verify,save_metadata,migrate,delete_metadata
