"""The ledger must expose provenance gaps rather than inventing support."""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'dietnerd-backend'))
from evidence_ledger import build_claim_evidence_ledger


class LedgerTest(unittest.TestCase):
    def test_unique_title_match_is_still_unverified(self):
        source = {'title': 'Mediterranean diet and kidney health', 'url': 'https://pubmed.ncbi.nlm.nih.gov/123/',
                  'abstract': 'Unrelated to the claimed endpoint.'}
        answer = ('What we know\nThis diet improved renal outcomes [1].\n'
                  'References:\n[1] A Author. Mediterranean diet and kidney health. Journal.\n')
        row, = build_claim_evidence_ledger(answer, [source])
        self.assertEqual(row['source_url'], source['url'])
        self.assertEqual(row['support_status'], 'not independently verified')
        self.assertIsNone(row['evidence_passage'])
        self.assertIsNone(row['population'])

    def test_ambiguous_source_remains_unresolved(self):
        article = {'title': 'Mediterranean diet and kidney health'}
        answer = 'What we know\nThis diet improved renal outcomes [2].\nReferences:\n[2] Mediterranean diet and kidney health.'
        row, = build_claim_evidence_ledger(answer, [article, article])
        self.assertEqual(row['support_status'], 'source unresolved')
        self.assertIsNone(row['source_url'])

    def test_no_citations_means_no_ledger_claims(self):
        self.assertEqual(build_claim_evidence_ledger('What we do not know\nNo direct trial.', []), [])


if __name__ == '__main__':
    unittest.main()

def test_generated_markdown_reference_format_resolves_unique_source():
    source = {'title': 'Effect of micronutrient supplements on influenza and other respiratory tract infections among adults: a systematic review and meta-analysis.',
              'url': 'https://pubmed.ncbi.nlm.nih.gov/33472840/'}
    answer = ('### What we know\n- The source discusses respiratory infections [1].\n\n'
              '### References\n\n1. Abioye AI. Effect of micronutrient supplements on influenza and other respiratory tract infections among adults: a systematic review and meta-analysis. BMJ.\n')
    row, = build_claim_evidence_ledger(answer, [source])
    assert row['source_url'] == source['url']
    assert row['support_status'] == 'not independently verified'
    assert row['evidence_passage'] is None
