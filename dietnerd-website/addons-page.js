(async function () {
    const user = await DietNerdAPI.currentUser();
    if (!user) {
        window.location.href = 'login.html';
        return;
    }
    document.getElementById('signed-in').textContent = user;
    document.documentElement.classList.remove('auth-pending');
    for (const feature of ['ledger']) {
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
})();
