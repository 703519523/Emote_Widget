const SplashScreenAPI = {
    setVersion(version) {
        requestAnimationFrame(() => {
            const element = document.getElementById('splash-version');
            if (element) element.textContent = `v${version}`;
        });
    },

    updateMainProgress(progress, text) {
        requestAnimationFrame(() => {
            const bar = document.getElementById('main-progress-bar');
            const label = document.getElementById('main-progress-label');
            if (bar) bar.style.width = `${progress * 100}%`;
            if (label) label.textContent = text;
        });
    },

    updatePluginProgress(progress, text) {
        requestAnimationFrame(() => {
            const bar = document.getElementById('plugin-progress-bar');
            const label = document.getElementById('plugin-progress-label');
            if (bar) bar.style.width = `${progress * 100}%`;
            if (label) label.textContent = text;
        });
    },

    addLog(message, isError = false) {
        requestAnimationFrame(() => {
            const consoleDiv = document.getElementById('error-console');
            if (!consoleDiv) return;
            const p = document.createElement('p');
            p.textContent = message;
            p.className = isError ? 'error-message' : 'info-message';
            consoleDiv.appendChild(p);
            consoleDiv.scrollTop = consoleDiv.scrollHeight;
        });
    },

    dismiss() {
        requestAnimationFrame(() => {
            const splashScreen = document.getElementById('splash-screen');
            if (!splashScreen) return;
            splashScreen.classList.add('fade-out');
            splashScreen.addEventListener('transitionend', () => splashScreen.remove(), { once: true });
        });
    }
};

console.log("[Splash] SplashScreenAPI object created and ready (with requestAnimationFrame).");