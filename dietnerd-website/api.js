// Shared API helper. The session lives in an HttpOnly cookie set by the
// backend, so every request is sent with credentials and a 401 sends the
// user back to the sign-in page.
(function () {
    const baseURL = (window.env && window.env.API_URL) || '';

    async function apiFetch(path, options = {}) {
        const response = await fetch(`${baseURL}${path}`, { credentials: 'include', ...options });
        if (response.status === 401 && !options.allowUnauthorized) {
            sessionStorage.removeItem('dietnerd_user');
            sessionStorage.removeItem('dietnerd_conversation_id');
            if (!/login\.html$/.test(window.location.pathname)) {
                window.location.href = 'login.html';
            }
        }
        return response;
    }

    async function readError(response, fallback) {
        try {
            const data = await response.json();
            if (typeof data.detail === 'string') return data.detail;
        } catch (e) { /* not JSON */ }
        return fallback;
    }

    async function currentUser() {
        try {
            const response = await apiFetch('/me', { allowUnauthorized: true });
            if (response.status === 401 || response.status === 403) return null;
            if (!response.ok) return undefined;
            const data = await response.json();
            sessionStorage.setItem('dietnerd_user', data.email);
            window.DietNerdAPI.sessionExpiresInSeconds = data.session_expires_in_seconds;
            return data.email;
        } catch (e) {
            return undefined; // server unreachable
        }
    }

    window.DietNerdAPI = { baseURL, apiFetch, readError, currentUser };
})();
