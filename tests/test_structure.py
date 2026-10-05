import os,sys,tempfile,unittest,subprocess,threading,random
from pathlib import Path
from unittest.mock import patch,MagicMock
from cryptography.fernet import Fernet
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.update(DATABASE_URL='sqlite:///'+tempfile.mktemp(suffix='.db'),ADMIN_PASSWORD='test-password-1234',CAMERA_KEY=Fernet.generate_key().decode(),MONITOR_ENABLED='false')
from backend.main import app,Base,Session
from backend.analytics import aggregate,compact_observations
from backend.transcoding import Converters
from backend.probe import fast_probe_video
from fastapi.testclient import TestClient
class Structure(unittest.TestCase):
 def test_race_metadata_history_snapshot(self):
  with TestClient(app) as c,patch('backend.video.socket.create_connection'):
   h={'Authorization':'Bearer '+c.post('/api/login',json={'username':'admin','password':'test-password-1234'}).json()['token']}
   body=dict(name='Race-demo',manufacturer='Intelbras',model='NVD',ip='10.0.0.1',port=554,channel=1,lat=-13,lng=-58,username='test',password='test-only',device_type='nvr',unit_id=1)
   id=c.post('/api/cameras',headers=h,json=body).json()['id']
   def old_probe(url):
    body['ip']='10.0.0.2';self.assertEqual(c.put(f'/api/cameras/{id}',headers=h,json=body).status_code,200)
    return {'status':'online','video':True,'codec':'h264','diagnostic':'Old result'}
   with patch('backend.probe.probe_video',side_effect=old_probe):self.assertEqual(c.post(f'/api/cameras/{id}/test',headers=h).status_code,409)
   good={'status':'online','video':True,'codec':'h264','diagnostic':'Online'}
   with patch('backend.probe.probe_video',return_value=good):
    for _ in range(4):self.assertEqual(c.post(f'/api/cameras/{id}/test',headers=h).status_code,200)
   body['name']='Renamed';self.assertEqual(c.put(f'/api/cameras/{id}',headers=h,json=body).json()['status'],'online')
   classes={m.class_.__name__:m.class_ for m in Base.registry.mappers}
   with Session() as s:
    from sqlalchemy import select,func
    self.assertEqual(s.scalar(select(func.count()).select_from(classes['Observation']).where(classes['Observation'].camera_id==id,classes['Observation'].status=='online')),1)
   snap=c.get('/api/snapshot',headers=h);self.assertEqual(snap.status_code,200)
   self.assertEqual(set(snap.json()),{'units','sectors','cameras','overview','monitor','events','maintenance','alerts'})
   self.assertEqual(c.get('/api/snapshot').status_code,401)
   self.assertEqual(c.get('/api/dashboard?hours=24',headers=h).status_code,200)
   with Session.begin() as session:
    revision=session.get(classes['ConnectionRevision'],id);session.delete(revision)
  # Upgrade seeds missing revisions while preserving an existing online result.
  with TestClient(app) as c:
   body['name']='Renamed after restart'
   self.assertEqual(c.put(f'/api/cameras/{id}',headers=h,json=body).json()['status'],'online')

 def test_compaction_preserves_gaps_and_unknown(self):
  rng=random.Random(7);samples=[]
  for cam in range(1,5):
   for i in range(2500):samples.append(dict(id=cam*10000+i,camera_id=cam,timestamp=i*10,valid_until=i*10+rng.choice([5,20,100]),status=rng.choice(['online','offline','unknown'])))
  cameras=[{'id':i} for i in range(1,5)]
  self.assertEqual(aggregate(cameras,samples,0,26000),aggregate(cameras,compact_observations(iter(samples),0,26000),0,26000))
  repeated=[dict(id=i,camera_id=1,timestamp=i*10,valid_until=i*10+20,status='online') for i in range(210001)]
  self.assertEqual(len(compact_observations(iter(repeated),0,3000000)),1)
 def test_fast_timeout_is_inconclusive(self):
  with patch('backend.probe.subprocess.run',side_effect=subprocess.TimeoutExpired('ffprobe',6)):
   result=fast_probe_video('rtsp://test');self.assertTrue(result['needs_slow']);self.assertEqual(result['status'],'unknown')
 def test_converter_preparation_does_not_block_removal(self):
  m=Converters();entered=threading.Event();release=threading.Event();errors=[]
  def prepare():entered.set();release.wait(3)
  def worker():
   try:m.ensure(1,'input','target',prepare)
   except Exception as e:errors.append(e)
  t=threading.Thread(target=worker);t.start();self.assertTrue(entered.wait(1))
  removed=threading.Event();r=threading.Thread(target=lambda:(m.remove(1),removed.set()));r.start()
  try:self.assertTrue(removed.wait(.5))
  finally:release.set();t.join(3);r.join(3)
  self.assertFalse(m.jobs);self.assertEqual(errors[0].status_code,409)
if __name__=='__main__':unittest.main()
