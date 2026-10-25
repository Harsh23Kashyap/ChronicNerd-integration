"""Regression for poisoned cached analysis under a real, unrelated PMID.

Synthetic fixtures: no network/DB required. A title match is not evidence that a
saved model summary belongs to the fetched PubMed paper.
"""
import pathlib
import sys
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'dietnerd-backend'))
import main
from research_audit import assemble_heavy_sources, card, fresh_pubmed_metadata
from article_analysis import pubmed_abstract_fallback

PMID = '41723912'
TITLE = 'Resistance training partially restores age-related differences in skeletal muscle amino acid transporters'
ABSTRACT = 'Training increased lean leg mass. SNAT9<sub>M</sub> changed in older adults.'
POISON = '1. Purpose & Design: New drug XYZ treats chronic pain. N=150. ABC Pharmaceuticals.'

class FakeConnection:
    def cursor(self): return self
    def execute(self, sql, params): assert params == (PMID,)
    def fetchone(self):
        import json
        return (json.dumps({'PMID': PMID, 'summary': POISON, 'citation': 'Wrong drug trial'}),)
    def close(self): pass

class QuarantineTest(unittest.TestCase):
    def test_reference_endpoint_ignores_poison_and_preserves_original_row(self):
        client = TestClient(main.app)
        main.app.dependency_overrides[main.current_user] = lambda: 'test@example.com'
        try:
            fallback = {'title': TITLE,
                        'summary': '1. PubMed abstract (original source text):\nTraining increased lean leg mass.',
                        'url': f'https://pubmed.ncbi.nlm.nih.gov/{PMID}/',
                        'analysis_scope': 'PubMed abstract only; no full-text appraisal'}
            with patch.object(main, '_get_db_connection', return_value=FakeConnection()), \
                 patch('article_analysis.pubmed_abstract_fallback', return_value=fallback):
                result = client.get(f'/articles/{PMID}')
            self.assertEqual(result.status_code, 200, result.text)
            self.assertEqual(result.json()['analysis_scope'], fallback['analysis_scope'])
            self.assertNotIn('XYZ', result.text)
            self.assertNotIn('chronic pain', result.text)
            self.assertNotIn('ABC Pharmaceuticals', result.text)
        finally:
            main.app.dependency_overrides.clear()

    def test_heavy_assembly_disregards_poisoned_cached_summary(self):
        record = {'MedlineCitation': {'PMID': PMID, 'Article': {
            'ArticleTitle': TITLE,
            'Abstract': {'AbstractText': [ABSTRACT]},
            'PublicationTypeList': ['Randomized Controlled Trial']}}}
        cached = [{'PMID': PMID, 'title': TITLE, 'citation': 'Wrong drug trial',
                   'summary': POISON, 'url': f'https://pubmed.ncbi.nlm.nih.gov/{PMID}/'}]
        with patch('helper_functions.generate_ama_citation', return_value='Real authors. '+TITLE+'. 2026.'):
            rows = assemble_heavy_sources([record], cached)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['analysis_scope'], 'PubMed abstract only')
        self.assertNotIn('XYZ', str(rows))
        self.assertNotIn('chronic pain', str(rows))
        self.assertNotIn('ABC Pharmaceuticals', str(rows))
        evidence = card(rows[0])
        self.assertIn('PubMed abstract only', evidence['design'])
        self.assertNotIn('N=150', str(evidence))

    def test_short_selected_paper_answer_retains_verified_reference(self):
        from helper_functions import assemble_verified_references, enforce_heavy_answer
        answer = ("The PubMed abstract reports resistance training with protein supplementation "
                  "in young and older adults [1]. It does not mention drug XYZ.")
        result = enforce_heavy_answer(assemble_verified_references(
            answer, {1: {'citation': 'Lander E. Resistance training study. 2026.'}}))
        self.assertIn('References', result)
        self.assertIn('Lander E.', result)
        self.assertNotIn('could not be checked', result)

    def test_abstract_markup_is_plain_text_not_html(self):
        record = {'MedlineCitation': {'Article': {'Abstract': {
            'AbstractText': ['SNAT9<sub>M</sub> increased (p < 0.001); older (p < 0.05); &female; participants. <script>alert(1)</script>']}}}}
        text = fresh_pubmed_metadata(record)['abstract']
        self.assertIn('SNAT9M', text)
        self.assertIn('p < 0.001', text)
        self.assertIn('p < 0.05', text)
        self.assertNotIn('<sub>', text)
        self.assertNotIn('<script>', text)
        self.assertNotIn('&female;', text)

if __name__ == '__main__': unittest.main()
