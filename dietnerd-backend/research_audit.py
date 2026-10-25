"""Conservative, inspectable Heavy research trail. Unknown checks stay unknown."""
from datetime import datetime, timezone
import re
import html


def _types(article):
    value = article.get('publication_type') or []
    return [str(x) for x in (value if isinstance(value, list) else [value])]


def lane(article):
    types = ' '.join(_types(article)).lower()
    if 'guideline' in types or 'consensus' in types: return 'guideline or consensus'
    if 'systematic review' in types or 'meta-analysis' in types: return 'systematic review or meta-analysis'
    if 'randomized controlled trial' in types or 'clinical trial' in types: return 'trial'
    if 'review' in types: return 'other review'
    return 'primary or unclassified'


def identity(article):
    pmid = str(article.get('PMID') or '')
    url = str(article.get('url') or '')
    if not re.fullmatch(r'\d{1,12}',pmid) or url != f'https://pubmed.ncbi.nlm.nih.gov/{pmid}/':
        return 'identity incomplete'
    if article.get('retraction_status') == 'retracted':
        return 'marked retracted in fresh PubMed metadata'
    if article.get('retraction_status') == 'correction':
        return 'correction noted in fresh PubMed metadata; details require review'
    if any('retracted publication' in t.lower() for t in _types(article)):
        return 'marked retracted in PubMed metadata'
    return 'PubMed PMID and URL recorded; current retraction status not independently checked'


def card(article):
    summary = str(article.get('summary') or '')
    def section(name):
        match = re.search(r'(?im)^\s*(?:\*\*)?\d+[.)]\s*' + re.escape(name) + r'[^\n]*:\s*(.*?)(?=^\s*(?:\*\*)?\d+[.)]|\Z)',summary,re.S|re.M)
        return re.sub(r'\s+',' ',match.group(1)).strip()[:400] if match else ''
    return {
        'pmid':str(article.get('PMID') or ''),'title':str(article.get('title') or '')[:500],
        'citation':str(article.get('citation') or '')[:900],'url':str(article.get('url') or ''),
        'lane':lane(article),'identity':identity(article),
        'text_access':'full text reported' if article.get('full_text') else 'abstract only or full text unconfirmed',
        'design':('PubMed abstract only; no independent design appraisal' if article.get('analysis_scope') == 'PubMed abstract only' else section('Purpose & Design') or section('Type of Study') or 'not extracted'),
        'population':('See original abstract; not independently appraised' if article.get('analysis_scope') == 'PubMed abstract only' else section('Testing Subject') or 'not extracted'),
        'sample_size':section('Size of Study') or 'not extracted',
        'duration':section('Length of Experiment') or 'not extracted',
        'outcome':section('Main Conclusions') or 'not extracted',
        'effect_and_uncertainty':section('Effect Size') or section('Confidence Interval') or 'not extracted',
        'funding_or_conflicts':section('Sources of Funding or Conflict of Interest') or 'not extracted',
        'fit_to_question':'not independently verified',
        'methodology_review':'model summary available; not independently appraised',
        'evidence_passage':'not independently verified against the source',
    }


def heavy_search_queries(general, existing, question=None):
    """Search the protein-design lanes without dragging a combined query into ICU studies.

    Goal terms come only from the user's standalone question, never a private
    profile. Calorie searches remain in the original generated query set.
    """
    general = str(general or '').strip()[:350]
    queries = [str(query).strip() for query in existing if str(query).strip()]
    if not general:
        return queries[:8]
    question = str(question or '')
    combined = bool(re.search(r'\bprotein\b', question, re.I) and
                    re.search(r'\bcalori(?:e|es)\b|\benergy\b', question, re.I))
    if combined:
        base = ('("Dietary Proteins"[MeSH Terms] OR "protein intake"[Title/Abstract]) '
                'AND ("Adult"[MeSH Terms] OR adults[Title/Abstract])')
        if re.search(r'\bmuscle|resistance training|strength|hypertrophy\b', question, re.I):
            base += ' AND ("Resistance Training"[MeSH Terms] OR strength[Title/Abstract])'
    else:
        base = general
    lanes = [f'({base}) AND (Guideline[Publication Type] OR Consensus Development Conference[Publication Type])',
             f'({base}) AND (Systematic Review[Publication Type] OR Meta-Analysis[Publication Type])',
             f'({base}) AND (Randomized Controlled Trial[Publication Type] OR Clinical Trial[Publication Type])']
    return list(dict.fromkeys(lanes + queries))[:8]


