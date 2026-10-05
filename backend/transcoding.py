"""Bounded on-demand converters; no shell or credentials in log output."""
import subprocess,threading,time,hashlib,logging
from fastapi import HTTPException

def command(source,target):
 return ['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-rtsp_transport','tcp','-timeout','25000000','-threads','2','-i',source,'-map','0:v:0','-map','0:a:0?','-vf',"scale=w='min(640,iw)':h='min(360,ih)':force_original_aspect_ratio=decrease:force_divisible_by=2",'-r','10','-c:v','libx264','-preset','ultrafast','-tune','zerolatency','-threads','2','-pix_fmt','yuv420p','-crf','30','-maxrate','600k','-bufsize','600k','-g','10','-keyint_min','10','-sc_threshold','0','-c:a','aac','-ac','1','-ar','16000','-b:a','32k','-f','rtsp','-rtsp_transport','tcp',target]

class Converters:
 def __init__(self,limit=2,idle=45):
  self.limit=limit;self.idle=idle;self.jobs={};self.errors={};self.lock=threading.RLock();self.done=threading.Event();self.thread=None
 def start(self):
  self.done.clear();self.thread=threading.Thread(target=self.reap,daemon=True,name='video-converters');self.thread.start()
 def ensure(self,id,source,target,prepare):
  signature=hashlib.sha256(source.encode()).hexdigest()
  self.collect()
  with self.lock:
   job=self.jobs.get(id)
   same=job and job['signature']==signature
  if same:
   if not job['ready'].wait(15):raise HTTPException(503,'Conversão ainda sendo preparada.')
   self.touch(id);return
  if job:self.remove(id)
  with self.lock:
   if id in self.jobs:raise HTTPException(409,'Canal sendo preparado por outra solicitação.')
   if len(self.jobs)>=self.limit:raise HTTPException(429,'Limite de conversões simultâneas atingido. Feche outra câmera em conversão e tente novamente em alguns segundos.')
   reservation={'process':None,'signature':signature,'last':time.monotonic(),'ready':threading.Event()}
   self.jobs[id]=reservation
  process=None
  try:
   # Network preparation and process shutdown never hold the shared jobs lock.
   prepare()
   with self.lock:
    if self.jobs.get(id) is not reservation:raise HTTPException(409,'Conversão cancelada.')
   try:process=subprocess.Popen(command(source,target),stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
   except OSError:raise HTTPException(503,'Conversor de vídeo indisponível.')
   with self.lock:
    accepted=self.jobs.get(id) is reservation
    if accepted:reservation['process']=process;self.errors.pop(id,None)
   if not accepted:
    self.terminate(process);raise HTTPException(409,'Conversão cancelada.')
   threading.Thread(target=self.capture,args=(id,process),daemon=True,name='converter-diagnostic').start()
  except Exception:
   with self.lock:
    if self.jobs.get(id) is reservation:self.jobs.pop(id,None)
   raise
  finally:reservation['ready'].set()
 def capture(self,id,process):
  # Read bounded lines; publish only fixed messages, never raw FFmpeg output.
  reason='Conversão de vídeo encerrou antes de disponibilizar a imagem.'
  if process.stderr:
   while True:
    line=process.stderr.readline(4096)
    if not line:break
    value=line.lower()
    if b'401' in value or b'unauthorized' in value or b'403' in value:reason='Conversão: autenticação ou permissão RTSP rejeitada.'
    elif b'connection refused' in value:reason='Conversão: conexão RTSP recusada. Verifique gravador e gateway.'
    elif b'timed out' in value:reason='Conversão: timeout ao receber o stream RTSP.'
    elif b'option not found' in value or b'unrecognized option' in value:reason='Conversão: opção FFmpeg incompatível com a versão instalada.'
    elif b'unknown encoder' in value:reason='Conversão: codificador H.264 indisponível.'
    elif b'error reinitializing filters' in value or b'failed to configure' in value:reason='Conversão: falha ao preparar a resolução do vídeo.'
    elif b'not enough frames' in value or b'could not find codec parameters' in value:reason='Conversão: stream sem quadros suficientes para iniciar.'
  code=process.wait()
  if code and not self.done.is_set():
   with self.lock:
    current=self.jobs.get(id)
    if current and current['process'] is process:self.errors[id]=reason
   logging.getLogger(__name__).warning('Canal ID %s: %s (saída %s)',id,reason,code)
 def touch(self,id):
  with self.lock:
   job=self.jobs.get(id)
   if not job or not job['process'] or job['process'].poll() is not None:raise HTTPException(502,self.errors.get(id,'A conversão encerrou. Clique em reproduzir para reiniciar.'))
   job['last']=time.monotonic()
 def terminate(self,p):
  if p and p.poll() is None:
   p.terminate()
   try:p.wait(timeout=3)
   except subprocess.TimeoutExpired:p.kill();p.wait(timeout=3)
 def remove(self,id):
  with self.lock:job=self.jobs.pop(id,None)
  if job:
   job['ready'].set();self.terminate(job['process'])
 def collect(self):
  with self.lock:
   stale=[(id,job) for id,job in self.jobs.items() if job['process'] is not None and (job['process'].poll() is not None or time.monotonic()-job['last']>self.idle)]
   removed=[]
   for id,job in stale:
    if self.jobs.get(id) is job:removed.append(self.jobs.pop(id))
  for job in removed:job['ready'].set();self.terminate(job['process'])
 def reap(self):
  while not self.done.wait(5):self.collect()
 def stop(self):
  self.done.set()
  if self.thread:self.thread.join(timeout=6)
  with self.lock:ids=list(self.jobs)
  for id in ids:self.remove(id)
