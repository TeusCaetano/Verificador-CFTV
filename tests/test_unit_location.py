import os,sys,tempfile,unittest
from pathlib import Path
from cryptography.fernet import Fernet
os.environ.update(DATABASE_URL='sqlite:///'+tempfile.mktemp(suffix='.db'),ADMIN_PASSWORD='test-password-1234',CAMERA_KEY=Fernet.generate_key().decode(),MONITOR_ENABLED='false')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.main import app,Session,Camera
from fastapi.testclient import TestClient
class Location(unittest.TestCase):
 def test_scope_and_validation(self):
  with TestClient(app) as c:
   h={'Authorization':'Bearer '+c.post('/api/login',json={'username':'admin','password':'test-password-1234'}).json()['token']}
   uid=c.post('/api/units',headers=h,json={'name':'Filial teste','lat':-58,'lng':-13}).json()['id']
   other=c.post('/api/units',headers=h,json={'name':'Outra teste','lat':-58,'lng':-13}).json()['id']
   with Session.begin() as s:
    for i,(unit,lat,lng) in enumerate([(uid,-58,-13),(uid,-12,-57),(other,-58,-13)],100):s.add(Camera(id=i,name=str(i),manufacturer='Intelbras',model='NVD',ip='10.0.0.1',port=554,channel=i,lat=lat,lng=lng,unit_id=unit))
   url=f'/api/units/{uid}/location';body={'lat':-13,'lng':-58,'camera_scope':'center'}
   self.assertEqual(c.patch(url,json=body).status_code,401)
   self.assertEqual(c.patch(url,headers=h,json=dict(body,lat=91)).status_code,422)
   self.assertEqual(c.patch(url,headers=h,json=body).json()['updated_cameras'],1)
   with Session() as s:
    self.assertEqual((s.get(Camera,100).lat,s.get(Camera,100).lng),(-13,-58));self.assertEqual(s.get(Camera,101).lat,-12);self.assertEqual(s.get(Camera,102).lat,-58)
   self.assertEqual(c.patch(url,headers=h,json=dict(body,lat=-14,camera_scope='none')).json()['updated_cameras'],0)
   self.assertEqual(c.patch(url,headers=h,json=dict(body,camera_scope='all')).json()['updated_cameras'],2)
   with Session() as s:self.assertEqual(s.get(Camera,102).lat,-58);self.assertEqual(s.get(Camera,101).lat,-13)
   self.assertEqual(c.patch('/api/units/99999/location',headers=h,json=body).status_code,404)
if __name__=='__main__':unittest.main()