def assemble_heavy_sources(relevant_records, cached_summaries):
    """Rebuild source identity from this run's PubMed XML, not cached analysis.

    Older cache rows may omit title/abstract and use article_type rather than
    publication_type. Summaries are useful context, but never authorize a source
    without a fresh record, PMID, abstract and citation.
    """
    from helper_functions import generate_ama_citation
    cached = {str(row.get('PMID') or row.get('article_id') or ''):row
              for row in cached_summaries if isinstance(row,dict)}
    sources=[];seen=set()
    for record in relevant_records:
        med=record.get('MedlineCitation') or {}
        article=med.get('Article') or {}
        pmid=str(med.get('PMID') or '')
        if not re.fullmatch(r'\d{1,12}',pmid) or pmid in seen: continue
        title=str(article.get('ArticleTitle') or '').strip()
        fresh=fresh_pubmed_metadata(record)
        if not title or not fresh['abstract'].strip() or fresh['retraction_status']=='retracted': continue
        row=cached.get(pmid,{})
        if pmid == '41723912':
            # Defense in depth: reject this poisoned cache even if a future
            # caller bypasses the API's matching-stage quarantine.
            row = {'analysis_scope': 'PubMed abstract only',
                   'summary': '1. PubMed abstract (original source text):\n' + fresh['abstract']
                    + '\n2. Evidence limits:\nAbstract only. No model-generated analysis is available for this paper.'}
        citation=str(row.get('citation') or '').strip() or str(generate_ama_citation(record)).strip()
        if not citation or title.casefold().rstrip('.') not in citation.casefold():
            citation=str(generate_ama_citation(record)).strip()
        if not citation or title.casefold().rstrip('.') not in citation.casefold(): continue
        types=[str(item) for item in (article.get('PublicationTypeList') or [])]
        sources.append({**row,'title':title,'PMID':pmid,'url':f'https://pubmed.ncbi.nlm.nih.gov/{pmid}/',
                        'citation':citation,'publication_type':types,
                        'summary':str(row.get('summary') or ''),**fresh})
        seen.add(pmid)
    return sources

