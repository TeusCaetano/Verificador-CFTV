import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.channel_state import parse_hikvision_states

XML=b'''<?xml version="1.0" encoding="UTF-8"?>
<InputProxyChannelStatusList xmlns="http://www.hikvision.com/ver20/XMLSchema">
<InputProxyChannelStatus><id>1</id><sourceInputPortDescriptor><proxyProtocol>HIKVISION</proxyProtocol></sourceInputPortDescriptor><online>true</online></InputProxyChannelStatus>
<InputProxyChannelStatus><id>2</id><online>false</online></InputProxyChannelStatus>
</InputProxyChannelStatusList>'''
class HikvisionState(unittest.TestCase):
    def test_parses_namespaced_status(self):
        self.assertEqual(parse_hikvision_states(XML),{1:'online',2:'offline'})
    def test_rejects_entities_duplicates_and_empty(self):
        for bad in (b'<!DOCTYPE x [<!ENTITY a "b">]><x/>',b'<a/>',b'not xml',
                    b'<l><InputProxyChannelStatus><id>1</id><online>true</online></InputProxyChannelStatus><InputProxyChannelStatus><id>1</id><online>false</online></InputProxyChannelStatus></l>'):
            with self.assertRaises(ValueError):parse_hikvision_states(bad)
if __name__=='__main__':unittest.main()
