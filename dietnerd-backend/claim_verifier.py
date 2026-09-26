"""Conservative numerical provenance check over retrieved source text.

A number appearing in an abstract does not prove causal support. Its absence
from retrieved abstracts produces an audit warning; it does not prove the full text lacks it. Model-generated
summaries are never the sole source for this check.
"""
import re

NUMBER = re.compile(r'(?<![A-Za-z0-9])\d+(?:\.\d+)?\s*(?:g\s*/\s*kg|grams?\s+per\s+kg|kcal|calories?)\b', re.I)
REF = re.compile(r'\[(\d+)\]')
HEADING = re.compile(r'(?im)^\s*(?:#{1,4}\s*)?References\s*:?',re.I)


def _tokens(text):
    return {re.sub(r'\s+','',m.group().lower()).replace('gramsperkg','g/kg') for m in NUMBER.finditer(str(text or ''))}


def find_unchecked_quantities(answer, indexed):
    body = HEADING.split(str(answer or ''))[0]
    problems=[]
    for line in body.splitlines():
        claims=_tokens(line)
        if not claims:
            continue
        ids={int(n) for n in REF.findall(line)}
        if not ids:
            problems.append({'line':line[:300], 'reason':'numeric claim has no adjacent source ID'})
            continue
        source_text=' '.join(str(indexed.get(i,{}).get('source_text_excerpt') or indexed.get(i,{}).get('abstract') or '') for i in ids)
        source_tokens=_tokens(source_text)
        # Full-text summaries are not the primary source. Full text may contain
        # the number even when this abstract-only check cannot confirm it.
        for quantity in claims - source_tokens:
            problems.append({'line':line[:300], 'reason':f'{quantity} not found in cited retrieved abstract'})
    return problems


def source_passage_check(claim, source):
    """Locate verbatim shared text; lexical match is not clinical validation."""
    source_text = str(source.get('source_text_excerpt') or source.get('abstract') or '')
    words = [w for w in re.findall(r'[a-z0-9]+', str(claim).lower()) if len(w) > 4]
    if not source_text or len(words) < 3:
        return {'status':'not checked','passage':None}
    sentences = re.split(r'(?<=[.!?])\s+',source_text)
    ranked = sorted(sentences,key=lambda x:sum(w in x.lower() for w in set(words)),reverse=True)
    if not ranked or sum(w in ranked[0].lower() for w in set(words)) < 3:
        return {'status':'no close passage found','passage':None}
    return {'status':'candidate lexical passage only; meaning not verified',
            'passage':ranked[0][:500]}


def audit_arithmetic(answer, body_weight=None):
    """Check explicit weight × per-kg equations; no target is inferred."""
    from decimal import Decimal, InvalidOperation
    issues=[]
    text=str(answer or '')
    pattern=re.compile(r'(?P<weight>\d{2,3}(?:\.\d+)?)\s*(?:kg)?\s*[×x*]\s*(?P<factor>\d(?:\.\d+)?)\s*(?:g\s*/\s*kg)?\s*=\s*(?P<result>\d+(?:\.\d+)?)\s*g\s*/\s*day',re.I)
    for match in pattern.finditer(text):
        try:
            w=Decimal(match.group('weight')); f=Decimal(match.group('factor')); result=Decimal(match.group('result'))
        except InvalidOperation:
            continue
        exact=w*f
        # A whole-number daily target may be rounded to the nearest gram.
        tolerance=Decimal('0.5') if result == result.to_integral_value() else Decimal('0.05')
        if abs(exact-result) > tolerance:
            issues.append({'equation':match.group()[:150],'reason':'multiplication mismatch'})
        if body_weight is not None and w != Decimal(str(body_weight)):
            issues.append({'equation':match.group()[:150],'reason':'body weight differs from supplied value'})
    return issues



CALORIE_TARGET = re.compile(r'\b\d{2,4}\s*(?:to|[-–])\s*\d{2,4}\s*(?:kcal|calories?)\b|\b\d{3,4}\s*(?:kcal|calories?)\b|\b(?:add|eat|consume|target|aim for|recommend|increase)\b[^.!?\n]{0,70}\b(?:surplus|deficit)\b', re.I)
CALORIE_HEADING = re.compile(r'(?im)^(?:#{1,4}\s*|\*\*)?\s*(?:\d+[.)]\s*)?calori(?:e|es)\s+(?:intake|recommendation|target|needs|and energy needs)\s*(?:\*\*)?\s*:?\s*$')
SOURCE_MARKER = re.compile(r'\[(\d+)\]')


def remove_ungrounded_calorie_prescription(answer):
    """Preserve a separate protein brief, but never leave fabricated kcal math.

    The model may write LaTex equations, prose, or summary repetitions. Only
    structural removal of the whole calorie section is safe. If that section
    cannot be isolated, withhold the whole result for a corrected synthesis.
    """
    text = str(answer or '')
    # Even nonnumerical surplus advice is a personal calorie prescription
    # when an explicit weight-loss goal contradicts it.
    surplus_advice = re.search(r'\b(?:add|eat|consume|target|aim for|recommend(?:ed)?|increase)\b[^.!?\n]{0,90}\b(?:surplus|more calories)\b|\b(?:calorie|energy)\s+surplus\s+(?:is|will|should)\b', text, re.I)
    if not CALORIE_TARGET.search(text) and not surplus_advice:
        return text, False
    heading = CALORIE_HEADING.search(text)
    if not heading:
        return None, True
    prefix = text[:heading.start()].rstrip()
    # Do not misread a summary bullet 'Calorie Intake: 2200 kcal' as a
    # heading that starts a safe removable section: it has content after ':'
    # and will fail the anchored CALORIE_HEADING match above.
    # Drop everything from the calorie heading until references. Summaries
    # repeat kcal targets and cannot be safely cleaned sentence-by-sentence.
    references = re.search(r'(?im)^\s*References\s*:?\s*$', text[heading.end():])
    tail = text[heading.end()+references.start():] if references else ''
    disclaimer = re.search(r'DietChat is an exploratory tool[\s\S]*$', tail or text)
    if not prefix or CALORIE_TARGET.search(prefix) or re.search(r'\b\d{2,4}\s*(?:to|[-–])\s*\d{2,4}\s*(?:kcal|calories?)\b', prefix, re.I):
        return None, True
    cited = {int(n) for n in SOURCE_MARKER.findall(prefix)}
    if tail and cited:
        ref_lines=[]
        for line in tail.splitlines()[1:]:
            match=re.match(r'\s*\[(\d+)\]\s+',line)
            if match and int(match.group(1)) in cited:
                ref_lines.append(line)
        refs='\n\nReferences\n'+'\n'.join(ref_lines) if ref_lines else ''
    else:
        refs=''
    note=('Daily calories cannot be set from body weight alone. Your goal, activity '
          'and energy-intake or expenditure baseline are needed for an individual target.')
    safe=prefix+'\n\n'+note+refs
    if disclaimer and 'DietChat is an exploratory tool' not in safe:
        safe+='\n\n'+disclaimer.group().strip()
    if CALORIE_TARGET.search(safe):
        return None, True
    return safe, True
