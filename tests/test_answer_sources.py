import sys
import pathlib
import unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'dietnerd-backend'))
from answer_sources import extract_answer_sources

class AnswerSourcesTest(unittest.TestCase):
    def test_answer_specific_metadata_and_fallback(self):
        answer = 'Finding [1][2].\nReferences:\n[1] A Author. Specific trial of vitamin D. doi:10.1234/abc\n[2] B Author. Different trial. PMID: 12345\nDietNerd is an exploratory tool.'
        rows = extract_answer_sources(answer, {'[1] A Author. Specific trial of vitamin D. doi:10.1234/abc': {'URL':'https://pubmed.ncbi.nlm.nih.gov/456/'}})
        self.assertEqual([r['url'] for r in rows], ['https://pubmed.ncbi.nlm.nih.gov/456/', 'https://pubmed.ncbi.nlm.nih.gov/12345/'])
        self.assertNotIn('DietNerd', rows[-1]['title'])
    def test_pubmed_priority_and_conclusion_excerpt(self):
        answer = ('Finding [1][2].\nReferences:\n'
                  '[1] Doe. Dietary review. doi:10.1234/review\n'
                  '[2] Roe. Specific trial of vitamin D. PMID: 12345\n'
                  'DietNerd is an exploratory tool.')
        meta = {'[2] Roe. Specific trial of vitamin D. PMID: 12345': {
            'PMID': '12345', 'URL': 'https://pubmed.ncbi.nlm.nih.gov/12345/',
            'Summary': '1. Purpose & Design: Study\n2. Main Conclusions: Modest effect in adults.\n3. Risks: None reported.'}}
        rows = extract_answer_sources(answer, meta)
        self.assertEqual([row['number'] for row in rows], [2, 1])
        self.assertEqual(rows[0]['summary_excerpt'], 'Modest effect in adults.')
        self.assertEqual(rows[1]['summary_excerpt'], '')
        self.assertEqual(rows[1]['url'], 'https://doi.org/10.1234/review')

    def test_no_fabricated_source_from_markers(self):
        self.assertEqual(extract_answer_sources('Risk [1]. No source list.', {'[1] unrelated': {'URL':'https://example.com'}}), [])
    def test_unlinked_citation_is_honest(self):
        self.assertEqual(extract_answer_sources('Fact [1].\n### References\n[1] Smith. Study of food.')[0]['url'], '')

if __name__ == '__main__': unittest.main()
