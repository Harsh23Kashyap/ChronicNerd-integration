(async function () {
    const user = await DietNerdAPI.currentUser();
    if (!user) {
        window.location.href = 'login.html';
        return;
    }
    document.getElementById('signed-in').textContent = user;
    document.documentElement.classList.remove('auth-pending');
    for (const feature of ['ledger', 'notebook']) {
        const input = document.getElementById('toggle-' + feature);
        input.checked = ChronicNerdAddons.enabled(feature);
        const state = input.parentElement.querySelector('.switch-state');
        const updateState = () => { state.textContent = input.checked ? 'On' : 'Off'; };
        updateState();
        input.addEventListener('change', () => {
            try { ChronicNerdAddons.setEnabled(feature, input.checked); }
            catch { input.checked = !input.checked; }
            updateState();
        });
    }
    function renderNotes() {
        const container = document.getElementById('notes');
        container.replaceChildren();
        const entries = ChronicNerdAddons.notebook();
        if (!entries.length) {
            const p = document.createElement('p');
            p.className = 'empty';
            p.textContent = 'Nothing saved yet. Enable the notebook, then use Save on an answer.';
            container.append(p);
            return;
        }
        entries.forEach(entry => {
            const article = document.createElement('article');
            article.className = 'note';
            const time = document.createElement('time');
            const saved = new Date(entry.savedAt);
            time.textContent = Number.isNaN(saved.getTime()) ? 'Saved research' : saved.toLocaleString();
            const title = document.createElement('h3');
            title.textContent = entry.question || 'Research question';
            const body = document.createElement('p');
            body.textContent = entry.answer || '';
            article.append(time, title, body);
            (Array.isArray(entry.sources) ? entry.sources : []).forEach(url => {
                if (typeof url !== 'string' || !/^https:\/\//.test(url)) return;
                const link = document.createElement('a');
                link.href = url;
                link.target = '_blank'; link.rel = 'noopener noreferrer';
                link.textContent = url;
                article.append(link);
            });
            const remove = document.createElement('button');
            remove.type = 'button'; remove.textContent = 'Remove from this browser';
            remove.addEventListener('click', () => { ChronicNerdAddons.removeNote(entry.id); renderNotes(); });
            article.append(remove);
            container.append(article);
        });
    }
    renderNotes();
})();
