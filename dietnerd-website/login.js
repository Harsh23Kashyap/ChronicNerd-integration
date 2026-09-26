(function () {
    const { apiFetch, readError, currentUser } = window.DietNerdAPI;
    const forms = ['login-form', 'register-form'];

    function show(id) {
        forms.forEach((formId) => { document.getElementById(formId).hidden = formId !== id; });
        document.querySelectorAll('.error-message, .success-message').forEach((el) => { el.textContent = ''; });
        const first = document.querySelector(`#${id} input`);
        if (first) first.focus();
        const titles = {
            'login-form': 'Sign in', 'register-form': 'Create account',
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
        if (!email || !password) { errorEl.textContent = 'Please enter your username and password.'; return; }
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
        const emailFeedback = document.getElementById('register-email-feedback');
        emailFeedback.textContent = '';
        document.getElementById('register-email').removeAttribute('aria-invalid');
        errorEl.textContent = '';
        if (!email || !password) { errorEl.textContent = 'Please enter a username and a password.'; return; }
        if (password.length < 8) { errorEl.textContent = 'Password must be at least 8 characters.'; return; }
        if (password !== confirm) { errorEl.textContent = 'The two passwords do not match.'; return; }
        const button = document.getElementById('register-button');
        setBusy(button, true, 'Creating account...');
        try {
            const res = await post('/register', { email, password });
            if (!res.ok) {
                const message = await readError(res, 'Could not create the account.');
                if (res.status === 409 && /already (?:registered|exists)/i.test(message)) {
                    emailFeedback.textContent = 'This email or username is already registered. Try signing in.';
                    document.getElementById('register-email').setAttribute('aria-invalid', 'true');
                } else errorEl.textContent = message;
                return;
            }
            const data = await res.json();
            sessionStorage.setItem('dietnerd_user', data.email);
            window.location.href = 'index.html';
        } catch (e) {
            errorEl.textContent = 'Could not reach the server. Please try again in a moment.';
        } finally {
            setBusy(button, false);
        }
    });

    show('login-form');
    currentUser().then((email) => { if (email) window.location.href = 'index.html'; });
})();

document.getElementById('register-email').addEventListener('input', () => {
    document.getElementById('register-email-feedback').textContent = '';
    document.getElementById('register-email').removeAttribute('aria-invalid');
});
