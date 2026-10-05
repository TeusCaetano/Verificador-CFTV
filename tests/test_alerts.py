import os,sys,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch,MagicMock
from cryptography.fernet import Fernet
os.environ.update(DATABASE_URL='sqlite:///'+tempfile.mktemp(suffix='.db'),ADMIN_PASSWORD='test-password-1234',CAMERA_KEY=Fernet.generate_key().decode(),MONITOR_ENABLED='false')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.main import app,Base,Session
from fastapi.testclient import TestClient

class AlertLifecycle(unittest.TestCase):
 def test_lifecycle_permissions_maintenance_and_stale(self):
  with TestClient(app) as c:
   def login(name):return {'Authorization':'Bearer '+c.post('/api/login',json={'username':name,'password':'test-password-1234'}).json()['token']}
   h=login('admin')
   for name,role in [('operator','operator'),('viewer','viewer')]:
    self.assertEqual(c.post('/api/users',headers=h,json={'username':name,'password':'test-password-1234','role':role}).status_code,201)
   op=login('operator');view=login('viewer')
   body=dict(name='Piloto',manufacturer='Intelbras',model='NVD3316',ip='10.104.3.9',port=5009,channel=1,lat=-13,lng=-58,username='camerauser',password='test-camera-pass',device_type='nvr')
   cam=c.post('/api/cameras',headers=h,json=body).json()['id']
   def alerts():return c.get('/api/alerts',headers=h).json()
   def fail():
    with patch('backend.video.socket.create_connection',side_effect=OSError()):
     self.assertEqual(c.post(f'/api/cameras/{cam}/test',headers=h).status_code,200)
   def online():
    with patch('backend.video.socket.create_connection',return_value=MagicMock()),patch('backend.video.subprocess.run',return_value=MagicMock(returncode=0,stdout=b'{"streams":[{"codec_name":"h264"}]}',stderr=b'')):
     self.assertEqual(c.post(f'/api/cameras/{cam}/test',headers=h).status_code,200)
   fail();fail();self.assertEqual(alerts()['summary']['open'],0)
   fail();a=alerts()['rows'][0];self.assertEqual(a['kind'],'offline')
   fail();self.assertEqual(alerts()['summary']['open'],1)
   treatment={'acknowledge':True,'owner':'operator','note':'VPN em análise'}
   self.assertEqual(c.post(f"/api/alerts/{a['id']}/treat",headers=view,json=treatment).status_code,403)
   self.assertEqual(c.post(f"/api/alerts/{a['id']}/treat",headers=op,json=treatment).status_code,200)
   self.assertEqual(alerts()['rows'][0]['state'],'acknowledged')
   online();self.assertEqual(alerts()['summary']['open'],0)
   for _ in range(3):fail()
   self.assertEqual(alerts()['summary']['recurring_devices'],1)
   self.assertEqual(c.post(f'/api/cameras/{cam}/maintenance',headers=view,json={'minutes':60,'reason':'Teste'}).status_code,403)
   self.assertEqual(c.post(f'/api/cameras/{cam}/maintenance',headers=op,json={'minutes':60,'reason':'Troca de câmera'}).status_code,200)
   for _ in range(4):fail()
   self.assertEqual(alerts()['summary']['open'],0)
   self.assertEqual(alerts()['summary']['maintenance'],1)
   c.post(f'/api/cameras/{cam}/maintenance',headers=op,json={'minutes':0,'reason':'Finalizada'})
   fail();fail();self.assertEqual(alerts()['summary']['open'],0)
   fail();self.assertEqual(alerts()['summary']['open'],1)
   c.put(f'/api/cameras/{cam}',headers=h,json=body);self.assertEqual(alerts()['summary']['open'],1)
   body['port']=555
   c.put(f'/api/cameras/{cam}',headers=h,json=body);self.assertEqual(alerts()['summary']['open'],0)
   classes={m.class_.__name__:m.class_ for m in Base.registry.mappers}
   with Session.begin() as s:
    s.get(classes['AlertState'],cam).since=int(time.time())-1000
    s.get(classes['Connection'],cam).checked_at=0
   self.assertEqual(alerts()['rows'][0]['kind'],'unverified')
   online();self.assertEqual(alerts()['summary']['open'],0)
   for _ in range(3):fail()
   with patch('backend.video.httpx.delete',return_value=MagicMock(status_code=200)):
    self.assertEqual(c.delete(f'/api/cameras/{cam}',headers=h).status_code,200)
   self.assertEqual(alerts()['summary']['open'],0)
   self.assertEqual(c.get('/api/alerts').status_code,401)
   self.assertEqual(c.get('/api/dashboard',headers=h).status_code,200)
   self.assertEqual(c.get('/api/overview',headers=h).status_code,200)
if __name__=='__main__':unittest.main()