def prioritize_heavy_evidence(articles, question, limit=12, selected_pmid=None, private_goal=''):
    """Rank actual adult daily-dose evidence before single trials and timing papers.

    Retrieval and relevance are broad; this is a synthesis shortlist, not a
    claim-support verdict. The user-selected PMID remains visible even when
    it cannot support a general recommendation.
    """
    from helper_functions import prepare_indexed_evidence
    valid, _ = prepare_indexed_evidence(articles)
    valid = [a for a in valid if str(a.get('abstract') or '').strip() and a.get('retraction_status') != 'retracted'
             and 'retracted publication' not in ' '.join(_types(a)).lower()]
    pinned=[a for a in valid if str(a.get('PMID')) == str(selected_pmid)] if selected_pmid else []
    question=str(question or '')
    if not re.search(r'\bprotein\b',question,re.I):
        return (pinned[:1]+[a for a in valid if a not in pinned])[:limit]
    goal=bool(re.search(r'\b(?:muscle|strength|resistance training|hypertrophy)\b',question+' '+str(private_goal),re.I))
    athlete_goal=bool(re.search(r'\b(?:athlete\w*|sport\w*|bodybuild\w*|powerlift\w*)\b',question+' '+str(private_goal),re.I))
    # Only exact user populations can raise a specialized paper's priority.
    named_specialized=bool(re.search(r'\b(?:pregnan\w*|child\w*|pediatri\w*|hospitali[sz]\w*|cancer|'
                                      r'obesity|overweight|diabetes|sarcopeni\w*|vegan\w*|vegetarian\w*)\b',
                                     question+' '+str(private_goal),re.I))
    specialty=re.compile(r'\b(?:pregnan\w*|pediatri\w*|adolescen\w*|child\w*|infant\w*|young athlete\w*|'
                         r'hospitali[sz]\w*|inpatient\w*|intensive care|critical\w* ill|cancer|chemotherap\w*|'
                         r'dialysis|renal failure|diabetes|obesity|overweight|sarcopeni\w*|frail\w*|'
                         r'elderly|geriatri\w*|older adult\w*|vegan\w*|vegetarian\w*)\b',re.I)
    exposure=re.compile(r'\b(?:protein (?:intake|requirement\w*|recommendation\w*|dose\w*|supplementation)|'
                        r'dietary protein\w*|high.protein|higher.protein)\b',re.I)
    dose=re.compile(r'\b(?:\d(?:\.\d+)?\s*g\s*/\s*kg|grams per kilogram|protein requirement\w*|'
                    r'protein recommendation\w*|daily protein|protein intake|dose.response|upper limit|'
                    r'recommended dietary allowance)\b',re.I)
    timing=re.compile(r'\b(?:timing|distribution|every \d+ hours?|hourly|post.exercise|post.workout|'
                      r'myofibrillar protein synthesis|muscle protein synthesis|meal frequency)\b',re.I)
    ranked=[]
    for original_index,article in enumerate(valid):
        title=str(article.get('title') or '')
        abstract=str(article.get('abstract') or '')
        if not abstract.strip(): continue
        text=title+' '+abstract
        # Retrieval classifiers are broad. A title that identifies an animal-only
        # experiment cannot support an ordinary adult intake answer.
        if re.search(r'\b(?:rat\w*|mice|mouse|murine|rodent\w*|swine|pig\w*|rabbit\w*|animal.only|in vitro)\b', title, re.I):
            continue
        # An adult human comparison of measured protein intakes can be useful even
        # when its abstract says 'dietary intake' rather than the exact phrase above.
        comparison=bool(re.search(r'\b(?:protein|amino acid)\b',text,re.I) and
                        re.search(r'\b(?:adult|women|men|participants|humans?)\b',text,re.I) and
                        re.search(r'\b(?:intake|dose|diet|consum|supplement|requirement)\w*\b',text,re.I))
        if not exposure.search(text) and not comparison: continue
        if specialty.search(title) and not named_specialized: continue
        if re.search(r'\b(?:elite athlete\w*|athlete\w*|sports nutrition|sport performance)\b',title,re.I) and not athlete_goal: continue
        kind=lane(article)
        types=' '.join(_types(article)).lower()
        is_position=bool(re.search(r'position stand|position statement|consensus statement|practice guideline|'
                                   r'expert consensus|(?:dietary |protein )recommendations?',title,re.I))
        review=kind=='systematic review or meta-analysis'
        guideline=kind=='guideline or consensus' or is_position
        cohort=bool(re.search(r'cohort|prospective|longitudinal|population.based',title+' '+types,re.I))
        has_dose=bool(dose.search(text))
        title_dose=bool(dose.search(title))
        title_timing=bool(timing.search(title))
        adult=bool(re.search(r'healthy adults?|healthy (?:men|women)|adult\w*|humans?',text,re.I))
        muscle=bool(re.search(r'muscle|strength|resistance training|hypertrophy',title,re.I))
        # A single timing trial cannot answer daily intake. It stays behind
        # adult dose reviews/guidelines, and only enters as supporting context.
        if title_timing and not has_dose: continue
        if title_timing and kind == 'trial': continue
        if not goal and muscle and not re.search(r'\b(?:general adult\w*|healthy adult\w*|dietary protein requirement\w*)\b',title,re.I):
            # Retain as lower-tier context rather than losing the pooled dose
            # finding entirely when no goal was supplied.
            muscle_without_goal=True
        else: muscle_without_goal=False
        if review and has_dose: tier=3 if muscle_without_goal else 0
        elif guideline and has_dose: tier=1
        elif cohort and has_dose: tier=2
        elif review: tier=3
        elif guideline: tier=4
        elif kind=='trial' and has_dose: tier=5
        else: tier=6
        score=(9 if title_dose else 0)+(5 if has_dose else 0)+(3 if adult else 0)
        score+=(4 if goal and muscle else 0)
        score-=12 if title_timing else 0
        score-=8 if specialty.search(abstract) and not adult and not named_specialized else 0
        ranked.append((tier,-score,original_index,article))
    ranked.sort(key=lambda row:row[:3])
    chosen=pinned[:1];seen={str(a.get('PMID') or a.get('title')) for a in chosen}
    # A direct daily-intake question must have a dose review/guideline as its
    # lead. Single trials enter only as supporting context after higher tiers.
    for tier,_,_,article in ranked:
        if tier>=5 and not athlete_goal and not any(item[0] in (0,1,2,3,4) for item in ranked):
            continue
        key=str(article.get('PMID') or article.get('title'))
        if key not in seen:
            chosen.append(article);seen.add(key)
        if len(chosen)>=max(limit,60): break
    # Keep the high-fit lead, then expose distinct adult evidence designs to
    # synthesis; do not treat the 30 highest review scores as 30 independent
    # experiments. The excluded/specialized population guards above still apply.
    if len(chosen)>8 and limit>=20:
        from collections import Counter
        reserve=chosen[:3]; remainder=chosen[3:]; balanced=[]; counts=Counter()
        while remainder and len(reserve)+len(balanced)<limit:
            best=min(range(len(remainder)),key=lambda i:(counts[lane(remainder[i])],i))
            item=remainder.pop(best);balanced.append(item);counts[lane(item)]+=1
        chosen=reserve+balanced
    return chosen[:limit]

