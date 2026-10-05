import os,sys,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch,MagicMock
from cryptography.fernet import Fernet
os.environ.update(DATABASE_URL='sqlite:///'+tempfile.mktemp(suffix='.db'),ADMIN_PASSWORD='test-password-1234',CAMERA_KEY=Fernet.generate_key().decode(),MONITOR_ENABLED='false')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.main import app,Session,Base
from fastapi.testclient import TestClient

class FreeChannelFlow(unittest.TestCase):
 def test_disable_reactivate_alerts_streams_report_and_batch(self):
  with TestClient(app) as c:
   token=c.post('/api/login',json={'username':'admin','password':'test-password-1234'}).json()['token'];h={'Authorization':'Bearer '+token}
   body=dict(name='UP_3LGS_NVD09-CAM14',manufacturer='Intelbras',model='NVD3316',ip='10.104.3.9',port=5009,channel=14,lat=-13,lng=-58,username='camerauser',password='camera-pass',device_type='nvr')
   cam=c.post('/api/cameras',headers=h,json=body).json()['id']
   with patch('backend.video.socket.create_connection',side_effect=OSError()):
    for _ in range(3):self.assertEqual(c.post(f'/api/cameras/{cam}/test',headers=h).status_code,200)
   self.assertEqual(c.get('/api/alerts',headers=h).json()['summary']['open'],1)
   r=c.patch(f'/api/cameras/{cam}/channel-mode',headers=h,json={'is_free':True});self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.json()['status'],'free');self.assertTrue(r.json()['has_password'])
   self.assertEqual(c.get('/api/alerts',headers=h).json()['summary']['open'],0)
   self.assertEqual(c.get('/api/dashboard',headers=h).json()['camera_count'],0)
   self.assertEqual(c.get('/api/overview',headers=h).json()['free_channels'],1)
   with patch('backend.video.socket.create_connection') as socket:
    self.assertEqual(c.post(f'/api/cameras/{cam}/test',headers=h).status_code,409);socket.assert_not_called()
   self.assertEqual(c.post(f'/api/cameras/{cam}/live',headers=h).status_code,409)
   classes={m.class_.__name__:m.class_ for m in Base.registry.mappers}
   with Session.begin() as s:s.get(classes['AlertState'],cam).since=int(time.time())-1000
   self.assertEqual(c.get('/api/alerts',headers=h).json()['summary']['open'],0)
   r=c.patch(f'/api/cameras/{cam}/channel-mode',headers=h,json={'is_free':False});self.assertEqual(r.json()['status'],'unknown')
   with patch('backend.video.socket.create_connection',return_value=MagicMock()),patch('backend.video.subprocess.run',return_value=MagicMock(returncode=0,stdout=b'{"streams":[{"codec_name":"h264"}]}',stderr=b'')):
    self.assertEqual(c.post(f'/api/cameras/{cam}/test',headers=h).json()['status'],'online')
   p=c.post('/api/inventory/batch-preview',headers=h,json={'device':body,'channels':[15,16],'prefix':'UP_3LGS_NVD09','free_channels':[15,16]}).json();self.assertTrue(all(r['is_free'] for r in p['rows']))
   self.assertEqual(c.post('/api/inventory/commit',headers=h,json={'token':p['token']}).status_code,201)
   rows=c.get('/api/cameras',headers=h).json();self.assertEqual(sum(x['status']=='free' for x in rows),2)
   self.assertEqual(c.get('/api/dashboard',headers=h).json()['camera_count'],1)
   self.assertEqual(c.get('/api/alerts',headers=h).json()['summary']['open'],0)
   c.post('/api/users',headers=h,json={'username':'viewer','password':'test-password-1234','role':'viewer'})
   v=c.post('/api/login',json={'username':'viewer','password':'test-password-1234'}).json()['token']
   self.assertEqual(c.patch(f'/api/cameras/{cam}/channel-mode',headers={'Authorization':'Bearer '+v},json={'is_free':True}).status_code,403)
if __name__=='__main__':unittest.main()
