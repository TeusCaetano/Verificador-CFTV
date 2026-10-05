import sys,socket,threading,hashlib,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.probe import describe_probe,sdp_video_codec

SDP='v=0\r\nm=video 0 RTP/AVP 96\r\na=rtpmap:96 H264/90000\r\n'
def serve(handler):
    server=socket.socket();server.bind(('127.0.0.1',0));server.listen(1)
    def run():
        conn,_=server.accept()
        with conn:handler(conn)
        server.close()
    threading.Thread(target=run,daemon=True).start()
    return server.getsockname()[1]
def read_request(conn):
    data=b''
    while b'\r\n\r\n' not in data:data+=conn.recv(4096)
    return data.decode()
def reply(conn,status,extra='',body=''):
    conn.sendall(f'RTSP/1.0 {status}\r\nCSeq: 1\r\n{extra}Content-Length: {len(body)}\r\n\r\n{body}'.encode())

class Describe(unittest.TestCase):
    def test_digest_auth_returns_codec(self):
        def handler(conn):
            read_request(conn);reply(conn,'401 Unauthorized','WWW-Authenticate: Digest realm="r", nonce="n", qop="auth"\r\n')
            request=read_request(conn)
            uri=request.split()[1]
            ha1=hashlib.md5(b'u:r:p').hexdigest();ha2=hashlib.md5(('DESCRIBE:'+uri).encode()).hexdigest()
            fields=dict(x.strip().split('=',1) for x in request.split('Authorization: Digest ')[1].split('\r\n')[0].split(','))
            cnonce=fields['cnonce'].strip('"')
            expected=hashlib.md5(f'{ha1}:n:00000001:{cnonce}:auth:{ha2}'.encode()).hexdigest()
            ok=fields['response'].strip('"')==expected
            reply(conn,'200 OK' if ok else '401 Unauthorized','',SDP if ok else '')
        port=serve(handler)
        r=describe_probe(f'rtsp://u:p@127.0.0.1:{port}/cam')
        self.assertEqual((r['status'],r.get('codec')),('online','h264'))
    def test_wrong_password_is_offline(self):
        def handler(conn):
            read_request(conn);reply(conn,'401 Unauthorized','WWW-Authenticate: Basic realm="r"\r\n')
            read_request(conn);reply(conn,'401 Unauthorized')
        port=serve(handler)
        self.assertEqual(describe_probe(f'rtsp://u:x@127.0.0.1:{port}/cam')['status'],'offline')
    def test_404_and_refused_are_inconclusive(self):
        port=serve(lambda c:(read_request(c),reply(c,'404 Not Found')))
        self.assertEqual(describe_probe(f'rtsp://u:p@127.0.0.1:{port}/cam')['status'],'unknown')
        self.assertEqual(describe_probe('rtsp://u:p@127.0.0.1:1/cam',timeout=1)['status'],'unknown')
    def test_sdp_codecs(self):
        self.assertEqual(sdp_video_codec('m=video 0 RTP/AVP 26\r\n'),'mjpeg')
        self.assertIsNone(sdp_video_codec('m=audio 0 RTP/AVP 8\r\n'))
        self.assertEqual(sdp_video_codec('m=video 0 RTP/AVP 98\r\na=rtpmap:98 H265/90000\r\n'),'hevc')
if __name__=='__main__':unittest.main()