def review_overlap(articles):
    """Only report overlap when two reviews name the same cited PMID in source text."""
    reviews=[a for a in articles if isinstance(a,dict) and lane(a) in ('systematic review or meta-analysis','other review')]
    mentions={str(a.get('PMID') or ''):set(re.findall(r'\bPMID\s*:?\s*(\d{5,12})\b',
              str(a.get('source_text_excerpt') or ''),re.I)) for a in reviews}
    findings=[]
    ids=list(mentions)
    for i,first in enumerate(ids):
        for second in ids[i+1:]:
            shared=sorted(mentions[first] & mentions[second])
            if shared:
                findings.append({'reviews':[first,second],'shared_pmids':shared[:30]})
    return {'detected':findings[:20],
            'status':'Shared explicit PMID mentions only; absence does not prove independent studies'}


def build_audit(question, queries, retrieved, relevant, articles, ledger, answer, excluded=None):
    cards=[{**card(a),'appraisal':study_appraisal(a,question)} for a in articles if isinstance(a,dict) and not str(a.get('publication_type','')).startswith('User-supplied PDF')]
    cited={row.get('source_url') for row in ledger if row.get('source_url')}
    from claim_verifier import find_unchecked_quantities, audit_arithmetic
    from helper_functions import prepare_indexed_evidence
    _, indexed = prepare_indexed_evidence(articles)
    numeric_warnings=find_unchecked_quantities(answer,indexed)
    weight_match=re.search(r'\b(?:weight|wieght)\s*(?:is|:|=)?\s*(\d{2,3}(?:\.\d+)?)\s*(?:kg|kgs)\b',question,re.I)
    arithmetic_warnings=audit_arithmetic(answer,weight_match.group(1) if weight_match else None)
    from claim_verifier import source_passage_check
    passage_checks=[]
    for row in ledger:
        marker = re.fullmatch(r'\[(\d+)\]',str(row.get('citation_marker') or ''))
        if marker and int(marker.group(1)) in indexed:
            check=source_passage_check(row.get('claim'),indexed[int(marker.group(1))])
            passage_checks.append({'citation_marker':row.get('citation_marker'),
                                   'claim':str(row.get('claim') or '')[:300],**check})
    exclusions=[{
        'pmid':str(item.get('MedlineCitation',{}).get('PMID') or ''),
        'title':str(item.get('MedlineCitation',{}).get('Article',{}).get('ArticleTitle') or '')[:300],
        'reason':str(item.get('dietnerd_exclusion_reason') or 'not classified; reason unavailable')
    } for item in (excluded or []) if isinstance(item,dict)]
    return {
        'created_at':datetime.now(timezone.utc).isoformat(),
        'question':question,
        'queries':[str(q)[:500] for q in queries[:8]],
        'retrieved_count':len(retrieved),'relevant_count':len(relevant),
        'deep_analysis_count':sum(bool(article.get('summary')) for article in articles),
        'synthesis_source_count':len(cards),
        'selection_note':'The synthesis uses only the source cards shown here after a second direct-fit screen. Broad questions exclude specialized populations; selected papers are retained and labeled even when indirect.',
        'excluded_count':len(exclusions) if excluded is not None else max(0,len(retrieved)-len(relevant)),
        'screening_note':'Title/abstract exclusions record classifier or deterministic filter decisions, not a full-text systematic review.',
        'exclusions':exclusions[:100],
        'deduplication':'PMID across PubMed queries; review overlap checked only where explicit PMIDs appear in retrieved excerpts',
        'review_overlap':review_overlap(articles),
        'retrieval_lanes':{name:sum(1 for source in cards if source['lane']==name) for name in ('guideline or consensus','systematic review or meta-analysis','trial','other review','primary or unclassified')},
        'answer_length':len(answer or ''),
        'sources':cards[:30],
        'cited_count':len(cited),'claim_support':'Source identities matched by title; quantitative tokens and candidate lexical passages checked in cited source excerpts, but interpretation is not independently verified',
        'calorie_check':'A weight alone cannot establish daily calories or a surplus; confirm goal and energy needs.',
        'numeric_warnings':numeric_warnings[:20],
        'arithmetic_warnings':arithmetic_warnings[:20],
        'passage_checks':passage_checks[:50],
        'limits':['Fetched PubMed metadata inspected for retraction/correction; later status changes are possible',
                  'Lexical passage candidates do not prove clinical support for a claim',
                  'Review overlap without explicit PMIDs and study-level risk of bias are not independently assessed'],
    }


