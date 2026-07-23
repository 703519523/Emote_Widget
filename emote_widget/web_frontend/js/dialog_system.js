// ==========================================================
// ==  Dialog System Module (对话框系统)
// ==  Responsibility: 气泡显示、打字机特效、动态跟随、主题加载
// ==========================================================

/**
 * 本模块实现了一个富交互的角色对话框系统。
 * 
 * 主要特性:
 * 1. **动态跟随**: 对话框会根据角色模型的实时位置 (坐标 + 缩放) 自动计算屏幕坐标，
 *    确保气泡始终悬浮在角色头顶。
 * 2. **主题引擎**: 支持加载 HTML/CSS 模板，实现完全自定义的对话框外观。
 * 3. **打字机特效**: 逐字显示文本，带有简单的入场动画。
 */

// Global State
window.currentDialogTheme = null;
window.dialogContainer = null;
window.dialogText = null;
window.dialogBox = null;
window.hideDialogTimeout = null;
window.typewritingTimeout = null;
window.debounceTimeout = null;
window.currentDialogText = "";
window.dialogYOffset = -80; // 默认垂直偏移量
window.currentLoadedTheme = null;

// ==========================================================
// ==  Public API (Called by Python)
// ==========================================================

/**
 * 显示角色对话框。
 * @param {string} text - 文本内容
 * @param {number} duration_ms - 显示时长 (ms)
 * @param {string} themeUrl - 主题文件 URL (emote://)
 * @param {number} y_offset - 垂直偏移修正
 * @param {number} type_speed - 打字速度 (ms/char)
 * @param {string} anchor_marker - 锚点标记 (暂未启用)
 */
window.showCharacterDialog = async function(text, duration_ms = 3000, themeUrl, y_offset, type_speed, anchor_marker) {
    // 1. 加载或切换主题
    await loadDialogTheme(themeUrl);
    
    // 2. 检查 DOM 完整性
    if (!ensureDialogElements()) return;

    window.dialogYOffset = y_offset;

    // 3. 更新位置并显示
    updateDialogPosition(); 
    showDialog();
    
    // 4. 播放打字机动画
    typewriterEffect(window.dialogText, text, type_speed);
    
    // 5. 设置自动隐藏定时器 (打字时间 + 停留时间)
    const typingDuration = text.length * type_speed;
    const totalDuration = typingDuration + duration_ms + 500;
    
    clearTimeout(window.hideDialogTimeout);
    window.hideDialogTimeout = setTimeout(hideDialog, totalDuration);
}

/**
 * 防抖动的更新位置函数。
 * 用于在模型移动频繁时降低 DOM 操作频率。
 */
window.debouncedUpdateDialogPosition = function() {
    const DEBOUNCE_DELAY = 150; // ms
    clearTimeout(window.debounceTimeout);
    window.debounceTimeout = setTimeout(() => {
        updateDialogPosition();
    }, DEBOUNCE_DELAY);
}

/**
 * 实时计算对话框位置。
 * 根据 Live2D 模型的 World Transform 计算屏幕坐标。
 */
window.updateDialogPosition = function() {
    if (!ensureDialogElements() || !window.emotePlayer || !window.emotePlayer.isCharaProfileAvailable) return;

    const state = {
        scale: window.emotePlayer.scale,
        coord: window.emotePlayer.coord,
        bounds: window.emotePlayer.charaBounds
    };

    const pos = calculateDialogPosition(state, window.dialogYOffset);
    if (!pos) return;

    // 应用坐标
    // 使用 transform 实现平滑移动
    window.dialogContainer.style.left = `${pos.left}px`;
    window.dialogContainer.style.top = `${pos.top}px`;
    window.dialogContainer.style.transform = `translate(-50%, -100%) scale(${pos.scale})`;
}

// ==========================================================
// ==  Theme Loader (主题加载器)
// ==========================================================

async function loadDialogTheme(themeUrl) {
    if (window.currentLoadedTheme === themeUrl) return;

    console.log(`[THEME] Loading theme from: ${themeUrl}`);
    const dialogRoot = document.getElementById('dialog-root');

    try {
        // 使用 XMLHttpRequest 而非 fetch，以获得更好的本地协议 (emote://, file://) 兼容性
        const themeContent = await new Promise((resolve, reject) => {
            const xhr = new XMLHttpRequest();
            xhr.open('GET', themeUrl);
            xhr.onload = () => {
                // QtWebEngine 对自定义协议可能返回 status 0，视为成功
                if ((xhr.status >= 200 && xhr.status < 300) || xhr.status === 0) {
                    resolve(xhr.responseText);
                } else {
                    reject(new Error(`Load failed, status: ${xhr.status}`));
                }
            };
            xhr.onerror = () => reject(new Error('Network Error (XHR)'));
            xhr.send();
        });
        
        // 解析 HTML 片段
        const tempDiv = document.createElement('div');
        tempDiv.innerHTML = themeContent;

        const styleElement = tempDiv.querySelector('#dialog-theme-style');
        const htmlElement = tempDiv.querySelector('#dialog-theme-html');

        if (!styleElement || !htmlElement) {
            throw new Error(`Theme file is missing required IDs (#dialog-theme-style or #dialog-theme-html).`);
        }

        // 注入 CSS (替换旧样式)
        const oldStyle = document.getElementById('dynamic-dialog-style');
        if (oldStyle) oldStyle.remove();
        styleElement.id = 'dynamic-dialog-style';
        document.head.appendChild(styleElement);

        // 注入 HTML 结构
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
        return false;
    }

    // 默认主题通过 XHR 异步预加载；加载完成前挂载点为空是正常状态，不应误报结构损坏。
    if (!window.currentLoadedTheme) return false;

    // 缓存 DOM 引用
    window.dialogContainer = dialogRoot.querySelector(".dialog-container");
    window.dialogText = dialogRoot.querySelector("#dialog-text");
    window.dialogBox = dialogRoot.querySelector(".dialog-box");
    
    const success = window.dialogContainer && window.dialogText && window.dialogBox;
    if (!success) {
        console.error("[CRITICAL] Dialog theme structure invalid. Missing container, text, or box elements.");
    }
    return success;
}

