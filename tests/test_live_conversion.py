import os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch,MagicMock
from cryptography.fernet import Fernet
os.environ.update(DATABASE_URL='sqlite:///'+tempfile.mktemp(suffix='.db'),ADMIN_PASSWORD='test-password-1234',CAMERA_KEY=Fernet.generate_key().decode(),MONITOR_ENABLED='false')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.main import app
from fastapi.testclient import TestClient
class Live(unittest.TestCase):
 def test_codec_routes(self):
  with TestClient(app) as c,patch('backend.video.httpx.Client') as client,patch('backend.transcoding.subprocess.Popen') as popen:
   mock=MagicMock();mock.get.return_value.status_code=404;client.return_value.__enter__.return_value=mock
   popen.return_value.poll.return_value=None
   popen.return_value.stderr=None
   popen.return_value.wait.return_value=0
   h={'Authorization':'Bearer '+c.post('/api/login',json={'username':'admin','password':'test-password-1234'}).json()['token']}
   for channel,codec in [(1,'h264'),(2,'hevc'),(3,'mjpeg')]:
    body=dict(name='CAM'+str(channel),manufacturer='Intelbras',model='NVD',ip='10.0.0.1',port=554,channel=channel,lat=-13,lng=-58,username='user',password='secret',device_type='nvr',unit_id=1)
    r=c.post('/api/cameras',headers=h,json=body);self.assertEqual(r.status_code,201,r.text);id=r.json()['id']
    with patch('backend.video.probe_codec',return_value=codec):
     r=c.post(f'/api/cameras/{id}/live',headers=h);self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.json()['converted'],codec in ('hevc','mjpeg'))
     self.assertEqual(c.post(f'/api/cameras/{id}/live',headers=h).status_code,200)
   self.assertEqual(popen.call_count,2)
if __name__=='__main__':unittest.main()
