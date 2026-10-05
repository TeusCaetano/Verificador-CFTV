"""Bounded retry for slow RTSP startup. Never include credentials in diagnostics."""
import subprocess,json,socket,hashlib,base64,re,secrets
from urllib.parse import urlsplit,unquote

def streams_of(stdout):
    try:return json.loads(stdout or b'{}').get('streams',[])
    except ValueError:return []

def probe_video(url):
    for attempt,(read_us,analysis_us,size,deadline) in enumerate([(10_000_000,3_000_000,2_000_000,18),(25_000_000,10_000_000,4_000_000,40)],start=1):
        try:
            p=subprocess.run(['ffprobe','-v','error','-rtsp_transport','tcp','-rw_timeout',str(read_us),'-analyzeduration',str(analysis_us),'-probesize',str(size),'-select_streams','v:0','-show_entries','stream=codec_name,width,height','-of','json',url],capture_output=True,timeout=deadline)
        except subprocess.TimeoutExpired:
            if attempt==1:continue
            return {'status':'offline','network':True,'video':False,'attempts':attempt,'diagnostic':'O stream não respondeu em duas tentativas (limites de 18s e 40s). Verifique o stream selecionado e o gravador.'}
        streams=streams_of(p.stdout)
        if p.returncode==0 and streams:
            return {'status':'online','network':True,'video':True,'codec':streams[0].get('codec_name'),'attempts':attempt,'diagnostic':('Stream disponível após nova tentativa; inicialização lenta. ' if attempt>1 else 'Stream do canal disponível. ')+'Isso não comprova imagem útil da câmera conectada ao NVR.'}
        error=(p.stderr or b'').lower()
        if b'401' in error or b'unauthorized' in error or b'403' in error or b'forbidden' in error:
            return {'status':'offline','network':True,'video':False,'attempts':attempt,'diagnostic':'Autenticação ou permissão rejeitada. Verifique usuário e senha.'}
        slow=any(x in error for x in [b'timed out',b'timeout',b'connection timed',b'resource temporarily unavailable']) or (p.returncode==0 and not streams)
        if attempt==1 and slow:continue
        return {'status':'offline','network':True,'video':False,'attempts':attempt,'diagnostic':'Porta acessível, mas stream indisponível. Verifique canal, stream principal/secundário, caminho RTSP e permissões.'}


def fast_probe_video(url):
    """One bounded pass; inconclusive results go to the separate retry pool."""
    try:
        p=subprocess.run(['ffprobe','-v','error','-rtsp_transport','tcp','-timeout','4000000','-analyzeduration','500000','-probesize','500000','-select_streams','v:0','-show_entries','stream=codec_name','-of','json',url],capture_output=True,timeout=6)
        streams=streams_of(p.stdout)
        if p.returncode==0 and streams:return {'status':'online','network':True,'video':True,'codec':streams[0].get('codec_name'),'diagnostic':'Stream RTSP disponível. Imagem útil e câmera física não validadas.'}
        error=(p.stderr or b'').lower()
        if any(x in error for x in (b'401',b'403',b'unauthorized',b'forbidden')):return {'status':'offline','video':False,'diagnostic':'Autenticação RTSP rejeitada.'}
    except subprocess.TimeoutExpired:pass
    return {'status':'unknown','video':False,'needs_slow':True,'diagnostic':'Consulta rápida inconclusiva; confirmação na fila de tentativas lentas.'}


def _challenge(headers):
    """Prefer Digest over Basic; return (scheme, params) or None."""
    found={}
    for value in headers.get('www-authenticate',[]):
        scheme,_,rest=value.partition(' ')
        found[scheme.lower()]=dict(re.findall(r'(\w+)="?([^",]*)"?',rest))
    for scheme in ('digest','basic'):
        if scheme in found:return scheme,found[scheme]

