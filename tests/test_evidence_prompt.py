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
        self.assertIn('do not directly compare', output)
        self.assertIn('cannot establish which option is better', output)
        self.assertNotIn('References:', output)

    def test_when_both_diets_retrieved_model_must_acknowledge_evidence_limits(self):
        articles = [{'title': 'Mediterranean versus low-carbohydrate diet in CKD'}]
        reply = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='What we know\nDirect comparison in this study only.\n\nWhat we don\'t know\nThe evidence is limited.\n\nWhat to ask a dietitian\nDoes it fit me?'))])
        with patch.object(h.client.chat.completions, 'create', return_value=reply) as create:
            output = h.generate_final_response(articles, 'Compare Mediterranean and low-carbohydrate diets for a person with CKD.')
        system = create.call_args.kwargs['messages'][0]['content']
        self.assertIn('a comparison is not supported and stop there', system)
        self.assertIn('there is no minimum citation count', system)
        self.assertNotIn('choose at least 8 articles', system)
        self.assertIn('Direct comparison in this study only', output)

class AnswerShapeTest(unittest.TestCase):
    def test_freeform_recommendation_is_stopped(self):
        unsafe = 'You should take this supplement daily.'
        answer = h.enforce_three_part_answer(unsafe)
        self.assertNotIn(unsafe, answer)
        for heading in ('What we know', "What we don't know", 'What to ask a dietitian'):
            self.assertIn(heading, answer)

    def test_complete_three_part_answer_is_preserved(self):
        answer = 'What we know\nEvidence is limited.\n\nWhat we don\'t know\nNo direct trial.\n\nWhat to ask a dietitian\nIs this relevant?'
        self.assertEqual(h.enforce_three_part_answer(answer), answer)


if __name__ == '__main__':
    unittest.main()


class ComparisonGateTest(unittest.TestCase):
    def test_two_separate_arm_studies_must_not_support_a_head_to_head_claim(self):
        sources = [
            {'title': 'Mediterranean diet and CKD incidence'},
            {'title': 'Low-carbohydrate diets and diabetes management'},
        ]
        with patch.object(h.client.chat.completions, 'create') as create:
            answer = h.generate_final_response(sources, 'Compare Mediterranean diet and low-carbohydrate diet for CKD.')
        create.assert_not_called()
        self.assertIn('cannot rank or recommend', answer)
        self.assertNotIn('References', answer)

    def test_unparsed_comparison_has_no_false_pair(self):
        self.assertIsNone(h.extract_comparison_terms('Is the Mediterranean diet healthy?'))
        self.assertIsNone(h.extract_comparison_terms('Compare effectiveness, uncertainty, and safety. Cite the original studies.'))
        self.assertIsNone(h.extract_comparison_terms('Compare efficacy, risks, and benefits for probiotic use.'))
        self.assertIsNone(h.extract_comparison_terms('Compare effectiveness and safety for probiotic use.'))
        self.assertEqual(h.extract_comparison_terms('Which is better, Mediterranean or low-carb?'), ('mediterranean', 'low-carb'))
        self.assertEqual(h.extract_comparison_terms('Compare Mediterranean and low-carbohydrate diets for CKD'),
                         ('mediterranean', 'low-carbohydrate diets'))


class ComparisonSourceQualityTest(unittest.TestCase):
    def test_two_arms_in_unrelated_sentences_do_not_qualify(self):
        source = {'title': 'Nutrition review', 'abstract':
                  'The Mediterranean diet was reviewed for healthy adults. '
                  'A different study compared low-carbohydrate diets with usual care.'}
        self.assertFalse(h.article_directly_compares(source, 'mediterranean diet', 'low-carbohydrate diets'))

    def test_generated_summary_cannot_make_a_source_qualify(self):
        source = {'title': 'Mediterranean diet and CKD',
                  'summary': 'Compared Mediterranean and low-carbohydrate diets'}
        self.assertFalse(h.article_directly_compares(source, 'mediterranean', 'low-carbohydrate diets'))


class RawPubMedComparisonTest(unittest.TestCase):
    def test_cached_summary_does_not_hide_direct_comparison_in_original(self):
        original = [{'MedlineCitation': {'Article': {
            'ArticleTitle': 'Mediterranean versus low-carbohydrate diets',
            'Abstract': {'AbstractText': ['A randomized comparison of both diets.']}
        }}}]
        reply = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='What we know\nEvidence is limited.'))])
        with patch.object(h.client.chat.completions, 'create', return_value=reply) as create:
            h.generate_final_response([{'summary': 'A cached summary without original metadata'}],
                                      'Compare Mediterranean and low-carbohydrate diets',
                                      original_articles=original)
        self.assertEqual(create.call_count, 2)  # bounded structure-repair retry

    def test_comparison_does_not_qualify_from_generated_summary(self):
        source = {'title': 'Mediterranean diet and CKD', 'summary': 'Compared it with low carbohydrate diets'}
        self.assertFalse(h.article_directly_compares(source, 'mediterranean', 'low-carbohydrate diets'))

class HeavyStructureRepairTest(unittest.TestCase):
    def test_valid_three_part_answer_survives_ownline_headings(self):
        answer = "What we know\nSupported.\n\nWhat we don't know\nMissing.\n\nWhat to ask a dietitian\nWhat matters?"
        self.assertEqual(h.enforce_three_part_answer(answer), answer)
    def test_heavy_retries_shape_once_but_never_publishes_invalid_reply(self):
        from types import SimpleNamespace
        bad = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='Loose clinical advice'))])
        with patch.object(h.client.chat.completions, 'create', return_value=bad) as create:
            result = h.generate_final_response([], 'protein', answer_mode='heavy')
        self.assertEqual(create.call_count, 2)
        self.assertIn('could not be checked', result)
        self.assertNotIn('Loose clinical advice', result)
    def test_unlinked_author_year_retries_then_stops(self):
        from types import SimpleNamespace
        bare = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="What we know\nMorton et al., 2018 says X.\nWhat we don't know\nUnknown.\nWhat to ask a dietitian\nAsk?"))])
        with patch.object(h.client.chat.completions, 'create', return_value=bare) as create:
            result = h.generate_final_response([], 'protein')
        self.assertEqual(create.call_count, 2)
        self.assertIn('answer-structure check', result)
        self.assertNotIn('Morton et al.', result)
