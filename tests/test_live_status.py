import os,sys,tempfile,time,unittest,re
from pathlib import Path
from unittest.mock import patch,MagicMock
from cryptography.fernet import Fernet
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.update(DATABASE_URL='sqlite:///'+tempfile.mktemp(suffix='.db'),ADMIN_PASSWORD='test-password-1234',CAMERA_KEY=Fernet.generate_key().decode(),MONITOR_ENABLED='false')
from backend.main import app,Base,Session
from fastapi.testclient import TestClient
import httpx
class PlaybackStatus(unittest.TestCase):
 counter=0
 def setUp(self):
  type(self).counter+=1
  self.c=TestClient(app);self.c.__enter__();self.addCleanup(lambda:self.c.__exit__(None,None,None))
  token=self.c.post('/api/login',json={'username':'admin','password':'test-password-1234'}).json()['token']
  self.h={'Authorization':'Bearer '+token,'X-Video-Client':'browser-one'}
  self.body=dict(name='Live '+self._testMethodName,manufacturer='Intelbras',model='NVD',ip='10.0.0.1',port=554,channel=type(self).counter,lat=-13,lng=-58,username='test',password='test-only',device_type='nvr',unit_id=1)
  self.id=self.c.post('/api/cameras',headers=self.h,json=self.body).json()['id']
  self.classes={m.class_.__name__:m.class_ for m in Base.registry.mappers}
  proxy=next(r.endpoint for r in app.routes if getattr(r,'path','')=='/api/live/{ticket}/{asset}')
  self.cells=dict(zip(proxy.__code__.co_freevars,[c.cell_contents for c in proxy.__closure__]))
  self.media=self.cells['media_client']
 def open(self):
  gateway=MagicMock();gateway.get.return_value.status_code=404
  with patch('backend.video.probe_codec',return_value='h264'),patch('backend.video.httpx.Client') as client:
   client.return_value.__enter__.return_value=gateway
   result=self.c.post(f'/api/cameras/{self.id}/live',headers=self.h);self.assertEqual(result.status_code,200,result.text)
  url=result.json()['url'];self.ticket=url.split('/')[3]
  def response(target):return httpx.Response(200,text='#EXTM3U\n#EXT-X-MAP:URI="init.mp4"\n#EXTINF:1\nseg1.m4s\n',request=httpx.Request('GET',target))
  with patch.object(self.media,'get',side_effect=response):playlist=self.c.get(url).text
  self.init=re.search(r'URI="([^"]+)"',playlist)[1];self.segment=next(line for line in playlist.splitlines() if line and not line.startswith('#'))
 def fetch(self,url,payload):
  with patch.object(self.media,'get',side_effect=lambda target:httpx.Response(200,content=payload,request=httpx.Request('GET',target))):
   response=self.c.get(url);self.assertEqual(response.status_code,200,response.text)
 def frame(self):self.fetch(self.segment,(8).to_bytes(4,'big')+b'moof'+(12).to_bytes(4,'big')+b'mdat'+b'data')
 def confirm(self,headers=None):return self.c.post('/api/live-confirm',headers=headers or self.h,json={'ticket':self.ticket})
 def camera(self):return next(r for r in self.c.get('/api/cameras',headers=self.h).json() if r['id']==self.id)
 def test_only_playlist_or_initialization_does_not_set_online(self):
  self.open();self.assertFalse(self.confirm().json()['confirmed']);self.assertEqual(self.camera()['status'],'unknown')
  self.fetch(self.init,(8).to_bytes(4,'big')+b'ftyp'+(8).to_bytes(4,'big')+b'moov')
  self.assertFalse(self.confirm().json()['confirmed']);self.assertEqual(self.camera()['status'],'unknown')
 def test_progress_updates_inventory_snapshot_and_coalesces_history(self):
  self.open();self.frame();result=self.confirm();self.assertEqual(result.status_code,200,result.text);self.assertTrue(result.json()['confirmed'])
  self.assertEqual(self.camera()['status'],'online')
  snapshot=self.c.get('/api/snapshot',headers=self.h).json();self.assertEqual(next(c for c in snapshot['cameras'] if c['id']==self.id)['status'],'online')
  self.assertTrue(self.confirm().json()['confirmed'])
  from sqlalchemy import select,func
  with Session() as session:self.assertEqual(session.scalar(select(func.count()).select_from(self.classes['Observation']).where(self.classes['Observation'].camera_id==self.id,self.classes['Observation'].status=='online')),1)
 def test_other_browser_and_expired_media_are_rejected(self):
  self.open();self.frame();headers=self.h|{'X-Video-Client':'another-browser'};self.assertEqual(self.confirm(headers).status_code,403)
  self.cells['tickets'][self.ticket]['media_at']=time.monotonic()-20
  self.assertFalse(self.confirm().json()['confirmed']);self.assertEqual(self.camera()['status'],'unknown')
 def test_config_changes_invalidate_old_playback(self):
  self.open();self.frame();body=self.body|{'ip':'10.0.0.2'};self.c.put(f'/api/cameras/{self.id}',headers=self.h,json=body)
  self.assertEqual(self.confirm().status_code,409);self.assertEqual(self.camera()['status'],'unknown')
 def test_free_channel_and_canceled_ticket_cannot_set_online(self):
  self.open();self.frame();self.c.patch(f'/api/cameras/{self.id}/channel-mode',headers=self.h,json={'is_free':True})
  self.assertEqual(self.confirm().status_code,409);self.assertEqual(self.camera()['status'],'free')
 def test_recorder_disconnected_state_is_preserved(self):
  self.open();self.frame()
  with Session.begin() as session:
   record=session.get(self.classes['Connection'],self.id);record.status='offline';record.checked_at=int(time.time());record.diagnostic='Estado do canal informado pelo gravador: câmera sem conexão ativa.'
  self.assertFalse(self.confirm().json()['confirmed']);self.assertEqual(self.camera()['status'],'offline')
 def test_old_failed_probe_does_not_overwrite_current_reproduction(self):
  self.open();self.frame()
  def slow_result(url):
   self.assertTrue(self.confirm().json()['confirmed'])
   return {'status':'offline','video':False,'diagnostic':'Old timeout'}
  with patch('backend.video.socket.create_connection'),patch('backend.probe.probe_video',side_effect=slow_result):
   response=self.c.post(f'/api/cameras/{self.id}/test',headers=self.h);self.assertEqual(response.status_code,200,response.text)
  self.assertEqual(self.camera()['status'],'online')
 def test_stopped_video_is_not_used_to_override_a_failed_probe(self):
  self.open();self.frame();self.confirm();self.cells['live_evidence'][self.id]['at']=time.monotonic()-20
  with patch('backend.video.socket.create_connection'),patch('backend.probe.probe_video',return_value={'status':'offline','video':False,'diagnostic':'Confirmed failure'}):
   self.assertEqual(self.c.post(f'/api/cameras/{self.id}/test',headers=self.h).status_code,200)
  self.assertEqual(self.camera()['status'],'offline')
if __name__=='__main__':unittest.main()
