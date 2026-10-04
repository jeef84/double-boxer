#!/usr/bin/env python3
"""Standard-library GPU architecture benchmark. See README before running."""
import argparse, concurrent.futures as cf, csv, hashlib, html, json, math, os
import pathlib, random, statistics, subprocess, sys, tempfile, time, urllib.request
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent
VERSION = '1.0.0'

REVIEW_SOURCE = '''import time
from collections import OrderedDict
class Clock:
    def __init__(self, now=None):
        self._time = time.time() if now is None else now
    def now(self):
        return self._time
    def pause(self, seconds):
        self._time += seconds
class TTLCache:
    def __init__(self, maxsize, clock=None):
        self.maxsize = maxsize
        self.clock = clock or clock.Clock()
        self.items = OrderedDict()
    def get(self, key):
        if key not in self.items:
            return None
        value, expires = self.items[key]
        if expires is not None and self.clock.now() >= expires:
            del self.items[key]
            return None
        self.items.move_to_end(key)
        return value
    def set(self, key, value, ttl=None):
        expires = None if ttl is None else self.clock.now() + ttl
        if key in self.items:
            del self.items[key]
        if len(self.items) >= self.maxsize:
            self.items.popitem(last=False)
        self.items[key] = (value, expires)
'''

TASKS = {
 'ttl_review': {
  'kind': 'review',
  'prompt': 'Review this synthetic TTL cache. For each of the five behaviors return a JSON object with "outcomes": a list of exactly five strings, each "pass", "fail", or "error", in order, and "defects": a list of objects with "category" and "explanation". Categories allowed: constructor_shadowing, frozen_clock, eviction_before_expiry, exact_expiry, update_expiry. Judge: (1) default construction; (2) successive now calls on ONE production clock as mocked time changes; (3) capacity 2, A ttl100 and B ttl1 at t0, insert C at t2; A/C must remain; (4) capacity2, A/B ttl100 at t0, update A at t2 ttl50: both remain, A alive51 absent52; (5) absent exactly at expiry. Identify only actual implementation defects. Source:\n' + REVIEW_SOURCE,
 },
 'intervals': {
  'kind': 'code',
  'prompt': 'Write solution.py with merge_intervals(intervals). Intervals are closed integer endpoint pairs with start<=end. Return sorted merged pairs as a list of tuples; touching endpoints merge. Do not mutate the input. Empty input returns []. Reject any reversed interval with ValueError. Use only standard library. Return JSON {"code": "complete Python source"}.',
  'tests': '''import unittest
from solution import merge_intervals as f
class Checks(unittest.TestCase):
 def test_empty(self): self.assertEqual(f([]), [])
 def test_overlap(self): self.assertEqual(f([(5,7),(1,3),(2,6)]), [(1,7)])
 def test_touch(self): self.assertEqual(f([(1,2),(2,3),(5,5)]), [(1,3),(5,5)])
 def test_nested(self): self.assertEqual(f([(0,10),(2,3),(-4,-1)]), [(-4,-1),(0,10)])
 def test_immutable(self):
  a=[[5,7],[1,3]]; b=[x[:] for x in a]; f(a); self.assertEqual(a,b)
 def test_reversed(self):
  with self.assertRaises(ValueError): f([(3,1)])
''',
 },
 'ttl_implementation': {
  'kind': 'code',
  'prompt': 'Write solution.py implementing TTLCache(maxsize, clock). clock is a callable returning seconds. set(key,value,ttl=None), get(key) returns value or None. Positive integer maxsize required, else ValueError. Use LRU: successful get makes most recent, set makes most recent. Expired if now>=deadline; remove expired entries BEFORE evicting live LRU entries. ttl=None never expires; ttl<=0 means immediately absent. Updating at capacity preserves other entries and resets TTL. Standard library only. Return JSON {"code":"complete Python source"}.',
  'tests': '''import unittest
from solution import TTLCache
class Checks(unittest.TestCase):
 def setUp(self): self.t=0; self.c=TTLCache(2, lambda:self.t)
 def test_expired_first(self):
  self.c.set('A',1,100); self.c.set('B',2,1); self.t=2; self.c.set('C',3,100)
  self.assertEqual(self.c.get('A'),1); self.assertEqual(self.c.get('C'),3); self.assertIsNone(self.c.get('B'))
 def test_update(self):
  self.c.set('A',1,100); self.c.set('B',2,100); self.t=2; self.c.set('A',3,50)
  self.assertEqual(self.c.get('B'),2); self.t=51; self.assertEqual(self.c.get('A'),3)
  self.t=52; self.assertIsNone(self.c.get('A')); self.assertEqual(self.c.get('B'),2)
 def test_lru(self):
  self.c.set('A',1); self.c.set('B',2); self.c.get('A'); self.c.set('C',3)
  self.assertIsNone(self.c.get('B')); self.assertEqual(self.c.get('A'),1)
 def test_zero(self): self.c.set('A',1,0); self.assertIsNone(self.c.get('A'))
 def test_forever(self): self.c.set('A',1); self.t=1e9; self.assertEqual(self.c.get('A'),1)
 def test_invalid(self):
  with self.assertRaises(ValueError): TTLCache(0,lambda:0)
''',
 }
}

