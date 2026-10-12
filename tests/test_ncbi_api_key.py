"""E-utilities requests use the account's NCBI key, never publisher requests."""
import importlib
import os
import sys
import unittest
from unittest.mock import patch


class NCBIKeyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, 'dietnerd-backend')
        cls.h = importlib.import_module('helper_functions')

    def test_article_retrieval_sets_entrez_key(self):
        h = self.h
        prior = h.Entrez.api_key
        try:
            with patch.dict(os.environ, {'NCBI_API_KEY': 'test-ncbi-secret', 'ENTREZ_EMAIL': 'test@example.invalid'}), patch.object(h, 'exponential_backoff', side_effect=[[], []]) as backoff:
                with patch.object(h.Entrez, 'read', return_value={'IdList': []}):
                    self.assertEqual(h.article_retrieval('vitamin c'), [])
                    self.assertEqual(h.Entrez.api_key, 'test-ncbi-secret')
                    self.assertEqual(h.Entrez.email, 'test@example.invalid')
        finally:
            h.Entrez.api_key = prior
