const params = new URLSearchParams(window.location.search);
const pmid = params.get('pmid');
const target = document.getElementById('reference-content');
function paragraph(text, parent) { const p=document.createElement('p'); p.textContent=text; parent.append(p); return p; }
function parseSections(summary) {
    const sections=[]; let active=null;
    for(const line of String(summary||'').split(/\r?\n/)) {
        const match=line.trim().match(/^(?:\*\*)?\s*(\d{1,2})[.)]\s*([^:]+):?(?:\*\*)?\s*(.*)$/);
        if(match){active={number:match[1],title:match[2].replace(/\*\*/g,'').trim(),lines:[]};sections.push(active);if(match[3]) active.lines.push(match[3]);}
        else if(active && line.trim()) active.lines.push(line.trim());
    }
    return sections;
}
function render(article) {
    target.replaceChildren();
    const head=document.createElement('div');head.className='paper-heading';
    const title=document.createElement('h2');title.textContent=article.title||'Article analysis';head.append(title);
    if(article.citation){const citation=document.createElement('p');citation.className='citation';citation.textContent=article.citation;head.append(citation);}
    const meta=document.createElement('div');meta.className='paper-meta';if(article.pmid){const id=document.createElement('span');id.textContent=`PMID ${article.pmid}`;meta.append(id);}head.append(meta);target.append(head);
    paragraph('This is an automated paper summary. Check the original article for methods, numbers, and limitations before relying on it.',target).className='reading-note';
    if(/^https:\/\//i.test(article.url||'')){const link=document.getElementById('read-article');link.href=article.url;link.hidden=false;}
    const summary=String(article.summary||'');
    const invalid=/no content provided|provide the details or text of the research paper|cannot (?:access|summari[sz]e) (?:this|the) (?:research )?paper/i.test(summary);
    const sections=invalid?[]:parseSections(summary);
    if(!sections.length){const empty=document.createElement('div');empty.className='empty-analysis';paragraph(invalid?'The saved analysis does not contain research findings. Read the original article instead.':summary||'An analysis is not available for this article yet. Use Read Article to review the original paper.',empty);target.append(empty);return;}
    const grid=document.createElement('div');grid.className='analysis-grid';
    sections.forEach(section=>{const block=document.createElement('section');block.className='analysis-section';const h=document.createElement('h3');const number=document.createElement('span');number.className='number';number.textContent=section.number;h.append(number,document.createTextNode(section.title));block.append(h);paragraph(section.lines.join('\n'),block);grid.append(block);});target.append(grid);
}
async function load(){
    if(!pmid||!/^\d{1,12}$/.test(pmid)){target.textContent='Choose an article from the Sources list to view its analysis.';return;}
    const original=document.getElementById('read-article');
    original.href=`https://pubmed.ncbi.nlm.nih.gov/${pmid}/`; original.hidden=false;
    try{
        const response=await DietNerdAPI.apiFetch(`/articles/${encodeURIComponent(pmid)}`);
        if(!response.ok){target.textContent=response.status===404?'No saved analysis was found for this article. Open its original source from the Sources list.':'Could not load the article analysis. Try again.';return;}
        render(await response.json());
    }catch(error){target.textContent='Could not reach the research server. Try again.';}
}
load();
