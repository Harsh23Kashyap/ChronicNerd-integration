import os, pathlib, sys, unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'dietnerd-backend'))
import main

class AnswerModeEndpointTest(unittest.TestCase):
 def setUp(self):
  main.app.dependency_overrides[main.current_user]=lambda:'owner@example.com';self.client=TestClient(main.app)
 def tearDown(self):main.app.dependency_overrides.clear()
 def test_rejects_unknown_mode(self):
  self.assertEqual(self.client.post('/process_query',json={'user_query':'q','temporary':True,'answer_mode':'untrusted'}).status_code,400)
 def test_heavy_skips_generic_cache(self):
  with patch.object(main,'query_db_final') as cache:
   r=self.client.post('/cached_answer',json={'user_query':'q','answer_mode':'heavy'})
  self.assertEqual(r.status_code,409);cache.assert_not_called()
 def test_temporary_heavy_remains_profile_free(self):
  with patch.dict(os.environ,{'OPENAI_API_KEY':'test'}),patch.object(main,'_run_research_with_key') as run:
   r=self.client.post('/process_query',json={'user_query':'q','temporary':True,'use_profile':True,'answer_mode':'heavy'})
  self.assertEqual(r.status_code,200,r.text)
  self.assertFalse(run.call_args.args[-2]);self.assertEqual(run.call_args.args[-1],'heavy')
  rid=r.json()['request_id']
  with main.request_event_lock:
   for table in (main.request_events,main.request_event_base,main.request_updated_at,main.request_created_at,main.request_owners):table.pop(rid,None)
 def test_heavy_includes_selected_pmid_after_relevance_filter(self):
  import pandas as pd
  article={'MedlineCitation':{'PMID':'12345'}}
  with patch.object(main,'get_session_memory',return_value=[]),patch.object(main,'check_attachment_exists',return_value=False),\
       patch.object(main,'get_diet_profile_prompt',return_value=''),patch.object(main,'get_profile_documents',return_value=[]),\
       patch.object(main,'query_generation',return_value=('q','q',['q'])),patch.object(main,'collect_articles',return_value=[]),\
       patch.object(main,'concurrent_relevance_classification',return_value=([],[])),\
       patch.object(main,'fetch_selected_pmid_articles',return_value=[article]) as selected,\
       patch.object(main,'connect_to_reliability_analysis_db',return_value=pd.DataFrame([{'x':1}])),\
       patch.object(main,'article_matching',return_value=([],[article])) as matching,\
       patch.object(main,'concurrent_article_processing',return_value=[]),\
       patch.object(main,'generate_final_response',return_value='Answer') as synthesis,\
       patch.object(main,'write_articles_to_db'),patch.object(main,'write_output_to_db'),\
       patch.object(main,'append_session_memory'),patch.object(main,'get_conversation_summary',return_value=''),\
       patch.object(main,'update_conversation_summary',return_value=''),patch.object(main,'set_conversation_summary'),patch.object(main,'send_update'):
   main.process_user_query('q','req','owner@example.com','conv',paper_context={'pmid':'12345','title':'Study','abstract':'Abstract','url':'https://pubmed.ncbi.nlm.nih.gov/12345/'},answer_mode='heavy')
  selected.assert_called_once_with('12345');self.assertEqual(matching.call_args.args[0],[article]);self.assertEqual(synthesis.call_args.kwargs['answer_mode'],'heavy')
 def test_light_does_not_fetch_selected_pmid_as_article(self):
  with patch.object(main,'get_session_memory',return_value=[]),patch.object(main,'get_diet_profile_prompt',return_value=''),\
       patch.object(main,'get_profile_documents',return_value=[]),patch.object(main,'check_attachment_exists',return_value=False),\
       patch.object(main,'fetch_selected_pmid_articles') as selected,patch.object(main,'try_answer_from_attachment',return_value=(True,'Paper answer',None)),\
       patch.object(main,'append_session_memory'),patch.object(main,'get_conversation_summary',return_value=''),\
       patch.object(main,'update_conversation_summary',return_value=''),patch.object(main,'set_conversation_summary'),patch.object(main,'send_update'):
   main.process_user_query('q','req','owner@example.com','conv',paper_context={'pmid':'12345','title':'Study','abstract':'Abstract','url':'https://pubmed.ncbi.nlm.nih.gov/12345/'},answer_mode='light')
  selected.assert_not_called()

