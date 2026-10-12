"""Execute actual extractor without importing model/database clients."""
import ast
from pathlib import Path
import re
import unittest
SOURCE = Path(__file__).resolve().parents[1] / 'dietnerd-backend/helper_functions.py'
DOI = '10.1002/wps.20617'
CASES = [('https://onlinelibrary.wiley.com/doi/' + DOI, DOI)] + [
    ('https://onlinelibrary.wiley.com/doi/' + mode + '/' + DOI, DOI)
    for mode in ('full', 'abs', 'pdf', 'epdf', 'pdfdirect')] + [
    ('https://onlinelibrary.wiley.com/doi/full/' + DOI + '?tracking=1#section', DOI),
    ('https://onlinelibrary.wiley.com/doi/full/10.1002%2Fwps.20617', DOI),
    ('https://onlinelibrary.wiley.com/doi/', ''),
    ('https://onlinelibrary.wiley.com/other/' + DOI, ''),
    ('https://onlinelibrary.wiley.com/doi/full/not-a-doi', ''),
    ('https://onlinelibrary.wiley.com/doi/10.1002/nested/suffix', '10.1002/nested/suffix')]
def load_extract(source):
    node = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == 'extract_doi_wiley')
    ns = {'re': re}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(SOURCE), 'exec'), ns)
    return ns['extract_doi_wiley']
class WileyDOITests(unittest.TestCase):
    def test_url_paths(self):
        extract = load_extract(SOURCE.read_text())
        for url, expected in CASES:
            with self.subTest(url=url): self.assertEqual(extract(url), expected)
if __name__ == '__main__': unittest.main()
