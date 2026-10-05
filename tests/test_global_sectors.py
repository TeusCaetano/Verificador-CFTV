import os,sys,tempfile,unittest
from unittest.mock import patch,MagicMock
from pathlib import Path
from cryptography.fernet import Fernet
os.environ.update(DATABASE_URL='sqlite:///'+tempfile.mktemp(suffix='.db'),ADMIN_PASSWORD='test-password-1234',CAMERA_KEY=Fernet.generate_key().decode(),MONITOR_ENABLED='false')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.main import app,Session,Base,migrate_inventory
from fastapi.testclient import TestClient
class GlobalSectors(unittest.TestCase):
 def test_reuse_migration_and_removal(self):
  with TestClient(app) as c:
   token=c.post('/api/login',json={'username':'admin','password':'test-password-1234'}).json()['token'];h={'Authorization':'Bearer '+token}
   uid=c.post('/api/units',headers=h,json={'name':'Outra','lat':-12,'lng':-57}).json()['id']
   models={m.class_.__name__:m.class_ for m in Base.registry.mappers};Sector=models['Sector'];Meta=models['CameraInventory']
   with Session.begin() as s:
    a=Sector(name='Portaria',unit_id=1);b=Sector(name=' portaria ',unit_id=uid);s.add_all([a,b]);s.flush();old=b.id;s.add(Meta(id=999,sector_id=old,recorder_name='',source_key=None))
   migrate_inventory();migrate_inventory()
   rows=c.get('/api/sectors',headers=h).json();self.assertEqual(len(rows),1);sid=rows[0]['id'];self.assertEqual(set(rows[0]['unit_ids']),{1,uid})
   with Session() as s:self.assertEqual(s.get(Meta,999).sector_id,sid)
   self.assertEqual(c.delete('/api/sectors/'+str(sid),headers=h).status_code,409)
   self.assertEqual(c.post('/api/sectors',headers=h,json={'name':'PORTARIA'}).status_code,409)
   spare=c.post('/api/sectors',headers=h,json={'name':'Oficina'}).json()['id']
   self.assertEqual(c.put(f'/api/units/{uid}/sectors/{spare}',headers=h).status_code,200)
   self.assertEqual(c.delete(f'/api/units/{uid}/sectors/{spare}',headers=h).status_code,200)
   self.assertEqual(c.delete('/api/sectors/'+str(spare),headers=h).status_code,200)
   body=dict(name='CAM-global',manufacturer='Intelbras',model='NVD3316',ip='10.104.3.9',port=5009,channel=1,lat=-13,lng=-58,username='camerauser',password='camera-pass',device_type='nvr',unit_id=uid,sector_id=sid)
   with patch('backend.video.httpx.Client',return_value=MagicMock()):r=c.post('/api/cameras',headers=h,json=body);self.assertEqual(r.status_code,201,r.text);cam=r.json()['id']
   self.assertEqual(c.delete(f'/api/units/{uid}/sectors/{sid}',headers=h).status_code,409)
   with patch('backend.video.httpx.Client',return_value=MagicMock()),patch('backend.video.httpx.delete',return_value=MagicMock()):
    self.assertEqual(c.delete('/api/cameras/'+str(cam),headers=h).status_code,200)
   self.assertEqual(c.delete('/api/units/'+str(uid),headers=h).status_code,409)
   self.assertEqual(c.delete(f'/api/units/{uid}/sectors/{sid}',headers=h).status_code,200)
   self.assertEqual(c.delete('/api/units/'+str(uid),headers=h).status_code,200)
   self.assertEqual(c.get('/api/sectors',headers=h).json()[0]['unit_ids'],[1])
if __name__=='__main__':unittest.main()
