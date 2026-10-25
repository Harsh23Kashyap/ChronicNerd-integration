"""Selected paper stays source 1 and leads the Heavy prompt, not general-range context."""
import pathlib,sys,unittest
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'dietnerd-backend'))
import helper_functions as h
class SelectedAnchorTest(unittest.TestCase):
 def test_selected_paper_first_and_extrapolation_labeled(self):
  selected={'PMID':'25169440','title':'Pasiakos protein review','citation':'Pasiakos et al. Protein review. 2014.','abstract':'Measured outcomes in adults.'}
  other={'PMID':'28698222','title':'Morton protein review','citation':'Morton et al. Protein review. 2018.','abstract':'Pooled dose-response.'}
  class Reply:
   choices=[type('Choice',(),{'message':type('Message',(),{'content':'Selected paper findings [1] are limited to measured outcomes.'})()})()]
  calls=[]
  def create(**kwargs): calls.append(kwargs);return Reply()
  with patch.object(h,'client') as mocked:
   mocked.chat.completions.create.side_effect=create
   h.generate_final_response([other,selected],'What does selected paper show?',answer_mode='heavy',selected_pmid='25169440')
  self.assertTrue(calls)
  system=calls[0]['messages'][0]['content'];user=calls[0]['messages'][1]['content']
  self.assertIn('selected source [1]',system)
  self.assertIn('1.6-2.2 g/kg',system)
  self.assertLess(user.index("'PMID': '25169440'"),user.index("'PMID': '28698222'"))
if __name__=='__main__':unittest.main()
