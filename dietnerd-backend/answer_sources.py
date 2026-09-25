"""Per-answer citation links. Never infer an article solely from a bracket number."""
import re

HEADING = re.compile(r'(?im)^\s*(?:#{1,4}\s*)?(?:\*\*)?References?(?:\*\*)?:?\s*$')
REFERENCE = re.compile(r'^\s*(?:\[(\d+)\]|(\d+)\.)\s*(.+)$')


def extract_answer_sources(answer, citations=None, ledger=None):
    match = HEADING.search(answer or '')
    if not match:
        return []
    metadata = citations if isinstance(citations, dict) else {}
    rows = []
    for line in (answer or '')[match.end():].splitlines():
        if re.match(r'^\s*(?:DietNerd|ChronicNerd) is\b', line, re.I):
            break
        item = REFERENCE.match(line)
        if not item:
            continue
        number = int(item.group(1) or item.group(2))
        title = item.group(3).split('\nDietNerd is')[0].strip()[:400]
        if not title:
            continue
        url = ''
        # Match citation text as well as its number: metadata keys are usually
        # unnumbered, and an unrelated answer may reuse [1].
        normalize = lambda value: re.sub(r'\W+', ' ', value.casefold()).strip()
        normalized = normalize(title)
        for key, details in metadata.items():
            if not isinstance(key, str):
                continue
            other = normalize(re.sub(r'^\s*(?:\[\d+\]|\d+\.)\s*', '', key))
            if len(other) > 24 and (other in normalized or normalized in other) and isinstance(details, dict):
                url = details.get('URL') or ''
                break
        if not url:
            for claim in ledger or []:
                if (isinstance(claim, dict) and claim.get('citation_marker') == f'[{number}]'
                        and claim.get('source_url') and normalize(claim.get('source_title') or '') in normalized
                        and len(normalize(claim.get('source_title') or '')) > 12):
                    url = claim['source_url']
                    break
        if not re.match(r'^https://', str(url), re.I):
            pmid = re.search(r'\bPMID\s*:\s*(\d{1,12})\b', title, re.I)
            doi = re.search(r'\b(10\.\d{4,9}/[^\s,;<>]+)', title, re.I)
            url = (f'https://pubmed.ncbi.nlm.nih.gov/{pmid.group(1)}/' if pmid else
                   f'https://doi.org/{doi.group(1).rstrip(".)]")}' if doi else '')
        if number not in {row['number'] for row in rows}:
            rows.append({'number': number, 'title': title, 'url': url})
    return sorted(rows, key=lambda row: row['number'])
