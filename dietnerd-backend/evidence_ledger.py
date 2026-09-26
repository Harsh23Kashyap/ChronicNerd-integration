"""Conservative provenance ledger for cited answer sentences.

A citation marker is not a verified support label. This module never upgrades a
model-generated assertion into evidence; it exposes exactly which source was
resolved and which checks still need a human or source-specific verifier.
"""
import re

REFERENCE_LINE = re.compile(r'^\s*(?:\[(\d+)\]|(\d+)\.)\s*(.+)$')
CITATION = re.compile(r'\[(\d+)\]')


def _clean(value):
    return re.sub(r'\W+', ' ', str(value or '').casefold()).strip()


def build_claim_evidence_ledger(answer, articles):
    """Return an auditable list; unresolved markers remain explicitly unresolved."""
    if not isinstance(answer, str) or not isinstance(articles, list):
        return []
    heading = re.search(r'(?im)^\s*(?:#{1,6}\s*)?References\s*:?\s*$', answer)
    main = answer[:heading.start()] if heading else answer
    references = answer[heading.end():] if heading else ''
    reference_lines = {}
    for line in references.splitlines():
        match = REFERENCE_LINE.match(line)
        if match:
            reference_lines[match.group(1) or match.group(2)] = match.group(3).strip()
    # Match a reference only if its exact article title is present uniquely.
    resolved = {}
    for number, text in reference_lines.items():
        normalized = _clean(text)
        matches = [article for article in articles if isinstance(article, dict)
                   and len(_clean(article.get('title'))) >= 12
                   and _clean(article.get('title')) in normalized]
        if len(matches) == 1:
            resolved[number] = matches[0]
    rows = []
    # Lines/bullets are deliberately kept whole. Sentence tokenization risks
    # detaching a citation from the clause it qualifies.
    for line in main.splitlines():
        line = line.strip().lstrip('*- ').strip()
        markers = list(dict.fromkeys(CITATION.findall(line)))
        if not markers or len(line) < 20:
            continue
        for number in markers:
            article = resolved.get(number)
            rows.append({
                'claim': line,
                'citation_marker': f'[{number}]',
                'source_title': str(article.get('title', '')) if article else None,
                'source_url': str(article.get('url', '')) if article else None,
                'population': None,
                'endpoint': None,
                'support_status': 'not independently verified' if article else 'source unresolved',
                'evidence_passage': None,
                'evidence_note': ('Source matched by title; passage and support not verified.' if article
                                  else 'Citation could not be matched uniquely to a retrieved source.'),
            })
    return rows
