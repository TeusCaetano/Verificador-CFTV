import subprocess,time,json,threading
from fastapi import HTTPException

def probe_codec(url,cancel):
 p=subprocess.Popen(['ffprobe','-v','error','-rtsp_transport','tcp','-timeout','15000000','-analyzeduration','1000000','-probesize','500000','-select_streams','v:0','-show_entries','stream=codec_name','-of','json',url],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
 deadline=time.monotonic()+18
 try:
  while time.monotonic()<deadline:
   if cancel.is_set():raise HTTPException(409,'Abertura cancelada ao trocar de câmera.')
   try:
    output,_=p.communicate(timeout=0.15)
    streams=json.loads(output or b'{}').get('streams',[])
    if p.returncode or not streams:raise HTTPException(502,'Não foi possível identificar o stream. Confira o canal selecionado.')
    return streams[0].get('codec_name')
   except subprocess.TimeoutExpired:continue
  raise HTTPException(504,'O gravador demorou para informar o codec. Tente reproduzir novamente.')
 finally:
  if p.poll() is None:p.kill();p.communicate()

class Preparations:
 def __init__(self):self.lock=threading.Lock();self.requests={}
 def begin(self,key):
  event=threading.Event()
  with self.lock:
   old=self.requests.get(key)
   if old:old.set()
   self.requests[key]=event
  return event
 def finish(self,key,event):
  with self.lock:
   if self.requests.get(key) is event:self.requests.pop(key,None)
 def cancel(self,key):
  with self.lock:
   event=self.requests.get(key)
   if event:event.set()
