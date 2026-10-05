"""Read-only Intelbras/Hikvision inventory; failures never imply a free channel."""
import re,threading,ipaddress
from xml.etree import ElementTree as ET
import httpx
from fastapi import Depends,HTTPException
from pydantic import BaseModel,Field,IPvAnyAddress,SecretStr,model_validator

class DiscoverInput(BaseModel):
    ip:IPvAnyAddress
    management_port:int=Field(default=80,ge=1,le=65535)
    management_scheme:str=Field(default='http',pattern='^(http|https)$')
    manufacturer:str=Field(pattern='^(Intelbras|Hikvision)$')
    username:str=Field(min_length=1,max_length=100)
    password:SecretStr=Field(min_length=1,max_length=200)
    channels:list[int]=Field(min_length=1,max_length=256)
    @model_validator(mode='after')
    def check_channels(self):
        if len(set(self.channels))!=len(self.channels) or any(x<1 or x>256 for x in self.channels):raise ValueError('Canais devem ser únicos entre 1 e 256.')
        return self

class InventoryUnreadable(ValueError):pass

def parse_intelbras(text,channels):
    """getCameraAll describes UniqueChannel in zero-based device numbering.
    Missing entries are free only after a complete, recognized inventory response.
    Never use remote Channel (camera's own channel) as the NVR channel number.
    """
    text=text.strip()
    if text in ('camera=[]','cameras=[]'):
        return [{'channel':n,'state':'free','reason':'Lista completa do gravador vazia.'} for n in channels]
    records={}
    for line in text.splitlines():
        if not line.strip():continue
        match=re.fullmatch(r'(?:table\.)?camera\[(\d+)\]\.([A-Za-z0-9_.\[\]]+)=(.*)',line.strip())
        if not match:raise InventoryUnreadable('Resposta do cadastro de canais não reconhecida ou incompleta.')
        index=int(match[1]);key=match[2];value=match[3].strip().strip('"')
        record=records.setdefault(index,{})
        if key in record:raise InventoryUnreadable('Campos repetidos na resposta do gravador.')
        record[key]=value
    if not records:raise InventoryUnreadable('O gravador não retornou um cadastro de canais reconhecido.')
    result={}
    for record in records.values():
        raw=record.get('UniqueChannel')
        if raw is None or not raw.isdecimal() or not 0<=int(raw)<256:
            raise InventoryUnreadable('Numeração dos canais não confirmada pelo gravador.')
        channel=int(raw)+1
        if channel in result:raise InventoryUnreadable('Numeração duplicada na resposta do gravador.')
        address=record.get('DeviceInfo.Address','').strip()
        device_id=record.get('DeviceID','').strip()
        enabled=record.get('DeviceInfo.Enable',record.get('Enable','')).lower()
        if record.get('Type') not in (None,'Remote','Reserved32'):
            state,reason='unknown','Tipo de canal não suportado para detecção automática.'
        elif record.get('Enable','').lower()=='false' and record.get('DeviceInfo.Enable','').lower()=='false':
            state,reason='free','Cadastro do canal desativado no gravador; dados antigos não indicam câmera ativa.'
        elif address and address not in ('0.0.0.0','::'):
            state,reason='configured','Câmera cadastrada; comunicação será verificada pelo monitor.'
        elif device_id and enabled=='true':
            state,reason='configured','Dispositivo cadastrado no canal.'
        elif enabled=='false' and not device_id:
            state,reason='free','Canal explicitamente sem câmera habilitada no cadastro.'
        else:state,reason='unknown','Cadastro sem evidência suficiente; revisar manualmente.'
        result[channel]=(state,reason)
    return [{'channel':n,'state':result.get(n,('free','Canal ausente na lista completa de câmeras cadastradas.'))[0],
             'reason':result.get(n,('free','Canal ausente na lista completa de câmeras cadastradas.'))[1]} for n in channels]

