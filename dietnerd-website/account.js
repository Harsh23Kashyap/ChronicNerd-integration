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
        const seconds = Number(window.DietNerdAPI.sessionExpiresInSeconds);
        if (Number.isFinite(seconds) && seconds > 0) {
            const expiry = Date.now() + seconds * 1000;
            const label = document.getElementById('session-countdown');
            label.hidden = false;
            const update = () => {
                const remaining = Math.max(0, Math.ceil((expiry - Date.now()) / 1000));
                const days = Math.floor(remaining / 86400);
                const hours = Math.floor((remaining % 86400) / 3600);
                const minutes = Math.ceil((remaining % 3600) / 60);
                label.textContent = remaining ? `Sign-out in ${days ? `${days}d ` : ''}${days || hours ? `${hours}h` : `${minutes}m`}` : 'Session expired';
                if (!remaining) { window.clearInterval(timer); location.replace('login.html'); }
            };
            const timer = window.setInterval(update, 60000);
            update();
        }
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

    const signoutDialog = document.getElementById('signout-dialog');
    const signoutConfirm = document.getElementById('signout-confirm');
    document.getElementById('logout-link').addEventListener('click', () => {
        closeMenu();
        document.getElementById('signout-error').textContent = '';
        signoutDialog.showModal();
        document.getElementById('signout-cancel').focus();
    });
    document.getElementById('signout-cancel').addEventListener('click', () => signoutDialog.close());
    signoutConfirm.addEventListener('click', async () => {
        if (signoutConfirm.disabled) return;
        signoutConfirm.disabled = true;
        try {
            const response = await apiFetch('/logout', { method: 'POST', allowUnauthorized: true });
            if (!response.ok) throw new Error('Could not sign out. Try again.');
            sessionStorage.removeItem('dietnerd_user');
            sessionStorage.removeItem('dietnerd_conversation_id');
            window.location.href = 'login.html';
        } catch (e) {
            document.getElementById('signout-error').textContent = 'Could not sign out. Check your connection and try again.';
        } finally {
            signoutConfirm.disabled = false;
        }
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