TASKS['regression_tests'] = {
 'kind':'regression',
 'prompt': 'Write exactly five independent unittest tests for the implementation below. Files are review-target/clock.py (Clock class) and review-target/ttl_cache.py (TTLCache class importing clock). Return JSON {"test_code":"complete Python test source"}. Import explicitly from review-target relative to __file__. Never modify source files. Use an independent fake for cache timing. Test: default TTLCache(2) construction; ONE production Clock with mocked changing clock.time.time on successive now calls; expired B before live A eviction (capacity2 A ttl100 B ttl1 at0 insertC at2); update A at capacity2 with B ttl100 at0, updateA at2 ttl50, both values, A live51 absent52; key alive before and absent exactly at its deadline. Tests must assert required correct behavior even if implementation is broken. Do not import private grader code. Source:\n'+REVIEW_SOURCE
}

def regression_variants():
    clock_source=REVIEW_SOURCE.split('class TTLCache:')[0].replace('from collections import OrderedDict\n','')
    cache_source='import clock\nfrom collections import OrderedDict\nclass TTLCache:'+REVIEW_SOURCE.split('class TTLCache:')[1]
    fixed_clock=clock_source.replace('self._time = time.time() if now is None else now','self._fixed = now is not None\n        self._time = now').replace('return self._time','return self._time if self._fixed else time.time()')
    fixed_cache=cache_source.replace('import clock\n','import clock as clock_module\n').replace('clock or clock.Clock()','clock if clock is not None else clock_module.Clock()')
    fixed_cache=fixed_cache.replace('        if key in self.items:\n            del self.items[key]', '        now = self.clock.now()\n        for k, (_, deadline) in list(self.items.items()):\n            if deadline is not None and now >= deadline:\n                del self.items[k]\n        if key in self.items:\n            del self.items[key]')
    no_sweep=fixed_cache.replace('        for k, (_, deadline) in list(self.items.items()):\n            if deadline is not None and now >= deadline:\n                del self.items[k]\n','')
    frozen=fixed_clock.replace('return self._time if self._fixed else time.time()', 'return self._time if self._fixed else 1000')
    # The constructor still snapshots time in the frozen mutant, matching the original defect.
    frozen=clock_source
    boundary=fixed_cache.replace('self.clock.now() >= expires','self.clock.now() > expires')
    reset=fixed_cache.replace('        expires = None if ttl is None else self.clock.now() + ttl','        expires = self.items[key][1] if key in self.items else (None if ttl is None else self.clock.now() + ttl)')
    return {'original':(clock_source,cache_source),'fixed':(fixed_clock,fixed_cache),
            'frozen_clock':(frozen,fixed_cache),'eviction_before_expiry':(fixed_clock,no_sweep),
            'exact_boundary':(fixed_clock,boundary),'update_not_reset':(fixed_clock,reset)}

def save(path, data):
    path = pathlib.Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(data, indent=2), encoding='utf8'); temp.replace(path)

def get_json(url, timeout=15):
    with urllib.request.urlopen(url, timeout=timeout) as r: return json.load(r)

def extract_json(s):
    s=s.strip()
    if s.startswith('```'): s='\n'.join(s.splitlines()[1:-1])
    return json.loads(s)

