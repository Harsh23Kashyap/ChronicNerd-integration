
const baseURL = DietNerdAPI.baseURL;
const apiFetch = DietNerdAPI.apiFetch;

let temporaryChat = false;
const conversationProfileSettings = new Map();
let temporaryTurns = [];
let temporaryFile = null;
function getConversationId() {
    return temporaryChat ? null : (sessionStorage.getItem('dietnerd_conversation_id') || null);
}

function emptyStateMarkup(temporary = false) {
    const heading = temporary ? 'Temporary workspace' : 'Start a new conversation';
    const intro = temporary ? 'Ask a question here. This chat is not saved to your account.' : 'Ask a diet or nutrition question to begin.';
    const prompts = temporary
        ? ['What does research say about daily fiber?', 'How does hydration affect exercise?', 'Which foods contain iron?']
        : ['How much protein do I need daily?', 'Is coffee good for heart health?', 'What helps with iron deficiency?'];
    const buttons = prompts.map(text => `<button type="button" class="example-question">${text}</button>`).join('');
    return `<div class="welcome-message"><span class="assistant-avatar" aria-label="DietNerd"><img src="assets/dietnerd_mark.svg" alt=""></span><div><h2>${heading}</h2><p>${intro}</p><div id="example-questions" class="starter-questions" aria-label="Example questions">${buttons}</div></div></div>`;
}

function clearPaperScope() {
    paperContext = null;
    document.getElementById('paper-pdf').value = '';
    document.getElementById('paper-chip-row').hidden = true;
    document.getElementById('paper-chip-link').hidden = true;
}

function clearChatThread() {
    document.getElementById('chat-thread').innerHTML = '';
    document.getElementById('conversation-chapters').hidden = true;
    document.querySelector('.thread-jump').hidden = true;
    document.getElementById('followup-lens').hidden = true;
}

function enterConversationMode() {
    document.body.classList.add('conversation-mode');
}

function closeSourcesPanel() {
    const shell = document.querySelector('.chat-shell');
    const panel = document.getElementById('sources-panel');
    shell.classList.remove('sources-open');
    panel.setAttribute('aria-hidden', 'true');
}

function sourcePmid(source) {
    if (/^\d{1,12}$/.test(String(source.pmid || ''))) return String(source.pmid);
    return /^https:\/\/pubmed\.ncbi\.nlm\.nih\.gov\/(\d{1,12})\/?$/i.exec(source.url || '')?.[1] || '';
}

function analysisLink(source) {
    const pmid = sourcePmid(source);
    return pmid ? `reference.html?pmid=${encodeURIComponent(pmid)}` : '';
}

function openSourcesPanel(sourceCards) {
    const shell = document.querySelector('.chat-shell');
    const panel = document.getElementById('sources-panel');
    const content = document.getElementById('sources-panel-content');
    content.replaceChildren();
    const cards = Array.isArray(sourceCards) ? sourceCards : [];
    if (!cards.length) {
        const empty = document.createElement('p');
        empty.className = 'sources-empty';
        empty.textContent = 'No linked sources are available for this answer.';
        content.append(empty);
    }
    cards.forEach((source) => {
        const card = document.createElement('article');
        card.className = 'source-card';
        const label = document.createElement('span');
        label.className = 'sources-kicker';
        label.textContent = `Reference ${source.number}`;
        const title = document.createElement('strong');
        title.textContent = source.title || 'Source title unavailable';
        const note = document.createElement('p');
        note.textContent = 'Retrieved citation. Claim support is not independently verified.';
        if (source.summary_excerpt) {
            const excerpt = document.createElement('p');
            excerpt.className = 'source-summary';
            excerpt.textContent = source.summary_excerpt;
            card.append(label, title, excerpt, note);
        } else card.append(label, title, note);
        const analysis = analysisLink(source);
        if (analysis) {
            const view = document.createElement('a');
            view.className = 'source-analysis-link';
            view.href = analysis;
            view.textContent = 'View article analysis →';
            card.append(view);
            card.classList.add('linked-source');
            card.addEventListener('click', event => { if (!event.target.closest('a')) window.location.href = analysis; });
        }
        if (source.url && /^https:\/\//i.test(source.url)) {
            const link = document.createElement('a');
            link.href = source.url;
            link.target = '_blank';
            link.rel = 'noopener noreferrer';
            link.textContent = 'Read Article ↗';
            card.append(link);
        }
        content.append(card);
    });
    shell.classList.add('sources-open');
    panel.setAttribute('aria-hidden', 'false');
}

function splitReferenceSection(answer) {
    const match = /(?:^|\n)\s*(?:#{1,4}\s*)?(?:\*\*)?References?(?:\*\*)?:?\s*(?:\n|$)/i.exec(String(answer));
    return match ? { body: String(answer).slice(0, match.index), references: String(answer).slice(match.index + match[0].length) }
        : { body: String(answer), references: '' };
}

function sourceLink(citation, metadata) {
    const explicit = metadata && typeof metadata.URL === 'string' ? metadata.URL.trim() : '';
    if (/^https:\/\//i.test(explicit)) return explicit;
    const pmid = String(metadata?.PMID || '').trim();
    if (/^\d{1,12}$/.test(pmid)) return `https://pubmed.ncbi.nlm.nih.gov/${pmid}/`;
    const citationPmid = String(citation).match(/\bPMID\s*:\s*(\d{1,12})\b/i);
    if (citationPmid) return `https://pubmed.ncbi.nlm.nih.gov/${citationPmid[1]}/`;
    const match = String(citation).match(/(?:doi\s*:\s*|https?:\/\/(?:dx\.)?doi\.org\/|\b)(10\.\d{4,9}\/[^\s,;<>]+)/i);
    if (!match) return '';
    const doi = match[1].replace(/[.)\]]+$/, '');
    return `https://doi.org/${encodeURI(doi)}`;
}

function prioritizePubMedSources(rows) {
    return rows.sort((a, b) => Number(Boolean(sourcePmid(b))) - Number(Boolean(sourcePmid(a))) || a.number - b.number);
}

