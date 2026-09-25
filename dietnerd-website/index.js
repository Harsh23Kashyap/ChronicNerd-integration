
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

function openSourcesPanel(references) {
    const shell = document.querySelector('.chat-shell');
    const panel = document.getElementById('sources-panel');
    const content = document.getElementById('sources-panel-content');
    const wrapper = document.createElement('div');
    wrapper.innerHTML = references;
    const entries = Array.from(wrapper.querySelectorAll('a'));
    content.innerHTML = '';
    if (entries.length) {
        entries.forEach((entry, index) => {
            const card = document.createElement('article');
            card.className = 'source-card';
            const label = document.createElement('span');
            label.className = 'sources-kicker';
            label.textContent = `Source ${index + 1}`;
            card.append(label, entry.cloneNode(true));
            const detail = entry.nextSibling;
            if (detail && detail.textContent.trim()) {
                const note = document.createElement('p');
                note.textContent = detail.textContent.replace(/^\s*-\s*/, '');
                card.appendChild(note);
            }
            content.appendChild(card);
        });
    } else {
        const card = document.createElement('article');
        card.className = 'source-card';
        card.innerHTML = references;
        content.appendChild(card);
    }
    shell.classList.add('sources-open');
    panel.setAttribute('aria-hidden', 'false');
}

function appendChatMessage(role, text, references = '') {
    const thread = document.getElementById('chat-thread');
    const article = document.createElement('article');
    article.className = `chat-message ${role}`;
    const avatar = document.createElement('span');
    avatar.className = `${role}-avatar`;
    avatar.textContent = role === 'assistant' ? 'D' : 'You';
    const content = document.createElement('div');
    content.className = 'message-content';
    content.innerHTML = role === 'assistant' ? formatText(text) : text.replace(/&/g, '&amp;').replace(/</g, '&lt;');
    article.append(avatar, content);
    if (references && references !== 'No references available.') {
        const sourceButton = document.createElement('button');
        sourceButton.type = 'button';
        sourceButton.className = 'message-sources-button';
        sourceButton.textContent = 'View sources';
        sourceButton.addEventListener('click', () => openSourcesPanel(references));
        content.appendChild(sourceButton);
    }
    thread.appendChild(article);
    enterConversationMode();
    thread.scrollTop = thread.scrollHeight;
    return content;
}

async function refreshConversationList() {
    const select = document.getElementById('conversation-select');
    const currentId = getConversationId() || '';
    const response = await apiFetch('/conversations');
    if (!response.ok) return;
    const data = await response.json();
    select.innerHTML = '<option value="">New conversation</option>';
    (data.conversations || []).forEach((conversation) => {
        const option = document.createElement('option');
        option.value = conversation.conversation_id;
        option.textContent = conversation.title || 'Untitled conversation';
        select.appendChild(option);
    });
    select.value = currentId;
}