def chat(endpoint, messages, settings):
    """Measure client-observed first generated text (including reasoning) and content separately."""
    payload={'model':endpoint.get('model','local-coder'), 'messages':messages,
             'stream':True, 'stream_options':{'include_usage':True},
             'temperature':settings.get('temperature',0), 'max_tokens':settings.get('max_tokens',4096)}
    payload.update(endpoint.get('request_overrides',{}))
    if payload.get('stream') is not True: raise ValueError('stream must remain true')
    headers={'Content-Type':'application/json'}
    if endpoint.get('api_key_env'): headers['Authorization']='Bearer '+os.environ[endpoint['api_key_env']]
    req=urllib.request.Request(endpoint['url'].rstrip('/')+'/chat/completions',
         data=json.dumps(payload).encode(),headers=headers)
    t0=time.perf_counter(); first=None; content_first=None; content=''; reasoning=''; usage={}; timings={}; finish=None
    chunks=0
    with urllib.request.urlopen(req, timeout=settings.get('timeout_seconds',900)) as response:
        for line in response:
            if time.perf_counter()-t0>settings.get('timeout_seconds',900): raise TimeoutError('request wall time exceeded')
            line=line.decode('utf8').strip()
            if not line.startswith('data:'): continue
            data=line[5:].strip()
            if data=='[DONE]': break
            obj=json.loads(data)
            if obj.get('error'): raise RuntimeError(str(obj['error']))
            if obj.get('usage'): usage=obj['usage']
            if obj.get('timings'): timings=obj['timings']
            for choice in obj.get('choices',[]):
                delta=choice.get('delta',{})
                c=delta.get('content') or ''; r=delta.get('reasoning_content') or delta.get('reasoning') or ''
                if c or r:
                    now=time.perf_counter()-t0; chunks+=1
                    if first is None: first=now
                    if c and content_first is None: content_first=now
                content+=c; reasoning+=r
                if choice.get('finish_reason'): finish=choice['finish_reason']
    duration=time.perf_counter()-t0
    if not content and not reasoning: raise RuntimeError('stream returned no text')
    return {'content':content,'reasoning':reasoning,'usage':usage,'server_timings':timings,
            'ttft_s':first,'first_content_s':content_first,'duration_s':duration,
            'finish_reason':finish,'text_chunks':chunks,
            'output_tokens_per_wall_second':usage.get('completion_tokens',0)/duration if usage.get('completion_tokens') is not None else None}