function sourcesForAnswer(answer, ledger = [], storedSources = null) {
    if (Array.isArray(storedSources)) return prioritizePubMedSources(storedSources.filter(row => row && Number.isInteger(row.number) && typeof row.title === 'string').map(row => ({number:row.number,title:row.title,url:/^https:\/\//i.test(row.url || '') ? row.url : '',pmid:row.pmid || '',summary_excerpt: typeof row.summary_excerpt === 'string' ? row.summary_excerpt.slice(0,360) : ''})));
    const {references} = splitReferenceSection(answer);
    const lines = references.split(/\n(?=\s*(?:\[\d+\]|\d+\.))/);
    const fromAnswer = lines.flatMap(line => {
        const match = line.trim().match(/^(?:\[(\d+)\]|(\d+)\.)\s*(.+)/s);
        if (!match) return [];
        const number = Number(match[1] || match[2]);
        const citation = match[3].split(/\n(?=\s*(?:DietNerd|ChronicNerd) is\b)/i)[0].trim();
        const title = citation.slice(0, 240);
        if (!title) return [];
        const normalize = value => String(value).replace(/[^a-z0-9]+/gi, ' ').trim().toLowerCase();
        const ledgerUrl = (Array.isArray(ledger) ? ledger : []).find(row => row?.citation_marker === `[${number}]` && row?.source_title && normalize(citation).includes(normalize(row.source_title)) && normalize(row.source_title).length > 12)?.source_url;
        const url = (/^https:\/\//i.test(ledgerUrl || '') ? ledgerUrl : '') || sourceLink(citation);
        return [{number, title, url, pmid:sourcePmid({url})}];
    });
    return prioritizePubMedSources([...new Map(fromAnswer.map(source => [source.number, source])).values()]);
}

function appendInChatSources(content, sources) {
    const section = document.createElement('section');
    section.className = 'in-chat-sources';
    const heading = document.createElement('h3');
    heading.textContent = 'Sources';
    section.append(heading);
    if (!sources.length) {
        const empty = document.createElement('p');
        empty.className = 'sources-empty';
        empty.textContent = 'No linked articles were provided for this answer.';
        section.append(empty);
    }
    sources.forEach(source => {
        const analysis = analysisLink(source);
        const row = document.createElement(analysis || source.url ? 'a' : 'span');
        row.className = 'in-chat-source';
        if (analysis) { row.href = analysis; row.setAttribute('aria-label', `View analysis for source ${source.number}: ${source.title}`); }
        else if (source.url) { row.href = source.url; row.target = '_blank'; row.rel = 'noopener noreferrer'; }
        else row.title = 'Original article link unavailable';
        const number = document.createElement('span');
        number.textContent = `[${source.number}]`;
        const title = document.createElement('span');
        title.textContent = source.title;
        row.append(number, title);
        if (row.tagName === 'A') row.addEventListener('click', () => {
            const ref = String(source.number);
            const match = [...content.querySelectorAll('p')].find(el => el.textContent.includes(`[${ref}]`));
            for (const el of [row, match].filter(Boolean)) { el.classList.remove('source-flash'); void el.offsetWidth; el.classList.add('source-flash'); setTimeout(() => el.classList.remove('source-flash'), 850); }
        });
        section.append(row);
    });
    const actions = content.querySelector('.message-actions');
    if (actions) content.insertBefore(section, actions);
    else content.append(section);
}

function reconcileInlineCitations(answer, sources) {
    const refs = sourcesForAnswer(answer, [], Array.isArray(sources) && sources.length ? sources : null);
    const labels = new Set(refs.map(source => String(source.number)));
    const pmids = new Map(refs.filter(source => sourcePmid(source)).map(source => [sourcePmid(source), String(source.number)]));
    const body = splitReferenceSection(answer).body;
    return body.replace(/\[\s*(\d*)\s*\]/g, (match, raw) => {
        if (!raw) return '';
        if (labels.has(raw)) return `[${raw}]`;
        return pmids.has(raw) ? `[${pmids.get(raw)}]` : '';
    }).replace(/\s+([.,;:])/g, '$1');
}

function appendChatMessage(role, text, references = [], storedSources = null) {
    const thread = document.getElementById('chat-thread');
    thread.querySelector('.welcome-message')?.remove();
    const article = document.createElement('article');
    article.className = `chat-message ${role}`;
    const avatar = document.createElement('span');
    avatar.className = `${role}-avatar`;
    if (role === 'assistant') {
        const logo = document.createElement('img');
        logo.src = 'assets/dietnerd_mark.svg';
        logo.alt = '';
        avatar.append(logo);
        avatar.setAttribute('aria-label', 'DietNerd');
    } else avatar.textContent = 'You';
    const content = document.createElement('div');
    content.className = 'message-content';
    const answerBody = role === 'assistant' && Array.isArray(references)
        ? reconcileInlineCitations(text, storedSources)
        : text;
    content.innerHTML = role === 'assistant' ? formatText(answerBody) : String(text).replace(/&/g, '&amp;').replace(/</g, '&lt;');
    article.append(avatar, content);
    if (role === 'assistant') {
        const actions = document.createElement('div');
        actions.className = 'message-actions';
        const copy = document.createElement('button');
        copy.type = 'button'; copy.className = 'copy-answer'; copy.textContent = 'Copy answer';
        copy.setAttribute('aria-label', 'Copy answer text');
        copy.addEventListener('click', async () => {
            try {
                await navigator.clipboard.writeText(String(answerBody || ''));
                copy.textContent = 'Copied';
                window.setTimeout(() => { if (copy.isConnected) copy.textContent = 'Copy answer'; }, 1800);
            } catch { document.querySelector('.hint').textContent = 'Could not copy. Check clipboard permission.'; }
        });
        actions.append(copy); content.append(actions);
    }
    thread.appendChild(article);
    if (role === 'user') { updateConversationNavigation(); updateFollowupLens(); }
    enterConversationMode();
    thread.scrollTop = thread.scrollHeight;
    return content;
}

function filterConversationTitles() {
    const query = document.getElementById('history-search').value.trim().toLocaleLowerCase();
    const items = [...document.querySelectorAll('#conversation-list .conversation-item')];
    let visible = 0;
    items.forEach(item => {
        const title = item.querySelector('.conversation-row')?.textContent || '';
        item.hidden = !title.toLocaleLowerCase().includes(query);
        if (!item.hidden) visible++;
    });
    const empty = document.getElementById('history-search-empty');
    empty.hidden = !query || visible > 0;
}
document.getElementById('history-search').addEventListener('input', filterConversationTitles);

async function refreshConversationList() {
    const select = document.getElementById('conversation-select');
    const currentId = getConversationId() || '';
    const response = await apiFetch('/conversations');
    if (!response.ok) {
        document.querySelector('.sidebar-heading span').textContent = 'History unavailable';
        return;
    }
    const data = await response.json();
    conversationProfileSettings.clear();
    (data.conversations || []).forEach(c => conversationProfileSettings.set(c.conversation_id, c.use_profile !== false && c.use_profile !== 0));
    if (!temporaryChat && currentId && conversationProfileSettings.has(currentId)) setProfileUseUI(conversationProfileSettings.get(currentId));
    document.querySelector('.sidebar-heading span').textContent = `Conversations (${(data.conversations || []).length})`;
    select.innerHTML = '<option value="">New conversation</option>';
    const list = document.getElementById('conversation-list');
    list.replaceChildren();
    (data.conversations || []).forEach((conversation) => {
        const option = document.createElement('option');
        option.value = conversation.conversation_id;
        option.textContent = conversation.title || 'Untitled conversation';
        select.appendChild(option);
        const item = document.createElement('div');
        item.className = 'conversation-item';
        const row = document.createElement('button');
        row.type = 'button';
        row.className = 'conversation-row';
        row.dataset.conversationId = conversation.conversation_id;
        row.title = conversation.title || 'Untitled conversation';
        row.textContent = conversation.title || 'Untitled conversation';
        const rename = document.createElement('button');
        rename.type = 'button';
        rename.className = 'rename-button';
        rename.title = 'Rename conversation';
        rename.setAttribute('aria-label', `Rename ${conversation.title || 'Untitled conversation'}`);
        rename.textContent = '\u270e';
        rename.addEventListener('click', (event) => {
            event.stopPropagation();
            beginRename(item, conversation);
        });
        item.append(row, rename);
        list.appendChild(item);
    });
    filterConversationTitles();
    const selectedId = (data.conversations || []).some(c => c.conversation_id === currentId) ? currentId : '';
    select.value = selectedId;
    list.querySelectorAll('.conversation-row').forEach(row => {
        const active = row.dataset.conversationId === selectedId;
        row.classList.toggle('active', active);
        if (active) row.setAttribute('aria-current', 'true');
        else row.removeAttribute('aria-current');
    });
}

function refreshTitleAfterAnswer(conversationId) {
    if (!conversationId) return;
    [1500, 4000, 9000, 18000].forEach(delay => {
        window.setTimeout(() => {
            if (getConversationId() === conversationId) refreshConversationList().catch(() => {});
        }, delay);
    });
}

let conversationLoadToken = 0;
async function readConversationHistory(conversationId) {
    let lastError;
    for (let attempt = 0; attempt < 3; attempt++) {
        try {
            const response = await apiFetch(`/session_memory?conversation_id=${encodeURIComponent(conversationId)}`);
            if (response.ok || (response.status !== 502 && response.status !== 503 && response.status !== 504)) return response;
            lastError = new Error(`Research server temporarily unavailable (${response.status}).`);
        } catch (error) { lastError = error; }
        if (attempt < 2) await new Promise(resolve => setTimeout(resolve, (attempt + 1) * 900));
    }
    throw lastError || new Error('Could not load this conversation.');
}

async function renderSelectedConversation(conversationId) {
    if (!conversationId) return;
    const token = ++conversationLoadToken;
    enterConversationMode();
    closeSourcesPanel();
    const thread = document.getElementById('chat-thread');
    thread.innerHTML = '<div class="history-loading" role="status" aria-live="polite"><span class="history-loading-icon" aria-hidden="true"></span><span>Opening conversation...</span><span class="history-loading-line"></span><span class="history-loading-line short"></span></div>';
    try {
        const response = await readConversationHistory(conversationId);
        if (token !== conversationLoadToken) return;
        if (!response.ok) throw new Error(await DietNerdAPI.readError(response, 'Could not load this conversation.'));
        const data = await response.json();
        if (token !== conversationLoadToken) return;
        const entries = data.entries || [];
        clearChatThread();
        entries.forEach((entry) => {
            appendChatMessage('user', entry.raw_question || '');
            const content = appendChatMessage('assistant', entry.answer || '', [], entry.sources || null);
            appendEvidenceLedger(content, entry.evidence_ledger || []);
            appendInChatSources(content, sourcesForAnswer(entry.answer || '', [], Array.isArray(entry.sources) && entry.sources.length ? entry.sources : null));
        });
        document.getElementById('generate-pdf-button').classList.toggle('hidden', !entries.length);
        if (!entries.length) thread.innerHTML = '<div class="history-loading empty-history">This conversation has no completed answers yet.</div>';
        document.getElementById('question').value = '';
        updateConversationNavigation(); updateFollowupLens();
    } catch (err) {
        if (token === conversationLoadToken) {
            thread.innerHTML = '';
            const message = document.createElement('p');
            message.className = 'history-loading';
            message.textContent = err.message || 'Could not load this conversation.';
            thread.append(message);
        }
    }
}

const disclaimer = `
DietNerd is an exploratory tool designed to enrich your conversations with a registered dietitian or registered dietitian nutritionist, who can then review your profile before providing recommendations.
Please be aware that the insights provided by DietNerd may not fully take into consideration all potential medication interactions or pre-existing conditions.
To find a local expert near you, use this website: https://www.eatright.org/find-a-nutrition-expert
`

/**
 * Asynchronously checks if a given user query is valid.
 *
 * @param {string} userQuery - The user query to be checked.
 * @return {Promise<Object>} A Promise that resolves to the response object.
 * @throws {Error} If the network response is not ok.
 */
async function check_valid(userQuery) {
    console.log("Checking valid");
    try {
        const response = temporaryChat
            ? await apiFetch('/check_valid', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({user_query: userQuery})})
            : await apiFetch(`/check_valid/${encodeURIComponent(userQuery)}`);
        if (!response.ok) {
            throw new Error('Network response was not ok');
        }
        const result = await response.json();
        console.log('Check if valid response:', result);
        return result;
    } catch (error) {
        console.error('Error in query_generation:', error);
    }
}

/**
 * Retrieves an answer from the server based on the provided question.
 *
 * @param {string} question - The question to be asked.
 * @return {Promise<string>} The answer to the question.
 * @throws {Error} If the network response is not ok.
 */
const getAnswer = async (question) => {
    try {
        const response = await apiFetch('/cached_answer', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                user_query: question,
                conversation_id: getConversationId(),
                use_profile: document.getElementById('use-profile').checked,
                answer_mode: document.getElementById('answer-mode').value,
            }),
        });
        if (!response.ok) {
            throw new Error('Cached answer not found');
        }
        const result = await response.json();
        sessionStorage.setItem('dietnerd_conversation_id', result.conversation_id);
        await refreshConversationList();
        const cached = JSON.parse(result.cached_payload);
        try {
            localStorage.setItem('referenceObject', JSON.stringify(cached.citations_obj || {}));
            localStorage.setItem('citations', JSON.stringify(cached.citations || []));
        } catch { /* answer still renders when browser storage is full */ }
        return {answer: cached.end_output, sources: sourcesForAnswer(cached.end_output, [], result.sources || null)};
    } catch (err) {
        console.error('Fetch error:', err);
        throw err;
    }
};

/**
 * Generates an answer based on the given question.
 *
 * @param {string} question - The question to generate an answer for.
 * @return {Promise<Object>} A Promise that resolves to the generated answer.
 * @throws {Error} If the network response is not ok.
 */
const generate = async (question) => {
    try {
        const queryUrl = `${baseURL}/generate/${encodeURIComponent(question)}`;
        const response = await fetch(queryUrl);
        
        if (!response.ok) {
            throw new Error('Network response was not ok');
        }

        const result = await response.json();
        return result;
    } catch (err) {
        console.error('Fetch error:', err);
        throw err;
    }
};

/**
 * Retrieves a similarity search result from the server based on the provided question.
 *
 * @param {string} question - The question to be searched.
 * @return {Promise<Object>} A promise that resolves to the similarity search result object.
 * @throws {Error} If the network response is not ok.
 */
const get_sim = async (question) => {
    console.log("Getting Sim")
    try {
        const queryUrl = `/db_sim_search/${encodeURIComponent(question)}`;
        console.log(queryUrl)
        const response = await apiFetch(queryUrl);
        
        if (!response.ok) {
            throw new Error('Network response was not ok');
        }

        const result = await response.json();
        console.log(result)
        return result;
    } catch (err) {
        console.error('Fetch error:', err);
        throw err;
    }
};

/**
 * Split the citation into its components using regex
 *
 * @param {string} citation - The citation to be parsed
 * @return {Array} An array containing the authors, title, and journal of the citation
 */
function parseCitation(citation) {
    // Split the citation into its components using regex
    citation = citation.slice(1);
    const firstDotIndex = citation.indexOf('.');
    const secondDotIndex = citation.indexOf('.', firstDotIndex + 1);
    const authors = citation.substring(3, firstDotIndex).trim();
    const title = citation.substring(firstDotIndex + 1, secondDotIndex).trim();
    const journal = citation.substring(secondDotIndex + 1).trim();
    return [authors, title, journal];
}



/**
 * Formats references in the given output as clickable links.
 *
 * @param {string} output - The output containing references.
 * @return {string} The formatted references as a string.
 */
const formatReferences = (output) => {
    const citations = JSON.parse(localStorage.getItem('citations') || '[]');
    const citationObj = JSON.parse(localStorage.getItem('referenceObject') || '{}');
    const references = extractReferences(output);

    console.log("REFERENCES", references);
    if (references.length === 0) {
        return 'No references available.';
    }

    const seenReferences = new Set();
    const referenceList = references
        .map((ref) => {
            // Normalize the reference number
            const normalizedRef = normalizeReference(ref);

            // Skip if we've already seen this normalized reference
            if (seenReferences.has(normalizedRef)) {
                return null;
            }
            seenReferences.add(normalizedRef);

            const citation = findCitation(ref, citations);
            if (!citation) {
                return null;
            }

            console.log(citationObj);
            console.log(citation);

            // Check if citationObj[citation] exists before accessing it
            if (!citationObj[citation]) {
                return null;
            }

            const pmcid = citationObj[citation]["PMCID"];
            const fullText = pmcid !== 'None';
            const analysisText = getAnalysisText(fullText);

            const [authors, title, journal] = parseCitation(citation).map(escapeHtml);
            const safeRef = escapeHtml(ref);
            const citationToDisplay = `<strong>${safeRef} ${title}<br>${authors}<br>${journal}</strong>`;

            const pmid = String(citationObj[citation].PMID || '');
            const original = String(citationObj[citation].URL || '');
            const href = /^\d{1,12}$/.test(pmid) ? `reference.html?pmid=${encodeURIComponent(pmid)}` : /^https:\/\//i.test(original) ? original : '#';
            return `<a href="${escapeHtml(href)}" target="_blank" rel="noopener">${citationToDisplay}</a> - ${analysisText}`;
        })
        .filter(Boolean)
        .join('<br><br>');

    return `<b>References:</b><br><br> ${referenceList}`;
};
  
  // Function to normalize reference numbers
  const normalizeReference = (ref) => {
    // Remove any non-digit characters and convert to a number
    return parseInt(ref.replace(/\D/g, ''), 10);
  };

/**
 * Extracts references from the given output.
 *
 * @param {string} output - The output containing references.
 * @return {Array} An array of references.
 */
const extractReferences = (output) => {
    const referenceMarkers = [
        "References:", 
        "References", 
        "Reference:", 
        "### References", 
        "### References:", 
        "#### References", 
        "#### References:", 
        "**References:**", 
        "**References**:", 
        "**References**", 
        "Reference"
      ];
      
      // Initialize referencePart as undefined
      let referencePart = undefined;
      
      // Loop through each marker and try to find a match
      for (const marker of referenceMarkers) {
        if (output.includes(marker)) {
          // Split using the first matching marker and break the loop
          referencePart = output.split(marker)[1];
          break;
        }
      }
    
    if (!referencePart) return [];
  
    // Use a regex that matches both [n] and n. formats
    const referenceRegex = /(\[\d+\]|\d+\.)/g;
    
    // Find all matches
    const matches = referencePart.match(referenceRegex) || [];
    
    // Normalize and deduplicate the matches
    const uniqueReferences = [...new Set(matches.map(normalizeReference))];
    
    // Convert back to original format, preferring [n] over n.
    return uniqueReferences.map(num => matches.find(ref => normalizeReference(ref) === num) || `[${num}]`);
  };

/**
 * Finds the citation corresponding to the given reference.
 *
 * @param {string} ref - The reference.
 * @param {Array} citations - The array of citations.
 * @return {string|undefined} The citation corresponding to the reference, or undefined if not found.
 */
const findCitation = (ref, citations) => {
  const refNumber = ref.match(/\d+/)[0];
  return citations.find((citation) => citation.startsWith(`[${refNumber}]`) || citation.startsWith(`${refNumber}.`));
};


/**
 * Returns the analysis text based on whether the citation has full text or not.
 *
 * @param {boolean} fullText - Indicates whether the citation has full text.
 * @return {string} The analysis text.
 */
const getAnalysisText = (fullText) => {
  const iconStyle = 'width: 16px; height: 16px; vertical-align: middle; margin-right: 4px;';
  const analysisText = fullText ? 'Full Text Analysis' : 'Abstract Only Analysis';
  const imageUrl = fullText ? 'assets/full_text.png' : 'assets/abstract.png';
  return `<span style="color: black; font-weight: bold; border: 1px solid ${fullText ? 'green' : 'yellow'}; padding: 2px 4px; background-color: rgba(${fullText ? '0, 128, 0' : '255, 255, 0'}, 0.1); display: inline-flex; align-items: center;"><img src="${imageUrl}" alt="" style="${iconStyle}">${analysisText}</span>`;
};


/**
 * Formats the input text by replacing newline characters with `<br>`,
 * double asterisks with `<strong>`, triple hashes with `<strong>`,
 * and hyphens or asterisks with `<li>`.
 *
 * @param {string} input - The input text to be formatted.
 * @param {string} disclaimer - The disclaimer to be appended to the formatted text.
 * @return {string} The formatted text.
 */
const escapeHtml = (input) => String(input ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');

function parseAnswerTable(lines, start) {
    const split = line => line.trim().replace(/^\||\|$/g, '').split('|').map(cell => cell.trim());
    if (start + 2 >= lines.length || !lines[start].includes('|') || !/^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(lines[start+1])) return null;
    const headers = split(lines[start]);
    if (headers.length < 2 || headers.length > 8 || split(lines[start+1]).length !== headers.length) return null;
    const rows = []; let end = start + 2;
    while (end < lines.length && lines[end].includes('|') && rows.length < 30) {
        const cells = split(lines[end]); if (cells.length !== headers.length) break;
        rows.push(cells); end++;
    }
    if (!rows.length) return null;
    return {headers, rows, end};
}
function answerTableMarkup(table) {
    const cells = table.rows.map(row => `<tr>${row.map(cell => `<td>${escapeHtml(cell)}</td>`).join('')}</tr>`).join('');
    return `<div class="answer-table-scroll"><table><thead><tr>${table.headers.map(cell => `<th>${escapeHtml(cell)}</th>`).join('')}</tr></thead><tbody>${cells}</tbody></table></div>`;
}
function chartData(table) {
    // Chart only a simple category + one numeric measure. Units must not be mixed.
    if (table.headers.length !== 2 || table.rows.length < 2 || table.rows.length > 12) return null;
    const values = table.rows.map(row => Number(row[1].replace(/,/g, '')));
    if (values.some((n,i) => !Number.isFinite(n) || n < 0 || !/^\d+(?:,\d{3})*(?:\.\d+)?$/.test(table.rows[i][1])) || Math.max(...values) <= 0) return null;
    if (table.rows.some(row => !row[0] || row[0].length > 50)) return null;
    return values;
}
function answerChartMarkup(table, values) {
    const max = Math.max(...values);
    return `<div class="answer-chart" role="img" aria-label="Chart of ${escapeHtml(table.headers[1])} by ${escapeHtml(table.headers[0])}"><strong>${escapeHtml(table.headers[1])} by ${escapeHtml(table.headers[0])}</strong>${table.rows.map((row,i) => `<div class="chart-row"><span>${escapeHtml(row[0])}</span><div class="chart-track"><div class="chart-bar" style="width:${Math.max(0,Math.min(100,values[i]/max*100)).toFixed(2)}%"></div></div><b>${escapeHtml(row[1])}</b><button type="button" class="ask-chart-point" data-category="${escapeHtml(row[0])}" data-value="${escapeHtml(row[1])}" data-measure="${escapeHtml(table.headers[1])}" aria-label="Ask about ${escapeHtml(row[0])}">Ask</button></div>`).join('')}</div>`;
}
const formatPlainAnswer = text => escapeHtml(text).replace(/\n/g, '<br>').replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>').replace(/### (.*?)(<br>|$)/g, '<strong>$1</strong>$2').replace(/[-*] (.*?)(<br>|$)/g, '<li>$1</li>');
const formatText = (input) => {
    const lines = String(input ?? '').split(/\r?\n/);
    const fragments = [], plain = [];
    const flush = () => { if (plain.length) { fragments.push(formatPlainAnswer(plain.join('\n'))); plain.length = 0; } };
    for (let i=0; i<lines.length;) {
        const table = parseAnswerTable(lines,i);
        if (!table) { plain.push(lines[i]); i++; continue; }
        flush();
        const values = chartData(table);
        if (values) {
            fragments.push(`<div class="answer-data"><button type="button" class="table-chart-toggle" aria-expanded="false">View as chart</button><div class="answer-table-view">${answerTableMarkup(table)}</div><div class="answer-chart-view" hidden>${answerChartMarkup(table,values)}</div></div>`);
        } else fragments.push(answerTableMarkup(table));
        i = table.end;
    }
    flush(); return fragments.join('<br>');
};

/**
 * Generates a PDF document based on the formatted text content.
 */
const generatePDF = async () => {
    const id = getConversationId();
    const button = document.getElementById('generate-pdf-button');
    const oldLabel = button.textContent;
    button.disabled = true;
    button.textContent = 'Preparing PDF...';
    try {
        if (!window.jspdf?.jsPDF) throw new Error('PDF library unavailable. Try again after reconnecting.');
        if (!id) throw new Error('Choose a saved conversation before downloading.');
        const response = await apiFetch(`/session_memory?conversation_id=${encodeURIComponent(id)}`);
        if (!response.ok) throw new Error(await DietNerdAPI.readError(response, 'Could not load the conversation for export.'));
        const entries = (await response.json()).entries || [];
        if (!entries.length) throw new Error('This conversation has no saved answers yet.');
        const selected = Array.from(document.getElementById('conversation-select').options).find(option => option.value === id);
        const title = selected?.textContent?.trim() || 'DietNerd conversation';
        const filename = (title.replace(/[<>:"/\\|?*\x00-\x1f]/g, '').trim().replace(/\s+/g, ' ').slice(0, 90) || 'DietNerd conversation') + '.pdf';
        const doc = new window.jspdf.jsPDF({unit:'mm',format:'a4'});
        const width = doc.internal.pageSize.getWidth();
        const height = doc.internal.pageSize.getHeight();
        const margin = 18, contentWidth = width - 2 * margin;
        let y = margin;
        const pageIfNeeded = (lines = 1, leading = 6) => {
            if (y + lines * leading > height - margin) { doc.addPage(); y = margin; }
        };
        const write = (text, {size = 10, bold = false, leading = 6, indent = 0, gap = 0} = {}) => {
            doc.setFont('helvetica', bold ? 'bold' : 'normal'); doc.setFontSize(size);
            const lines = doc.splitTextToSize(String(text || ''), contentWidth - indent);
            for (const line of lines) { pageIfNeeded(1, leading); doc.text(line, margin + indent, y); y += leading; }
            y += gap;
        };
        doc.setProperties({title, subject:'DietNerd conversation export', creator:'DietNerd'});
        doc.setFillColor(23,63,53); doc.rect(0,0,width,7,'F');
        y = 22;
        write('DIETNERD / CONVERSATION', {size:9,bold:true,leading:6,gap:2});
        write(title, {size:17,bold:true,leading:9,gap:3});
        write(`${entries.length} answer${entries.length === 1 ? '' : 's'} · Exported ${new Date().toLocaleDateString()}`, {size:9,leading:5,gap:5});
        doc.setDrawColor(180,198,181); doc.line(margin,y,width-margin,y); y += 10;
        entries.forEach((entry, index) => {
            pageIfNeeded(5);
            write(`QUESTION ${String(index + 1).padStart(2,'0')}`, {size:9,bold:true,leading:6,gap:1});
            write(entry.raw_question || 'Question unavailable', {size:12,bold:true,leading:7,gap:6});
            const lines = String(entry.answer || '').split(/\r?\n/);
            for (let i=0; i<lines.length;) {
                const table = parseAnswerTable(lines,i);
                if (table) {
                    y += 2;
                    [table.headers,...table.rows].forEach((row,rowIndex) => {
                        pageIfNeeded(1,6);
                        write(row.join('  |  '), {size:9,bold:rowIndex===0,leading:5});
                    });
                    y += 3; i=table.end; continue;
                }
                const line = lines[i++].trim();
                if (!line) { y += 2; continue; }
                const heading = line.match(/^#{1,6}\s+(.+)$/);
                if (heading) { y += 2; write(heading[1].replace(/\*\*/g,''), {size:11,bold:true,leading:7,gap:2}); continue; }
                const bullet = line.match(/^[-*]\s+(.+)$/);
                if (bullet) { write('•  ' + bullet[1].replace(/\*\*/g,''), {indent:4,leading:6}); continue; }
                write(line.replace(/\*\*/g,''), {leading:6});
            }
            y += 7;
            doc.setDrawColor(205,219,206); if (index < entries.length-1) { pageIfNeeded(1); doc.line(margin,y,width-margin,y); y += 9; }
        });
        y += 4;
        write('DietNerd is an exploratory tool. Check important health information with a qualified professional.', {size:8,leading:5});
        const pages = doc.internal.getNumberOfPages();
        for (let page=1;page<=pages;page++) {
            doc.setPage(page); doc.setFont('helvetica','normal'); doc.setFontSize(8); doc.setTextColor(100,112,102);
            doc.text(`DietNerd  ·  ${page} / ${pages}`,width-margin,height-10,{align:'right'});
        }
        doc.save(filename);
    } catch (error) {
        document.querySelector('.hint').textContent = error.message || 'Could not prepare PDF.';
    } finally {
        button.disabled = false;
        button.textContent = oldLabel;
    }
};

/**
 * Runs the generation process for the given user query.
 *
 * @param {string} userQuery - The user query to generate the search phrases for.
 * @return {Promise<void>} - A promise that resolves when the generation process is complete.
 */
let attachmentExists = false;
// Answering the question from the attachment
function renderAttachmentChip(name, state = 'ready') {
    const item = document.createElement('span');
    item.className = `existing-attachment-item ${state === 'uploading' ? 'uploading' : ''}`;
    const icon = document.createElement('span');
    icon.className = 'attachment-file-icon';
    icon.setAttribute('aria-hidden', 'true');
    icon.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="#173f35" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 2.5h8l4 4V21H6z"/><path d="M14 2.5V7h4M9 11h6M9 15h6"/></svg>';
    const filename = document.createElement('span');
    filename.className = 'attachment-name';
    filename.textContent = name;
    filename.title = name;
    item.append(icon, filename);
    if (state === 'uploading') {
        const meter = document.createElement('span');
        meter.className = 'attachment-meter';
        meter.setAttribute('aria-hidden', 'true');
        item.append(meter);
    } else {
        const removeButton = document.createElement('button');
        removeButton.type = 'button';
        removeButton.className = 'existing-attachment-remove';
        removeButton.dataset.filename = name;
        removeButton.textContent = '×';
        removeButton.setAttribute('aria-label', `Remove ${name}`);
        item.append(removeButton);
    }
    return item;
}

async function refreshExistingAttachments() {
    const existingAttachmentsElement = document.getElementById('existing-attachments');
    const label = document.getElementById('attachment-label');
    const response = await apiFetch('/list_attachments');
    if (!response.ok) throw new Error(await DietNerdAPI.readError(response, `Could not load attachments (${response.status}).`));
    const data = await response.json();
    const documentNames = Array.isArray(data.documents) ? data.documents : [];
    attachmentExists = documentNames.length > 0;
    if (temporaryChat) return;
    existingAttachmentsElement.replaceChildren(...documentNames.map(name => renderAttachmentChip(name)));
    label.textContent = attachmentExists ? '' : 'No file attached';
}

document.addEventListener('DOMContentLoaded', function () {
    const fileInput = document.getElementById('attachment-file');
    const existingAttachmentsElement = document.getElementById('existing-attachments');

    refreshExistingAttachments().catch((err) => { document.getElementById('attachment-label').textContent = err.message; });
    document.getElementById('new-conversation').click();
    refreshConversationList();

    fileInput.addEventListener('change', async function () {
        if (temporaryChat) {
            const selected = fileInput.files[0];
            fileInput.value = '';
            if (!selected) return;
            if (!/\.(pdf|txt|csv)$/i.test(selected.name) || selected.size > 5 * 1024 * 1024 || !selected.size) {
                document.getElementById('attachment-label').textContent = 'Choose a PDF, TXT or CSV file up to 5 MB.';
                return;
            }
            temporaryFile = selected;
            existingAttachmentsElement.replaceChildren(renderAttachmentChip(selected.name));
            document.getElementById('attachment-label').textContent = 'Temporary file, not saved to your account';
            return;
        }
        if (!fileInput.files.length) return;
        const file = fileInput.files[0];
        fileInput.value = '';
        const formData = new FormData();
        formData.append('attachment', file);
        const label = document.getElementById('attachment-label');
        const attachButton = document.getElementById('attach-button');
        attachButton.disabled = true;
        existingAttachmentsElement.append(renderAttachmentChip(file.name, 'uploading'));
        label.textContent = `Uploading ${file.name}...`;
        label.classList.add('upload-active');
        try {
            const response = await apiFetch('/upload_attachment', { method: 'POST', body: formData });
            if (!response.ok) {
                label.textContent = await DietNerdAPI.readError(response, `Upload failed (${response.status}). Please try again.`);
                await refreshExistingAttachments().catch(() => {});
                return;
            }
            await refreshExistingAttachments();
            label.textContent = `${file.name} attached`;
        } catch (err) {
            existingAttachmentsElement.querySelector('.uploading')?.remove();
            label.textContent = `Could not upload ${file.name}. Check your connection and try again.`;
            console.error('Attachment upload failed:', err);
        } finally {
            attachButton.disabled = false;
            label.classList.remove('upload-active');
        }
    });

    existingAttachmentsElement.addEventListener('click', async function (event) {
        const removeButton = event.target.closest('.existing-attachment-remove');
        if (temporaryChat && removeButton) {
            temporaryFile = null;
            fileInput.value = '';
            existingAttachmentsElement.replaceChildren();
            document.getElementById('attachment-label').textContent = 'No temporary file attached';
            return;
        }
        if (!removeButton || removeButton.disabled) return;
        const filename = removeButton.dataset.filename;
        const chip = removeButton.closest('.existing-attachment-item');
        removeButton.disabled = true;
        chip.classList.add('removing');
        removeButton.setAttribute('aria-label', `Removing ${filename}`);
        document.getElementById('attachment-label').textContent = `Removing ${filename}...`;
        try {
            const response = await apiFetch(`/remove_attachment?filename=${encodeURIComponent(filename)}`, { method: 'DELETE' });
            if (!response.ok) throw new Error(await DietNerdAPI.readError(response, `Could not remove attachment (${response.status}).`));
            await refreshExistingAttachments();
        } catch (err) {
            chip.classList.remove('removing');
            removeButton.disabled = false;
            removeButton.setAttribute('aria-label', `Remove ${filename}`);
            document.getElementById('attachment-label').textContent = err.message || `Could not remove ${filename}. Try again.`;
            console.error('Attachment removal failed:', err);
        }
    });
});

/**
 * Shows an assistant bubble with live progress while an answer is generated.
 */
function appendPendingMessage() {
    const thread = document.getElementById('chat-thread');
    const article = document.createElement('article');
    article.className = 'chat-message assistant pending';
    const avatar = document.createElement('span');
    avatar.className = 'assistant-avatar';
    avatar.innerHTML = '<img src="assets/dietnerd_mark.svg" alt="">';
    avatar.setAttribute('aria-label', 'DietNerd');
    const content = document.createElement('div');
    content.className = 'message-content';
    const status = document.createElement('p');
    status.className = 'pending-status';
    status.textContent = 'Looking at your question...';
    const note = document.createElement('p');
    note.className = 'pending-note';
    note.textContent = 'Searching published research can take a minute. Please keep this page open.';
    const journey = document.createElement('section');
    journey.className = 'research-journey';
    journey.setAttribute('aria-label', 'Research journey');
    const journeyHead = document.createElement('div');
    journeyHead.className = 'research-journey-head';
    const journeyTitle = document.createElement('strong');
    journeyTitle.textContent = 'Research journey';
    const elapsed = document.createElement('span');
    elapsed.className = 'research-elapsed';
    elapsed.textContent = 'Just started';
    journeyHead.append(journeyTitle, elapsed);
    const steps = document.createElement('ol');
    steps.className = 'research-steps';
    const articleList = document.createElement('div');
    articleList.className = 'progress-articles';
    const labels = ['Understand the question', 'Find research', 'Check relevant studies', 'Write the answer'];
    labels.forEach(label => {
        const step = document.createElement('li');
        const marker = document.createElement('span'); marker.className = 'research-step-marker'; marker.setAttribute('aria-hidden', 'true');
        const name = document.createElement('span'); name.textContent = label;
        step.append(marker, name); steps.append(step);
    });
    journey.append(journeyHead, steps);
    let stage = 0;
    let latestStatus = '';
    const replay = [];
    const record = (label) => { if (replay.at(-1) !== label && replay.length < 24) replay.push(label); };
    record('Question received');
    const startedAt = Date.now();
    function renderStage() {
        [...steps.children].forEach((step, index) => {
            step.classList.toggle('active', index === stage);
            step.classList.toggle('complete', index < stage);
            if (index === stage) step.setAttribute('aria-current', 'step');
            else step.removeAttribute('aria-current');
        });
        journey.setAttribute('aria-label', `Research journey: ${labels[stage]}`);
    }
    renderStage();
    const stageTimer = window.setInterval(() => {
        const seconds = Math.floor((Date.now() - startedAt) / 1000);
        if (!journey.classList.contains('paused')) elapsed.textContent = seconds < 60 ? `${seconds}s elapsed` : `${Math.floor(seconds / 60)}m ${String(seconds % 60).padStart(2, '0')}s elapsed`;
    }, 1000);
    content.append(status, note, journey, articleList);
    article.append(avatar, content);
    thread.appendChild(article);
    enterConversationMode();
    thread.scrollTop = thread.scrollHeight;
    return {
        replay() { return replay.slice(); },
        addArticles(update) {
            articleList.replaceChildren();
            const heading = document.createElement('strong');
            heading.textContent = update.stage === 'relevant' ? 'Relevant paper titles found' : 'Paper titles found';
            const list = document.createElement('ul');
            (update.article_titles || []).slice(0,5).forEach(title => { const li = document.createElement('li'); li.textContent = title; list.appendChild(li); });
            articleList.append(heading, list);
            record(update.stage === 'relevant' ? 'Relevant paper titles retrieved' : 'Paper titles retrieved');
            stage = Math.max(stage, update.stage === 'relevant' ? 2 : 1);
            renderStage();
            note.textContent = update.note || 'Retrieved titles do not prove support for the answer.';
            thread.scrollTop = thread.scrollHeight;
        },
        setStatus(text) {
            if (text === latestStatus) return;
            latestStatus = text;
            if (/Generated PubMed queries|Retrieved .* Articles|Classified .* Relevant Articles|Processed .* Articles/i.test(text)) record(text.slice(0,130));
            status.textContent = text;
            if (/Connection interrupted/i.test(text)) {
                journey.classList.add('paused');
                elapsed.textContent = 'Reconnecting';
                return;
            }
            journey.classList.remove('paused');
            if (/Generated PubMed queries|Retrieved .* Articles/i.test(text)) stage = Math.max(stage, 1);
            if (/Classified .* Relevant Articles|Processed .* Articles/i.test(text)) stage = Math.max(stage, 2);
            if (/Processed .* Articles/i.test(text)) stage = 3;
            renderStage();
        },
        remove() { window.clearInterval(stageTimer); article.remove(); },
        fail(message, retry) {
            window.clearInterval(stageTimer);
            article.classList.remove('pending');
            article.classList.add('failed');
            content.replaceChildren();
            const text = document.createElement('p');
            text.textContent = message;
            content.appendChild(text);
            if (retry) {
                const button = document.createElement('button');
                button.type = 'button';
                button.className = 'message-sources-button';
                button.textContent = 'Try again';
                button.addEventListener('click', () => { article.remove(); retry(); });
                content.appendChild(button);
            }
        },
    };
}

function appendEvidenceLedger(content, ledger) {
    if (!ChronicNerdAddons.enabled('ledger')) return;
    if (!Array.isArray(ledger) || !ledger.length) return;
    const details = document.createElement('details');
    details.className = 'evidence-ledger';
    const summary = document.createElement('summary');
    summary.textContent = `Evidence check · ${ledger.length} cited claim${ledger.length === 1 ? '' : 's'}`;
    details.append(summary);
    ledger.forEach(row => {
        const entry = document.createElement('div');
        entry.className = 'evidence-ledger-entry';
        const claim = document.createElement('p');
        claim.textContent = `${row.citation_marker || ''} ${row.claim || ''}`;
        const source = document.createElement('p');
        source.textContent = row.source_title
            ? `Source: ${row.source_title}` : 'Source unresolved';
        const status = document.createElement('p');
        status.textContent = row.evidence_note || 'Support not independently verified.';
        entry.append(claim, source, status);
        if (row.source_url && /^https:\/\//.test(row.source_url)) {
            const link = document.createElement('a');
            link.href = row.source_url;
            link.textContent = 'Open source';
            link.target = '_blank';
            link.rel = 'noopener noreferrer';
            entry.append(link);
        }
        details.append(entry);
    });
    content.append(details);
}

function appendFollowups(content, question, answer) {
    if (!String(question || '').trim() || !String(answer || '').trim()) return;
    const options = [
        'What are the main limits of the evidence in your last answer?',
        'Who might respond differently, and why?',
        'What should I ask a dietitian about this?',
    ];
    const box = document.createElement('div');
    box.className = 'answer-followups';
    const title = document.createElement('p');
    title.textContent = 'Keep exploring';
    box.append(title);
    options.forEach(text => {
        const button = document.createElement('button');
        button.type = 'button';
        button.textContent = text;
        button.addEventListener('click', () => {
            if (questionInFlight) return;
            document.getElementById('question').value = text;
            document.getElementById('submit').click();
        });
        box.append(button);
    });
    content.append(box);
}

function showAssistantAnswer(answer, ledger = [], question = '', storedSources = null, replay = null) {
    const content = appendChatMessage('assistant', answer, [], storedSources);
    appendEvidenceLedger(content, ledger);
    appendInChatSources(content, sourcesForAnswer(answer, ledger, storedSources));
    appendFollowups(content, question, answer);
    if (replay?.length) appendResearchReplay(content, replay);
    if (!temporaryChat) document.getElementById('generate-pdf-button').classList.remove('hidden');
}

function conversationHasTurns() {
    return Boolean(getConversationId()) && document.querySelectorAll('#chat-thread .chat-message.user').length > 1;
}

let questionInFlight = false;
// Answer mode is a per-question choice, not a persistent account profile setting.
document.getElementById('answer-mode').addEventListener('change', event => {
    if (questionInFlight) { event.target.value = 'light'; return; }
    document.querySelector('.hint').textContent = event.target.value === 'heavy'
        ? 'Heavy combines PubMed research with the paper you choose. It takes longer.'
        : 'Light uses the standard research path.';
});
let selectedSuggestion = false;
function setComposerBusy(busy) {
    questionInFlight = busy;
    document.getElementById('submit').disabled = busy;
    document.getElementById('use-profile').disabled = busy || temporaryChat;
    document.getElementById('answer-mode').disabled = busy;
    document.getElementById('question').setAttribute('aria-busy', busy ? 'true' : 'false');
}

async function runGeneration(userQuery, pending) {
    const isTemporary = temporaryChat;
    const paperFile = paperContext?.file || null;
    const file = paperFile || (isTemporary ? temporaryFile : null);
    const payload = { user_query: userQuery, conversation_id: getConversationId(), temporary: isTemporary, use_profile: !isTemporary && document.getElementById('use-profile').checked, temporary_history: isTemporary ? temporaryTurns.slice(-8) : [], answer_mode: document.getElementById('answer-mode').value };
    if (paperContext?.pmid) payload.paper_pmid = paperContext.pmid;
    if (file) {
        const bytes = new Uint8Array(await file.arrayBuffer());
        let binary = '';
        for (let i = 0; i < bytes.length; i += 8192) binary += String.fromCharCode(...bytes.subarray(i, i + 8192));
        payload.attachment_filename = file.name;
        payload.attachment_base64 = btoa(binary);
    }
    const endpoint = paperFile ? '/process_query/paper_pdf' : file ? '/process_query/temporary_attachment' : '/process_query';
    const response = await apiFetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });
    if (!response.ok) {
        throw new Error(await DietNerdAPI.readError(response, `The question could not be sent (${response.status}).`));
    }
    const data = await response.json();
    if (!isTemporary) {
        sessionStorage.setItem('dietnerd_conversation_id', data.conversation_id);
        refreshConversationList();
    }

    return new Promise((resolve, reject) => {
        const eventSource = new EventSource(`${baseURL}/sse?request_id=${encodeURIComponent(data.request_id)}`, { withCredentials: true });
        let lostAt = 0;
        const reconnectTimer = window.setInterval(() => {
            // EventSource retries transient failures. A lasting failure should
            // not leave the send button locked forever.
            if (lostAt && Date.now() - lostAt > 60000) {
                window.clearInterval(reconnectTimer);
                eventSource.close();
                if (isTemporary) {
                    reject(new Error('Research connection did not recover. Temporary answers cannot be restored after a disconnect.'));
                } else {
                    readConversationHistory(data.conversation_id).then(async history => {
                        if (!history.ok) throw new Error('Could not retrieve the saved research answer.');
                        const saved = (await history.json()).entries?.find(entry => entry.request_id === data.request_id);
                        if (saved?.answer) resolve({end_output:saved.answer, session_memory_entry:saved});
                        else reject(new Error('Research connection did not recover. Open this conversation from history to check whether the answer finished.'));
                    }).catch(reject);
                }
            }
        }, 1000);
        eventSource.onopen = () => {
            if (lostAt && pending) pending.setStatus('Connected again. Catching up on research...');
            lostAt = 0;
        };
        eventSource.onmessage = (event) => {
            let message;
            try { message = JSON.parse(event.data); }
            catch { return; }
            if (!message.update) return;
            if (message.update.end_output) {
                window.clearInterval(reconnectTimer);
                eventSource.close();
                if (!isTemporary) try {
                    localStorage.setItem('referenceObject', JSON.stringify(message.update.citations_obj || {}));
                    localStorage.setItem('citations', JSON.stringify(message.update.citations || []));
                } catch (error) { console.warn('Could not save reference metadata locally.'); }
                resolve(message.update);
            } else if (message.update.article_titles && pending) {
                pending.addArticles(message.update);
            } else if (pending) {
                pending.setStatus(String(message.update));
            }
        };
        eventSource.onerror = () => {
            if (!lostAt) lostAt = Date.now();
            if (pending) pending.setStatus('Connection interrupted. Reconnecting to the same research request...');
        };
    });
}

async function generateAnswer(question) {
    const pending = appendPendingMessage();
    setComposerBusy(true);
    try {
        const validity = await check_valid(question);
        if (validity && validity.response && validity.response !== 'good') {
            pending.remove();
            appendChatMessage('assistant', validity.response);
            return;
        }
        const result = await runGeneration(question, pending);
        pending.remove();
        showAssistantAnswer(result.end_output, result.evidence_ledger || [], question, result.session_memory_entry?.sources || null, pending.replay());
        if (temporaryChat) temporaryTurns.push({raw_question: question.slice(0, 2000), answer: result.end_output.slice(0, 15000)});
        refreshTitleAfterAnswer(getConversationId());
    } catch (err) {
        console.error(err);
        pending.fail(`${err.message || 'Something went wrong.'} Please try again.`, () => generateAnswer(question));
    } finally {
        setComposerBusy(false);
    }
}

async function answerFromAttachment(question) {
    const pending = appendPendingMessage();
    pending.setStatus('Reading your attached file...');
    setComposerBusy(true);
    try {
        const result = await runGeneration(question, pending);
        pending.remove();
        showAssistantAnswer(result.end_output, result.evidence_ledger || [], question, result.session_memory_entry?.sources || null, pending.replay());
        refreshTitleAfterAnswer(getConversationId());
    } catch (err) {
        console.error(err);
        pending.fail(`${err.message || 'Something went wrong.'} Please try again.`, () => answerFromAttachment(question));
    } finally {
        setComposerBusy(false);
    }
}

function offerSimilarQuestions(question, similar) {
    const container = document.getElementById('similarQuestions');
    const hintElement = document.querySelector('.hint');
    container.replaceChildren();
    hintElement.textContent = '';
    const seen = new Set([question.trim().toLocaleLowerCase().replace(/\s+/g, ' ')]);
    const unique = (Array.isArray(similar) ? similar : []).filter((item) => {
        const text = String(item?.[1] || '').trim();
        const key = text.toLocaleLowerCase().replace(/\s+/g, ' ');
        if (!key || seen.has(key)) return false;
        seen.add(key);
        return true;
    }).slice(0, 4);
    if (unique.length) {
        const title = document.createElement('p');
        title.className = 'similar-title';
        title.textContent = 'Related questions with saved answers';
        container.append(title);
        const choices = document.createElement('div');
        choices.className = 'similar-choices';
        unique.forEach((item) => {
            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'related-question-choice';
            button.textContent = String(item[1]);
            button.addEventListener('click', () => {
                container.style.display = 'none';
                hintElement.textContent = '';
                const last = Array.from(document.querySelectorAll('#chat-thread .chat-message.user')).at(-1);
                if (last) last.remove();
                selectedSuggestion = true;
                document.getElementById('question').value = String(item[1]);
                document.getElementById('submit').click();
            });
            choices.appendChild(button);
        });
        container.append(choices);
    }
    const original = document.createElement('button');
    original.type = 'button';
    original.className = 'generate-original';
    original.textContent = 'Answer my question';
    original.addEventListener('click', () => {
        container.style.display = 'none';
        hintElement.textContent = '';
        generateAnswer(question);
    });
    container.appendChild(original);
    container.style.display = 'flex';
}

document.getElementById('submit').addEventListener('click', async () => {
    const input = document.getElementById('question');
    const question = input.value.trim();
    const similarQuestionsContainer = document.getElementById('similarQuestions');
    const hintElement = document.querySelector('.hint');
    if (questionInFlight) return;
    if (!question) {
        hintElement.textContent = 'Please type a question first.';
        return;
    }
    if (temporaryChat && question.length > 2000) {
        hintElement.textContent = 'Temporary questions must be 2,000 characters or fewer.';
        return;
    }
    document.getElementById('generate-pdf-button').classList.add('hidden');
    document.getElementById('example-questions')?.classList.add('hidden');
    similarQuestionsContainer.style.display = 'none';
    hintElement.textContent = '';
    const useSelectedSuggestion = selectedSuggestion;
    selectedSuggestion = false;
    appendChatMessage('user', question);
    input.value = '';

    if (paperContext) {
        await generateAnswer(question);
        return;
    }

    if (attachmentExists && !temporaryChat) {
        await answerFromAttachment(question);
        return;
    }

    if (temporaryChat || document.getElementById('use-profile').checked || document.getElementById('answer-mode').value === 'heavy') {
        // Generic cache and similar saved answers cannot include this account's profile.
        await generateAnswer(question);
        return;
    }

    setComposerBusy(true);
    const initialStatus = appendPendingMessage();
    initialStatus.setStatus('Checking for a saved answer...');
    let cachedAnswer = null;
    try {
        if (!useSelectedSuggestion && !conversationHasTurns()) cachedAnswer = await getAnswer(question);
    } catch (err) {
        cachedAnswer = null;
    } finally {
        initialStatus.remove();
    }
    if (cachedAnswer) {
        setComposerBusy(false);
        showAssistantAnswer(cachedAnswer.answer, [], question, cachedAnswer.sources);
        refreshTitleAfterAnswer(getConversationId());
        return;
    }

    // Follow-ups inside a conversation go straight to generation so the
    // earlier turns are used to understand the question.
    if (useSelectedSuggestion || conversationHasTurns()) {
        setComposerBusy(false);
        await generateAnswer(question);
        return;
    }
    let similar = [];
    const searchStatus = appendPendingMessage();
    searchStatus.setStatus('Finding related questions...');
    try {
        similar = await get_sim(question);
    } catch (err) {
        similar = [];
    } finally {
        searchStatus.remove();
        setComposerBusy(false);
    }
    offerSimilarQuestions(question, similar || []);
});


document.getElementById('history-toggle').addEventListener('click', () => {
    const sidebar = document.querySelector('.chat-sidebar');
    const open = sidebar.classList.toggle('history-open');
    document.getElementById('history-toggle').setAttribute('aria-expanded', String(open));
});
document.getElementById('conversation-list').addEventListener('click', (event) => {
    const row = event.target.closest('.conversation-row');
    if (!row) return;
    document.getElementById('conversation-select').value = row.dataset.conversationId;
    document.getElementById('conversation-select').dispatchEvent(new Event('change'));
    document.querySelector('.chat-sidebar').classList.remove('history-open');
    document.getElementById('history-toggle').setAttribute('aria-expanded', 'false');
});

document.getElementById('conversation-select').addEventListener('change', async (event) => {
    const conversationId = event.target.value;
    if (!conversationId) {
        document.getElementById('new-conversation').click();
        return;
    }
    if (questionInFlight) {
        document.getElementById('conversation-select').value = getConversationId() || '';
        return;
    }
    temporaryChat = false;
    clearPaperScope();
    document.body.classList.remove('temporary-mode');
    temporaryTurns = [];
    temporaryFile = null;
    document.getElementById('attachment-file').value = '';
    document.getElementById('existing-attachments').replaceChildren();
    refreshExistingAttachments().catch(() => {});
    document.getElementById('attach-button').title = 'Attach a file';
    document.getElementById('temporary-chat').setAttribute('aria-pressed', 'false');
    document.getElementById('delete-conversation').hidden = false;
    document.getElementById('attach-button').disabled = false;
    document.getElementById('existing-attachments').hidden = false;
    document.getElementById('attachment-label').textContent = attachmentExists ? '' : 'No file attached';
    document.getElementById('chat-title').textContent = 'DietNerd assistant';
    sessionStorage.setItem('dietnerd_conversation_id', conversationId);
    setProfileUseUI(conversationProfileSettings.get(conversationId) !== false);
    await renderSelectedConversation(conversationId);
    document.querySelectorAll('.conversation-row').forEach(row => {
        const active = row.dataset.conversationId === conversationId;
        row.classList.toggle('active', active);
        if (active) row.setAttribute('aria-current', 'true');
        else row.removeAttribute('aria-current');
    });
});

document.getElementById('temporary-chat').addEventListener('click', () => {
    if (questionInFlight) return;
    document.getElementById('new-conversation').click();
    temporaryChat = true;
    clearPaperScope();
    document.body.classList.add('temporary-mode');
    setProfileUseUI(false, true);
    temporaryTurns = [];
    temporaryFile = null;
    document.getElementById('attachment-file').value = '';
    document.getElementById('existing-attachments').replaceChildren();
    document.getElementById('attach-button').title = 'Attach a temporary file';
    document.getElementById('temporary-chat').setAttribute('aria-pressed', 'true');
    document.getElementById('chat-title').textContent = 'Temporary chat';
    clearChatThread();
    document.getElementById('chat-thread').innerHTML = emptyStateMarkup(true);
    document.getElementById('delete-conversation').hidden = true;
    document.getElementById('attach-button').disabled = false;
    document.getElementById('existing-attachments').hidden = false;
    document.getElementById('attachment-label').textContent = 'No temporary file attached';
    document.querySelector('.hint').textContent = 'Not saved to your account. This tab clears when you leave or reload.';
});

document.getElementById('new-conversation').addEventListener('click', () => {
    if (questionInFlight) return;
    document.getElementById('attach-button').disabled = false;
    document.getElementById('existing-attachments').hidden = false;
    document.getElementById('attachment-label').textContent = attachmentExists ? '' : 'No file attached';
    temporaryChat = false;
    clearPaperScope();
    document.body.classList.remove('temporary-mode');
    setProfileUseUI(true);
    temporaryTurns = [];
    temporaryFile = null;
    document.getElementById('attachment-file').value = '';
    document.getElementById('existing-attachments').replaceChildren();
    refreshExistingAttachments().catch(() => {});
    document.getElementById('attach-button').title = 'Attach a file';
    document.getElementById('temporary-chat').setAttribute('aria-pressed', 'false');
    document.getElementById('chat-title').textContent = 'DietNerd assistant';
    document.getElementById('delete-conversation').hidden = false;
    enterConversationMode();
    closeSourcesPanel();
    ++conversationLoadToken;
    sessionStorage.removeItem('dietnerd_conversation_id');
    document.getElementById('conversation-select').value = '';
    document.querySelectorAll('.conversation-row.active').forEach(row => { row.classList.remove('active'); row.removeAttribute('aria-current'); });
    document.getElementById('question').value = '';
    clearChatThread();
    document.getElementById('chat-thread').innerHTML = emptyStateMarkup();
    document.getElementById('similarQuestions').style.display = 'none';
    document.getElementById('generate-pdf-button').classList.add('hidden');
    document.querySelector('.hint').textContent = '';
});

const deleteDialog = document.getElementById('delete-conversation-dialog');
const deleteConfirm = document.getElementById('delete-dialog-confirm');
let pendingDeleteId = null;
document.getElementById('delete-conversation').addEventListener('click', () => {
    const conversationId = getConversationId();
    if (!conversationId) {
        document.querySelector('.hint').textContent = 'Choose a conversation to delete.';
        return;
    }
    pendingDeleteId = conversationId;
    document.getElementById('delete-dialog-error').hidden = true;
    deleteDialog.showModal();
});
document.getElementById('delete-dialog-cancel').addEventListener('click', () => deleteDialog.close());
deleteDialog.addEventListener('close', () => { pendingDeleteId = null; });
deleteConfirm.addEventListener('click', async () => {
    const conversationId = pendingDeleteId;
    if (!conversationId || deleteConfirm.disabled) return;
    const error = document.getElementById('delete-dialog-error');
    error.hidden = true;
    deleteConfirm.disabled = true;
    deleteConfirm.textContent = 'Deleting...';
    deleteDialog.classList.add('deleting');
    try {
        const response = await apiFetch(`/conversations/${encodeURIComponent(conversationId)}`, {method: 'DELETE'});
        if (!response.ok) throw new Error(await DietNerdAPI.readError(response, `Could not delete this conversation (${response.status}).`));
        if (getConversationId() === conversationId) {
            sessionStorage.removeItem('dietnerd_conversation_id');
            document.getElementById('new-conversation').click();
        }
        deleteDialog.close();
        try { await refreshConversationList(); }
        catch { document.querySelector('.hint').textContent = 'Deleted. Refresh to update conversation history.'; }
    } catch (err) {
        error.textContent = err.message || 'Could not delete this conversation. Try again.';
        error.hidden = false;
    } finally {
        deleteConfirm.disabled = false;
        deleteConfirm.textContent = 'Delete conversation';
        deleteDialog.classList.remove('deleting');
    }
});

document.getElementById('generate-pdf-button').addEventListener('click', async(event) => {
    generatePDF();
});

// Event listener for the enter key on the input field
document.getElementById('question').addEventListener('keydown', (event) => {
    if (event.key === 'Enter') {
        event.preventDefault(); // Prevent the default form submission behavior
        document.getElementById('submit').click();
    }
});

document.getElementById('chat-thread').addEventListener('click', (event) => {
    const prompt = event.target.closest('.example-question');
    if (!prompt || questionInFlight) return;
    const input = document.getElementById('question');
    input.value = prompt.textContent.trim();
    input.dispatchEvent(new Event('input', { bubbles: true }));
    document.getElementById('submit').click();
});
for (const feature of ['ledger']) {
    const checkbox = document.getElementById(`sidebar-${feature}`);
    checkbox.checked = ChronicNerdAddons.enabled(feature);
    checkbox.addEventListener('change', () => {
        try { ChronicNerdAddons.setEnabled(feature, checkbox.checked); }
        catch { checkbox.checked = !checkbox.checked; }
    });
}
const composerInput = document.getElementById('question');
composerInput.addEventListener('input', () => { composerInput.style.height = 'auto'; composerInput.style.height = `${Math.min(composerInput.scrollHeight, 140)}px`; });

document.getElementById('close-sources').addEventListener('click', closeSourcesPanel);
document.addEventListener('keydown', event => { if (event.key === 'Escape') closeSourcesPanel(); });
if (getConversationId()) enterConversationMode();

// Desktop sidebar width is a local display preference, never conversation data.
(() => {
    const shell = document.querySelector('.chat-shell');
    const grip = document.getElementById('sidebar-resizer');
    const saved = Number(localStorage.getItem('dietnerd_sidebar_width'));
    const clamp = value => Math.max(220, Math.min(480, Math.round(value)));
    const apply = value => { const width = clamp(value); shell.style.setProperty('--sidebar-width', `${width}px`); grip.setAttribute('aria-valuenow', width); return width; };
    if (Number.isFinite(saved) && saved >= 220 && saved <= 480) apply(saved);
    let dragging = false;
    grip.addEventListener('pointerdown', e => {
        if (e.button !== 0 || matchMedia('(max-width: 800px)').matches) return;
        dragging = true;
        grip.setPointerCapture(e.pointerId);
        shell.classList.add('is-resizing');
        document.body.classList.add('sidebar-dragging');
        e.preventDefault();
    });
    grip.addEventListener('pointermove', e => { if (dragging) apply(e.clientX - shell.getBoundingClientRect().left); });
    const finish = () => {
        if (!dragging) return;
        dragging = false;
        shell.classList.remove('is-resizing');
        document.body.classList.remove('sidebar-dragging');
        localStorage.setItem('dietnerd_sidebar_width', grip.getAttribute('aria-valuenow'));
    };
    grip.addEventListener('pointerup', finish);
    grip.addEventListener('pointercancel', finish);
    grip.addEventListener('keydown', e => {
        if (!['ArrowLeft','ArrowRight','Home','End'].includes(e.key)) return;
        e.preventDefault();
        const next = e.key === 'Home' ? 220 : e.key === 'End' ? 480 : Number(grip.getAttribute('aria-valuenow')) + (e.key === 'ArrowLeft' ? -20 : 20);
        localStorage.setItem('dietnerd_sidebar_width', apply(next));
    });
})();


// First-time orientation: three skippable pointers, never blocks the composer.
(() => {
    const key = 'dietnerd_tour_seen';
    if (localStorage.getItem(key)) return;
    const tour = document.getElementById('onboarding-tour');
    const steps = [
        {target:'#question', heading:'Ask a nutrition question', body:'Type here or choose an example question to start.'},
        {target:'#temporary-chat', heading:'Choose your workspace', body:'Temporary chat is not saved to your account. Saved conversations stay in the history.'},
        {target:'.chat-header', heading:'Check the sources', body:'When an answer cites research, open its sources and read the study before relying on it.'},
    ];
    let step = 0;
    function close() { tour.hidden = true; localStorage.setItem(key,'1'); }
    function show() {
        const item = steps[step];
        const anchor = document.querySelector(item.target);
        if (!anchor) return close();
        document.getElementById('tour-count').textContent = `${step+1} / ${steps.length}`;
        document.getElementById('tour-heading').textContent = item.heading;
        document.getElementById('tour-body').textContent = item.body;
        document.getElementById('tour-next').textContent = step === steps.length - 1 ? 'Done' : 'Next';
        tour.hidden = false;
        const rect = anchor.getBoundingClientRect();
        const card = tour.querySelector('.tour-card');
        const w = Math.min(320, innerWidth - 24);
        const x = Math.max(12, Math.min(innerWidth - w - 12, rect.left + rect.width/2 - w/2));
        const y = rect.top > 245 ? rect.top - 175 : Math.min(innerHeight - 190, rect.bottom + 12);
        card.style.width = `${w}px`;
        card.style.left = `${x}px`;
        card.style.top = `${Math.max(12,y)}px`;
    }
    document.getElementById('tour-skip').addEventListener('click',close);
    document.getElementById('tour-next').addEventListener('click',()=>{if (++step>=steps.length) close(); else show();});
    addEventListener('resize',()=>{if (!tour.hidden) show();});
    // Wait until the authenticated app has finished opening.
    const ready = new MutationObserver(()=>{
        if (document.documentElement.classList.contains('auth-pending')) return;
        ready.disconnect();
        show();
    });
    if (document.documentElement.classList.contains('auth-pending')) ready.observe(document.documentElement,{attributes:true,attributeFilter:['class']});
    else show();
})();

// Ask-about-a-paper: scope the chat to one PubMed paper's abstract.
let paperContext = null;
(() => {
    const dialog = document.getElementById('paper-dialog');
    const input = document.getElementById('paper-input');
    const error = document.getElementById('paper-dialog-error');
    const load = document.getElementById('paper-load');
    const pdfInput = document.getElementById('paper-pdf');
    document.getElementById('paper-button').addEventListener('click', () => {
        error.hidden = true;
        input.value = '';
        pdfInput.value = '';
        dialog.showModal();
        input.focus();
    });
    document.getElementById('paper-cancel').addEventListener('click', () => dialog.close());
    document.getElementById('paper-clear').addEventListener('click', clearPaperScope);
    pdfInput.addEventListener('change', () => {
        const file = pdfInput.files?.[0];
        if (!file) return;
        if (!/\.pdf$/i.test(file.name) || !file.size || file.size > 5 * 1024 * 1024) {
            error.textContent = 'Choose a PDF file up to 5 MB.';
            error.hidden = false;
            pdfInput.value = '';
            return;
        }
        error.hidden = true;
        input.value = '';
        paperContext = { file };
        document.getElementById('paper-chip-text').textContent = `Asking about PDF: ${file.name}`;
        document.getElementById('paper-chip-link').hidden = true;
        document.getElementById('paper-chip-row').hidden = false;
        dialog.close();
    });
    input.addEventListener('input', () => { error.hidden = true; });
    input.addEventListener('keydown', (event) => { if (event.key === 'Enter') { event.preventDefault(); load.click(); } });
    load.addEventListener('click', async () => {
        const raw = input.value.trim();
        const match = raw.match(/^https:\/\/pubmed\.ncbi\.nlm\.nih\.gov\/(\d{1,12})\/?(?:\?[^#]*)?$/i) || raw.match(/^(\d{1,12})$/);
        if (!match) { error.textContent = 'Enter a PubMed link or PMID.'; error.hidden = false; return; }
        load.disabled = true; load.textContent = 'Loading...';
        try {
            const response = await apiFetch(`/paper_context/${match[1]}`);
            if (!response.ok) throw new Error(await DietNerdAPI.readError(response, 'Could not load that paper.'));
            const paper = await response.json();
            paperContext = { pmid: paper.pmid, title: paper.title, abstract: paper.abstract, url: paper.url };
            document.getElementById('paper-chip-text').textContent = `Asking about: ${paper.title} (PMID ${paper.pmid})`;
            const paperLink = document.getElementById('paper-chip-link');
            paperLink.href = `https://pubmed.ncbi.nlm.nih.gov/${paper.pmid}/`;
            paperLink.hidden = false;
            document.getElementById('paper-chip-row').hidden = false;
            dialog.close();
        } catch (err) {
            error.textContent = err.message || 'Could not load that paper.';
            error.hidden = false;
        } finally {
            load.disabled = false; load.textContent = 'Use this paper';
        }
    });
})();

// Diet profile: optional account-level personalization.
(() => {
    const dialog = document.getElementById('profile-dialog');
    const form = document.getElementById('profile-form');
    const age = document.getElementById('profile-age');
    const ageTrigger = document.getElementById('profile-age-trigger');
    const ageOptions = document.getElementById('profile-age-options');
    const ageItems = [...ageOptions.querySelectorAll('[role="option"]')];
    let activeAge = 0;
    function setAge(value) {
        age.value = value;
        const selected = Math.max(0, ageItems.findIndex(item => item.dataset.value === age.value));
        activeAge = selected;
        ageTrigger.textContent = ageItems[selected].textContent;
        ageItems.forEach((item, i) => item.setAttribute('aria-selected', String(i === selected)));
        ageTrigger.setAttribute('aria-activedescendant', ageItems[selected].id);
    }
    function focusAge(index) {
        activeAge = (index + ageItems.length) % ageItems.length;
        ageTrigger.setAttribute('aria-activedescendant', ageItems[activeAge].id);
        ageItems.forEach((item, i) => item.classList.toggle('active-option', i === activeAge));
        ageItems[activeAge].scrollIntoView({block: 'nearest'});
    }
    function closeAge() {
        ageOptions.hidden = true;
        ageTrigger.setAttribute('aria-expanded', 'false');
    }
    function openAge() {
        ageOptions.hidden = false;
        ageTrigger.setAttribute('aria-expanded', 'true');
        focusAge(Math.max(0, ageItems.findIndex(item => item.dataset.value === age.value)));
    }
    ageTrigger.addEventListener('click', () => ageOptions.hidden ? openAge() : closeAge());
    ageTrigger.addEventListener('keydown', event => {
        if (event.key === 'Escape' && !ageOptions.hidden) { event.preventDefault(); event.stopPropagation(); closeAge(); return; }
        if (event.key === 'Tab') { closeAge(); return; }
        if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
            event.preventDefault();
            if (ageOptions.hidden) openAge();
            else focusAge(event.key === 'Home' ? 0 : event.key === 'End' ? ageItems.length - 1 : activeAge + (event.key === 'ArrowDown' ? 1 : -1));
        } else if (event.key === 'Enter' || event.key === ' ') {
            if (!ageOptions.hidden) { event.preventDefault(); setAge(ageItems[activeAge].dataset.value); closeAge(); }
        } else if (event.key.length === 1 && /[0-9p]/i.test(event.key)) {
            const match = ageItems.findIndex(item => item.textContent.toLowerCase().startsWith(event.key.toLowerCase()));
            if (match >= 0) { event.preventDefault(); if (ageOptions.hidden) openAge(); focusAge(match); }
        }
    });
    ageOptions.addEventListener('click', event => {
        const item = event.target.closest('[role="option"]');
        if (!item) return;
        setAge(item.dataset.value); closeAge(); ageTrigger.focus();
    });
    dialog.addEventListener('click', event => { if (!event.target.closest('.profile-age-picker')) closeAge(); });
    dialog.addEventListener('close', closeAge);
    const goals = document.getElementById('profile-goals');
    const conditions = document.getElementById('profile-conditions');
    const notes = document.getElementById('profile-additional-notes');
    const error = document.getElementById('profile-error');
    const success = document.getElementById('profile-success');
    const profileFileInput = document.getElementById('profile-file-input');
    const profileFileList = document.getElementById('profile-file-list');
    const profileFileStatus = document.getElementById('profile-file-status');
    async function loadProfileFiles() {
        profileFileList.replaceChildren();
        try {
            const response = await apiFetch('/profile/documents');
            if (!response.ok) throw new Error(await DietNerdAPI.readError(response, 'Could not load profile files.'));
            const {documents} = await response.json();
            for (const filename of documents) {
                const item = document.createElement('li');
                const label = document.createElement('span');
                label.textContent = filename;
                const remove = document.createElement('button');
                remove.type = 'button'; remove.className = 'secondary-button'; remove.textContent = 'Remove';
                remove.setAttribute('aria-label', `Remove ${filename}`);
                remove.addEventListener('click', async () => {
                    if (!window.confirm(`Remove ${filename} from your profile?`)) return;
                    try {
                        const reply = await apiFetch(`/profile/documents?filename=${encodeURIComponent(filename)}`, {method: 'DELETE'});
                        if (!reply.ok) throw new Error(await DietNerdAPI.readError(reply, 'Could not remove file.'));
                        profileFileStatus.textContent = `${filename} removed.`;
                        await loadProfileFiles();
                    } catch (err) { profileFileStatus.textContent = err.message; }
                });
                item.append(label, remove); profileFileList.append(item);
            }
            if (!documents.length) profileFileStatus.textContent = 'No profile files saved.';
        } catch (err) { profileFileStatus.textContent = err.message; }
    }
    const profileFileName = document.getElementById('profile-file-name');
    profileFileInput.addEventListener('change', () => { profileFileName.textContent = profileFileInput.files[0]?.name || 'No file chosen'; });
    document.getElementById('profile-file-upload').addEventListener('click', async () => {
        const file = profileFileInput.files[0];
        if (!file) { profileFileStatus.textContent = 'Choose a file first.'; return; }
        if (!/\.(pdf|txt|csv)$/i.test(file.name) || file.size > 5 * 1024 * 1024 || file.size === 0) {
            profileFileStatus.textContent = 'Choose a PDF, TXT or CSV file up to 5 MB.'; return;
        }
        profileFileStatus.textContent = 'Adding file...';
        try {
            const payload = new FormData(); payload.append('attachment', file);
            const response = await apiFetch('/profile/documents', {method: 'POST', body: payload});
            if (!response.ok) throw new Error(await DietNerdAPI.readError(response, 'Could not add file.'));
            profileFileInput.value = '';
            profileFileName.textContent = 'No file chosen';
            profileFileStatus.textContent = `${file.name} saved to your profile.`;
            await loadProfileFiles();
            profileFileStatus.textContent = `${file.name} saved to your profile.`;
        } catch (err) { profileFileStatus.textContent = err.message; }
    });
    async function loadProfile() {
        error.textContent = ''; success.textContent = '';
        try {
            const response = await apiFetch('/profile');
            if (!response.ok) throw new Error(await DietNerdAPI.readError(response, 'Could not load the profile.'));
            const profile = await response.json();
            setAge(profile.age_range || '');
            goals.value = profile.goals || '';
            conditions.value = profile.conditions || '';
            notes.value = profile.additional_notes || '';
        } catch (err) { error.textContent = err.message; }
    }
    async function saveProfile(payload, doneMessage) {
        error.textContent = ''; success.textContent = '';
        try {
            const response = await apiFetch('/profile', {method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)});
            if (!response.ok) throw new Error(await DietNerdAPI.readError(response, 'Could not save the profile.'));
            success.textContent = doneMessage;
            return true;
        } catch (err) { error.textContent = err.message; return false; }
    }
    document.getElementById('diet-profile-link').addEventListener('click', () => {
        document.getElementById('account-dropdown').hidden = true;
        document.getElementById('account-button').setAttribute('aria-expanded', 'false');
        dialog.showModal();
        closeAge();
        loadProfile();
        loadProfileFiles();
    });
    document.getElementById('profile-cancel').addEventListener('click', () => dialog.close());
    document.getElementById('profile-clear').addEventListener('click', async () => {
        if (await saveProfile({age_range: '', goals: '', conditions: '', additional_notes: ''}, 'Profile cleared.')) {
            setAge(''); goals.value = ''; conditions.value = ''; notes.value = '';
        }
    });
    form.addEventListener('submit', async (event) => {
        event.preventDefault();
        await saveProfile({age_range: age.value, goals: goals.value.trim(), conditions: conditions.value.trim(), additional_notes: notes.value.trim()}, 'Profile saved.');
    });
})();

function setProfileUseUI(enabled, temporary = false) {
    const toggle = document.getElementById('use-profile');
    toggle.checked = !temporary && enabled;
    toggle.disabled = temporary || questionInFlight;
    document.getElementById('answer-mode').disabled = questionInFlight;
    document.getElementById('profile-use-note').textContent = temporary
        ? 'Temporary chats never use your profile.'
        : 'Applies to this conversation only.';
}
document.getElementById('use-profile').addEventListener('change', async event => {
    const toggle = event.target;
    const conversationId = getConversationId();
    if (temporaryChat || questionInFlight) { setProfileUseUI(false, temporaryChat); return; }
    if (!conversationId) return; // New conversation setting is sent with its first query.
    const selected = toggle.checked;
    toggle.disabled = true;
    try {
        const response = await apiFetch(`/conversations/${encodeURIComponent(conversationId)}/profile`, {
            method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({use_profile: selected}),
        });
        if (!response.ok) throw new Error(await DietNerdAPI.readError(response, 'Could not update profile setting.'));
        conversationProfileSettings.set(conversationId, selected);
        document.getElementById('profile-use-note').textContent = selected ? 'Profile on for this conversation.' : 'Profile off for this conversation.';
    } catch (error) {
        toggle.checked = !selected;
        document.getElementById('profile-use-note').textContent = error.message || 'Could not update profile setting.';
    } finally { toggle.disabled = false; }
});

// Rename a saved conversation inline.
function beginRename(item, conversation) {
    const input = document.createElement('input');
    input.className = 'rename-input';
    input.value = conversation.title || '';
    input.maxLength = 120;
    input.setAttribute('aria-label', 'Conversation name');
    item.replaceChildren(input);
    input.focus();
    input.select();
    let done = false;
    const cancel = () => { if (!done) { done = true; refreshConversationList(); } };
    const save = async () => {
        if (done) return;
        const title = input.value.trim();
        if (!title || title === (conversation.title || '')) { cancel(); return; }
        done = true;
        input.disabled = true;
        try {
            const response = await apiFetch(`/conversations/${conversation.conversation_id}`, {
                method: 'PUT',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({title}),
            });
            if (!response.ok) throw new Error(await DietNerdAPI.readError(response, 'Could not rename the conversation.'));
            if (getConversationId() === conversation.conversation_id) {
                document.getElementById('chat-title').textContent = title;
            }
            await refreshConversationList();
        } catch (err) {
            done = false;
            input.disabled = false;
            input.classList.add('rename-error');
            input.title = err.message;
            input.focus();
        }
    };
    input.addEventListener('keydown', (event) => {
        if (event.key === 'Enter') { event.preventDefault(); save(); }
        if (event.key === 'Escape') { event.preventDefault(); cancel(); }
    });
    input.addEventListener('blur', save);
}


// Chart state is per answer. Plain Markdown tables and nonnumeric values stay as tables.
document.getElementById('chat-thread').addEventListener('click', event => {
    const button = event.target.closest('.table-chart-toggle');
    if (!button) return;
    const container = button.closest('.answer-data');
    const chart = container.querySelector('.answer-chart-view');
    const table = container.querySelector('.answer-table-view');
    const show = chart.hidden;
    chart.hidden = !show; table.hidden = show;
    button.closest('.answer-data').querySelectorAll('.ask-chart-point').forEach(el => el.hidden = !show);
    button.textContent = show ? 'View as table' : 'View as chart';
    button.setAttribute('aria-expanded', String(show));
});

// Dictation only fills the composer. It never sends a question without a separate click.
(() => {
    if (!window.isSecureContext || !(window.SpeechRecognition || window.webkitSpeechRecognition)) return;
    const button = document.getElementById('voice-input');
    const input = document.getElementById('question');
    button.hidden = false;
    let active = false, recognition = null;
    button.addEventListener('click', () => {
        if (active) { recognition.stop(); return; }
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        recognition = new SpeechRecognition(); recognition.lang = navigator.language || 'en-IN';
        recognition.interimResults = true; recognition.continuous = false;
        const original = input.value.trimEnd();
        recognition.onstart = () => { active = true; button.setAttribute('aria-pressed','true'); button.title = 'Stop dictation'; };
        recognition.onresult = event => {
            const words = Array.from(event.results).map(result => result[0].transcript).join(' ').trim();
            input.value = original ? `${original} ${words}` : words;
            input.dispatchEvent(new Event('input',{bubbles:true}));
        };
        recognition.onerror = event => { document.querySelector('.hint').textContent = event.error === 'not-allowed' ? 'Microphone access was denied. You can still type your question.' : 'Dictation stopped. You can type or try again.'; };
        recognition.onend = () => { active = false; button.setAttribute('aria-pressed','false'); button.title = 'Dictate message'; input.focus(); };
        try { recognition.start(); } catch { document.querySelector('.hint').textContent = 'Could not start dictation. Type your question instead.'; }
    });
})();


// Replay is built from events seen during this research request only. It is not a persisted audit log.
function appendResearchReplay(content, events) {
    const details = document.createElement('details'); details.className = 'research-replay';
    const summary = document.createElement('summary'); summary.textContent = 'Replay research steps';
    const note = document.createElement('p'); note.textContent = 'Steps observed in this tab. This is not a record of every source checked.';
    const list = document.createElement('ol');
    events.forEach(event => { const li = document.createElement('li'); li.textContent = event; list.append(li); });
    details.append(summary,note,list); content.append(details);
}

// Navigation is derived from visible user turns, never sent as extra model context.
function updateConversationNavigation() {
    const turns = [...document.querySelectorAll('#chat-thread .chat-message.user')];
    const nav = document.getElementById('conversation-chapters');
    const links = document.getElementById('chapter-links'); links.replaceChildren();
    nav.hidden = turns.length < 3;
    if (nav.hidden) return;
    turns.forEach((turn,i) => {
        const button = document.createElement('button'); button.type = 'button';
        button.textContent = `${i+1}. ${turn.querySelector('.message-content')?.textContent.trim().slice(0,45) || 'Question'}`;
        button.title = turn.querySelector('.message-content')?.textContent.trim() || 'Question';
        button.addEventListener('click', () => turn.scrollIntoView({block:'start',behavior:matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth'}));
        links.append(button);
    });
    updateActiveChapter();
}
function updateActiveChapter() {
    const turns = [...document.querySelectorAll('#chat-thread .chat-message.user')];
    const buttons = [...document.querySelectorAll('#chapter-links button')];
    const top = document.getElementById('chat-thread').getBoundingClientRect().top + 70;
    let active = 0; turns.forEach((turn,i) => { if (turn.getBoundingClientRect().top <= top) active = i; });
    buttons.forEach((button,i) => { if (i === active) button.setAttribute('aria-current','true'); else button.removeAttribute('aria-current'); });
}
function updateFollowupLens() {
    const turns = [...document.querySelectorAll('#chat-thread .chat-message.user')];
    const lens = document.getElementById('followup-lens');
    lens.hidden = turns.length < 2 || !getConversationId() && !temporaryChat;
    document.getElementById('followup-context').textContent = turns.length ? `${Math.min(turns.length,8)} recent question${turns.length === 1 ? '' : 's'} may help with a follow-up. This is not an exact source list.` : '';
}
document.getElementById('view-context').addEventListener('click', () => {
    const last = [...document.querySelectorAll('#chat-thread .chat-message.user')].at(-1);
    last?.scrollIntoView({block:'center',behavior:matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth'});
});
const threadForJump = document.getElementById('chat-thread');
threadForJump.addEventListener('scroll', () => {
    const jumps = document.querySelector('.thread-jump');
    updateActiveChapter();
    const longThread = Boolean(threadForJump.querySelector('.chat-message.user')) && threadForJump.scrollHeight > threadForJump.clientHeight + 100;
    jumps.hidden = !longThread || threadForJump.scrollTop < 140;
    document.getElementById('latest-message').hidden = threadForJump.scrollHeight - threadForJump.scrollTop - threadForJump.clientHeight < 80;
}, {passive:true});
document.getElementById('previous-message').addEventListener('click', () => {
    const current = threadForJump.getBoundingClientRect().top;
    const prior = [...threadForJump.querySelectorAll('.chat-message')].filter(el => el.getBoundingClientRect().top < current - 24).at(-1);
    (prior || threadForJump.querySelector('.chat-message'))?.scrollIntoView({block:'start',behavior:matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth'});
});
document.getElementById('latest-message').addEventListener('click', () => { threadForJump.scrollTo({top:threadForJump.scrollHeight,behavior:matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth'}); });

document.getElementById('chat-thread').addEventListener('click', event => {
    const point = event.target.closest('.ask-chart-point'); if (!point) return;
    const question = document.getElementById('question');
    const label = point.dataset.category, measure = point.dataset.measure, value = point.dataset.value;
    if (!label || !measure || !value) return;
    const table = point.closest('.answer-data')?.querySelector('table');
    const rows = table ? [...table.rows].map(row => [...row.cells].map(cell => cell.textContent.trim()).join(' | ')).slice(0,13) : [];
    if (rows.length < 3) return;
    const draft = `In this earlier comparison table:\n${rows.join('\n')}\nFor ${label}, ${measure} is ${value}. What explains that value?`;
    question.value = draft; question.dispatchEvent(new Event('input',{bubbles:true})); question.focus();
    // The table values travel in the reviewed question, so old turns do not need to be in the context window. No request fires here.
});
