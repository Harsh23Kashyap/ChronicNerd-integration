// Small, isolated About-page previews. They do not access account data or the live chat.
(() => {
    const temporary = document.querySelector('.mini-temp-toggle');
    temporary?.addEventListener('click', () => {
        const active = temporary.getAttribute('aria-pressed') !== 'true';
        temporary.setAttribute('aria-pressed', String(active));
        temporary.textContent = active ? 'Preview saved chat' : 'Preview temporary chat';
        const demo = temporary.closest('.chat-demo');
        demo.classList.toggle('preview-temporary', active);
        demo.querySelector('.mini-mode').textContent = active ? 'Temporary · not saved' : 'Saved conversation';
        demo.querySelector('.mini-question').textContent = active ? 'A question just for now' : 'How much protein do I need?';
        demo.querySelector('.mini-answer').textContent = active ? 'This preview is not added to history.' : "Let's look at your goal and the research.";
    });
    const toggle = document.querySelector('.mini-chart-toggle');
    toggle?.addEventListener('click', () => {
        const chart = toggle.closest('.comparison-demo').querySelector('.mini-chart');
        const table = toggle.closest('.comparison-demo').querySelector('.mini-table');
        const show = chart.hidden;
        chart.hidden = !show; table.hidden = show;
        toggle.setAttribute('aria-pressed', String(show));
        toggle.textContent = show ? 'View as table' : 'View as chart';
    });
    const copy = document.querySelector('.mini-copy');
    copy?.addEventListener('click', () => {
        copy.textContent = 'Copied · preview';
        setTimeout(() => { if (copy.isConnected) copy.textContent = 'Copy answer'; }, 1800);
    });
})();