def grade(task, answer, directory, allow_code):
    try: obj=extract_json(answer)
    except Exception as e: return {'score':0,'success':False,'error':'invalid JSON: '+str(e)}
    if task['kind']=='regression':
        if not allow_code: return {'score':None,'success':False,'error':'code execution not enabled'}
        test_code=obj.get('test_code')
        if not isinstance(test_code,str):return {'score':0,'success':False,'error':'missing test_code'}
        records={};passed=0
        for name,(clock_src,cache_src) in regression_variants().items():
            variant=directory/name;target=variant/'review-target';target.mkdir(parents=True,exist_ok=True)
            (target/'clock.py').write_text(clock_src);(target/'ttl_cache.py').write_text(cache_src)
            r=grade({'kind':'code','tests':test_code,'test_count':5},json.dumps({'code':''}),variant,True)
            counts=r.get('counts',{});valid=counts.get('run')==5
            if name=='original': ok=valid and counts.get('failures')==2 and counts.get('errors')==1
            elif name=='fixed': ok=valid and counts.get('failures')==0 and counts.get('errors')==0
            else: ok=valid and counts.get('failures',0)>0 and counts.get('errors')==0
            records[name]={'check_passed':ok,**r};passed+=int(ok)
        return {'score':passed/len(records),'success':passed==len(records),'mutation_checks':records,
                'note':'Generated tests must pass fixed code and detect seeded clock, eviction, boundary and update defects. Original must produce exactly five tests: 2 pass, 2 fail, 1 error.'}
    if task['kind']=='review':
        expected=['error','fail','fail','pass','pass']; categories={'constructor_shadowing','frozen_clock','eviction_before_expiry'}
        outcomes=obj.get('outcomes',[]); defects=obj.get('defects',[])
        actual={x.get('category') for x in defects if isinstance(x,dict)}
        correct=sum(a==b for a,b in zip(outcomes,expected)) if isinstance(outcomes,list) and len(outcomes)==5 else 0
        # Each expected defect earns a point; false positives each remove a point.
        points=correct+len(actual&categories)-len(actual-categories)
        return {'score':max(0,points)/8,'success':outcomes==expected and actual==categories,
                'outcomes_correct':correct,'expected_outcomes':expected,'actual_outcomes':outcomes,
                'expected_defects':sorted(categories),'actual_defects':sorted(str(x) for x in actual),
                'note':'Structured classification score; explanations retained for human audit, not semantically graded.'}
    if not allow_code: return {'score':None,'success':False,'error':'code execution not enabled'}
    code=obj.get('code')
    if not isinstance(code,str): return {'score':0,'success':False,'error':'missing code string'}
    directory.mkdir(parents=True,exist_ok=True)
    (directory/'solution.py').write_text(code)
    (directory/'test_solution.py').write_text(task['tests'])
    # Trusted runner always exits with structured counts; generated module is NOT a security sandbox.
    runner='''import sys, json, unittest
sys.path.insert(0, sys.argv[1])
suite=unittest.defaultTestLoader.discover(sys.argv[1],pattern="test_solution.py")
r=unittest.TextTestRunner(verbosity=2).run(suite)
print("BENCH_RESULT="+json.dumps({"run":r.testsRun,"failures":len(r.failures),"errors":len(r.errors)}))
'''
    (directory/'runner.py').write_text(runner)
    try:
        p=subprocess.run([sys.executable,'-I',str(directory/'runner.py'),str(directory)],
                         cwd=directory,capture_output=True,text=True,timeout=20)
        (directory/'runner_output.txt').write_text(p.stdout+p.stderr)
        lines=[x for x in p.stdout.splitlines() if x.startswith('BENCH_RESULT=')]
        if not lines: raise RuntimeError('runner produced no counts: '+(p.stderr+p.stdout)[-1500:])
        counts=json.loads(lines[-1].split('=',1)[1]); n=counts['run']
        passed=n-counts['failures']-counts['errors']
        return {'score':passed/n if n else 0,'success':n==task.get('test_count',6) and passed==n,'counts':counts,
                'runner_exit_code':p.returncode,'runner_output':p.stdout+p.stderr}
    except Exception as e: return {'score':0,'success':False,'error':str(e)}

def run_trial(scenario, task_id, rep, settings, directory, allow_code):
    directory.mkdir(parents=True,exist_ok=True); task=TASKS[task_id]
    start=time.perf_counter(); calls=[]
    result={'scenario':scenario['id'],'task':task_id,'repeat':rep,'architecture':scenario['architecture']}
    try:
        producer=scenario['endpoints'][rep%len(scenario['endpoints'])] if scenario['architecture']=='independent_pool' else scenario['endpoints'][0]
        messages=[{'role':'system','content':'Follow the task exactly. Output valid JSON only in your final answer. Do not include markdown fences.'},
                  {'role':'user','content':task['prompt']}]
        first=chat(producer,messages,settings); calls.append(first)
        final=first['content']
        if scenario.get('workflow')=='review_revise':
            reviewer=scenario['endpoints'][1]
            critique=chat(reviewer,[messages[0],{'role':'user','content':task['prompt']+'\nCandidate answer:\n'+final+'\nReview independently. Return JSON {"issues": [...], "suggestions": [...]}. Do not assume the candidate is correct.'}],settings)
            calls.append(critique)
            revised=chat(producer,messages+[{'role':'assistant','content':final},{'role':'user','content':'Independent review:\n'+critique['content']+'\nReturn your final corrected answer in the ORIGINAL requested JSON format. Verify the review rather than blindly accepting it.'}],settings)
            calls.append(revised); final=revised['content']
        result['grade']=grade(task,final,directory/'execution',allow_code)
    except Exception as e: result['grade']={'score':0,'success':False,'error':str(e)}; result['infrastructure_error']=True
    result.update({'duration_s':time.perf_counter()-start,'calls':calls,
                   'completion_tokens':sum(c['usage'].get('completion_tokens',0) or 0 for c in calls),
                   'tokens_known':bool(calls) and all('completion_tokens' in c['usage'] for c in calls),
                   'ttft_s':calls[0]['ttft_s'] if calls else None,
                   'first_content_s':calls[0]['first_content_s'] if calls else None})
    save(directory/'result.json',result); return result

