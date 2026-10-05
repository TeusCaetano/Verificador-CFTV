import os,sys,tempfile,unittest,time
from pathlib import Path
from unittest.mock import patch,MagicMock
from cryptography.fernet import Fernet
os.environ.update(DATABASE_URL='sqlite:///'+tempfile.mktemp(suffix='.db'),ADMIN_PASSWORD='test-password-1234',CAMERA_KEY=Fernet.generate_key().decode(),MONITOR_ENABLED='false')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.main import app,Session,Base
from backend.channel_state import parse_states
from fastapi.testclient import TestClient
class ChannelState(unittest.TestCase):
 def test_parsing(self):
  self.assertEqual(parse_states({'states':[{'channel':26,'connectionState':'Unconnect'},{'channel':28,'connectionState':'Connected'},{'channel':30,'connectionState':'Connecting'}]}),{27:'offline',29:'online',31:'unknown'})
  with self.assertRaises(ValueError):parse_states({'states':[]})
 def test_monitor_and_stale_offline(self):
  with TestClient(app) as c,patch('backend.video.httpx.Client') as client:
   mock=MagicMock();mock.get.return_value.status_code=404;mock.post.return_value.status_code=200;mock.post.return_value.content=b'{}';mock.post.return_value.json.return_value={'states':[{'channel':26,'connectionState':'Unconnect'}]};client.return_value.__enter__.return_value=mock
   h={'Authorization':'Bearer '+c.post('/api/login',json={'username':'admin','password':'test-password-1234'}).json()['token']}
   b=dict(name='CAN27',manufacturer='Intelbras',model='NVD',ip='10.0.0.5',port=5005,channel=27,lat=-13,lng=-58,username='user',password='secret',device_type='nvr',unit_id=1)
   r=c.post('/api/cameras',headers=h,json=b);self.assertEqual(r.status_code,201,r.text);id=r.json()['id']
   r=c.put(f'/api/cameras/{id}/recorder-status',headers=h,json={'enabled':True,'web_port':4005,'scheme':'http'});self.assertEqual(r.status_code,200,r.text)
   with patch('backend.probe.probe_video') as probe:
    r=c.post(f'/api/cameras/{id}/test',headers=h);self.assertEqual(r.json()['status'],'offline');probe.assert_not_called()
   models={m.class_.__name__:m.class_ for m in Base.registry.mappers}
   with Session.begin() as s:s.get(models['Connection'],id).checked_at=int(time.time())-1000
   row=next(x for x in c.get('/api/cameras',headers=h).json() if x['id']==id);self.assertEqual(row['status'],'offline');self.assertTrue(row['verification_stale']);self.assertEqual(row['last_status'],'offline')
   mock.post.return_value.json.return_value={}
   with patch('backend.channel_state.time.monotonic',return_value=time.monotonic()+40),patch('backend.video.socket.create_connection'),patch('backend.probe.probe_video',return_value={'status':'online','video':True,'codec':'h264','diagnostic':'Stream disponível.'}) as probe:
    r=c.post(f'/api/cameras/{id}/test',headers=h);self.assertEqual(r.json()['status'],'online',r.text);self.assertIn('RTSP',r.json()['diagnostic']);probe.assert_called_once()
   r=c.put(f'/api/cameras/{id}/recorder-status',headers=h,json={'enabled':True,'web_port':4999,'scheme':'http'});self.assertEqual(r.status_code,422,r.text)
   self.assertEqual(c.get(f'/api/cameras/{id}/recorder-status',headers=h).json()['web_port'],4005)

if __name__=='__main__':unittest.main()
