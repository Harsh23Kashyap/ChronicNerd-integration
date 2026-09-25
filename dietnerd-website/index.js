
const baseURL = DietNerdAPI.baseURL;
const apiFetch = DietNerdAPI.apiFetch;

function getConversationId() {
    return sessionStorage.getItem('dietnerd_conversation_id') || null;
}

function clearChatThread() {
    document.getElementById('chat-thread').innerHTML = '';
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
        card.append(label, title, note);
        if (source.url && /^https:\/\//i.test(source.url)) {
            const link = document.createElement('a');
            link.href = source.url;
            link.target = '_blank';
            link.rel = 'noopener noreferrer';
            link.textContent = 'Open original in new tab ↗';
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

function sourcesForAnswer(answer) {
    let objects = {};
    try { objects = JSON.parse(localStorage.getItem('referenceObject') || '{}') || {}; } catch { /* citations still render */ }
    const {references} = splitReferenceSection(answer);
    const lines = references.split(/\n(?=\s*(?:\[\d+\]|\d+\.))/);
    const fromAnswer = lines.flatMap(line => {
        const match = line.trim().match(/^(?:\[(\d+)\]|(\d+)\.)\s*(.+)/s);
        if (!match) return [];
        const number = Number(match[1] || match[2]);
        const title = match[3].split(/\n(?=\s*(?:DietNerd|ChronicNerd) is\b)/i)[0].trim().slice(0, 240);
        if (!title) return [];
        const normalized = value => String(value).replace(/^\s*(?:\[\d+\]|\d+\.)\s*/, '').trim().replace(/\s+/g,' ').toLowerCase();
        const metadata = Object.entries(objects).find(([citation]) => normalized(citation) === normalized(line.split('\n')[0]));
        return [{number, title, url: metadata && typeof metadata[1]?.URL === 'string' ? metadata[1].URL : ''}];
    });
    return [...new Map(fromAnswer.map(source => [source.number, source])).values()].sort((a,b)=>a.number-b.number);
}

function appendInChatSources(content, sources) {
    if (!sources.length) return;
    const section = document.createElement('section');
    section.className = 'in-chat-sources';
    const heading = document.createElement('h3');
    heading.textContent = 'Sources';
    section.append(heading);
    sources.forEach(source => {
        const row = document.createElement('button');
        row.type = 'button';
        row.className = 'in-chat-source';
        const number = document.createElement('span');
        number.textContent = `[${source.number}]`;
        const title = document.createElement('span');
        title.textContent = source.title;
        row.append(number, title);
        row.addEventListener('click', () => openSourcesPanel(sources));
        section.append(row);
    });
    content.append(section);
}

function appendChatMessage(role, text, references = []) {
    const thread = document.getElementById('chat-thread');
    thread.querySelector('.welcome-message')?.remove();
    const article = document.createElement('article');
    article.className = `chat-message ${role}`;
    const avatar = document.createElement('span');
    avatar.className = `${role}-avatar`;
    avatar.textContent = role === 'assistant' ? 'D' : 'You';
    const content = document.createElement('div');
    content.className = 'message-content';
    const answerBody = role === 'assistant' && Array.isArray(references) && references.length
        ? splitReferenceSection(text).body
        : text;
    content.innerHTML = role === 'assistant' ? formatText(answerBody) : String(text).replace(/&/g, '&amp;').replace(/</g, '&lt;');
    article.append(avatar, content);
    if (role === 'assistant' && Array.isArray(references)) appendInChatSources(content, references);
    thread.appendChild(article);
    enterConversationMode();
    thread.scrollTop = thread.scrollHeight;
    return content;
}

async function refreshConversationList() {
    const select = document.getElementById('conversation-select');
    const currentId = getConversationId() || '';
    const response = await apiFetch('/conversations');
    if (!response.ok) {
        document.querySelector('.sidebar-heading span').textContent = 'History unavailable';
        return;
    }
    const data = await response.json();
    document.querySelector('.sidebar-heading span').textContent = `Conversations (${(data.conversations || []).length})`;
    select.innerHTML = '<option value="">New conversation</option>';
    const list = document.getElementById('conversation-list');
    list.replaceChildren();
    (data.conversations || []).forEach((conversation) => {
        const option = document.createElement('option');
        option.value = conversation.conversation_id;
        option.textContent = conversation.title || 'Untitled conversation';
        select.appendChild(option);
        const row = document.createElement('button');
        row.type = 'button';
        row.className = 'conversation-row';
        row.dataset.conversationId = conversation.conversation_id;
        row.title = conversation.title || 'Untitled conversation';
        row.textContent = conversation.title || 'Untitled conversation';
        list.appendChild(row);
    });
    const latestId = (data.conversations || [])[0]?.conversation_id || '';
    const selectedId = (data.conversations || []).some(c => c.conversation_id === currentId) ? currentId : latestId;
    select.value = selectedId;
    list.querySelectorAll('.conversation-row').forEach(row => {
        const active = row.dataset.conversationId === selectedId;
        row.classList.toggle('active', active);
        if (active) row.setAttribute('aria-current', 'true');
        else row.removeAttribute('aria-current');
    });
    if (selectedId && selectedId !== currentId && !questionInFlight &&
        !document.querySelector('#chat-thread .chat-message.user')) {
        sessionStorage.setItem('dietnerd_conversation_id', selectedId);
        await renderSelectedConversation(selectedId);
    }
}

let conversationLoadToken = 0;
async function renderSelectedConversation(conversationId) {
    if (!conversationId) return;
    const token = ++conversationLoadToken;
    enterConversationMode();
    closeSourcesPanel();
    const thread = document.getElementById('chat-thread');
    thread.innerHTML = '<div class="history-loading" role="status" aria-live="polite"><span class="history-loading-icon" aria-hidden="true"></span><span>Opening conversation...</span><span class="history-loading-line"></span><span class="history-loading-line short"></span></div>';
    try {
        const response = await apiFetch(`/session_memory?conversation_id=${encodeURIComponent(conversationId)}`);
        if (token !== conversationLoadToken) return;
        if (!response.ok) throw new Error(await DietNerdAPI.readError(response, 'Could not load this conversation.'));
        const data = await response.json();
        if (token !== conversationLoadToken) return;
        const entries = data.entries || [];
        clearChatThread();
        entries.forEach((entry) => {
            appendChatMessage('user', entry.raw_question || '');
            const content = appendChatMessage('assistant', entry.answer || '', sourcesForAnswer(entry.answer || ''));
            appendEvidenceLedger(content, entry.evidence_ledger || []);
        });
        if (!entries.length) thread.innerHTML = '<div class="history-loading empty-history">This conversation has no completed answers yet.</div>';
        document.getElementById('question').value = '';
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
        const response = await apiFetch(`/check_valid/${encodeURIComponent(userQuery)}`);
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
            }),
        });
        if (!response.ok) {
            throw new Error('Cached answer not found');
        }
        const result = await response.json();
        sessionStorage.setItem('dietnerd_conversation_id', result.conversation_id);
        await refreshConversationList();
        const cached = JSON.parse(result.cached_payload);
        localStorage.setItem('referenceObject', JSON.stringify(cached.citations_obj || {}));
        localStorage.setItem('citations', JSON.stringify(cached.citations || []));
        localStorage.setItem('allArticles', JSON.stringify(cached.relevant_articles || cached.relevent_articles || []));
        return cached.end_output.replace(/(^|\n)(\d+)\.\s/g, '\n\n$2. ');
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

            return `<a href="reference.html?ref=${encodeURIComponent(ref)}" target="_blank" rel="noopener">${citationToDisplay}</a> - ${analysisText}`;
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

