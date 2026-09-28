// Opt-in interface state only. Core evidence and safety stops cannot be disabled.
(function () {
    const prefix = 'chronicnerd:addons:v1:';
    // Interface preferences are browser data, not an access boundary.
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
        if (name !== 'ledger') throw new Error('This add-on is not available yet.');
        if (value) localStorage.setItem(storageKey, 'yes');
        else localStorage.removeItem(storageKey);
    }
    window.ChronicNerdAddons = Object.freeze({enabled, setEnabled, account});
})();
