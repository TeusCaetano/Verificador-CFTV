import os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch,MagicMock
from cryptography.fernet import Fernet
os.environ.update(DATABASE_URL='sqlite:///'+tempfile.mktemp(suffix='.db'),ADMIN_PASSWORD='test-password-1234',CAMERA_KEY=Fernet.generate_key().decode(),MONITOR_ENABLED='false')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.main import app,Session,Base
from fastapi.testclient import TestClient
class Positions(unittest.TestCase):
 def test_move_assign_sector_without_resetting_stream_and_alarms(self):
  with TestClient(app) as c:
   token=c.post('/api/login',json={'username':'admin','password':'test-password-1234'}).json()['token'];h={'Authorization':'Bearer '+token}
   sector=c.post('/api/sectors',headers=h,json={'unit_id':1,'name':'Portaria'}).json()['id']
   unit=c.post('/api/units',headers=h,json={'name':'Outra','lat':-12,'lng':-57}).json()['id']
   other=c.post('/api/sectors',headers=h,json={'unit_id':unit,'name':'Outro setor'}).json()['id']
   body=dict(name='CAM01',manufacturer='Intelbras',model='NVD3316',ip='10.104.3.9',port=5009,channel=1,lat=-13,lng=-58,username='camerauser',password='camera-pass',device_type='nvr')
   cam=c.post('/api/cameras',headers=h,json=body).json()['id']
   with patch('backend.video.socket.create_connection',return_value=MagicMock()),patch('backend.video.subprocess.run',return_value=MagicMock(returncode=0,stdout=b'{"streams":[{"codec_name":"h264"}]}',stderr=b'')):
    c.post(f'/api/cameras/{cam}/test',headers=h)
   classes={m.class_.__name__:m.class_ for m in Base.registry.mappers}
   with Session() as s:
    old=s.get(classes['Connection'],cam);checked=old.checked_at;encrypted=old.password_encrypted
    observations=s.query(classes['Observation']).count()
   r=c.patch(f'/api/cameras/{cam}/position',headers=h,json={'lat':-13.2583,'lng':-58.7326,'sector_id':sector})
   self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.json()['status'],'online');self.assertEqual(r.json()['sector_name'],'Portaria');self.assertEqual(r.json()['lat'],-13.2583)
   with Session() as s:
    state=s.get(classes['Connection'],cam);self.assertEqual(state.checked_at,checked);self.assertEqual(state.password_encrypted,encrypted);self.assertEqual(s.query(classes['Observation']).count(),observations)
   self.assertEqual(c.patch(f'/api/cameras/{cam}/position',headers=h,json={'lat':100,'lng':0,'sector_id':sector}).status_code,422)
   self.assertEqual(c.patch(f'/api/cameras/{cam}/position',headers=h,json={'lat':0,'lng':0,'sector_id':other}).status_code,422)
   c.post('/api/users',headers=h,json={'username':'viewer','password':'test-password-1234','role':'viewer'})
   v=c.post('/api/login',json={'username':'viewer','password':'test-password-1234'}).json()['token']
   self.assertEqual(c.patch(f'/api/cameras/{cam}/position',headers={'Authorization':'Bearer '+v},json={'lat':0,'lng':0}).status_code,403)
   self.assertEqual(c.patch('/api/cameras/999/position',headers=h,json={'lat':0,'lng':0}).status_code,404)
if __name__=='__main__':unittest.main()