# Optional read-only SSH telemetry: command source is bundled, not model-supplied.
MONITOR = '''import json,time,subprocess,pathlib
while True:
 d={"unix_time":time.time()}
 try:
  p=subprocess.run(["nvidia-smi","--query-gpu=memory.used,utilization.gpu,power.draw,temperature.gpu","--format=csv,noheader,nounits"],capture_output=True,text=True,timeout=4)
  d["gpu_csv"]=p.stdout.strip();d["gpu_error"]=p.stderr.strip()
 except Exception as e:d["gpu_error"]=str(e)
 for name in ("tailscale0",):
  try:
   base=pathlib.Path("/sys/class/net")/name/"statistics"
   d[name]={k:int((base/k).read_text()) for k in ("rx_bytes","tx_bytes")}
  except Exception as e:d[name]={"error":str(e)}
 print(json.dumps(d),flush=True);time.sleep(1)
'''

def telemetry_start(nodes, directory):
    procs=[]
    for node in nodes:
        if not node.get('ssh'): continue
        f=(directory/(node['id']+'-telemetry.jsonl')).open('a')
        err=(directory/(node['id']+'-telemetry.stderr')).open('a')
        p=subprocess.Popen(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=5',node['ssh'],'python3 -u -'],stdin=subprocess.PIPE,stdout=f,stderr=err,text=True)
        p.stdin.write(MONITOR);p.stdin.close();procs.append((p,f,err))
    return procs

def telemetry_stop(procs):
    for p,f,err in procs:
        p.terminate()
        try:p.wait(timeout=5)
        except subprocess.TimeoutExpired:p.kill();p.wait()
        f.close();err.close()

def telemetry_summary(directory):
    out={}
    for p in directory.glob('*-telemetry.jsonl'):
        samples=[]
        for line in p.read_text().splitlines():
            try:samples.append(json.loads(line))
            except ValueError:pass
        mem=[];util=[];power=[];rx=tx=0
        for s in samples:
            for row in s.get('gpu_csv','').splitlines():
                try:
                    a,b,c,d=[float(x.strip()) for x in row.split(',')];mem.append(a);util.append(b);power.append(c)
                except ValueError:pass
        for a,b in zip(samples,samples[1:]):
            aa=a.get('tailscale0',{});bb=b.get('tailscale0',{})
            rx+=max(0,bb.get('rx_bytes',0)-aa.get('rx_bytes',0));tx+=max(0,bb.get('tx_bytes',0)-aa.get('tx_bytes',0))
        out[p.stem]={'samples':len(samples),'peak_vram_mib':max(mem) if mem else None,
                    'mean_gpu_util_pct':statistics.mean(util) if util else None,
                    'mean_power_w':statistics.mean(power) if power else None,'rx_bytes':rx,'tx_bytes':tx}
    return out

def percentile(values,q):
    values=sorted(x for x in values if x is not None)
    return values[min(len(values)-1,math.ceil(q*len(values))-1)] if values else None

def wilson(k,n):
    if not n:return [0,1]
    z=1.96;p=k/n;den=1+z*z/n;mid=(p+z*z/(2*n))/den
    half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
    return [max(0,mid-half),min(1,mid+half)]

def generate_report(run_dir):
    manifest=json.loads((run_dir/'manifest.json').read_text()); rows=[]; summaries=[]
    for sc in manifest['scenarios']:
        sid=sc['id']; results=[]
        for p in (run_dir/sid).glob('trials/*/result.json'): results.append(json.loads(p.read_text()))
        loadpath=run_dir/sid/'load.json'; load=json.loads(loadpath.read_text()) if loadpath.exists() else {}
        n=len(results);k=sum(x['grade']['success'] for x in results)
        errorpath=run_dir/sid/'scenario_error.json'
        scenario_error=json.loads(errorpath.read_text()) if errorpath.exists() else None
        summary={'scenario_error':scenario_error,'scenario':sid,'architecture':sc['architecture'],'label':sc['label'],'trials':n,'successes':k,
                 'success_rate':k/n if n else None,'success_ci95':wilson(k,n),
                 'mean_score':statistics.mean(x['grade']['score'] or 0 for x in results) if n else None,
                 'median_task_s':percentile([x['duration_s'] for x in results],.5),
                 'p95_task_s':percentile([x['duration_s'] for x in results],.95),
                 'median_ttft_s':percentile([x['ttft_s'] for x in results],.5),
                 'median_first_content_s':percentile([x['first_content_s'] for x in results],.5),
                 'infrastructure_errors':sum(bool(x.get('infrastructure_error')) for x in results),
                 'load':load,'telemetry':telemetry_summary(run_dir/sid)}
        summaries.append(summary)
        for r in results:
            rows.append({'scenario':sid,'task':r['task'],'repeat':r['repeat'],'success':r['grade']['success'],
                         'score':r['grade']['score'],'duration_s':r['duration_s'],'ttft_s':r['ttft_s'],
                         'first_content_s':r['first_content_s'],'completion_tokens':r['completion_tokens'] if r['tokens_known'] else '',
                         'error':r['grade'].get('error','')})
    save(run_dir/'summary.json',summaries)
    with (run_dir/'trials.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]) if rows else ['scenario']);writer.writeheader();writer.writerows(rows)
    fmt=lambda v:'—' if v is None else f'{v:.2f}'
    md=['# GPU architecture benchmark',f'Run: {manifest["created"]} · Harness {VERSION}',
        '\n## Measured comparison',
        '| Configuration | Architecture | Success | Mean check score | Task median / p95 (s) | First text / answer median (s) |',
        '|---|---|---:|---:|---:|---:|']
    for s in summaries:
        md.append(f'| {s["label"]} | {s["architecture"]} | {s["successes"]}/{s["trials"]} | {fmt(s["mean_score"])} | {fmt(s["median_task_s"])} / {fmt(s["p95_task_s"])} | {fmt(s["median_ttft_s"])} / {fmt(s["median_first_content_s"])} |')
    md+=['\n## Concurrency and throughput','| Configuration | Clients | Completed / attempted | Requests/min | Reported output tokens/s | p95 first text (s) |','|---|---:|---:|---:|---:|---:|']
    for s in summaries:
        for l in s['load'].get('levels',[]):
            md.append(f'| {s["label"]} | {l["concurrency"]} | {l["completed"]}/{l["attempted"]} | {fmt(l["requests_per_min"])} | {fmt(l["output_tokens_per_s"])} | {fmt(l["p95_ttft_s"])} |')
    md+=['\n## Interpretation and limits',
      '- Success means all independent checks for a task passed; a correct partial answer is not a task success.',
      '- Review uses a synthetic version of the TTL defects, not your original files. Coding uses six independent unittest checks per task. Generated regression tests are scored against the original, a fixed implementation and four isolated mutations. No model self-reported counts are trusted.',
      '- First text includes reasoning; first answer excludes reasoning. These are client-observed times from request start, including queue/network delay, and SSE chunks can contain multiple tokens.',
      '- Throughput tokens come only from server-reported usage and include reasoning when the server counts it. Missing counts remain missing; characters are never called tokens.',
      '- Task time includes all model calls and grading. Collaborating agents use producer → reviewer → producer; parallel-independent load uses round-robin routing across endpoints.',
      '- Model/quantization changes confound architecture comparisons. Use the same file/settings on one GPU and RPC to isolate transport; compare IQ3 single versus Q5 RPC separately as a capacity-enabled quality comparison.',
      '- Requests include unique trial markers, but shared prefix caches may remain warm. This is an application benchmark, not a guaranteed cold-prefill benchmark. Warmup is excluded.',
      '- GPU/network samples cover each scenario, including warmup and load tests. Tailscale counters include all traffic on that interface, not RPC-only traffic; do not add both hosts and call it unique transferred bytes.',
      '- No energy estimate is produced from sparse samples. GPU power is not wall-system power. No claim about a network bottleneck follows from bandwidth alone.',
      '- Small samples have wide uncertainty; repeated tasks are correlated and confidence intervals are descriptive, not proof of general coding reliability.',
      '- This controlled harness is not OpenCode: it tests model review/coding and artifact exchange, not unrestricted editor tools, web search, or whole-repository coding.',
      '- Server availability or setup failures remain in the evidence. Unmeasured configurations have no invented numbers.',
      '\n## Per-configuration evidence']
    for s in summaries:
        md += [f'\n### {s["label"]}',f'Success 95% Wilson interval: {s["success_ci95"][0]:.1%}–{s["success_ci95"][1]:.1%}; infrastructure errors: {s["infrastructure_errors"]}.',
               'Telemetry: `'+json.dumps(s['telemetry'])+'`', 'Setup error: '+str(s['scenario_error']) if s['scenario_error'] else 'Setup completed.']
    text='\n'.join(md)+'\n';(run_dir/'report.md').write_text(text)
    # Fully offline, print-friendly report with explicit units, no external scripts.
    body='<h1>GPU architecture benchmark</h1><p>'+html.escape(manifest['created'])+'</p>'
    body+='<p>Observed task correctness, latency and concurrency. Unmeasured scenarios are not estimates.</p>'
    body+='<table><tr><th>Configuration</th><th>Architecture</th><th>Success</th><th>Task median / p95 seconds</th><th>First text / answer seconds</th></tr>'
    for s in summaries:
        body+='<tr>'+''.join('<td>'+html.escape(str(v))+'</td>' for v in [s['label'],s['architecture'],f'{s["successes"]}/{s["trials"]}',fmt(s['median_task_s'])+' / '+fmt(s['p95_task_s']),fmt(s['median_ttft_s'])+' / '+fmt(s['median_first_content_s'])])+'</tr>'
    body+='</table><h2>Throughput under concurrency</h2><table><tr><th>Configuration</th><th>Clients</th><th>Completed</th><th>Requests/min</th><th>Output tokens/s</th></tr>'
    for s in summaries:
        for l in s['load'].get('levels',[]):
            body+='<tr>'+''.join('<td>'+html.escape(str(v))+'</td>' for v in [s['label'],l['concurrency'],f'{l["completed"]}/{l["attempted"]}',fmt(l['requests_per_min']),fmt(l['output_tokens_per_s'])])+'</tr>'
    body+='</table><h2>Methods, caveats and evidence</h2><pre>'+html.escape(text)+'</pre>'
    (run_dir/'report.html').write_text('<!doctype html><meta charset="utf-8"><title>GPU benchmark</title><style>body{font:16px system-ui;margin:40px auto;max-width:1150px;padding:20px;color:#172b3a}table{border-collapse:collapse;width:100%;margin:24px 0}td,th{padding:12px;border-bottom:1px solid #ccd4dc;text-align:left}th{background:#eaf1f7}pre{white-space:pre-wrap;font:13px ui-monospace}h1{color:#123b65}@media print{body{margin:0;font-size:11px}tr{break-inside:avoid}}</style>'+body)
    return summaries

def load_test(sc,settings,directory):
    levels=[]
    for concurrency in settings.get('concurrency',[1,2,4]):
        n=max(concurrency,settings.get('load_requests_per_level',4));start=time.perf_counter()
        def one(i):
            ep=sc['endpoints'][i%len(sc['endpoints'])]
            try:
                result=chat(ep,[{'role':'user','content':f'Benchmark marker {sc["id"]}-{concurrency}-{i}. Explain how a Python dictionary differs from a list in 150 words.'}],dict(settings,max_tokens=settings.get('load_max_tokens',256)))
                return result
            except Exception as e:return {'error':str(e)}
        with cf.ThreadPoolExecutor(max_workers=concurrency) as pool: results=list(pool.map(one,range(n)))
        duration=time.perf_counter()-start;ok=[r for r in results if 'error' not in r]
        known=bool(ok) and all('completion_tokens' in r['usage'] for r in ok)
        levels.append({'concurrency':concurrency,'attempted':n,'completed':len(ok),'duration_s':duration,
                       'requests_per_min':len(ok)*60/duration,
                       'output_tokens_per_s':sum(r['usage'].get('completion_tokens',0) for r in ok)/duration if known else None,
                       'p95_ttft_s':percentile([r['ttft_s'] for r in ok],.95),'requests':results})
        save(directory/'load.json',{'levels':levels,'complete':False})
    save(directory/'load.json',{'levels':levels,'complete':True})
    return {'levels':levels,'complete':True}

def run_hook(hook,timeout):
    if hook:
        # Explicitly configured trusted argv, never inferred process kills or model commands.
        subprocess.run(hook,check=True,timeout=timeout)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',default=str(ROOT/'config.json'))
    p.add_argument('--output',default=str(ROOT/'runs'))
    p.add_argument('--resume',type=pathlib.Path)
    p.add_argument('--report-only',type=pathlib.Path)
    p.add_argument('--allow-code-execution',action='store_true')
    p.add_argument('--scenario',action='append')
    args=p.parse_args()
    if args.report_only:
        generate_report(args.report_only);print(args.report_only/'report.html');return
    config=json.loads(pathlib.Path(args.config).read_text());settings=config['settings']
    scenarios=[s for s in config['scenarios'] if s.get('enabled',True) and (not args.scenario or s['id'] in args.scenario)]
    if not scenarios: p.error('no scenarios selected')
    if any(TASKS[t]['kind'] in ('code','regression') for t in settings['tasks']) and not args.allow_code_execution:
        p.error('Coding tasks execute generated Python. Use a disposable OS/container and --allow-code-execution, or select only ttl_review in config.')
    directory=args.resume or pathlib.Path(args.output)/datetime.now().strftime('%Y%m%d-%H%M%S')
    directory.mkdir(parents=True,exist_ok=True)
    public_config=json.loads(json.dumps(config))
    # Only environment VARIABLE NAMES are configured for keys, never key values.
    manifest={'version':VERSION,'created':datetime.now(timezone.utc).isoformat(),'config':public_config,'scenarios':scenarios,
              'client':{'python':sys.version,'platform':sys.platform},
              'suite_sha256':hashlib.sha256(json.dumps(TASKS,sort_keys=True).encode()).hexdigest()}
    if args.resume and (directory/'manifest.json').exists():
        old=json.loads((directory/'manifest.json').read_text())
        if old['suite_sha256']!=manifest['suite_sha256'] or old['config']!=public_config: p.error('resume requires identical suite and configuration')
        manifest=old;scenarios=old['scenarios']
    save(directory/'manifest.json',manifest)
    randomizer=random.Random(settings.get('seed',42))
    for sc in scenarios:
        d=directory/sc['id'];d.mkdir(exist_ok=True);procs=[]
        print('\nSCENARIO:',sc['label'],flush=True)
        try:
            run_hook(sc.get('setup_argv'),settings.get('setup_timeout_seconds',1800))
            identities=[]
            for ep in sc['endpoints']:
                identities.append({'endpoint':ep['url'],'models':get_json(ep['url'].rstrip('/')+'/models')})
            save(d/'server_identity.json',identities)
            for node in config.get('nodes',[]):
                if not node.get('ssh'): continue
                probe=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=5',node['ssh'],
                    'uname -a; nvidia-smi; git -C ~/inference/llama.cpp rev-parse HEAD; cat ~/inference/gpu-bench-managed/server.log 2>/dev/null | tail -n 80'],
                    capture_output=True,text=True,timeout=30)
                (d/(node['id']+'-environment.txt')).write_text(probe.stdout+probe.stderr)
            (d/'scenario_error.json').unlink(missing_ok=True)
            procs=telemetry_start(config.get('nodes',[]),d)
            if not args.resume:
                for ep in sc['endpoints']: chat(ep,[{'role':'user','content':'Reply with OK.'}],dict(settings,max_tokens=64))
            jobs=[(task,rep) for rep in range(settings.get('repeats',3)) for task in settings['tasks']];randomizer.shuffle(jobs)
            for task,rep in jobs:
                td=d/'trials'/f'{task}-{rep}'
                if (td/'result.json').exists(): continue
                # Unique suffix reduces exact request cache reuse without changing task semantics.
                original=TASKS[task]['prompt'];TASKS[task]['prompt']=original+f'\nTrial marker: {sc["id"]}/{rep}. This marker does not affect the task.'
                try:r=run_trial(sc,task,rep,settings,td,args.allow_code_execution)
                finally:TASKS[task]['prompt']=original
                print(task,rep,'PASS' if r['grade']['success'] else 'FAIL',f'{r["duration_s"]:.1f}s',flush=True)
                generate_report(directory)
            if not (d/'load.json').exists() or not json.loads((d/'load.json').read_text()).get('complete'):load_test(sc,settings,d)
        except Exception as e:
            save(d/'scenario_error.json',{'error':str(e)});print('Scenario unavailable:',e,flush=True)
        finally:
            telemetry_stop(procs)
            try:run_hook(sc.get('teardown_argv'),settings.get('setup_timeout_seconds',1800))
            except Exception as e:save(d/'teardown_error.json',{'error':str(e)})
            generate_report(directory)
    print('\nReport:',directory/'report.html',flush=True)

if __name__=='__main__':main()
