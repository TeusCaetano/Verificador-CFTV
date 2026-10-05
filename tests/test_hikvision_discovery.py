import sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import httpx
from backend.discovery import parse_hikvision,InventoryUnreadable,DiscoverInput,configure_discovery

def inventory(records,namespace='http://www.hikvision.com/ver20/XMLSchema'):
 return '<InputProxyChannelList xmlns="'+namespace+'">'+''.join(records)+'</InputProxyChannelList>'
def record(id,address=None,enabled=None,extra=''):
 return '<InputProxyChannel><id>'+str(id)+'</id>'+('' if enabled is None else '<enabled>'+enabled+'</enabled>')+'<sourceInputPortDescriptor>'+('' if address is None else '<ipAddress>'+address+'</ipAddress>')+'<srcInputPort>1</srcInputPort>'+extra+'</sourceInputPortDescriptor></InputProxyChannel>'
class Hikvision(unittest.TestCase):
 def test_configured_free_and_missing(self):
  rows=parse_hikvision(inventory([record(1,'10.1.1.1','true'),record(2,'0.0.0.0','false'),record(3,'','false')]),[1,2,3,4])
  self.assertEqual([r['state'] for r in rows],['configured','free','free','unknown'])
 def test_offline_and_disabled_address_are_occupied(self):
  text=inventory([record(1,'10.1.1.1','false','<online>false</online>')])
  self.assertEqual(parse_hikvision(text,[1])[0]['state'],'configured')
 def test_namespaces_hostname_ipv6_and_source_port(self):
  text=inventory([record(33,None,'true','<hostName>cam.local</hostName>'),record(34,None,None,'<ipv6Address>2001:db8::5</ipv6Address>')],'http://www.isapi.org/ver20/XMLSchema')
  self.assertEqual([r['state'] for r in parse_hikvision(text,[1,33,34])],['unknown','configured','configured'])
 def test_empty_incomplete_and_pending_are_unknown(self):
  for text in (inventory([]),inventory([record(1,None,None)]),inventory([record(1,'0.0.0.0','true')])):
   self.assertEqual(parse_hikvision(text,[1])[0]['state'],'unknown')
 def test_invalid_and_duplicate_responses(self):
  for text in ('<html>Login</html>','<InputProxyChannelList>','<ResponseStatus><statusCode>4</statusCode></ResponseStatus>',inventory([record(1,'10.0.0.1'),record(1,'10.0.0.2')]),inventory([record(0,'10.0.0.1')]),'<!DOCTYPE x [<!ENTITY a "x">]>'+inventory([])):
   with self.assertRaises(InventoryUnreadable):parse_hikvision(text,[1])
 def test_conflicting_flags_and_invalid_address(self):
  for text in (inventory([record(1,'10.0.0.1','true','<enabled>false</enabled>')]),inventory([record(1,'invalid','false')])):
   self.assertEqual(parse_hikvision(text,[1])[0]['state'],'unknown')
 def test_route_path_auth_and_failures(self):
  class App:
   def post(self,path):
    def wrap(f):self.call=f;return f
    return wrap
  app=App();configure_discovery(app,lambda:None)
  body=DiscoverInput(ip='10.104.3.8',manufacturer='Hikvision',username='admin',password='private-test-only',channels=[1,2],management_port=4080)
  original=httpx.Client;paths=[]
  def response(request):
   paths.append(str(request.url));return httpx.Response(200,text=inventory([record(1,'10.0.0.1'),record(2,'0.0.0.0','false')]))
  with patch('backend.discovery.httpx.Client',side_effect=lambda **kw:original(transport=httpx.MockTransport(response),**kw)):result=app.call(body,{})
  self.assertTrue(result['confirmed']);self.assertEqual([r['state'] for r in result['rows']],['configured','free']);self.assertTrue(paths[0].endswith(':4080/ISAPI/ContentMgmt/InputProxy/channels'))
  for status,text in [(401,'Unauthorized'),(403,'Forbidden'),(404,'Not supported'),(200,'<html>Login</html>')]:
   with patch('backend.discovery.httpx.Client',side_effect=lambda **kw:original(transport=httpx.MockTransport(lambda request:httpx.Response(status,text=text)),**kw)):result=app.call(body,{})
   self.assertFalse(result['confirmed']);self.assertTrue(all(r['state']=='unknown' for r in result['rows']));self.assertNotIn('private-test-only',str(result))
 def test_digest_challenge_and_basic_fallback(self):
  class App:
   def post(self,path):
    def wrap(f):self.call=f;return f
    return wrap
  app=App();configure_discovery(app,lambda:None)
  body=DiscoverInput(ip='10.104.3.8',manufacturer='Hikvision',username='admin',password='private-test-only',channels=[1])
  original=httpx.Client
  for expected in ('Digest','Basic'):
   seen=[]
   def response(request):
    header=request.headers.get('Authorization','');seen.append(header.split(' ',1)[0])
    if header.startswith(expected+' '):return httpx.Response(200,text=inventory([record(1,'10.0.0.1')]))
    challenge={'WWW-Authenticate':'Digest realm="NVR", nonce="testnonce", algorithm=MD5, qop="auth"'} if expected=='Digest' else {}
    return httpx.Response(401,headers=challenge)
   with patch('backend.discovery.httpx.Client',side_effect=lambda **kw:original(transport=httpx.MockTransport(response),**kw)):result=app.call(body,{})
   self.assertTrue(result['confirmed']);self.assertIn(expected,seen)
 def test_timeout_does_not_mark_free(self):
  class App:
   def post(self,path):
    def wrap(f):self.call=f;return f
    return wrap
  app=App();configure_discovery(app,lambda:None)
  body=DiscoverInput(ip='10.104.3.8',manufacturer='Hikvision',username='admin',password='private-test-only',channels=[1,2])
  with patch('backend.discovery.httpx.Client',side_effect=httpx.ConnectTimeout('Timeout')):result=app.call(body,{})
  self.assertFalse(result['confirmed']);self.assertEqual([r['state'] for r in result['rows']],['unknown','unknown'])
if __name__=='__main__':unittest.main()