def parse_hikvision(text,channels):
    """ISAPI digital input IDs are used literally, not streaming IDs or offsets.
    Missing entries remain unknown: a hybrid DVR can omit analog inputs here.
    """
    if len(text)>2_000_000 or '<!DOCTYPE' in text.upper() or '<!ENTITY' in text.upper():
        raise InventoryUnreadable('XML de canais não permitido; revise manualmente.')
    try:root=ET.fromstring(text)
    except ET.ParseError:raise InventoryUnreadable('Resposta XML Hikvision inválida ou incompleta.')
    def tag(node):return node.tag.rsplit('}',1)[-1]
    if tag(root)!='InputProxyChannelList':
        raise InventoryUnreadable('Cadastro ISAPI Hikvision não reconhecido. Confira firmware e permissão.')
    if any(tag(node)!='InputProxyChannel' for node in root):
        raise InventoryUnreadable('Lista Hikvision com estrutura não reconhecida; revise manualmente.')
    def field(node,name):
        matches=[child for child in node if tag(child)==name]
        if len(matches)>1:raise InventoryUnreadable('Campos repetidos no cadastro Hikvision.')
        return (matches[0].text or '').strip() if matches else None
    found={}
    for record in root:
        raw=field(record,'id')
        if raw is None or not raw.isdecimal() or not 1<=int(raw)<=65535:
            raise InventoryUnreadable('Numeração dos canais Hikvision não confirmada.')
        channel=int(raw)
        if channel in found:raise InventoryUnreadable('Numeração duplicada no cadastro Hikvision.')
        descriptors=[node for node in record if tag(node)=='sourceInputPortDescriptor']
        if len(descriptors)>1:raise InventoryUnreadable('Origem duplicada no canal Hikvision.')
        descriptor=descriptors[0] if descriptors else record
        flags=[field(record,'enabled'),field(record,'enable')]
        if descriptor is not record:flags.extend([field(descriptor,'enabled'),field(descriptor,'enable')])
        flags=[value.lower() for value in flags if value is not None]
        enabled=flags[0] if flags and len(set(flags))==1 and flags[0] in ('true','false') else None
        contradictory=bool(flags) and enabled is None
        values=[field(descriptor,'ipAddress'),field(descriptor,'ipv6Address')]
        hostname=field(descriptor,'hostName')
        address_present=bool(hostname and hostname.lower() not in ('null','none'))
        explicit_empty=False;invalid=False
        for value in values:
            if value is None:continue
            if not value:explicit_empty=True;continue
            try:
                address=ipaddress.ip_address(value)
                if address.is_unspecified:explicit_empty=True
                else:address_present=True
            except ValueError:invalid=True
        if contradictory or invalid:
            state,reason='unknown','Cadastro inconsistente ou endereço não reconhecido; revisar manualmente.'
        elif address_present:
            state,reason='configured','Câmera cadastrada no canal Hikvision; estar offline não torna o canal livre.'
        elif enabled=='false' or (explicit_empty and enabled!='true'):
            state,reason='free','Canal Hikvision sem origem de câmera cadastrada ou habilitada.'
        else:
            state,reason='unknown','Canal sem evidência suficiente de ocupação; revisar manualmente.'
        found[channel]=(state,reason)
    absent=('unknown','Canal não retornado pelo ISAPI; confira numeração e canais analógicos manualmente.')
    return [{'channel':n,'state':found.get(n,absent)[0],'reason':found.get(n,absent)[1]} for n in channels]

def configure_discovery(app,admin):
    slots=threading.BoundedSemaphore(2)
    @app.post('/api/inventory/discover-channels')
    def discover(body:DiscoverInput,user=Depends(admin)):
        def unknown(message):return {'confirmed':False,'message':message,'rows':[{'channel':n,'state':'unknown','reason':message} for n in body.channels]}
        if not slots.acquire(blocking=False):raise HTTPException(429,'Há duas consultas em andamento. Tente novamente.')
        try:
            host=str(body.ip);host='['+host+']' if ':' in host else host
            path='/cgi-bin/LogicDeviceManager.cgi?action=getCameraAll' if body.manufacturer=='Intelbras' else '/ISAPI/ContentMgmt/InputProxy/channels'
            url=f'{body.management_scheme}://{host}:{body.management_port}'+path
            password=body.password.get_secret_value()
            with httpx.Client(timeout=httpx.Timeout(10,connect=5),trust_env=False,follow_redirects=False) as client:
                auth=httpx.DigestAuth(body.username,password)
                def read(auth):
                    with client.stream('GET',url,auth=auth) as response:
                        if response.status_code!=200:return response.status_code,''
                        data=bytearray()
                        for chunk in response.iter_bytes():
                            data.extend(chunk)
                            if len(data)>2_000_000:raise InventoryUnreadable('Cadastro excede o limite de leitura; revisar manualmente.')
                        return 200,data.decode('utf-8',errors='strict')
                status,text=read(auth)
                if status==401:status,text=read(httpx.BasicAuth(body.username,password))
                if status in (401,403):return unknown('Acesso negado. Verifique usuário, senha e permissão de consultar câmeras.')
                if status!=200:return unknown('Consulta não disponível nesta porta ou firmware (HTTP '+str(status)+'). Revise manualmente.')
                parser=parse_intelbras if body.manufacturer=='Intelbras' else parse_hikvision
                rows=parser(text,body.channels)
                confirmed=all(r['state']!='unknown' for r in rows)
                return {'confirmed':confirmed,'message':'Consulta concluída. Confira os canais antes de salvar.' if confirmed else 'Consulta parcial. Canais inconclusivos exigem revisão manual.','rows':rows}
        except (httpx.HTTPError,UnicodeError):return unknown('Não foi possível consultar o gravador. Confira IP, porta web, protocolo e conexão VPN.')
        except InventoryUnreadable as e:return unknown(str(e))
        finally:slots.release()