def fresh_pubmed_metadata(record):
    """Inspect this request's fetched PubMed XML, not a stored model summary."""
    med = record.get('MedlineCitation', {})
    article = med.get('Article', {})
    types = [str(t).lower() for t in article.get('PublicationTypeList', [])]
    corrections = med.get('CommentsCorrectionsList', []) or []
    correction_types = [str(c.get('RefType', '') if isinstance(c, dict) else getattr(c, 'attributes', {}).get('RefType', '')).lower()
                        for c in corrections]
    if any('retracted publication' in t for t in types) or any('retractionin' in t for t in correction_types):
        status = 'retracted'
    elif any('erratum' in t or 'correction' in t for t in types + correction_types):
        status = 'correction'
    else:
        status = 'not marked in fetched PubMed record'
    fragments = article.get('Abstract', {}).get('AbstractText', []) or []
    return {'abstract': ' '.join(re.sub(r'</?[A-Za-z][A-Za-z0-9:_-]*(?:\s+[^<>]*?)?\s*/?>', '', html.unescape(str(part))) for part in fragments)[:20000],
            'retraction_status': status}


def study_appraisal(article, question):
    """Separate observable metadata from a risk-of-bias verdict we cannot prove."""
    text=' '.join((str(article.get('title') or ''),str(article.get('abstract') or ''))).lower()
    types=' '.join(_types(article)).lower()
    question_words={w for w in re.findall(r'[a-z]{5,}',str(question).lower())}
    title_words={w for w in re.findall(r'[a-z]{5,}',str(article.get('title') or '').lower())}
    overlap=sorted(question_words & title_words)
    design=('randomized trial' if 'randomized controlled trial' in types else
            'systematic review' if 'systematic review' in types or 'meta-analysis' in types else
            'other or unknown')
    return {'observed_design':design, 'matching_title_terms':overlap[:12],
            'population_fit':'unknown without direct population and outcome review',
            'risk_of_bias':'not independently appraised',
            'randomization_reported':bool(re.search(r'\brandomi[sz]ed\b',text)),
            'funding_disclosed_in_excerpt':bool(re.search(r'\bfund(?:ing|ed)\b|conflict of interest',text))}
