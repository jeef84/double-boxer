"""Harness validation fixture; never included in model prompts."""
import pathlib,sys,unittest
from unittest import mock
sys.path.insert(0,str(pathlib.Path(__file__).parent/'review-target'))
import clock
from ttl_cache import TTLCache
class Fake:
 def __init__(self):self.t=0
 def now(self):return self.t
class Checks(unittest.TestCase):
 def test_constructor(self):self.assertIsInstance(TTLCache(2),TTLCache)
 def test_clock(self):
  with mock.patch('clock.time.time',return_value=1000) as t:
   c=clock.Clock();self.assertEqual(c.now(),1000);t.return_value=1001;self.assertEqual(c.now(),1001)
 def test_eviction(self):
  f=Fake();c=TTLCache(2,f);c.set('A',1,100);c.set('B',2,1);f.t=2;c.set('C',3,100)
  self.assertEqual(c.get('A'),1);self.assertEqual(c.get('C'),3);self.assertIsNone(c.get('B'))
 def test_update(self):
  f=Fake();c=TTLCache(2,f);c.set('A',1,100);c.set('B',2,100);f.t=2;c.set('A',3,50)
  self.assertEqual(c.get('A'),3);self.assertEqual(c.get('B'),2);f.t=51;self.assertEqual(c.get('A'),3);f.t=52;self.assertIsNone(c.get('A'))
 def test_boundary(self):
  f=Fake();c=TTLCache(2,f);c.set('A',1,5);f.t=4;self.assertEqual(c.get('A'),1);f.t=5;self.assertIsNone(c.get('A'))
