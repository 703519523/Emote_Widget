// ==========================================================
// ==  Dialog System Module
// ==  Handles dialog themes, typewriter effects, and positioning
// ==========================================================

// Global State
window.currentDialogTheme = null;
window.dialogContainer = null;
window.dialogText = null;
window.dialogBox = null;
window.hideDialogTimeout = null;
window.typewritingTimeout = null;
window.debounceTimeout = null;
window.currentDialogText = "";
window.dialogYOffset = -80; // Default offset
window.currentLoadedTheme = null;

// ==========================================================
// ==  Public API (Called by Python or Core)
// ==========================================================

window.showCharacterDialog = async function(text, duration_ms = 3000, themeUrl, y_offset, type_speed, anchor_marker) {
    // [Modified] Pass URL directly
    await loadDialogTheme(themeUrl);
    
    // Check to prevent errors if theme loading failed
    if (!ensureDialogElements()) return;

    window.dialogYOffset = y_offset;

    updateDialogPosition(); 
    showDialog();
    
    typewriterEffect(window.dialogText, text, type_speed);
    
    const typingDuration = text.length * type_speed;
    const totalDuration = typingDuration + duration_ms + 500;
    
    clearTimeout(window.hideDialogTimeout);
    window.hideDialogTimeout = setTimeout(hideDialog, totalDuration);
}

window.debouncedUpdateDialogPosition = function() {
    const DEBOUNCE_DELAY = 150; // ms
    
    // Clear previous timer
    clearTimeout(window.debounceTimeout);
    
    // Set new timer
    window.debounceTimeout = setTimeout(() => {
        updateDialogPosition();
    }, DEBOUNCE_DELAY);
}

window.updateDialogPosition = function() {
    if (!ensureDialogElements() || !window.emotePlayer || !window.emotePlayer.isCharaProfileAvailable) return;

    const state = {
        scale: window.emotePlayer.scale,
        coord: window.emotePlayer.coord,
        bounds: window.emotePlayer.charaBounds
    };

    const pos = calculateDialogPosition(state, window.dialogYOffset);
    if (!pos) return;

    // Use left/top as anchor center, transform using translate(-50%, -100%)
    window.dialogContainer.style.left = `${pos.left}px`;
    window.dialogContainer.style.top = `${pos.top}px`;
    window.dialogContainer.style.transform = `translate(-50%, -100%) scale(${pos.scale})`;
}

// ==========================================================
// ==  Theme Loader
// ==========================================================

async function loadDialogTheme(themeUrl) {
    if (window.currentLoadedTheme === themeUrl) return;

    console.log(`[THEME] Loading theme from: ${themeUrl}`);
    
    const dialogRoot = document.getElementById('dialog-root');

    try {
        // Use XMLHttpRequest instead of fetch for better custom protocol support (emote://)
        const themeContent = await new Promise((resolve, reject) => {
            const xhr = new XMLHttpRequest();
            xhr.open('GET', themeUrl);
            xhr.onload = () => {
                // Some WebEngine versions return status 0 for custom protocols
                if ((xhr.status >= 200 && xhr.status < 300) || xhr.status === 0) {
                    resolve(xhr.responseText);
                } else {
                    reject(new Error(`Load failed, status: ${xhr.status}`));
                }
            };
            xhr.onerror = () => reject(new Error('Network Error (XHR)'));
            xhr.send();
        });
        
        const tempDiv = document.createElement('div');
        tempDiv.innerHTML = themeContent;

        const styleElement = tempDiv.querySelector('#dialog-theme-style');
        const htmlElement = tempDiv.querySelector('#dialog-theme-html');

        if (!styleElement || !htmlElement) {
            throw new Error(`Theme file is missing required IDs (#dialog-theme-style or #dialog-theme-html).`);
        }

        const oldStyle = document.getElementById('dynamic-dialog-style');
        if (oldStyle) oldStyle.remove();
        styleElement.id = 'dynamic-dialog-style';
        document.head.appendChild(styleElement);

        dialogRoot.innerHTML = htmlElement.innerHTML;
        
        window.currentLoadedTheme = themeUrl;
        console.log(`[THEME] Loaded successfully.`);

    } catch (err) {
        if (typeof window.handleJsError === 'function') window.handleJsError(err, `loadDialogTheme('${themeUrl}')`);
    }
}

function ensureDialogElements() {
    const dialogRoot = document.getElementById('dialog-root');
    if (!dialogRoot) {
        console.error("[CRITICAL] Dialog root element '#dialog-root' not found in the DOM.");
        window.dialogContainer = window.dialogText = window.dialogBox = null;
        return false;
    }

    window.dialogContainer = dialogRoot.querySelector(".dialog-container");
    window.dialogText = dialogRoot.querySelector("#dialog-text");
    window.dialogBox = dialogRoot.querySelector(".dialog-box");
    
    const success = window.dialogContainer && window.dialogText && window.dialogBox;
    if (!success) {
        console.error(
            "[CRITICAL] Dialog element query failed within '#dialog-root'.\n" +
            `  - .dialog-container found: ${!!window.dialogContainer}\n` +
            `  - #dialog-text found: ${!!window.dialogText}\n` +
            `  - .dialog-box found: ${!!window.dialogBox}\n` +
            "  Please check the HTML structure of your theme file and the unwrapping logic in loadDialogTheme."
        );
    }
    return success;
}

// ==========================================================
// ==  Typewriter Effect
// ==========================================================

