# Wiley DOI path extraction: 20 paired offline runs

Base: 745d09547e3b092f5c66e7d1915e455ffb90b797, existing integration PR6 head. This follow-up is based on PR6, not old main.

The current extractor returns everything after doi/, so Wiley's full/abs/pdf/epdf/pdfdirect path modes and URL tracking data become part of the DOI sent to the TDM API. The patch reads the URL path, removes a recognized view mode, decodes escaped path characters and returns a DOI-shaped identifier. Ordinary DOI paths, nested suffixes and missing DOI behavior are preserved; invalid paths return an empty string.

Observed publisher sources: https://onlinelibrary.wiley.com/doi/full/10.1002/wps.20617 (full path), https://onlinelibrary.wiley.com/library-info/resources/text-and-datamining (API takes the DOI, not full/DOI).

Each row executes the actual extractor AST in two fresh Python processes. Twelve cases cover direct path, five view modes, query/fragment, escaped separator, empty/missing/invalid paths, and nested DOI suffix. No API, model, token, database or network access in these tests; no live retrieval-quality claim.

Run: python3 -m unittest discover -s tests -p test_wiley_doi_paths.py -v (1 test with 12 subcases). Reproduce: python3 tests/prove_wiley_doi_paths.py.

| Run | Before exact DOI cases | After exact DOI cases | Before full URL | After full URL |
| --- | --- | --- | --- | --- |
| 1 | 4/12 | 12/12 | full/10.1002/wps.20617 | 10.1002/wps.20617 |
| 2 | 4/12 | 12/12 | full/10.1002/wps.20617 | 10.1002/wps.20617 |
| 3 | 4/12 | 12/12 | full/10.1002/wps.20617 | 10.1002/wps.20617 |
| 4 | 4/12 | 12/12 | full/10.1002/wps.20617 | 10.1002/wps.20617 |
| 5 | 4/12 | 12/12 | full/10.1002/wps.20617 | 10.1002/wps.20617 |
| 6 | 4/12 | 12/12 | full/10.1002/wps.20617 | 10.1002/wps.20617 |
| 7 | 4/12 | 12/12 | full/10.1002/wps.20617 | 10.1002/wps.20617 |
| 8 | 4/12 | 12/12 | full/10.1002/wps.20617 | 10.1002/wps.20617 |
| 9 | 4/12 | 12/12 | full/10.1002/wps.20617 | 10.1002/wps.20617 |
| 10 | 4/12 | 12/12 | full/10.1002/wps.20617 | 10.1002/wps.20617 |
| 11 | 4/12 | 12/12 | full/10.1002/wps.20617 | 10.1002/wps.20617 |
| 12 | 4/12 | 12/12 | full/10.1002/wps.20617 | 10.1002/wps.20617 |
| 13 | 4/12 | 12/12 | full/10.1002/wps.20617 | 10.1002/wps.20617 |
| 14 | 4/12 | 12/12 | full/10.1002/wps.20617 | 10.1002/wps.20617 |
| 15 | 4/12 | 12/12 | full/10.1002/wps.20617 | 10.1002/wps.20617 |
| 16 | 4/12 | 12/12 | full/10.1002/wps.20617 | 10.1002/wps.20617 |
| 17 | 4/12 | 12/12 | full/10.1002/wps.20617 | 10.1002/wps.20617 |
| 18 | 4/12 | 12/12 | full/10.1002/wps.20617 | 10.1002/wps.20617 |
| 19 | 4/12 | 12/12 | full/10.1002/wps.20617 | 10.1002/wps.20617 |
| 20 | 4/12 | 12/12 | full/10.1002/wps.20617 | 10.1002/wps.20617 |
