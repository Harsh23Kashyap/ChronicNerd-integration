(() => {
    const key = 'dietnerd_theme';
    let saved;
    try { saved = localStorage.getItem(key); } catch { saved = null; }
    const media = matchMedia('(prefers-color-scheme: dark)');
    const apply = () => {
        let mode;
        try { mode = localStorage.getItem(key) || 'system'; } catch { mode = 'system'; }
        const dark = mode === 'dark' || (mode === 'system' && media.matches);
        document.documentElement.dataset.theme = dark ? 'dark' : 'light';
        document.querySelectorAll('[data-theme-toggle]').forEach(button => {
            button.textContent = dark ? 'Light mode' : 'Dark mode';
            button.setAttribute('aria-label', dark ? 'Switch to light mode' : 'Switch to dark mode');
        });
    };
    if (saved && !['dark','light','system'].includes(saved)) { try { localStorage.removeItem(key); } catch {} }
    apply();
    media.addEventListener?.('change', apply);
    document.addEventListener('DOMContentLoaded', () => {
        apply();
        document.querySelectorAll('[data-theme-toggle]').forEach(button => button.addEventListener('click', () => {
            try { localStorage.setItem(key, document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark'); } catch {}
            apply();
        }));
    });
})();
