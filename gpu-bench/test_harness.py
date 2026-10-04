import http.server, json, pathlib, tempfile, threading, unittest
import bench

class MockServer(http.server.BaseHTTPRequestHandler):
    def log_message(self,*a): pass
    def do_GET(self):
        self.send_response(200);self.end_headers();self.wfile.write(b'{"data":[{"id":"local-coder"}]}')
    def do_POST(self):
        payload=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers()
        events=[{'choices':[{'delta':{'reasoning_content':'checking'}}]},
                {'choices':[{'delta':{'content':'{"outcomes":["error","fail","fail","pass","pass"],"defects":[{"category":"constructor_shadowing"},{"category":"frozen_clock"},{"category":"eviction_before_expiry"}]}'},'finish_reason':'stop'}]},
                {'choices':[],'usage':{'completion_tokens':42,'prompt_tokens':10}}]
        for e in events:self.wfile.write(('data: '+json.dumps(e)+'\n\n').encode());self.wfile.flush()
        self.wfile.write(b'data: [DONE]\n\n')

class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=http.server.ThreadingHTTPServer(('127.0.0.1',0),MockServer)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.endpoint={'url':f'http://127.0.0.1:{cls.server.server_port}/v1'}
    @classmethod
    def tearDownClass(cls):cls.server.shutdown();cls.server.server_close();cls.thread.join()
    def test_stream_usage_reasoning_and_answer_timing(self):
        r=bench.chat(self.endpoint,[{'role':'user','content':'x'}],{})
        self.assertEqual(r['usage']['completion_tokens'],42)
        self.assertEqual(r['reasoning'],'checking');self.assertLessEqual(r['ttft_s'],r['first_content_s'])
        self.assertEqual(r['finish_reason'],'stop')
    def test_review_false_positives_penalized(self):
        valid={'outcomes':['error','fail','fail','pass','pass'],'defects':[{'category':x} for x in ['constructor_shadowing','frozen_clock','eviction_before_expiry']]}
        with tempfile.TemporaryDirectory() as d:
            a=bench.grade(bench.TASKS['ttl_review'],json.dumps(valid),pathlib.Path(d),False)
            self.assertTrue(a['success']);self.assertEqual(a['score'],1)
            valid['defects'].append({'category':'exact_expiry'})
            b=bench.grade(bench.TASKS['ttl_review'],json.dumps(valid),pathlib.Path(d),False)
            self.assertFalse(b['success']);self.assertLess(b['score'],1)
    def test_actual_execution_pass_and_fail(self):
        good='''def merge_intervals(intervals):
 a=sorted((x,y) for x,y in intervals)
 if any(x>y for x,y in a): raise ValueError()
 out=[]
 for x,y in a:
  if out and x<=out[-1][1]:out[-1]=(out[-1][0],max(out[-1][1],y))
  else:out.append((x,y))
 return out
'''
        with tempfile.TemporaryDirectory() as d:
            a=bench.grade(bench.TASKS['intervals'],json.dumps({'code':good}),pathlib.Path(d)/'good',True)
            self.assertTrue(a['success']);self.assertEqual(a['counts']['run'],6)
            b=bench.grade(bench.TASKS['intervals'],json.dumps({'code':'def merge_intervals(x): return []'}),pathlib.Path(d)/'bad',True)
            self.assertFalse(b['success']);self.assertGreater(b['counts']['failures'],0)
    def test_regression_mutation_grader(self):
        code=(pathlib.Path(bench.__file__).parent/'reference_regression.py').read_text()
        with tempfile.TemporaryDirectory() as d:
            r=bench.grade(bench.TASKS['regression_tests'],json.dumps({'test_code':code}),pathlib.Path(d),True)
            self.assertTrue(r['success'],r)
            self.assertEqual(r['score'],1)
            counts=r['mutation_checks']['original']['counts']
            self.assertEqual(counts,{'run':5,'failures':2,'errors':1})
    def test_malformed_not_success(self):
        self.assertFalse(bench.grade(bench.TASKS['ttl_review'],'not json',pathlib.Path('.'),False)['success'])
    def test_complete_trial_report_and_load(self):
        with tempfile.TemporaryDirectory() as d:
            path=pathlib.Path(d);sc={'id':'mock','label':'MOCK ONLY','architecture':'single_gpu','endpoints':[self.endpoint]}
            bench.save(path/'manifest.json',{'created':'mock integration test, not GPU measurements','scenarios':[sc]})
            r=bench.run_trial(sc,'ttl_review',0,{},path/'mock/trials/review-0',False)
            self.assertTrue(r['grade']['success'])
            bench.load_test(sc,{'concurrency':[1,2],'load_requests_per_level':2},path/'mock')
            summary=bench.generate_report(path)
            self.assertEqual(summary[0]['successes'],1)
            self.assertTrue((path/'report.html').exists());self.assertTrue((path/'trials.csv').exists())
            self.assertTrue(json.loads((path/'mock/load.json').read_text())['complete'])
    def test_collaboration_runs_three_calls(self):
        with tempfile.TemporaryDirectory() as d:
            sc={'id':'mock','architecture':'collaborating_agents','workflow':'review_revise','endpoints':[self.endpoint,self.endpoint]}
            r=bench.run_trial(sc,'ttl_review',0,{},pathlib.Path(d),False)
            self.assertEqual(len(r['calls']),3);self.assertTrue(r['grade']['success'])

if __name__=='__main__':unittest.main(verbosity=2)