function typewriterEffect(element, text, speed_ms = 50) {
    clearTimeout(window.typewritingTimeout);
    if (!element || !text) return;

    element.innerHTML = ''; // Clear old content
    const dialogBox = element.closest(".dialog-box");
    if (!dialogBox) return;

    // Shrink dialog first
    dialogBox.style.opacity = '0';
    dialogBox.style.maxHeight = '0px';
    dialogBox.style.paddingTop = '0';
    dialogBox.style.paddingBottom = '0';

    const lines = text.split('\n');
    let currentLineIndex = 0;
    let currentLineCharIndex = 0;
    let currentLineElement = null;
    let lineSpans = [];

    // Expand dialog (fade in outer box)
    requestAnimationFrame(() => {
        dialogBox.style.opacity = '1';
        dialogBox.style.paddingTop = '15px';
        dialogBox.style.paddingBottom = '15px';
    });

    function revealNextChar() {
        if (currentLineIndex >= lines.length) {
            // All done, ensure final height is accurate
            requestAnimationFrame(() => {
                dialogBox.style.maxHeight = dialogBox.scrollHeight + 'px';
            });
            return;
        }

        // New line
        if (!currentLineElement) {
            currentLineElement = document.createElement('div');
            currentLineElement.className = 'dialog-line';
            element.appendChild(currentLineElement);
            lineSpans = [];
            currentLineCharIndex = 0;

            // Grow height dynamically to ensure smooth animation
            requestAnimationFrame(() => {
                dialogBox.style.maxHeight = dialogBox.scrollHeight + 'px';
            });
        }

        const currentLineText = lines[currentLineIndex];

        if (currentLineCharIndex < currentLineText.length) {
            const char = currentLineText[currentLineCharIndex];
            const span = document.createElement('span');
            span.className = 'char';
            span.innerHTML = char === ' ' ? '&nbsp;' : char;
            span.style.opacity = '0';
            span.style.transform = 'translateY(-20px) rotateX(90deg)';
            currentLineElement.appendChild(span);
            lineSpans.push(span);

            // Trigger animation next frame
            requestAnimationFrame(() => {
                span.style.opacity = '1';
                span.style.transform = 'translateY(0) rotateX(0)';
                dialogBox.style.maxHeight = dialogBox.scrollHeight + 'px';
            });

            currentLineCharIndex++;
            window.typewritingTimeout = setTimeout(revealNextChar, speed_ms);

        } else {
            // Line complete, merge spans to plain text for performance
            const lineFinalText = lineSpans.map(s => s.textContent).join('');
            currentLineElement.innerHTML = lineFinalText;

            currentLineIndex++;
            currentLineElement = null;
            lineSpans = [];

            // Continue to next line
            window.typewritingTimeout = setTimeout(revealNextChar, speed_ms);
        }
    }

    revealNextChar();
}

// ==========================================================
// ==  Visibility Management
// ==========================================================

function showDialog() {
    if (!ensureDialogElements()) return;

    window.dialogContainer.classList.add("visible");
    window.dialogContainer.style.opacity = '1';

    if (window.dialogBox) {
        // Shrink first, then expand
        window.dialogBox.style.maxHeight = '0px';

        // Expand next frame
        requestAnimationFrame(() => {
            window.dialogBox.classList.add("open");
        });
    }
}

function hideDialog() {
    if (!ensureDialogElements()) return;
    if (window.dialogBox) {
        window.dialogBox.classList.remove("open");
    }

    window.dialogContainer.style.opacity = '0';
    window.dialogContainer.classList.remove("visible");
    clearTimeout(window.hideDialogTimeout);
    clearTimeout(window.typewritingTimeout);

    if (window.dialogText) {
        const onTransitionEnd = (e) => {
            if (e.propertyName === "opacity") {
                window.dialogText.innerHTML = "";
                if (window.dialogBox) {
                    window.dialogBox.style.maxHeight = '0px';
                    window.dialogBox.style.paddingTop = '0px';
                    window.dialogBox.style.paddingBottom = '0px';
                    window.dialogBox.style.borderWidth = '0px';
                    window.dialogBox.style.borderColor = 'transparent';
                }

                // Remove listener to avoid leaks
                window.dialogContainer.removeEventListener("transitionend", onTransitionEnd);
            }
        };
        window.dialogContainer.addEventListener("transitionend", onTransitionEnd);
    }
}

// ==========================================================
// ==  Helpers
// ==========================================================

function calculateDialogPosition(emotePlayerState, y_offset_px) {
    if (!window.dialogContainer || !emotePlayerState) return null;

    const { scale, coord, bounds } = emotePlayerState;
    const canvas = document.getElementById('emote-canvas');
    const viewportWidth = document.body.clientWidth;
    const viewportHeight = document.body.clientHeight;
    const safeMargin = 50;

    // Anchor: Model top center
    const anchorX_model = (bounds.left + bounds.right) / 2;
    const anchorY_model = bounds.top;

    // To World Coordinates
    const worldX = anchorX_model * scale + coord[0];
    const worldY = anchorY_model * scale + coord[1];

    // Map to Screen
    const screenX = worldX + canvas.clientWidth / 2;
    const screenY = worldY + canvas.clientHeight / 2 + y_offset_px;

    // Boundary Limits
    const finalX = Math.min(Math.max(screenX, safeMargin), viewportWidth - safeMargin);
    const finalY = Math.min(Math.max(screenY, safeMargin), viewportHeight - safeMargin);

    return { left: finalX, top: finalY, scale: 1 };
}
