"""Regression for sparse evidence in direct comparative health questions."""
import pathlib
import sys
import unittest
from unittest.mock import patch
from types import SimpleNamespace

BACKEND = pathlib.Path(__file__).resolve().parents[1] / 'dietnerd-backend'
sys.path.insert(0, str(BACKEND))
import helper_functions as h


class EvidencePromptTest(unittest.TestCase):
    def test_sparse_comparison_must_not_be_ranked_from_indirect_sources(self):
        articles = [
            {'title': 'Mediterranean diet and CKD incidence', 'citation': 'CKD incidence', 'summary': 'Observational prevention study'},
            {'title': 'Vitamin B12 in metformin users', 'citation': 'B12 monitoring', 'summary': 'No dietary comparison'},
        ]
        with patch.object(h.client.chat.completions, 'create') as create:
            output = h.generate_final_response(articles, 'Compare Mediterranean and low-carbohydrate diets for a person with CKD.')
        create.assert_not_called()
        self.assertIn('do not include a low-carbohydrate diet study', output)
        self.assertIn('cannot support a comparison', output)
        self.assertNotIn('References:', output)

    def test_when_both_diets_retrieved_model_must_acknowledge_evidence_limits(self):
        articles = [{'title': 'Mediterranean versus low-carbohydrate diet in CKD'}]
        reply = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='Direct comparison in this study only.'))])
        with patch.object(h.client.chat.completions, 'create', return_value=reply) as create:
            output = h.generate_final_response(articles, 'Compare Mediterranean and low-carbohydrate diets for a person with CKD.')
        system = create.call_args.kwargs['messages'][0]['content']
        self.assertIn('a comparison is not supported and stop there', system)
        self.assertIn('there is no minimum citation count', system)
        self.assertNotIn('choose at least 8 articles', system)
        self.assertIn('Direct comparison in this study only', output)

if __name__ == '__main__':
    unittest.main()