async function renderSelectedConversation(conversationId) {
    if (!conversationId) return;
    enterConversationMode();
    const response = await apiFetch(`/session_memory?conversation_id=${encodeURIComponent(conversationId)}`);
    if (!response.ok) return;
    const data = await response.json();
    const entries = data.entries || [];
    clearChatThread();
    entries.forEach((entry) => {
        appendChatMessage('user', entry.raw_question || '');
        appendChatMessage('assistant', entry.answer || '');
    });
    document.getElementById('question').value = '';
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
async function refreshExistingAttachments() {
    const existingAttachmentsElement = document.getElementById('existing-attachments');
    const label = document.getElementById('attachment-label');
    try {
        const response = await apiFetch('/list_attachments');
        const data = await response.json();
        const documentNames = data.documents || [];
        attachmentExists = documentNames.length > 0;
        existingAttachmentsElement.replaceChildren();
        documentNames.forEach((name) => {
            const item = document.createElement('span');
            item.className = 'existing-attachment-item';
            item.appendChild(document.createTextNode(name));

            const removeButton = document.createElement('button');
            removeButton.type = 'button';
            removeButton.className = 'existing-attachment-remove';
            removeButton.dataset.filename = name;
            removeButton.textContent = '\u2715';
            item.appendChild(removeButton);
            existingAttachmentsElement.appendChild(item);
        });
        label.textContent = attachmentExists ? '' : 'No file attached';
    } catch (err) {
        console.log('Failed to fetch existing attachments:', err);
    }
}

document.addEventListener('DOMContentLoaded', function () {
    const fileInput = document.getElementById('attachment-file');
    const existingAttachmentsElement = document.getElementById('existing-attachments');

    refreshExistingAttachments();
    refreshConversationList();

    fileInput.addEventListener('change', async function () {
        if (fileInput.files.length > 0) {
            const file = fileInput.files[0];
            const formData = new FormData();
            formData.append('attachment', file);
            const label = document.getElementById('attachment-label');
            label.textContent = `Uploading ${file.name}...`;
            try {
                const response = await apiFetch('/upload_attachment', {
                    method: 'POST',
                    body: formData,
                });
                fileInput.value = '';
                if (!response.ok) {
                    label.textContent = await DietNerdAPI.readError(response, 'Upload failed. Please try again.');
                    return;
                }
                await refreshExistingAttachments();
            } catch (err) {
                label.textContent = 'Upload failed. Please try again.';
            }
        }
    });

    existingAttachmentsElement.addEventListener('click', async function (event) {
        if (!event.target.matches('.existing-attachment-remove')) return;
        const filename = event.target.dataset.filename;
        try {
            await apiFetch(`/remove_attachment?filename=${encodeURIComponent(filename)}`, {
                method: 'DELETE',
            });
            await refreshExistingAttachments();
        } catch (err) {
            console.log('Attachment removal failed:', err);
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
    content.append(status, note);
    article.append(avatar, content);
    thread.appendChild(article);
    enterConversationMode();
    thread.scrollTop = thread.scrollHeight;
    return {
        setStatus(text) { status.textContent = text; },
        remove() { article.remove(); },
        fail(message, retry) {
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

function showAssistantAnswer(answer) {
    localStorage.setItem('rawOutput', answer);
    appendChatMessage('assistant', answer, formatReferences(answer));
    document.getElementById('generate-pdf-button').classList.remove('hidden');
}

function conversationHasTurns() {
    return Boolean(getConversationId()) && document.querySelectorAll('#chat-thread .chat-message.user').length > 1;
}

let questionInFlight = false;
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
        eventSource.onmessage = (event) => {
            const message = JSON.parse(event.data);
            if (!message.update) return;
            if (message.update.end_output) {
                localStorage.setItem('referenceObject', JSON.stringify(message.update.citations_obj || {}));
                localStorage.setItem('citations', JSON.stringify(message.update.citations || []));
                localStorage.setItem('allArticles', JSON.stringify(message.update.relevant_articles || []));
                eventSource.close();
                resolve(message.update);
            } else if (pending) {
                pending.setStatus(String(message.update));
            }
        };
        eventSource.onerror = () => {
            eventSource.close();
            reject(new Error('The connection to DietNerd was lost while the answer was being prepared.'));
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
        showAssistantAnswer(result.end_output);
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
        showAssistantAnswer(result.end_output);
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
    hintElement.textContent = 'A new answer takes about a minute. For an instant answer, pick a similar question that has already been answered.';
    similar.forEach((item) => {
        const button = document.createElement('button');
        button.type = 'button';
        button.textContent = item[1];
        button.addEventListener('click', () => {
            container.style.display = 'none';
            hintElement.textContent = '';
            document.getElementById('question').value = item[1];
            document.getElementById('submit').click();
        });
        container.appendChild(button);
    });
    const original = document.createElement('button');
    original.type = 'button';
    original.className = 'generate-original';
    original.textContent = similar.length
        ? 'Answer my original question (about a minute)'
        : 'No similar questions found. Answer my question (about a minute)';
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
    appendChatMessage('user', question);
    input.value = '';

    if (attachmentExists) {
        await answerFromAttachment(question);
        return;
    }

    setComposerBusy(true);
    let cachedAnswer = null;
    try {
        cachedAnswer = await getAnswer(question);
    } catch (err) {
        cachedAnswer = null;
    } finally {
        setComposerBusy(false);
    }
    if (cachedAnswer) {
        showAssistantAnswer(cachedAnswer);
        return;
    }

    // Follow-ups inside a conversation go straight to generation so the
    // earlier turns are used to understand the question.
    if (conversationHasTurns()) {
        await generateAnswer(question);
        return;
    }
    let similar = [];
    try {
        similar = await get_sim(question);
    } catch (err) {
        similar = [];
    }
    offerSimilarQuestions(question, similar || []);
});


document.getElementById('conversation-select').addEventListener('change', async (event) => {
    const conversationId = event.target.value;
    if (!conversationId) {
        document.getElementById('new-conversation').click();
        return;
    }
    sessionStorage.setItem('dietnerd_conversation_id', conversationId);
    await renderSelectedConversation(conversationId);
});

document.getElementById('new-conversation').addEventListener('click', () => {
    enterConversationMode();
    closeSourcesPanel();
    sessionStorage.removeItem('dietnerd_conversation_id');
    document.getElementById('conversation-select').value = '';
    document.getElementById('question').value = '';
    document.getElementById('chat-thread').innerHTML = '<div class="welcome-message"><span class="assistant-avatar">D</span><div><h2>Start a new conversation</h2><p>Ask a diet or nutrition question to begin.</p></div></div>';
    document.getElementById('similarQuestions').style.display = 'none';
    document.getElementById('generate-pdf-button').classList.add('hidden');
    document.querySelector('.hint').textContent = '';
});

document.getElementById('delete-conversation').addEventListener('click', async () => {
    const conversationId = getConversationId();
    if (!conversationId) return;
    if (!window.confirm('Delete this conversation? This cannot be undone.')) return;
    const response = await apiFetch(`/conversations/${encodeURIComponent(conversationId)}`, {method: 'DELETE'});
    if (!response.ok) {
        console.error('Failed to delete conversation');
        return;
    }
    sessionStorage.removeItem('dietnerd_conversation_id');
    document.getElementById('new-conversation').click();
    await refreshConversationList();
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

document.addEventListener('DOMContentLoaded', function() {
    const questionInput = document.getElementById('question');
    const submitButton = document.getElementById('submit');
    const exampleQuestions = document.querySelectorAll('.example-question');

    exampleQuestions.forEach(question => {
        question.addEventListener('click', function() {
            questionInput.value = this.textContent;
            submitButton.click();
        });
    });
});
const composerInput = document.getElementById('question');
composerInput.addEventListener('input', () => { composerInput.style.height = 'auto'; composerInput.style.height = `${Math.min(composerInput.scrollHeight, 140)}px`; });

document.getElementById('close-sources').addEventListener('click', closeSourcesPanel);
document.addEventListener('keydown', event => { if (event.key === 'Escape') closeSourcesPanel(); });
if (getConversationId()) enterConversationMode();
