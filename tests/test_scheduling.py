import sys,unittest
from pathlib import Path
from collections import Counter
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.scheduling import select_ready
class Scheduling(unittest.TestCase):
 def test_parallel_capacity_and_host_limit(self):
  rows=[(i,('nvr'+str((i-1)//32),554),0) for i in range(1,97)]
  chosen=select_ready(rows,{},set(),0,8,2)
  self.assertEqual(len(chosen),6);self.assertEqual(set(Counter(rows[i-1][1] for i in chosen).values()),{2})
 def test_busy_slow_nvr_does_not_block_other_nvr(self):
  rows=[(1,'slow',0),(2,'slow',0),(3,'slow',0),(4,'fast',0),(5,'fast',0)]
  self.assertEqual(select_ready(rows,{},set([1,2]),0,8,2),[4,5])
 def test_oldest_checks_first_and_future_deadline(self):
  rows=[(1,'A',100),(2,'A',0),(3,'B',50)]
  self.assertEqual(select_ready(rows,{3:10},set(),0,2,1),[2])
 def test_capacity_full_no_queue(self):
  self.assertEqual(select_ready([(1,'A',0),(2,'B',0)],{},set([1]),0,1,2),[])
 def test_96_channels_fast_probes_before_expiry(self):
  rows=[(i,('nvr'+str((i-1)//32),554),0) for i in range(1,97)];due={};checked=set()
  for now in range(0,60,3):
   chosen=select_ready(rows,due,set(),now,8,2)
   checked.update(chosen)
   for id in chosen:due[id]=now+63
  self.assertEqual(len(checked),96)
if __name__=='__main__':unittest.main()
