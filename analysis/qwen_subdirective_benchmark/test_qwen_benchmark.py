import importlib.util, json, tempfile, unittest
from pathlib import Path
P=Path(__file__).with_name('qwen_benchmark.py'); spec=importlib.util.spec_from_file_location('qb',P); qb=importlib.util.module_from_spec(spec); spec.loader.exec_module(qb)
class TestBenchmark(unittest.TestCase):
 def test_clean_removes_source_fields(self):
  self.assertEqual(qb.clean({'evidence':'x','text':'y','labels':{},'keep':{'evidence_end':2,'v':1}}),{'keep':{'v':1}})
 def test_answer(self): self.assertEqual(qb.parse_answer('thinking {"code": 3, "rationale":"x"}')[0],3)
 def test_prompt_has_no_evidence(self): self.assertNotIn('evidence',qb.prompt_for({'operative_functions':[{'function_id':'x','evidence':'secret'}]},['x']))
 def test_prepared_alignment_count(self):
  self.assertEqual(len(json.loads((qb.OUT/'blind_requests.json').read_text())),172)
 def test_response_cache_is_terminal_only(self):
  with tempfile.TemporaryDirectory() as d:
   old=qb.OUT; qb.OUT=Path(d)
   try:
    qb.append_response({'target_id':'a','seed':1,'terminal':True})
    qb.append_response({'target_id':'b','seed':1,'terminal':False})
    self.assertEqual({(x['target_id'],x['seed']) for x in qb.responses() if x.get('terminal')},{('a',1)})
   finally: qb.OUT=old
 def test_metrics_and_consensus_tie_rule(self):
  rows=[{'gold_code':1,'prediction':1},{'gold_code':2,'prediction':1}]
  self.assertEqual(qb.metrics(rows)['accuracy'],.5)
  votes=[0,2,4]; counts=__import__('collections').Counter(votes); winners=[c for c,n in counts.items() if n==max(counts.values())]
  self.assertEqual(sorted(winners)[len(winners)//2],2)
