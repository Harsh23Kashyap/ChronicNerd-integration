"""Broad-query source-link retry must never fabricate citations or point to a random first hit."""
import pathlib,sys,unittest
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'dietnerd-backend'))
import helper_functions as h

class HeavySourceLinkRetry(unittest.TestCase):
    def source(self, n):
        return {'PMID':str(23871889+n),'title':f'Coffee source {n}',
                'citation':f'Coffee author {n}. Study. 2026.',
                'abstract':f'Coffee research abstract {n} on risk endpoints.',
                'url':f'https://pubmed.ncbi.nlm.nih.gov/{23871889+n}/'}
    def run_responses(self, responses, selected=None):
        class Reply:
            def __init__(self,text):
                self.choices=[type('Choice',(),{'message':type('Message',(),{'content':text})()})()]
        calls=[]
        def create(**kwargs):
            calls.append(kwargs)
            return Reply(responses[len(calls)-1])
        with patch.object(h,'client') as client:
            client.chat.completions.create.side_effect=create
            answer=h.generate_final_response([self.source(i) for i in range(2)],
                    'What do coffee trials show about cardiovascular outcomes?',answer_mode='heavy',selected_pmid=selected)
        return answer,calls
    def test_broad_uses_small_retry_after_two_uncited_attempts(self):
        answer,calls=self.run_responses(['Research evidence could not be checked.']*3 + ['The source abstracts address coffee and endpoints [1].'])
        self.assertEqual(len(calls),4)
        self.assertIn('coffee and endpoints [1]',answer)
        self.assertIn('References\n[1] Coffee author 0.',answer)
        self.assertNotIn('could not produce a source-linked answer',answer)
    def test_broad_failure_does_not_select_arbitrary_first_pubmed(self):
        answer,calls=self.run_responses(['Research evidence could not be checked.']*4)
        self.assertEqual(len(calls),4)
        self.assertIn('after the verification retry',answer)
        self.assertNotIn('https://pubmed.ncbi.nlm.nih.gov/',answer)
    def test_selected_paper_keeps_specific_refusal_without_extra_retry(self):
        answer,calls=self.run_responses(['Research evidence could not be checked.']*3,selected='23871889')
        self.assertEqual(len(calls),3)
        self.assertIn('selected abstract: https://pubmed.ncbi.nlm.nih.gov/23871889/',answer)
if __name__=='__main__':unittest.main()
