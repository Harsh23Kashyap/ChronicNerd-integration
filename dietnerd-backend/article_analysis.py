"""Truthful Article Analysis fallback for legacy cached model refusals.

This fetches the original PubMed abstract for the exact PMID. It never turns an
abstract into a full-text appraisal or treats a model refusal as findings.
"""
import re
import html
from Bio import Entrez

_REFUSAL = re.compile(r"no content provided|provide the details or text of the research paper|cannot (?:access|summari[sz]e) (?:this|the) (?:research )?paper", re.I)


def useful_summary(summary):
    text = str(summary or '').strip()
    return bool(text) and not _REFUSAL.search(text)


def pubmed_abstract_fallback(pmid, email=None, api_key=None):
    if not re.fullmatch(r'[0-9]{1,12}', str(pmid)):
        raise ValueError('Invalid PMID')
    if not email:
        raise RuntimeError('Entrez email is not configured')
    Entrez.email = email
    Entrez.api_key = api_key or None
    with Entrez.efetch(db='pubmed', id=str(pmid), rettype='medline', retmode='xml') as handle:
        records = Entrez.read(handle)
    for item in records.get('PubmedArticle', []):
        citation = item.get('MedlineCitation', {})
        if str(citation.get('PMID', '')) != str(pmid):
            continue
        article = citation.get('Article', {})
        abstract = article.get('Abstract', {}).get('AbstractText', [])
        parts = []
        for fragment in abstract:
            # PubMed abstracts can carry restricted inline XML tags. Keep text,
            # not literal markup or executable HTML, for the textContent UI.
            text = ' '.join(re.sub(r'</?[A-Za-z][A-Za-z0-9:_-]*(?:\s+[^<>]*?)?\s*/?>', '', html.unescape(str(fragment))).split())
            if text:
                label = fragment.attributes.get('Label', '') if hasattr(fragment, 'attributes') else ''
                parts.append((str(label).strip(), text))
        if not parts:
            return None
        source_text = '\n'.join(f'{label}: {text}' if label else text for label, text in parts)
        return {
            'title': str(article.get('ArticleTitle') or 'PubMed article'),
            'summary': '1. PubMed abstract (original source text):\n' + source_text
                       + '\n2. Evidence limits:\nAbstract only. Full-text methods, numerical claims and limitations have not been independently checked.',
            'url': f'https://pubmed.ncbi.nlm.nih.gov/{pmid}/',
            'analysis_scope': 'PubMed abstract only; no full-text appraisal',
        }
    return None
