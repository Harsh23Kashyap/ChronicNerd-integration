import pathlib, sys, unittest
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'dietnerd-backend'))
import helper_functions as h

class AnimalOnlyGuardTest(unittest.TestCase):
 def article(self,title,mesh=None,abstract='Outcome measured.'):
  row={'MedlineCitation':{'PMID':'123','Article':{'ArticleTitle':title,'Abstract':{'AbstractText':[abstract]}}}}
  if mesh is not None:row['MedlineCitation']['MeshHeadingList']=[{'DescriptorName':m} for m in mesh]
  return row
 def test_rat_title_is_rejected_without_llm_call(self):
  row=self.article('Effects of protein in rats fed a high-protein diet')
  with patch.object(h,'client') as client:
   self.assertEqual(h.relevance_classifier(row,'protein?')[:2],('123',False))
  client.chat.completions.create.assert_not_called()
 def test_mesh_animals_without_humans_rejected(self):
  self.assertTrue(h.is_animal_only_article(self.article('Protein diet intervention',mesh=['Animals','Rats'])))
 def test_mixed_human_and_animal_metadata_not_auto_rejected(self):
  self.assertFalse(h.is_animal_only_article(self.article('Comparative mechanism',mesh=['Animals','Humans'])))
 def test_human_study_with_rat_background_not_auto_rejected(self):
  self.assertFalse(h.is_animal_only_article(self.article('Human trial informed by work in rats',abstract='Participants were adults.')))
