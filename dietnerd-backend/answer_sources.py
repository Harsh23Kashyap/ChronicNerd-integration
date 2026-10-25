"""Per-answer citation links. Never infer an article solely from a bracket number."""
import re

HEADING = re.compile(r'(?im)^\s*(?:#{1,4}\s*)?(?:\*\*)?References?(?:\*\*)?:?\s*$')
REFERENCE = re.compile(r'^\s*(?:\[(\d+)\]|(\d+)\.)\s*(.+)$')


def extract_answer_sources(answer, citations=None, ledger=None, retrieved_articles=None):
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
        matched_pmid = ''
        summary_excerpt = ''
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
                candidate = str(details.get('PMID') or '')
                matched_pmid = candidate if re.fullmatch(r'\d{1,12}', candidate) else ''
                summary = details.get('Summary')
                if isinstance(summary, str):
                    section = re.search(r'(?ims)^\s*(?:\*\*)?2[.)]\s*Main Conclusions(?:\*\*)?\s*:?\s*(.*?)(?=^\s*(?:\*\*)?3[.)]|\Z)', summary)
                    if section:
                        summary_excerpt = re.sub(r'\s+', ' ', section.group(1)).strip(' *-')[:360]
                break
        if not url:
            for claim in ledger or []:
                if (isinstance(claim, dict) and claim.get('citation_marker') == f'[{number}]'
                        and claim.get('source_url') and normalize(claim.get('source_title') or '') in normalized
                        and len(normalize(claim.get('source_title') or '')) > 12):
                    url = claim['source_url']
                    break
        # Exact normalized title from a freshly retrieved PubMed record can
        # recover identity when the model has altered its long AMA citation.
        # Do not match by author/year, bracket number, substring or fuzzy score.
        if not re.match(r'^https://', str(url), re.I) and not matched_pmid:
            reference_text = normalize(title)
            candidates = []
            for article in retrieved_articles or []:
                if not isinstance(article, dict):
                    continue
                article_title = normalize(article.get('title') or '')
                pmid_candidate = str(article.get('PMID') or '')
                if len(article_title) < 24 or not re.fullmatch(r'\d{1,12}', pmid_candidate):
                    continue
                # Title must be a whole phrase in the reference, not an author
                # or topic substring; a reused title is ambiguous and withheld.
                if re.search(r'(?<!\w)' + re.escape(article_title) + r'(?!\w)', reference_text):
                    candidates.append(pmid_candidate)
            if len(set(candidates)) == 1:
                matched_pmid = candidates[0]
                url = f'https://pubmed.ncbi.nlm.nih.gov/{matched_pmid}/'
        if not re.match(r'^https://', str(url), re.I):
            pmid = re.search(r'\bPMID\s*:\s*(\d{1,12})\b', title, re.I)
            doi = re.search(r'\b(10\.\d{4,9}/[^\s,;<>]+)', title, re.I)
            url = (f'https://pubmed.ncbi.nlm.nih.gov/{pmid.group(1)}/' if pmid else
                   f'https://doi.org/{doi.group(1).rstrip(".)]")}' if doi else '')
        if number not in {row['number'] for row in rows}:
            pubmed = re.fullmatch(r'https://pubmed\.ncbi\.nlm\.nih\.gov/(\d{1,12})/?', str(url), re.I)
            rows.append({'number': number, 'title': title, 'url': url,
                         'pmid': matched_pmid or (pubmed.group(1) if pubmed else ''),
                         'summary_excerpt': summary_excerpt})
    return sorted(rows, key=lambda row: (not bool(row['pmid']), row['number']))


def recover_saved_source_links(answer, stored_sources, public_articles):
    """Fill missing links from uniquely matching cached PubMed titles, never cite support."""
    rows = stored_sources if isinstance(stored_sources, list) else []
    parsed = extract_answer_sources(answer)
    existing = {row.get('number'): row for row in rows if isinstance(row, dict)}
    by_number = {row['number']: row for row in parsed}
    result = []
    for number, citation in by_number.items():
        row = dict(existing.get(number) or citation)
        if not row.get('url'):
            normalized = re.sub(r'\W+', ' ', citation.get('title', '').casefold()).strip()
            candidates = set()
            for article in public_articles:
                title = re.sub(r'\W+', ' ', str(article.get('title') or '').casefold()).strip()
                pmid = str(article.get('PMID') or '')
                if len(title) < 24 or not re.fullmatch(r'\d{1,12}', pmid):
                    continue
                if re.search(r'(?<!\w)' + re.escape(title) + r'(?!\w)', normalized):
                    candidates.add(pmid)
            if len(candidates) == 1:
                row['pmid'] = next(iter(candidates))
                row['url'] = f"https://pubmed.ncbi.nlm.nih.gov/{row['pmid']}/"
        result.append(row)
    return result or rows
