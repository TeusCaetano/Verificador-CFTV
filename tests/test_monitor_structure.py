import os,sys,tempfile,unittest,threading,time
from pathlib import Path
from unittest.mock import patch
from cryptography.fernet import Fernet
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.update(DATABASE_URL='sqlite:///'+tempfile.mktemp(suffix='.db'),ADMIN_PASSWORD='test-password-1234',CAMERA_KEY=Fernet.generate_key().decode(),MONITOR_ENABLED='true',MONITOR_WORKERS='4',MONITOR_PER_RECORDER='2')
from backend.main import app
from fastapi.testclient import TestClient
class Monitor(unittest.TestCase):
 def test_slow_channel_does_not_block_healthy_siblings(self):
  slow=threading.Event();release=threading.Event()
  def fast(url):
   if 'channel=1&' in url:return {'status':'unknown','needs_slow':True}
   return {'status':'online','video':True,'codec':'h264','diagnostic':'Online'}
  def full(url):
   slow.set();release.wait(10)
   return {'status':'offline','video':False,'diagnostic':'Confirmed failure'}
  with patch('backend.video.socket.create_connection'),patch('backend.probe.fast_probe_video',side_effect=fast),patch('backend.probe.probe_video',side_effect=full):
   with TestClient(app) as c:
    try:
     h={'Authorization':'Bearer '+c.post('/api/login',json={'username':'admin','password':'test-password-1234'}).json()['token']}
     for ch in range(1,5):
      body=dict(name=f'Camera {ch}',manufacturer='Intelbras',model='NVD',ip='10.0.0.1',port=554,channel=ch,lat=-13,lng=-58,username='test',password='test-only',device_type='nvr',unit_id=1)
      self.assertEqual(c.post('/api/cameras',headers=h,json=body).status_code,201)
     self.assertTrue(slow.wait(5))
     deadline=time.monotonic()+5
     while time.monotonic()<deadline:
      rows=c.get('/api/cameras',headers=h).json()
      if sum(r['status']=='online' for r in rows)==3:break
      release.wait(.1)
     self.assertEqual(sum(r['status']=='online' for r in rows),3)
     self.assertFalse(release.is_set())
    finally:release.set()
if __name__=='__main__':unittest.main()
