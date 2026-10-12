"""Unit tests for the proposed per-query PubMed date ceiling; no network access."""
import json, pathlib, sys, unittest
from unittest.mock import patch
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'dietnerd-backend'))
import helper_functions as h
from datetime import date


def article(pmid, year, month, day, article_date=None):
    art = {'Journal': {'JournalIssue': {'PubDate': {'Year': str(year), 'Month': month, 'Day': str(day)}}}}
    if article_date is not None:
        art['ArticleDate'] = [{'Year': str(article_date[0]), 'Month': article_date[1], 'Day': str(article_date[2])}]
    return {'MedlineCitation': {'PMID': str(pmid), 'Article': art}}


class PubMedCutoffTest(unittest.TestCase):
    def retrieve(self, rows, cutoff='2020-12-31'):
        with patch.object(h, 'exponential_backoff', side_effect=[object(), object()]) as eb, \
             patch.object(h.Entrez, 'read', side_effect=[{'IdList': [str(i) for i in range(len(rows))]}, {'PubmedArticle': rows}]):
            result = h.article_retrieval('test query', retmax=10, max_publication_date=cutoff)
        return result, eb

    def test_entrez_search_gets_pdat_ceiling_and_no_lower_bound(self):
        with patch.object(h, 'exponential_backoff', side_effect=[object(), object()]) as eb, \
             patch.object(h.Entrez, 'read', side_effect=[{'IdList': ['1']}, {'PubmedArticle': []}]):
            h.article_retrieval('test query', max_publication_date='2020-12-31')
        kwargs = eb.call_args_list[0].kwargs
        self.assertEqual(len(eb.call_args_list), 2)
        self.assertEqual(kwargs['datetype'], 'pdat')
        self.assertEqual(kwargs['maxdate'], '2020/12/31')
        self.assertNotIn('mindate', kwargs)
        self.assertEqual(kwargs['term'], 'test query')

    def test_ceiling_inclusive_and_after_excluded(self):
        rows = [article('1', 2020, 'Dec', '31'), article('2', 2021, 'Jan', '1')]
        result, _ = self.retrieve(rows)
        self.assertEqual([str(x['MedlineCitation']['PMID']) for x in result], ['1'])

    def test_article_date_preferred_over_issue_date(self):
        rows = [article('1', 2021, 'Jan', '10', article_date=(2020, 'Dec', '31')),
                article('2', 2020, 'Dec', '31', article_date=(2021, 'Jan', '1'))]
        result, _ = self.retrieve(rows)
        self.assertEqual([str(x['MedlineCitation']['PMID']) for x in result], ['1'])

    def test_incomplete_or_invalid_dates_fail_closed(self):
        rows = [article('1', 2020, 'Dec', '31'), article('2', 2020, None, None), article('3', 2020, 'Foo', '32')]
        result, _ = self.retrieve(rows)
        self.assertEqual([str(x['MedlineCitation']['PMID']) for x in result], ['1'])


    def test_api_model_and_route_plumb_cutoff(self):
        main_source = (pathlib.Path(__file__).resolve().parents[1] / 'dietnerd-backend' / 'main.py').read_text()
        model = main_source.split('class QueryModel(BaseModel):', 1)[1].split('class AuthModel', 1)[0]
        self.assertIn('retrieval_cutoff_date: Optional[str] = None', model)
        self.assertIn('query.retrieval_cutoff_date', main_source)
        self.assertIn('max_publication_date=retrieval_cutoff_date', main_source)
        self.assertIn('@app.post("/process_query/evaluation")', main_source)
        route = main_source.split('@app.post("/process_query/evaluation")', 1)[1].split('@app.post(', 1)[0]
        self.assertIn('if not query.retrieval_cutoff_date', route)
        self.assertIn('Evaluation queries require retrieval_cutoff_date', route)
        self.assertIn('return await _start_query(background_tasks, query, email)', route)

    def test_all_benchmark_items_have_deterministic_cutoff_input(self):
        benchmark_path = pathlib.Path(__file__).resolve().parent / 'fixtures_benchmark.json'
        self.assertTrue(benchmark_path.is_file(), 'bundled benchmark fixture missing')
        benchmark = json.loads(benchmark_path.read_text())
        self.assertEqual(len(benchmark['items']), 2)
        self.assertEqual(benchmark['metadata']['status'], 'synthetic-test-fixture-only')
        self.assertIn('fictional', benchmark['metadata']['notice'])
        for item in benchmark['items']:
            pubdate = item.get('pubmed_article_date') or item.get('pubmed_journal_issue_pub_date')
            self.assertTrue(pubdate, item['id'])
            date.fromisoformat(pubdate)

    def test_iso_date_is_strict_format_and_calendar_valid(self):
        for value in ('2024-02-29', '2024-12-31'):
            self.assertTrue(h.strict_iso_date(value), value)
        for value in ('20240229', '2024-2-09', '2024-02-9', '2024-W09-4', '2024-02-30', None):
            self.assertFalse(h.strict_iso_date(value), value)

    def test_invalid_cutoff_rejected(self):
        with self.assertRaises(ValueError):
            h.article_retrieval('test query', max_publication_date='not-a-date')

    def test_collect_passes_date_ceiling_to_each_query(self):
        with patch.object(h, 'article_retrieval', return_value=[]) as retrieval:
            h.collect_articles(['one', 'two'], max_publication_date='2020-12-31')
        self.assertEqual(retrieval.call_count, 2)
        self.assertEqual([c.kwargs['max_publication_date'] for c in retrieval.call_args_list], ['2020-12-31', '2020-12-31'])


if __name__ == '__main__':
    unittest.main()
