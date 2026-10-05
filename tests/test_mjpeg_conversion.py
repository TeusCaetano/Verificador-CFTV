import unittest,sys,tempfile,subprocess,json,shutil
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.transcoding import command
class MJPEG(unittest.TestCase):
 @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg required')
 def test_real_mjpeg_decoding_and_h264_preview(self):
  with tempfile.TemporaryDirectory() as directory:
   source=Path(directory)/'source.avi';target=Path(directory)/'preview.mp4'
   subprocess.run(['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-f','lavfi','-i','testsrc2=size=800x600:rate=10','-frames:v','10','-c:v','mjpeg','-threads','1',str(source)],check=True,capture_output=True,timeout=30)
   args=command(str(source),str(target));file_args=[];i=0
   # File fixture exercises the same decode, scaling, H.264 encode and audio map.
   # Transport is covered by the live route tests, without accessing user NVRs.
   while i<len(args):
    if args[i] in ('-rtsp_transport','-timeout'):i+=2;continue
    if args[i]=='-f' and args[i+1]=='rtsp':file_args.extend(['-f','mp4']);i+=2;continue
    file_args.append(args[i]);i+=1
   subprocess.run(file_args,check=True,capture_output=True,timeout=30)
   result=subprocess.run(['ffprobe','-v','error','-select_streams','v:0','-show_entries','stream=codec_name,width,height,pix_fmt','-of','json',str(target)],check=True,capture_output=True,timeout=10)
   stream=json.loads(result.stdout)['streams'][0]
   self.assertEqual(stream['codec_name'],'h264');self.assertEqual(stream['pix_fmt'],'yuv420p');self.assertLessEqual(stream['width'],640);self.assertLessEqual(stream['height'],360)
if __name__=='__main__':unittest.main()
