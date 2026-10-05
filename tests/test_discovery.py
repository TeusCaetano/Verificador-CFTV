import unittest,sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.discovery import parse_intelbras,InventoryUnreadable,DiscoverInput,configure_discovery
import httpx
class Detection(unittest.TestCase):
 def test_31_cameras_and_channel_32_missing(self):
  text='\n'.join(f'camera[{i}].UniqueChannel={i}\ncamera[{i}].DeviceInfo.Address=10.104.3.{i+10}\ncamera[{i}].DeviceInfo.Enable=true' for i in range(31))
  rows=parse_intelbras(text,list(range(1,33)))
  self.assertTrue(all(x['state']=='configured' for x in rows[:31]));self.assertEqual(rows[31]['state'],'free')
 def test_offline_is_configured_and_unknown_is_not_free(self):
  rows=parse_intelbras('camera[0].UniqueChannel=0\ncamera[0].DeviceInfo.Address=10.0.0.2\ncamera[0].DeviceInfo.Enable=false\ncamera[0].Status=Offline\ncamera[1].UniqueChannel=1\ncamera[1].Enable=true',[1,2])
  self.assertEqual([x['state'] for x in rows],['configured','unknown'])
 def test_nested_fields_disabled_camera_and_compose(self):
  text='camera[0].UniqueChannel=0\ncamera[0].Enable=true\ncamera[0].DeviceInfo.Enable=true\ncamera[0].DeviceInfo.Address=10.0.0.2\ncamera[0].DeviceInfo.VideoInputs[0].Enable=true\ncamera[31].UniqueChannel=31\ncamera[31].Enable=false\ncamera[31].DeviceInfo.Enable=false\ncamera[31].DeviceInfo.Address=10.0.0.99\ncamera[31].DeviceID=old-device\ncamera[31].DeviceInfo.VideoInputs[0].MainStreamUrl=\ncamera[32].UniqueChannel=65\ncamera[32].Type=Compose'
  rows=parse_intelbras(text,[1,32]);self.assertEqual([r['state'] for r in rows],['configured','free'])
 def test_empty_and_malformed(self):
  self.assertEqual(parse_intelbras('camera=[]',[32])[0]['state'],'free')
  for text in ('','Error','<html>Login</html>','camera[0].DeviceInfo.Address=10.0.0.2','camera[0].UniqueChannel=0\ncamera[1].UniqueChannel=0','camera[0].UniqueChannel=0\ntruncated'):
   with self.assertRaises(InventoryUnreadable):parse_intelbras(text,[32])
 def test_remote_channel_is_not_nvr_channel(self):
  rows=parse_intelbras('camera[0].UniqueChannel=30\ncamera[0].Channel=0\ncamera[0].DeviceInfo.Address=10.0.0.2',[1,31,32])
  self.assertEqual([x['state'] for x in rows],['free','configured','free'])
 def test_request_failure_does_not_mark_free(self):
  class App:
   def post(self,path):
    def wrap(f):self.call=f;return f
    return wrap
  app=App();configure_discovery(app,lambda:None)
  body=DiscoverInput(ip='10.104.3.5',management_port=4005,manufacturer='Intelbras',username='admin',password='secret-password',channels=[31,32])
  original=httpx.Client
  for code,data in [(401,'Unauthorized'),(403,'Forbidden'),(404,'Not found'),(200,'Error'),(200,'<html>Login</html>')]:
   transport=httpx.MockTransport(lambda request:httpx.Response(code,text=data))
   with patch('backend.discovery.httpx.Client',side_effect=lambda **kw:original(transport=transport,**kw)):result=app.call(body,{})
   self.assertFalse(result['confirmed']);self.assertTrue(all(r['state']=='unknown' for r in result['rows']));self.assertNotIn('secret-password',str(result))
  transport=httpx.MockTransport(lambda request:httpx.Response(200,text='camera[0].UniqueChannel=30\ncamera[0].DeviceInfo.Address=10.0.0.2'))
  with patch('backend.discovery.httpx.Client',side_effect=lambda **kw:original(transport=transport,**kw)):result=app.call(body,{})
  self.assertTrue(result['confirmed']);self.assertEqual([r['state'] for r in result['rows']],['configured','free'])
if __name__=='__main__':unittest.main()
