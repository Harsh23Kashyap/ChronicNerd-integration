"""Food composition, separate from intervention-study claims and PubMed synthesis."""
import os,re,requests

FDC='https://api.nal.usda.gov/fdc/v1'
# These IDs identify a specified preparation, not all variants of a food.
FOODS={
 'chicken breast':(171477,'Chicken breast, cooked, roasted'),
 'paneer':(2705740,'Paneer cheese (USDA survey estimate)'),
 'tofu':(172475,'Tofu, firm, raw'),
 'lentils':(172421,'Lentils, cooked, boiled, no salt'),
 'eggs':(173424,'Eggs, whole, hard-boiled'),
}
PROTEIN=1003;FIBER=1079

def parse_comparison(question):
    q=str(question or '').lower()
    if not re.search(r'per\s+100\s*(?:g|grams)\b',q): return None
    if not re.search(r'\b(?:compar\w*|table|chart)\b',q): return None
    if not re.search(r'\bprotein\b',q) or not re.search(r'\bfib(?:er|re)\b',q): return None
    found=[key for key in FOODS if re.search(r'\b'+re.escape(key)+r'\b',q)]
    mentioned=re.search(r'\b(?:across|between|among)\s+(.+?)\s+(?:in a table|as a chart|in a chart|\?|$)',q)
    if mentioned:
        listed=mentioned.group(1).strip(' .')
        if not listed or any(part.strip(' ,') and part.strip(' ,') not in FOODS for part in re.split(r'\s*,?\s+and\s+|\s*,\s*',listed)):
            return None
    return found if len(found)>=2 else None

def _nutrient(food,number):
    for row in food.get('foodNutrients') or []:
        nutrient=row.get('nutrient') or {}
        if nutrient.get('id')==number and nutrient.get('unitName','').lower()=='g':
            amount=row.get('amount')
            if isinstance(amount,(int,float)) and not isinstance(amount,bool) and amount>=0:
                return amount
    return None

def render_food_comparison(question, session=None):
    foods=parse_comparison(question)
    if not foods: return None
    api_key=os.getenv('USDA_FDC_API_KEY')
    if not api_key:
        return {'answer':'Food-composition data is not configured yet. I cannot give a verified per-100g comparison table for these foods.','sources':[]}
    client=session or requests.Session()
    rows=[]; missing=[]; limited=False
    for name in foods:
        fdc_id,label=FOODS[name]
        try:
            response=client.get(f'{FDC}/food/{fdc_id}',params={'api_key':api_key},timeout=12)
            if response.status_code == 429:
                limited=True;break
            response.raise_for_status(); food=response.json()
            if not isinstance(food,dict):
                missing.append(label);continue
        except (requests.RequestException,ValueError):
            missing.append(label);continue
        if food.get('fdcId')!=fdc_id or food.get('dataType')!=('Survey (FNDDS)' if name=='paneer' else 'SR Legacy'):
            missing.append(label);continue
        protein=_nutrient(food,PROTEIN);fiber=_nutrient(food,FIBER)
        # A missing fiber field is not evidence of zero, even for animal foods.
        if protein is None or fiber is None:
            missing.append(label);continue
        rows.append((label,protein,fiber,fdc_id))
    if limited:
        return {'answer':'FoodData Central is rate-limiting nutrient lookups right now. Please retry later; I cannot verify the full table yet.','sources':[]}
    if missing:
        return {'answer':('I could not verify the per-100g protein and fiber values for every requested food right now '
                '('+', '.join(missing)+'). No comparison table is shown rather than filling the gaps with guesses.'),'sources':[]}
    if len(rows)!=len(foods):
        return {'answer':'Food-composition results are incomplete; no comparison table is shown.','sources':[]}
    out=['Protein and fiber per 100 g of the listed food preparations (USDA FoodData Central):','',
         '| Food preparation | Protein (g per 100 g) | Fiber (g per 100 g) |',
         '|---|---:|---:|']
    out += [f'| {label} | {protein:.1f} | {fiber:.1f} |' for label,protein,fiber,_ in rows]
    out += ['', 'USDA source record IDs:']
    out += [f'- {label}: FDC ID {fdc_id}, USDA FoodData Central' for label,_,_,fdc_id in rows]
    out += ['', 'The figures describe these specific preparations, not every chicken, paneer, tofu, lentil or egg product. Paneer is a USDA survey estimate; brand and moisture content vary. A missing nutrient value is not treated as zero.']
    sources=[{'number':i+1,'title':f'USDA FoodData Central: {label} (FDC ID {fdc_id})',
              'url':f'https://fdc.nal.usda.gov/food-details/{fdc_id}/nutrients','pmid':'',
              'summary_excerpt':f'Food composition record {fdc_id}; {"Survey (FNDDS)" if fdc_id==2705740 else "SR Legacy"}. Search by FDC ID.'}
             for i,(label,_,_,fdc_id) in enumerate(rows)]
    return {'answer':'\n'.join(out),'sources':sources}
