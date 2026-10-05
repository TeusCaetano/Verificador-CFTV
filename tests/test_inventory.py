import os,sys,tempfile,time,unittest,base64,csv,io,threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch,MagicMock
from cryptography.fernet import Fernet
os.environ.update(DATABASE_URL='sqlite:///'+tempfile.mktemp(suffix='.db'),ADMIN_PASSWORD='test-password-1234',CAMERA_KEY=Fernet.generate_key().decode(),MONITOR_ENABLED='false')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.main import app,Session,Base,Unit,Camera,User,password_hash,engine
from fastapi.testclient import TestClient
from openpyxl import Workbook,load_workbook

class InventoryFlow(unittest.TestCase):
 def setUp(self):
  Base.metadata.drop_all(engine)
 def test_migration_preserves_existing_devices_and_encrypted_credentials(self):
  old_tables=[table for table in Base.metadata.sorted_tables if table.name not in ['inventory_sectors','camera_inventory']]
  Base.metadata.create_all(engine,tables=old_tables)
  cls={m.class_.__name__:m.class_ for m in Base.registry.mappers}
  encrypted=Fernet(os.environ['CAMERA_KEY'].encode()).encrypt(b'legacy-secret').decode()
  with Session.begin() as s:
   s.add(Unit(id=1,name='Três Lagoas',lat=-13,lng=-58))
   s.add(User(username='admin',password_hash=password_hash('test-password-1234'),role='admin'))
   for id in [10,11]:
    s.add(Camera(id=id,name='Legacy '+str(id),manufacturer='Intelbras',model='NVD3316',ip='10.104.3.9',port=5009,channel=1,lat=-13,lng=-58,unit_id=1))
    s.add(cls['Connection'](id=id,device_type='nvr',username='legacy',password_encrypted=encrypted,stream='secondary',path='',status='online',checked_at=int(time.time()),diagnostic='Stream disponível'))
  with TestClient(app) as c:
   token=c.post('/api/login',json={'username':'admin','password':'test-password-1234'}).json()['token'];h={'Authorization':'Bearer '+token}
   rows=c.get('/api/cameras',headers=h).json();self.assertEqual(len(rows),2);self.assertEqual(rows[0]['id'],10);self.assertEqual(rows[0]['status'],'online')
   self.assertEqual(rows[0]['unit_name'],'Três Lagoas');self.assertEqual(rows[0]['sector_id'],0)
   with Session() as s:
    self.assertEqual(s.get(cls['Connection'],10).password_encrypted,encrypted)
    self.assertIsNone(s.get(cls['CameraInventory'],11).source_key)

 def test_registration_preview_atomicity_scope_and_import(self):
  with TestClient(app) as c:
   def login(name):return {'Authorization':'Bearer '+c.post('/api/login',json={'username':name,'password':'test-password-1234'}).json()['token']}
   h=login('admin');c.post('/api/users',headers=h,json={'username':'viewer','password':'test-password-1234','role':'viewer'});view=login('viewer')
   unit=c.post('/api/units',headers=h,json={'name':'Cascata','lat':-12,'lng':-57}).json()['id']
   sec=c.post('/api/sectors',headers=h,json={'unit_id':unit,'name':'Portaria'}).json()['id']
   self.assertEqual(c.post('/api/units',headers=h,json={'name':' cascata ','lat':-12,'lng':-57}).status_code,409)
   body=dict(name='Existing',manufacturer='Intelbras',model='NVD3316',ip='10.104.3.9',port=5009,channel=1,lat=-13,lng=-58,username='camerauser',password='camera-pass',unit_id=1,device_type='nvr',recorder_name='NVR Piloto')
   r=c.post('/api/cameras',headers=h,json=body);self.assertEqual(r.status_code,201,r.text);cam=r.json()['id'];self.assertTrue(r.json()['has_password']);self.assertNotIn('password',r.json())
   self.assertEqual(c.post('/api/cameras',headers=h,json=body).status_code,409)
   self.assertEqual(c.post('/api/cameras',headers=h,json=body|{'unit_id':1,'sector_id':sec}).status_code,422)
   self.assertEqual(c.put(f'/api/cameras/{cam}',headers=h,json=body|{'password':'','name':'Updated'}).status_code,200)
   device=body|{'unit_id':unit,'sector_id':sec,'recorder_name':'NVR Portaria'}
   preview=c.post('/api/inventory/batch-preview',headers=h,json={'device':device,'channels':[1,2,3],'prefix':'PORT'});self.assertEqual(preview.status_code,200,preview.text);p=preview.json();self.assertEqual(p['valid'],3);self.assertNotIn('camera-pass',preview.text)
   self.assertEqual(len(c.get('/api/cameras',headers=h).json()),1)
   self.assertEqual(c.post('/api/inventory/commit',headers=view,json={'token':p['token']}).status_code,403)
   other=login('admin');self.assertEqual(c.post('/api/inventory/commit',headers=other,json={'token':p['token']}).status_code,409)
   r=c.post('/api/inventory/commit',headers=h,json={'token':p['token']});self.assertEqual(r.status_code,201,r.text);self.assertEqual(r.json()['created'],3)
   self.assertEqual(c.post('/api/inventory/commit',headers=h,json={'token':p['token']}).status_code,409)
   devices=c.get('/api/cameras',headers=h).json();self.assertEqual(len(devices),4);self.assertEqual(devices[-1]['unit_name'],'Cascata');self.assertEqual(devices[-1]['sector_name'],'Portaria')
   p=c.post('/api/inventory/batch-preview',headers=h,json={'device':device,'channels':[1,4],'prefix':'PORT'}).json();self.assertEqual(p['invalid'],1);self.assertIsNone(p['token'])
   # Preview is valid, another registration arrives, commit rolls back all rows.
   p=c.post('/api/inventory/batch-preview',headers=h,json={'device':device,'channels':[4,5],'prefix':'PORT'}).json()
   self.assertEqual(c.post('/api/cameras',headers=h,json=device|{'name':'Other','channel':5}).status_code,201)
   self.assertEqual(c.post('/api/inventory/commit',headers=h,json={'token':p['token']}).status_code,409)
   self.assertFalse(any(x['unit_id']==unit and x['channel']==4 for x in c.get('/api/cameras',headers=h).json()))
   # CSV parsing with quotes, semicolon, accents, defaults and per-row location.
   text='nome;fabricante;ip;porta;canal;unidade;setor;tipo\n"Portaria; Leste";Hikvision;10.10.10.2;554;1;Cascata;Portaria;camera\n'
   r=c.post('/api/inventory/import-preview',headers=h,json={'format':'csv','content':base64.b64encode(text.encode('utf-8-sig')).decode(),'defaults':{'unit_id':1,'username':'operator','password':'secretcam'}});self.assertEqual(r.status_code,200,r.text);p=r.json();self.assertEqual(p['valid'],1);self.assertNotIn('secretcam',r.text)
   self.assertEqual(c.post('/api/inventory/commit',headers=h,json={'token':p['token']}).status_code,201)
   cam2=c.get('/api/cameras',headers=h).json()[-1];self.assertEqual(cam2['unit_id'],unit);self.assertEqual(cam2['lat'],-12);self.assertEqual(cam2['channel'],1)
   # Excel import and authenticated templates.
   template=c.get('/api/inventory/template/xlsx',headers=h);self.assertEqual(template.status_code,200)
   wb=load_workbook(io.BytesIO(template.content));wb.active.append(['Armazém','Intelbras','VIP','camera','10.10.10.3',554,1,'Cascata','Portaria','','','','','','secondary','']);out=io.BytesIO();wb.save(out)
   p=c.post('/api/inventory/import-preview',headers=h,json={'format':'xlsx','content':base64.b64encode(out.getvalue()).decode(),'defaults':{'unit_id':1,'username':'operator','password':'secretcam'}}).json();self.assertEqual(p['valid'],1,p)
   self.assertEqual(c.post('/api/inventory/commit',headers=h,json={'token':p['token']}).status_code,201)
   self.assertEqual(c.get('/api/inventory/template/csv').status_code,401)
   # New duplicates are blocked even after deletion followed by re-registration.
   with patch('backend.video.httpx.delete',return_value=MagicMock(status_code=200)):
    self.assertEqual(c.delete(f'/api/cameras/{cam}',headers=h).status_code,200)
   self.assertEqual(c.post('/api/cameras',headers=h,json=body).status_code,201)
   for path in ['/api/dashboard','/api/overview','/api/alerts','/api/maintenance','/api/sectors','/api/units']:
    self.assertEqual(c.get(path,headers=h).status_code,200,path)
   self.assertEqual(c.post('/api/inventory/batch-preview',headers=view,json={'device':body,'channels':[7],'prefix':'P'}).status_code,403)
   self.assertEqual(c.post('/api/sectors',headers=view,json={'name':'X','unit_id':1}).status_code,403)

if __name__=='__main__':unittest.main()
