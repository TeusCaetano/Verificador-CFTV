import sys,threading,unittest
from pathlib import Path
from unittest.mock import patch,MagicMock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.live_preparation import Preparations,probe_codec
from fastapi import HTTPException
class Prepare(unittest.TestCase):
 def test_latest_and_isolation(self):
  r=Preparations();old=r.begin(('user','tab'));other=r.begin(('user','other-tab'));new=r.begin(('user','tab'));self.assertTrue(old.is_set());self.assertFalse(other.is_set());r.finish(('user','tab'),old);self.assertIs(r.requests[('user','tab')],new);r.cancel(('user','tab'));self.assertTrue(new.is_set());self.assertFalse(other.is_set())
 def test_cancel_kills_probe(self):
  e=threading.Event();e.set()
  with patch('backend.live_preparation.subprocess.Popen') as p:
   p.return_value.poll.return_value=None
   with self.assertRaises(HTTPException) as error:probe_codec('secret-url',e)
   self.assertEqual(error.exception.status_code,409);p.return_value.kill.assert_called_once();p.return_value.communicate.assert_called_once()
if __name__=='__main__':unittest.main()