class PersonalizedSynthesisRetryTest(unittest.TestCase):
 def test_missing_weight_triggers_one_synthesis_retry_without_retrieval_leak(self):
  import pandas as pd
  with patch.object(main,'get_session_memory',return_value=[]),patch.object(main,'check_attachment_exists',return_value=False),\
       patch.object(main,'get_diet_profile_prompt',return_value='goals: build muscle; weight 72 kg'),\
       patch.object(main,'get_profile_documents',return_value=[]),patch.object(main,'query_generation',return_value=('q','q',['q'])) as retrieval,\
       patch.object(main,'collect_articles',return_value=[]),patch.object(main,'concurrent_relevance_classification',return_value=([],[])),\
       patch.object(main,'connect_to_reliability_analysis_db',return_value=pd.DataFrame([{'x':1}])),\
       patch.object(main,'article_matching',return_value=([],[])),patch.object(main,'concurrent_article_processing',return_value=[]),\
       patch.object(main,'generate_final_response',side_effect=['generic answer','72 kg: 72 x 1.6 g/kg = 115.2 g/day']) as synth,\
       patch.object(main,'write_articles_to_db'),patch.object(main,'write_output_to_db'),patch.object(main,'append_session_memory'),\
       patch.object(main,'get_conversation_summary',return_value=''),patch.object(main,'update_conversation_summary',return_value=''),\
       patch.object(main,'set_conversation_summary'),patch.object(main,'send_update'):
   result=main.process_user_query('What daily protein range for my body weight? Show calculation.','req','owner@example.com','conv')
  self.assertEqual(synth.call_count,2);self.assertIn('72 kg',synth.call_args.args[1]);self.assertEqual(retrieval.call_count,1)
  self.assertNotIn('72 kg',str(retrieval.call_args));self.assertIn('72 kg',result['end_output'])
 def test_no_retry_when_answer_uses_weight(self):
  import pandas as pd
  with patch.object(main,'get_session_memory',return_value=[]),patch.object(main,'check_attachment_exists',return_value=False),\
       patch.object(main,'get_diet_profile_prompt',return_value='weight 72 kg'),patch.object(main,'get_profile_documents',return_value=[]),\
       patch.object(main,'query_generation',return_value=('q','q',['q'])),patch.object(main,'collect_articles',return_value=[]),\
       patch.object(main,'concurrent_relevance_classification',return_value=([],[])),\
       patch.object(main,'connect_to_reliability_analysis_db',return_value=pd.DataFrame([{'x':1}])),\
       patch.object(main,'article_matching',return_value=([],[])),patch.object(main,'concurrent_article_processing',return_value=[]),\
       patch.object(main,'generate_final_response',return_value='The 72 kg input needs evidence.') as synth,\
       patch.object(main,'write_articles_to_db'),patch.object(main,'write_output_to_db'),patch.object(main,'append_session_memory'),\
       patch.object(main,'get_conversation_summary',return_value=''),patch.object(main,'update_conversation_summary',return_value=''),\
       patch.object(main,'set_conversation_summary'),patch.object(main,'send_update'):
   main.process_user_query('What daily protein range for my weight?','req','owner@example.com','conv')
  self.assertEqual(synth.call_count,1)

class HeavyPDFSourceTest(unittest.TestCase):
 def test_user_pdf_is_labeled_unverified_and_kept_out_of_article_db(self):
  from heavy_sources import summarize_selected_pdf
  from unittest.mock import MagicMock
  client=MagicMock();client.chat.completions.create.return_value.choices=[MagicMock(message=MagicMock(content='Purpose and design: not reported.'))]
  result=summarize_selected_pdf('Text from paper', 'study.pdf', client)
  self.assertEqual(result['PMID'],None)
  self.assertIn('unverified',result['publication_type'].lower())
  self.assertIn('untrusted data',client.chat.completions.create.call_args.kwargs['messages'][0]['content'])
  self.assertEqual(result['url'],'')
 def test_heavy_pdf_does_not_short_circuit_to_attachment_answer(self):
  import pandas as pd
  with patch.object(main,'get_session_memory',return_value=[]),patch.object(main,'get_diet_profile_prompt',return_value=''),\
       patch.object(main,'get_profile_documents',return_value=[]),patch.object(main,'check_attachment_exists') as saved,\
       patch.object(main,'try_answer_from_attachment') as shortcut,patch.object(main,'query_generation',return_value=('q','q',['q'])),\
       patch.object(main,'collect_articles',return_value=[]),patch.object(main,'concurrent_relevance_classification',return_value=([],[])),\
       patch.object(main,'connect_to_reliability_analysis_db',return_value=pd.DataFrame([{'x':1}])),\
       patch.object(main,'article_matching',return_value=([],[])),patch.object(main,'concurrent_article_processing',return_value=[]),\
       patch.object(main,'summarize_selected_pdf',return_value={'title':'paper.pdf','publication_type':'User-supplied PDF (unverified)','summary':'Results','citation':'User-supplied PDF: paper.pdf (not independently verified)','PMID':None,'url':''}) as summarize,\
       patch.object(main,'generate_final_response',return_value='Answer') as synth,\
       patch.object(main,'write_articles_to_db'),patch.object(main,'write_output_to_db'),\
       patch.object(main,'append_session_memory'),patch.object(main,'get_conversation_summary',return_value=''),\
       patch.object(main,'update_conversation_summary',return_value=''),patch.object(main,'set_conversation_summary'),patch.object(main,'send_update'):
   main.process_user_query('q','req','owner@example.com','conv',temporary_attachment_context='Selected paper PDF: paper.pdf\nText',answer_mode='heavy')
  saved.assert_not_called();shortcut.assert_not_called()
  summarize.assert_called_once();self.assertEqual(synth.call_args.args[0], [])
  self.assertIn('Selected PDF (user-provided, unverified',synth.call_args.args[2])

