// Helper to inject splash screen HTML if missing
(function() {
    const injectSplash = () => {
        if (!document.getElementById('splash-screen')) {
            const splashHTML = `
            <div id="splash-screen">
                <div class="splash-content">
                    <h1 class="splash-title">EmoteWidget <span id="splash-version"></span></h1>
                    <div class="progress-container">
                        <div class="progress-label" id="main-progress-label">初始化...</div>
                        <div class="progress-bar-background">
                            <div class="progress-bar-fill" id="main-progress-bar"></div>
                        </div>
                    </div>
                    <div class="progress-container">
                        <div class="progress-label" id="plugin-progress-label">等待插件...</div>
                        <div class="progress-bar-background">
                            <div class="progress-bar-fill" id="plugin-progress-bar"></div>
                        </div>
                    </div>
                    <div id="error-console">
                        <div class="error-header">加载日志:</div>
                    </div>
                </div>
            </div>`;
            document.body.insertAdjacentHTML('afterbegin', splashHTML);
        }
    };

    if (document.body) {
        injectSplash();
    } else {
        document.addEventListener('DOMContentLoaded', injectSplash);
    }
})();

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