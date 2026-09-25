(function () {
    function openHome(event) {
        if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
        const anchor = event.target.closest('a[href]');
        if (!anchor || anchor.target && anchor.target !== '_self' || anchor.hasAttribute('download')) return;
        const destination = new URL(anchor.href, window.location.href);
        if (destination.origin !== location.origin || !/(?:^|\/)index\.html$/.test(destination.pathname)) return;
        event.preventDefault();
        const overlay = document.getElementById('home-transition');
        overlay.hidden = false;
        requestAnimationFrame(() => requestAnimationFrame(() => { window.location.assign(destination.href); }));
    }
    document.addEventListener('click', openHome);
    window.addEventListener('pageshow', () => { document.getElementById('home-transition').hidden = true; });
})();