def _authorization(scheme,params,user,password,uri):
    if scheme=='basic':return 'Basic '+base64.b64encode(f'{user}:{password}'.encode()).decode()
    if params.get('algorithm','MD5').upper()!='MD5':raise ValueError('unsupported digest algorithm')
    md5=lambda s:hashlib.md5(s.encode()).hexdigest()
    realm=params.get('realm','');nonce=params.get('nonce','')
    ha1=md5(f'{user}:{realm}:{password}');ha2=md5(f'DESCRIBE:{uri}')
    base=f'Digest username="{user}", realm="{realm}", nonce="{nonce}", uri="{uri}"'
    if 'auth' in params.get('qop','').split(','):
        cnonce=secrets.token_hex(8)
        return base+f', response="{md5(f"{ha1}:{nonce}:00000001:{cnonce}:auth:{ha2}")}", qop=auth, nc=00000001, cnonce="{cnonce}"'
    return base+f', response="{md5(f"{ha1}:{nonce}:{ha2}")}"'

def _rtsp_describe(sock,uri,cseq,authorization=None):
    request=f'DESCRIBE {uri} RTSP/1.0\r\nCSeq: {cseq}\r\nUser-Agent: verificador-cftv\r\nAccept: application/sdp\r\n'
    if authorization:request+=f'Authorization: {authorization}\r\n'
    sock.sendall((request+'\r\n').encode())
    data=b''
    while b'\r\n\r\n' not in data:
        chunk=sock.recv(4096)
        if not chunk or len(data)>65536:raise ValueError('incomplete RTSP response')
        data+=chunk
    head,_,body=data.partition(b'\r\n\r\n')
    lines=head.decode('latin-1').split('\r\n')
    status=int(lines[0].split()[1]);headers={}
    for line in lines[1:]:
        name,_,value=line.partition(':');headers.setdefault(name.strip().lower(),[]).append(value.strip())
    length=min(int((headers.get('content-length') or ['0'])[0]),65536)
    while len(body)<length:
        chunk=sock.recv(4096)
        if not chunk:break
        body+=chunk
    return status,headers,body.decode('latin-1')

def sdp_video_codec(sdp):
    """Codec name of the first video media section, using ffprobe naming."""
    media=re.search(r'^m=video \d+ \S+ (\d+)',sdp,re.M)
    if not media:return None
    payload=media.group(1)
    mapped=re.search(rf'^a=rtpmap:{payload} ([A-Za-z0-9-]+)/',sdp,re.M)
    name=mapped.group(1).upper() if mapped else 'JPEG' if payload=='26' else ''
    return {'H264':'h264','H265':'hevc','HEVC':'hevc','JPEG':'mjpeg','MJPEG':'mjpeg'}.get(name,name.lower() or None)

def describe_probe(url,timeout=4):
    """RTSP DESCRIBE without a subprocess. Proves auth, path and codec but not that
    frames flow, so callers keep a periodic ffprobe check. Anything inconclusive
    returns status 'unknown' so the caller escalates to ffprobe."""
    inconclusive={'status':'unknown','video':False,'diagnostic':'Consulta RTSP leve inconclusiva.'}
    parts=urlsplit(url)
    try:
        host=parts.hostname;port=parts.port or 554
        user=unquote(parts.username or '');password=unquote(parts.password or '')
        uri=f'rtsp://{"["+host+"]" if ":" in host else host}:{port}{parts.path}'+('?'+parts.query if parts.query else '')
        with socket.create_connection((host,port),timeout=timeout) as sock:
            sock.settimeout(timeout)
            status,headers,body=_rtsp_describe(sock,uri,1)
            if status==401:
                challenge=_challenge(headers)
                if not challenge:return inconclusive
                status,headers,body=_rtsp_describe(sock,uri,2,_authorization(*challenge,user,password,uri))
    except (OSError,ValueError,IndexError,TypeError):return inconclusive
    if status in (401,403):return {'status':'offline','video':False,'diagnostic':'Autenticação RTSP rejeitada.'}
    if status==200:
        codec=sdp_video_codec(body)
        if codec:return {'status':'online','network':True,'video':True,'codec':codec,'diagnostic':'Stream RTSP disponível. Imagem útil e câmera física não validadas.'}
    return inconclusive
