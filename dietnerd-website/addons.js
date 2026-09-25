// Opt-in interface state only. Core evidence and safety stops cannot be disabled.
(function () {
    const prefix = 'chronicnerd:addons:v1:';
    // These preferences and user-selected answers are browser data, not an access
    // boundary. Do not save sensitive health information on a shared device.
    function account() {
        const email = sessionStorage.getItem('dietnerd_user');
        return email && /^[^@\s]+@[^@\s]+$/.test(email) ? email.trim().toLowerCase() : null;
    }
    function key(name) { const email = account(); return email ? prefix + email + ':' + name : null; }
    function enabled(name) {
        const storageKey = key('enabled:' + name);
        return Boolean(storageKey && localStorage.getItem(storageKey) === 'yes');
    }
    function setEnabled(name, value) {
        const storageKey = key('enabled:' + name);
        if (!storageKey) throw new Error('Sign in first.');
        if (!['ledger', 'notebook'].includes(name)) throw new Error('This add-on is not available yet.');
        if (value) localStorage.setItem(storageKey, 'yes');
        else localStorage.removeItem(storageKey);
    }
    function notebook() {
        const storageKey = key('notebook');
        if (!storageKey) return [];
        try {
            const entries = JSON.parse(localStorage.getItem(storageKey) || '[]');
            return Array.isArray(entries) ? entries.filter(item => item && typeof item === 'object' && typeof item.id === 'string' && typeof item.answer === 'string' && typeof item.question === 'string') : [];
        } catch { return []; }
    }
    function noteId() {
        // randomUUID is unavailable on HTTP public IPs in Safari. getRandomValues
        // supplies random bytes without requiring a secure context.
        const bytes = new Uint8Array(16);
        crypto.getRandomValues(bytes);
        return Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('');
    }
    function saveNote(question, answer, sources) {
        if (!enabled('notebook')) throw new Error('Enable the notebook first.');
        const storageKey = key('notebook');
        const entries = notebook();
        // User click is required. Only the visible answer and resolved source links
        // are stored locally; no credentials, hidden document text or API payloads.
        entries.unshift({id: noteId(), savedAt: new Date().toISOString(),
            question: String(question || '').slice(0, 2000),
            answer: String(answer || '').slice(0, 16000),
            sources: Array.isArray(sources) ? sources.filter(x => typeof x === 'string' && /^https:\/\//.test(x)).slice(0, 12) : []});
        localStorage.setItem(storageKey, JSON.stringify(entries.slice(0, 50)));
    }
    function removeNote(id) {
        const storageKey = key('notebook');
        if (storageKey) localStorage.setItem(storageKey, JSON.stringify(notebook().filter(entry => entry.id !== id)));
    }
    window.ChronicNerdAddons = Object.freeze({enabled, setEnabled, notebook, saveNote, removeNote, account});
})();