// ==========================================================
// ==  Typewriter Effect (打字机特效)
// ==========================================================

function typewriterEffect(element, text, speed_ms = 50) {
    clearTimeout(window.typewritingTimeout);
    if (!element || !text) return;

    element.innerHTML = ''; 
    const dialogBox = element.closest(".dialog-box");
    if (!dialogBox) return;

    // Reset Animation State
    dialogBox.style.opacity = '0';
    dialogBox.style.maxHeight = '0px';
    dialogBox.style.paddingTop = '0';
    dialogBox.style.paddingBottom = '0';

    const lines = text.split('\n');
    let currentLineIndex = 0;
    let currentLineCharIndex = 0;
    let currentLineElement = null;
    let lineSpans = [];

    // Fade In
    requestAnimationFrame(() => {
        dialogBox.style.opacity = '1';
        dialogBox.style.paddingTop = '15px';
        dialogBox.style.paddingBottom = '15px';
    });

    function revealNextChar() {
        if (currentLineIndex >= lines.length) {
            // End
            requestAnimationFrame(() => {
                dialogBox.style.maxHeight = dialogBox.scrollHeight + 'px';
            });
            return;
        }

        // Create New Line
        if (!currentLineElement) {
            currentLineElement = document.createElement('div');
            currentLineElement.className = 'dialog-line';
            element.appendChild(currentLineElement);
            lineSpans = [];
            currentLineCharIndex = 0;

            // Expand height
            requestAnimationFrame(() => {
                dialogBox.style.maxHeight = dialogBox.scrollHeight + 'px';
            });
        }

        const currentLineText = lines[currentLineIndex];

        if (currentLineCharIndex < currentLineText.length) {
            // Append Char
            const char = currentLineText[currentLineCharIndex];
            const span = document.createElement('span');
            span.className = 'char';
            span.innerHTML = char === ' ' ? '&nbsp;' : char;
            
            // Initial State (Hidden & Rotated)
            span.style.opacity = '0';
            span.style.transform = 'translateY(-20px) rotateX(90deg)';
            currentLineElement.appendChild(span);
            lineSpans.push(span);

            // Animate In
            requestAnimationFrame(() => {
                span.style.opacity = '1';
                span.style.transform = 'translateY(0) rotateX(0)';
                dialogBox.style.maxHeight = dialogBox.scrollHeight + 'px';
            });

            currentLineCharIndex++;
            window.typewritingTimeout = setTimeout(revealNextChar, speed_ms);

        } else {
            // Line Finished: Merge to plain text to save memory/rendering cost
            const lineFinalText = lineSpans.map(s => s.textContent).join('');
            currentLineElement.innerHTML = lineFinalText;

            currentLineIndex++;
            currentLineElement = null;
            lineSpans = [];

            window.typewritingTimeout = setTimeout(revealNextChar, speed_ms);
        }
    }

    revealNextChar();
}

// ==========================================================
// ==  Visibility Management (显隐控制)
// ==========================================================

function showDialog() {
    if (!ensureDialogElements()) return;

    window.dialogContainer.classList.add("visible");
    window.dialogContainer.style.opacity = '1';

    if (window.dialogBox) {
        window.dialogBox.style.maxHeight = '0px';
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
        // Cleanup after fade out
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

    // Anchor Point: Model Top Center (in Model Space)
    const anchorX_model = (bounds.left + bounds.right) / 2;
    const anchorY_model = bounds.top;

    // Convert to World Coordinates (Canvas Pixel Space)
    const worldX = anchorX_model * scale + coord[0];
    const worldY = anchorY_model * scale + coord[1];

    // Convert to Screen Coordinates (Origin: Top-Left)
    // Canvas Origin (0,0) is center of screen.
    const screenX = worldX + canvas.clientWidth / 2;
    const screenY = worldY + canvas.clientHeight / 2 + y_offset_px;

    // Clamp to Viewport (Prevent dialog going off-screen)
    const finalX = Math.min(Math.max(screenX, safeMargin), viewportWidth - safeMargin);
    const finalY = Math.min(Math.max(screenY, safeMargin), viewportHeight - safeMargin);

    return { left: finalX, top: finalY, scale: 1 };
}