const formatText = (input,disclaimer) => {
    // Escape untrusted answer/cache text before adding the small supported markup set.
    let formattedText = escapeHtml(input).replace(/\n/g, '<br>');
    // Replace **text** with <strong>text</strong>
    formattedText = formattedText.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    // Replace ###
    formattedText = formattedText.replace(/### (.*?)(<br>|$)/g, '<strong>$1</strong>$2');
    // Replace "-" with <li> 
    formattedText = formattedText.replace(/[-*] (.*?)(<br>|$)/g, '<li>$1</li>');
    return formattedText;
}

/**
 * Generates a PDF document based on the formatted text content.
 */
const generatePDF = () => {
    const question = document.getElementById('question').value.trim();
    const script = document.createElement('script');
    const text = localStorage.getItem("rawOutput");
    const citationObj = JSON.parse(localStorage.getItem('referenceObject'));
    script.src = 'https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js';
    document.body.appendChild(script);

    script.onload = function() {
        const { jsPDF } = window.jspdf;
        const doc = new jsPDF();

        const lineHeight = 7;
        let y = 20;
        const listItemIndent = 10;
        const maxWidth = 180;
        const pageHeight = doc.internal.pageSize.height;

        // Function to add formatted text with word wrap
        const addFormattedText = (text, startX, fontSize = 12) => {
            let x = startX;
            const lines = text.split('\n');

            lines.forEach(line => {
                x = startX;
                const isListItem = line.trim().startsWith('-');
                if (isListItem) {
                    x += listItemIndent;
                    line = line.substring(line.indexOf('-') + 1).trim();
                    doc.setFont("helvetica", "normal");
                    doc.setFontSize(fontSize);
                    doc.text('•', startX, y);
                }

                const parts = line.split(/(\*\*.*?\*\*)/);

                parts.forEach(part => {
                    if (part.startsWith('**') && part.endsWith('**')) {
                        doc.setFont("helvetica", "bold");
                        part = part.slice(2, -2);
                    } else {
                        doc.setFont("helvetica", "normal");
                    }

                    doc.setFontSize(fontSize);
                    const words = part.split(' ');
                    let currentLine = '';

                    words.forEach(word => {
                        const testLine = currentLine + (currentLine ? ' ' : '') + word;
                        const testWidth = doc.getTextWidth(testLine);

                        if (testWidth > maxWidth - x + 15) {
                            if (y > pageHeight - 20) {
                                doc.addPage();
                                y = 20;
                            }
                            doc.text(currentLine, x, y);
                            y += lineHeight;
                            currentLine = word;
                            x = isListItem ? startX + listItemIndent : startX;
                        } else {
                            currentLine = testLine;
                        }
                    });

                    if (currentLine) {
                        if (y > pageHeight - 20) {
                            doc.addPage();
                            y = 20;
                        }
                        doc.text(currentLine, x, y);
                        x += doc.getTextWidth(currentLine) + 1;
                    }
                });

                y += lineHeight;
                if (y > pageHeight - 20) {
                    doc.addPage();
                    y = 20;
                }
            });
        };

        // Add the question as a title
        doc.setFontSize(16);
        doc.setFont("helvetica", "bold");
        const titleLines = doc.splitTextToSize(question, maxWidth);
        titleLines.forEach(line => {
            doc.text(line, 15, y);
            y += 10;
        });
        y += 10;

        // Add the main content
        addFormattedText(text, 15);

        // Add citation summaries
        doc.addPage();
        y = 20;
        doc.setFontSize(16);
        doc.setFont("helvetica", "bold");
        doc.text("Citation Summaries", 15, y);
        y += 20;

        // `|| {}` guards the disabled localStorage block above — referenceObject is
        // null while citations are turned off, and Object.entries(null) throws.
        Object.entries(citationObj || {}).forEach(([citation, data], index) => {
            if (index > 0) {  
                doc.addPage();
                y = 20;
            }

            addFormattedText(`**Citation:** ${citation}`, 15, 14);
            y += lineHeight;
            addFormattedText(`**Summary:**`, 15, 14);
            y += lineHeight;
            addFormattedText(data.Summary, 15);
            y += lineHeight; 
            addFormattedText(`**PMID:** ${data.PMID}`, 15);
            y += lineHeight;
            addFormattedText(`**PMCID:** ${data.PMCID}`, 15);
            y += lineHeight;
            addFormattedText(`**URL:** ${data.URL}`, 15);
            y += lineHeight * 2;
        });

        doc.save("Dietnerd.pdf"); //ADD DATE AND TIME
    };
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
    existingAttachmentsElement.replaceChildren(...documentNames.map(name => renderAttachmentChip(name)));
    label.textContent = attachmentExists ? '' : 'No file attached';
}

document.addEventListener('DOMContentLoaded', function () {
    const fileInput = document.getElementById('attachment-file');
    const existingAttachmentsElement = document.getElementById('existing-attachments');

    refreshExistingAttachments().catch((err) => { document.getElementById('attachment-label').textContent = err.message; });
    refreshConversationList();

    fileInput.addEventListener('change', async function () {
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
    avatar.textContent = 'D';
    const content = document.createElement('div');
    content.className = 'message-content';
    const status = document.createElement('p');
    status.className = 'pending-status';
    status.textContent = 'Looking at your question...';
    const note = document.createElement('p');
    note.className = 'pending-note';
    note.textContent = 'Searching published research can take a minute. Please keep this page open.';
    const steps = document.createElement('ol');
    steps.className = 'research-steps';
    const articleList = document.createElement('div');
    articleList.className = 'progress-articles';
    const labels = ['Understanding question', 'Searching papers', 'Reading studies', 'Synthesizing answer'];
    labels.forEach(label => { const step = document.createElement('li'); step.textContent = label; steps.append(step); });
    let stage = 0;
    function renderStage() {
        [...steps.children].forEach((step, index) => {
            step.classList.toggle('active', index === stage);
            step.classList.toggle('complete', index < stage);
        });
    }
    renderStage();
    const stageTimer = window.setInterval(() => {
        // A pulse shows activity; only a real server event advances a stage.
        steps.classList.toggle('pulse');
    }, 1200);
    content.append(status, note, steps, articleList);
    article.append(avatar, content);
    thread.appendChild(article);
    enterConversationMode();
    thread.scrollTop = thread.scrollHeight;
    return {
        addArticles(update) {
            articleList.replaceChildren();
            const heading = document.createElement('strong');
            heading.textContent = update.stage === 'relevant' ? 'Relevant paper titles found' : 'Paper titles found';
            const list = document.createElement('ul');
            (update.article_titles || []).slice(0,5).forEach(title => { const li = document.createElement('li'); li.textContent = title; list.appendChild(li); });
            articleList.append(heading, list);
            note.textContent = update.note || 'Retrieved titles do not prove support for the answer.';
            thread.scrollTop = thread.scrollHeight;
        },
        setStatus(text) {
            status.textContent = text;
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

function showAssistantAnswer(answer, ledger = [], question = '') {
    localStorage.setItem('rawOutput', answer);
    const content = appendChatMessage('assistant', answer, sourcesForAnswer(answer));
    appendEvidenceLedger(content, ledger);
    if (ChronicNerdAddons.enabled('notebook')) {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'addon-save-button';
        button.textContent = 'Save to my notebook';
        button.addEventListener('click', () => {
            try {
                ChronicNerdAddons.saveNote(question, answer, ledger.map(row => row.source_url));
                button.textContent = 'Saved to notebook';
                button.disabled = true;
            } catch { button.textContent = 'Could not save locally'; }
        });
        content.append(button);
    }
    document.getElementById('generate-pdf-button').classList.remove('hidden');
}

function conversationHasTurns() {
    return Boolean(getConversationId()) && document.querySelectorAll('#chat-thread .chat-message.user').length > 1;
}

let questionInFlight = false;
let selectedSuggestion = false;
function setComposerBusy(busy) {
    questionInFlight = busy;
    document.getElementById('submit').disabled = busy;
    document.getElementById('question').setAttribute('aria-busy', busy ? 'true' : 'false');
}

async function runGeneration(userQuery, pending) {
    const response = await apiFetch('/process_query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_query: userQuery, conversation_id: getConversationId() }),
    });
    if (!response.ok) {
        throw new Error(await DietNerdAPI.readError(response, `The question could not be sent (${response.status}).`));
    }
    const data = await response.json();
    sessionStorage.setItem('dietnerd_conversation_id', data.conversation_id);
    refreshConversationList();

    return new Promise((resolve, reject) => {
        const eventSource = new EventSource(`${baseURL}/sse?request_id=${encodeURIComponent(data.request_id)}`, { withCredentials: true });
        let lostAt = 0;
        const reconnectTimer = window.setInterval(() => {
            // EventSource retries transient failures. A lasting failure should
            // not leave the send button locked forever.
            if (lostAt && Date.now() - lostAt > 60000) {
                window.clearInterval(reconnectTimer);
                eventSource.close();
                reject(new Error('Research connection did not recover. Open this conversation from history to check whether the answer finished.'));
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
                localStorage.setItem('referenceObject', JSON.stringify(message.update.citations_obj || {}));
                localStorage.setItem('citations', JSON.stringify(message.update.citations || []));
                localStorage.setItem('allArticles', JSON.stringify(message.update.relevant_articles || []));
                eventSource.close();
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
        showAssistantAnswer(result.end_output, result.evidence_ledger || [], question);
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
        showAssistantAnswer(result.end_output, result.evidence_ledger || [], question);
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
    document.getElementById('generate-pdf-button').classList.add('hidden');
    document.getElementById('example-questions')?.classList.add('hidden');
    similarQuestionsContainer.style.display = 'none';
    hintElement.textContent = '';
    const useSelectedSuggestion = selectedSuggestion;
    selectedSuggestion = false;
    appendChatMessage('user', question);
    input.value = '';

    if (attachmentExists) {
        await answerFromAttachment(question);
        return;
    }

    setComposerBusy(true);
    const initialStatus = appendPendingMessage();
    initialStatus.setStatus('Checking for a saved answer...');
    let cachedAnswer = null;
    try {
        cachedAnswer = await getAnswer(question);
    } catch (err) {
        cachedAnswer = null;
    } finally {
        initialStatus.remove();
    }
    if (cachedAnswer) {
        setComposerBusy(false);
        showAssistantAnswer(cachedAnswer, [], question);
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
    sessionStorage.setItem('dietnerd_conversation_id', conversationId);
    await renderSelectedConversation(conversationId);
    document.querySelectorAll('.conversation-row').forEach(row => {
        const active = row.dataset.conversationId === conversationId;
        row.classList.toggle('active', active);
        if (active) row.setAttribute('aria-current', 'true');
        else row.removeAttribute('aria-current');
    });
});

document.getElementById('new-conversation').addEventListener('click', () => {
    enterConversationMode();
    closeSourcesPanel();
    ++conversationLoadToken;
    sessionStorage.removeItem('dietnerd_conversation_id');
    document.getElementById('conversation-select').value = '';
    document.querySelectorAll('.conversation-row.active').forEach(row => { row.classList.remove('active'); row.removeAttribute('aria-current'); });
    document.getElementById('question').value = '';
    document.getElementById('chat-thread').innerHTML = '<div class="welcome-message"><span class="assistant-avatar">D</span><div><h2>Start a new conversation</h2><p>Ask a diet or nutrition question to begin.</p></div></div>';
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
for (const feature of ['ledger', 'notebook']) {
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
