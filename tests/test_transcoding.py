import sys,unittest
from pathlib import Path
from unittest.mock import patch,MagicMock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.transcoding import Converters,command
from fastapi import HTTPException
class Conversion(unittest.TestCase):
 def test_reuse_limit_expiry_shutdown(self):
  with patch('backend.transcoding.subprocess.Popen') as spawn:
   spawn.side_effect=lambda *a,**k:MagicMock(poll=MagicMock(return_value=None))
   m=Converters(limit=1,idle=45);prepare=MagicMock();m.ensure(1,'rtsp://secret','rtsp://video/1',prepare);m.ensure(1,'rtsp://secret','rtsp://video/1',prepare)
   self.assertEqual(spawn.call_count,1);self.assertEqual(prepare.call_count,1)
   with self.assertRaises(HTTPException) as e:m.ensure(2,'other','target',prepare)
   self.assertEqual(e.exception.status_code,429)
   m.touch(1);m.jobs[1]['last']-=46;m.collect();self.assertFalse(m.jobs)
   m.ensure(2,'other','target',prepare);m.stop();self.assertFalse(m.jobs)
 def test_settings(self):
  c=command('input','output');self.assertIn('libx264',c);self.assertIn('zerolatency',c);self.assertIn('10',c);self.assertIn('0:a:0?',c);self.assertIn('2',c)
if __name__=='__main__':unittest.main()
