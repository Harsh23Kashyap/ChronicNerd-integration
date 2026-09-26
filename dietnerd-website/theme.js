(() => {
    const key = 'dietnerd_theme';
    let saved;
    try { saved = localStorage.getItem(key); } catch { saved = null; }
    let currentMode = ['dark','light'].includes(saved) ? saved : 'light';
    const apply = () => {
        const dark = currentMode === 'dark';
        document.documentElement.dataset.theme = dark ? 'dark' : 'light';
        document.querySelectorAll('[data-theme-toggle]').forEach(button => {
            const label = dark ? 'Switch to light mode' : 'Switch to dark mode';
            button.setAttribute('aria-label', label);
            button.title = label;
        });
    };
    if (saved && !['dark','light'].includes(saved)) { try { localStorage.removeItem(key); } catch {} }
    apply();
    document.addEventListener('DOMContentLoaded', () => {
        apply();
        document.querySelectorAll('[data-theme-toggle]').forEach(button => button.addEventListener('click', () => {
            currentMode = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
            try { localStorage.setItem(key, currentMode); } catch {}
            apply();
            if (!matchMedia('(prefers-reduced-motion: reduce)').matches) {
                button.classList.remove('theme-just-changed');
                void button.offsetWidth;
                button.classList.add('theme-just-changed');
                setTimeout(() => button.classList.remove('theme-just-changed'), 420);
            }
        }));
    });
})();
