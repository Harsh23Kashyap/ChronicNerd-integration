(function () {
    const { apiFetch, readError, currentUser } = window.DietNerdAPI;
    const forms = ['login-form', 'register-form', 'forgot-form', 'reset-form'];
    let resetToken = null;

    function show(id) {
        forms.forEach((formId) => { document.getElementById(formId).hidden = formId !== id; });
        document.querySelectorAll('.error-message, .success-message').forEach((el) => { el.textContent = ''; });
        const first = document.querySelector(`#${id} input`);
        if (first) first.focus();
        const titles = {
            'login-form': 'Sign in', 'register-form': 'Create account',
            'forgot-form': 'Reset password', 'reset-form': 'Choose a new password',
        };
        document.title = `DietNerd - ${titles[id]}`;
    }

    function setBusy(button, busy, label) {
        if (!button.dataset.label) button.dataset.label = button.textContent;
        button.disabled = busy;
        button.textContent = busy ? label : button.dataset.label;
    }

    async function post(path, body) {
        return apiFetch(path, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
            allowUnauthorized: true,
        });
    }

    document.querySelectorAll('[data-show]').forEach((link) => {
        link.addEventListener('click', (event) => { event.preventDefault(); show(link.dataset.show); });
    });

    document.querySelectorAll('.toggle-password').forEach((button) => {
        button.addEventListener('click', () => {
            const input = document.getElementById(button.dataset.target);
            const reveal = input.type === 'password';
            input.type = reveal ? 'text' : 'password';
            button.textContent = reveal ? 'Hide' : 'Show';
            button.setAttribute('aria-label', reveal ? 'Hide password' : 'Show password');
        });
    });

    document.getElementById('login-form').addEventListener('submit', async (event) => {
        event.preventDefault();
        const email = document.getElementById('login-email').value.trim();
        const password = document.getElementById('login-password').value;
        const errorEl = document.getElementById('login-error');
        errorEl.textContent = '';
        if (!email || !password) { errorEl.textContent = 'Please enter your email and password.'; return; }
        const button = document.getElementById('login-button');
        setBusy(button, true, 'Signing in...');
        try {
            const res = await post('/login', { email, password });
            if (!res.ok) { errorEl.textContent = await readError(res, 'Sign in failed. Please try again.'); return; }
            const data = await res.json();
            sessionStorage.setItem('dietnerd_user', data.email);
            window.location.href = 'index.html';
        } catch (e) {
            errorEl.textContent = 'Could not reach the server. Please try again in a moment.';
        } finally {
            setBusy(button, false);
        }
    });

    document.getElementById('register-form').addEventListener('submit', async (event) => {
        event.preventDefault();
        const email = document.getElementById('register-email').value.trim();
        const password = document.getElementById('register-password').value;
        const confirm = document.getElementById('register-confirm').value;
        const errorEl = document.getElementById('register-error');
        errorEl.textContent = '';
        if (!email || !password) { errorEl.textContent = 'Please enter an email and a password.'; return; }
        if (password.length < 8) { errorEl.textContent = 'Password must be at least 8 characters.'; return; }
        if (password !== confirm) { errorEl.textContent = 'The two passwords do not match.'; return; }
        const button = document.getElementById('register-button');
        setBusy(button, true, 'Creating account...');
        try {
            const res = await post('/register', { email, password });
            if (!res.ok) { errorEl.textContent = await readError(res, 'Could not create the account.'); return; }
            const data = await res.json();
            sessionStorage.setItem('dietnerd_user', data.email);
            window.location.href = 'index.html';
        } catch (e) {
            errorEl.textContent = 'Could not reach the server. Please try again in a moment.';
        } finally {
            setBusy(button, false);
        }
    });

    document.getElementById('forgot-form').addEventListener('submit', async (event) => {
        event.preventDefault();
        const email = document.getElementById('forgot-email').value.trim();
        const errorEl = document.getElementById('forgot-error');
        const okEl = document.getElementById('forgot-success');
        errorEl.textContent = ''; okEl.textContent = '';
        if (!email) { errorEl.textContent = 'Please enter your email.'; return; }
        const button = document.getElementById('forgot-button');
        setBusy(button, true, 'Sending...');
        try {
            const res = await post('/forgot_password', { email });
            if (!res.ok) { errorEl.textContent = await readError(res, 'Could not send the link. Please try again.'); return; }
            okEl.textContent = (await res.json()).message;
        } catch (e) {
            errorEl.textContent = 'Could not reach the server. Please try again in a moment.';
        } finally {
            setBusy(button, false);
        }
    });

    document.getElementById('reset-form').addEventListener('submit', async (event) => {
        event.preventDefault();
        const password = document.getElementById('reset-password').value;
        const confirm = document.getElementById('reset-confirm').value;
        const errorEl = document.getElementById('reset-error');
        errorEl.textContent = '';
        if (password.length < 8) { errorEl.textContent = 'Password must be at least 8 characters.'; return; }
        if (password !== confirm) { errorEl.textContent = 'The two passwords do not match.'; return; }
        const button = document.getElementById('reset-button');
        setBusy(button, true, 'Saving...');
        try {
            const res = await post('/reset_password', { token: resetToken, password });
            if (!res.ok) { errorEl.textContent = await readError(res, 'This reset link is invalid or has expired.'); return; }
            const message = (await res.json()).message;
            history.replaceState(null, '', 'login.html');
            resetToken = null;
            show('login-form');
            document.getElementById('login-info').textContent = message;
        } catch (e) {
            errorEl.textContent = 'Could not reach the server. Please try again in a moment.';
        } finally {
            setBusy(button, false);
        }
    });

    function readResetToken() {
        const match = window.location.hash.match(/reset_token=([^&]+)/);
        if (!match) return false;
        resetToken = decodeURIComponent(match[1]);
        show('reset-form');
        return true;
    }

    // A reset link opened while this page is already loaded only changes the hash.
    window.addEventListener('hashchange', readResetToken);

    if (!readResetToken()) {
        show('login-form');
        currentUser().then((email) => { if (email) window.location.href = 'index.html'; });
    }
})();