class HeavyPromptContractTest(unittest.TestCase):
 def test_heavy_prompt_uses_v2_broad_source_synthesis_without_forced_citations(self):
  from unittest.mock import MagicMock
  import helper_functions as h
  old=h.client
  try:
   h.client=MagicMock()
   h.client.chat.completions.create.return_value.choices=[MagicMock(message=MagicMock(content="What we know\nOne finding.\n\nWhat we don't know\nLimits.\n\nWhat to ask a dietitian\nQuestion?"))]
   h.generate_final_response([], 'protein', answer_mode='heavy')
   instruction=h.client.chat.completions.create.call_args.kwargs['messages'][0]['content']
   self.assertIn('up to 20', instruction)
   self.assertIn('Do not invent studies',instruction)
   self.assertIn('study designs, human populations',instruction)
  finally:h.client=old

class PersonalizedArithmeticFallbackTest(unittest.TestCase):
 def test_model_generic_range_gets_safe_math_after_retry(self):
  import pandas as pd
  answer="What we know\nGeneral range 1.2 to 2.0 grams of protein per kilogram of body weight for adults.\n\nWhat we don't know\nNot a personal target.\n\nWhat to ask a dietitian\nWhat factors matter?"
  with patch.object(main,'get_session_memory',return_value=[]),patch.object(main,'check_attachment_exists',return_value=False),\
       patch.object(main,'get_diet_profile_prompt',return_value='weight 72 kg'),patch.object(main,'get_profile_documents',return_value=[]),\
       patch.object(main,'query_generation',return_value=('q','q',['q'])) as retrieval,patch.object(main,'collect_articles',return_value=[]),\
       patch.object(main,'concurrent_relevance_classification',return_value=([],[])),\
       patch.object(main,'connect_to_reliability_analysis_db',return_value=pd.DataFrame([{'x':1}])),\
       patch.object(main,'article_matching',return_value=([],[])),patch.object(main,'concurrent_article_processing',return_value=[]),\
       patch.object(main,'generate_final_response',side_effect=[answer,answer]) as synth,\
       patch.object(main,'write_articles_to_db'),patch.object(main,'write_output_to_db'),patch.object(main,'append_session_memory'),\
       patch.object(main,'get_conversation_summary',return_value=''),patch.object(main,'update_conversation_summary',return_value=''),\
       patch.object(main,'set_conversation_summary'),patch.object(main,'send_update'):
   result=main.process_user_query('What daily protein range for my body weight? Show calculation.','req','owner@example.com','conv')
  self.assertEqual(synth.call_count,2)
  self.assertIn('72 × 1.2 = 86.4 g/day',result['end_output'])
  self.assertIn('72 × 2.0 = 144 g/day',result['end_output'])
  self.assertIn('not an individualized recommendation',result['end_output'])
  self.assertEqual(retrieval.call_count,1)
  self.assertNotIn('72',str(retrieval.call_args))

class HeavyPersonalizationTest(unittest.TestCase):
 def test_heavy_retries_if_weight_present_but_daily_math_missing(self):
  import pandas as pd
  with patch.object(main,'get_session_memory',return_value=[]),patch.object(main,'check_attachment_exists',return_value=False),\
       patch.object(main,'get_diet_profile_prompt',return_value='additional notes: weight 72 kg; height 175 cm'),\
       patch.object(main,'get_profile_documents',return_value=[]),patch.object(main,'query_generation',return_value=('q','q',['q'])),\
       patch.object(main,'collect_articles',return_value=[]),patch.object(main,'concurrent_relevance_classification',return_value=([],[])),\
       patch.object(main,'connect_to_reliability_analysis_db',return_value=pd.DataFrame([{'x':1}])),\
       patch.object(main,'article_matching',return_value=([],[])),patch.object(main,'concurrent_article_processing',return_value=[]),\
       patch.object(main,'generate_final_response',side_effect=['Protein for a 72 kg person may be 1.6 g/kg/day.','For 72 kg, 72 x 1.6 = 115.2 g/day.']) as synthesis,\
       patch.object(main,'write_articles_to_db'),patch.object(main,'write_output_to_db'),patch.object(main,'append_session_memory'),\
       patch.object(main,'get_conversation_summary',return_value=''),patch.object(main,'update_conversation_summary',return_value=''),\
       patch.object(main,'set_conversation_summary'),patch.object(main,'send_update'):
   result=main.process_user_query('Protein for muscle with my weight?','req','owner@example.com','conv',answer_mode='heavy')
  self.assertEqual(synthesis.call_count,2)
  self.assertIn('115.2 g/day',result['end_output'])
