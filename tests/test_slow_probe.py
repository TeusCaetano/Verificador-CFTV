import unittest,sys,subprocess
from pathlib import Path
from unittest.mock import patch,MagicMock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.probe import probe_video
class SlowProbe(unittest.TestCase):
 def test_slow_then_online(self):
  with patch('backend.probe.subprocess.run',side_effect=[subprocess.TimeoutExpired('ffprobe',18),MagicMock(returncode=0,stdout=b'{"streams":[{"codec_name":"h264"}]}',stderr=b'')]) as run:
   r=probe_video('rtsp://private');self.assertEqual(r['status'],'online');self.assertEqual(r['attempts'],2);self.assertEqual(run.call_args.kwargs['timeout'],40)
 def test_fast_success_once(self):
  with patch('backend.probe.subprocess.run',return_value=MagicMock(returncode=0,stdout=b'{"streams":[{"codec_name":"h264"}]}',stderr=b'')) as run:
   self.assertEqual(probe_video('rtsp://private')['attempts'],1);self.assertEqual(run.call_count,1)
 def test_auth_failure_no_retry(self):
  with patch('backend.probe.subprocess.run',return_value=MagicMock(returncode=1,stdout=b'{}',stderr=b'401 Unauthorized')) as run:
   self.assertEqual(probe_video('rtsp://user:password@private')['status'],'offline');self.assertEqual(run.call_count,1)
 def test_two_timeouts_bounded(self):
  with patch('backend.probe.subprocess.run',side_effect=subprocess.TimeoutExpired('ffprobe',18)) as run:
   r=probe_video('rtsp://user:password@private');self.assertEqual(r['status'],'offline');self.assertEqual(run.call_count,2);self.assertNotIn('password',r['diagnostic'])
if __name__=='__main__':unittest.main()
