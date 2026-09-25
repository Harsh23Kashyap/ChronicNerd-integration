(function () {
    const { apiFetch, readError, currentUser } = window.DietNerdAPI;
    const button = document.getElementById('account-button');
    const dropdown = document.getElementById('account-dropdown');
    const dialog = document.getElementById('change-password-dialog');

    const loading = document.querySelector('.app-loading');
    const loadingTimer = window.setTimeout(() => {
        if (!document.documentElement.classList.contains('auth-pending')) return;
        loading?.classList.add('failed');
        loading?.querySelector('strong')?.replaceChildren(document.createTextNode('DietNerd is taking longer than expected'));
        const status = document.createElement('p');
        status.textContent = 'Check your connection and try again.';
        const retry = document.createElement('button');
        retry.type = 'button';
        retry.textContent = 'Try again';
        retry.addEventListener('click', () => location.reload());
        loading?.append(status, retry);
    }, 12000);
    currentUser().then((email) => {
        window.clearTimeout(loadingTimer);
        if (email === null) {
            loading?.querySelector('strong')?.replaceChildren(document.createTextNode('Taking you to sign in...'));
            window.location.replace('login.html');
            return;
        }
        document.documentElement.classList.remove('auth-pending');
        loading?.remove();
        document.getElementById('account-email').textContent = email || 'Account';
        if (email === undefined) {
            document.querySelector('.hint').textContent = 'DietNerd cannot reach its server right now. Please try again in a moment.';
        }
    }).catch(() => {
        window.clearTimeout(loadingTimer);
        loading?.classList.add('failed');
        loading?.querySelector('strong')?.replaceChildren(document.createTextNode('Could not open DietNerd'));
        const retry = document.createElement('button');
        retry.type = 'button';
        retry.textContent = 'Try again';
        retry.addEventListener('click', () => location.reload());
        loading?.append(retry);
    });

    function closeMenu() { dropdown.hidden = true; button.setAttribute('aria-expanded', 'false'); }
    button.addEventListener('click', (event) => {
        event.stopPropagation();
        dropdown.hidden = !dropdown.hidden;
        button.setAttribute('aria-expanded', String(!dropdown.hidden));
    });
    document.addEventListener('click', (event) => { if (!dropdown.contains(event.target)) closeMenu(); });
    document.addEventListener('keydown', (event) => { if (event.key === 'Escape') closeMenu(); });

    document.getElementById('logout-link').addEventListener('click', async () => {
        try { await apiFetch('/logout', { method: 'POST', allowUnauthorized: true }); } catch (e) { /* signing out locally anyway */ }
        sessionStorage.removeItem('dietnerd_user');
        sessionStorage.removeItem('dietnerd_conversation_id');
        window.location.href = 'login.html';
    });

    document.getElementById('change-password-link').addEventListener('click', () => {
        closeMenu();
        document.getElementById('change-password-form').reset();
        document.getElementById('change-password-error').textContent = '';
        document.getElementById('change-password-success').textContent = '';
        dialog.showModal();
    });
    document.getElementById('change-password-cancel').addEventListener('click', () => dialog.close());

    document.getElementById('change-password-form').addEventListener('submit', async (event) => {
        event.preventDefault();
        const current = document.getElementById('current-password').value;
        const next = document.getElementById('new-password').value;
        const confirm = document.getElementById('confirm-new-password').value;
        const errorEl = document.getElementById('change-password-error');
        const okEl = document.getElementById('change-password-success');
        errorEl.textContent = ''; okEl.textContent = '';
        if (next.length < 8) { errorEl.textContent = 'New password must be at least 8 characters.'; return; }
        if (next !== confirm) { errorEl.textContent = 'The two new passwords do not match.'; return; }
        const save = document.getElementById('change-password-save');
        save.disabled = true;
        try {
            const res = await apiFetch('/change_password', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ current_password: current, new_password: next }),
            });
            if (!res.ok) { errorEl.textContent = await readError(res, 'Could not change the password.'); return; }
            okEl.textContent = (await res.json()).message;
            document.getElementById('change-password-form').reset();
        } catch (e) {
            errorEl.textContent = 'Could not reach the server. Please try again.';
        } finally {
            save.disabled = false;
        }
    });
})();
