// ==========================================================
// ==  Core Renderer Module (核心渲染模块)
// ==  Responsibility: EmotePlayer 生命周期管理、画质控制、画布适配
// ==========================================================

/**
 * 本模块是 Web 前端的核心，负责：
 * 1. 管理 Live2D/EmotePlayer 实例的创建与销毁。
 * 2. 处理模型加载逻辑 (loadNewModel)。
 * 3. 处理窗口大小变化与 Canvas 分辨率自适应。
 * 4. 提供画质调节 API (setRenderQuality)。
 */

// [HOOK] Force WebGL Antialiasing (MSAA)
// 强制开启 WebGL 抗锯齿，这对于 Live2D 模型的边缘平滑度非常重要。
// 由于某些 EmotePlayer 版本内部可能默认关闭，这里通过 Hook 强制开启。
(function() {
    const originalGetContext = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function(type, attributes) {
        if (type === 'webgl' || type === 'experimental-webgl' || type === 'webgl2') {
            attributes = attributes || {};
            attributes.antialias = true; // 开启 MSAA
            attributes.alpha = true;     // 允许背景透明
            attributes.preserveDrawingBuffer = true; // 允许 readPixels (对 MaskSampler 至关重要)
            // console.log(`[Hook] WebGL Context created with antialias=true for ${type}`);
        }
        return originalGetContext.call(this, type, attributes);
    };
})();

// Global Variables (Exposed for Python API and other modules)
window.emotePlayer = null; // 当前 EmotePlayer 实例
window.RENDER_WIDTH = 2048; // 默认渲染分辨率宽
window.RENDER_HEIGHT = 2048 * (16/9); // 默认渲染分辨率高
window.currentScaleMode = 'auto';
window.currentScaleFactor = 1.0;
window.isMirrored = false;

// Internal state
let resizeTimeout = null;
window.modelLoadState = 'idle';
window.emoteRuntimeFatal = false;

window.requireReadyPlayer = function(operationName) {
    if (window.modelLoadState !== 'ready' || !window.emotePlayer || window.emoteRuntimeFatal) {
        console.debug(`[Render] Ignored ${operationName}: player is not ready.`);
        return false;
    }
    return true;
};

// ==========================================================
// ==  Public API (Called by Python)
// ==========================================================

/**
 * 设置渲染画质 (超采样倍率)。
 * @param {string} mode - 'low'(1x), 'high'(2x), 'ultra'(4x), 'auto'(DPI跟随)
 */
window.setRenderQuality = function(mode) {
    window.currentScaleMode = mode || 'auto';
    console.log(`[Render] Setting render quality to: ${window.currentScaleMode}`);

    switch (window.currentScaleMode) {
        case 'low':
            window.currentScaleFactor = 1.0;
            break;
        case 'high':
            window.currentScaleFactor = 2.0;
            break;
        case 'ultra':
            window.currentScaleFactor = 4.0;
            break;
        case 'auto':
        default:
            // Auto mode: follow system DPI (devicePixelRatio), minimum 1.0
            // 这在高分屏 (4K/Retina) 上能获得最佳清晰度
            window.currentScaleFactor = Math.max(window.devicePixelRatio || 1.0, 1.0);
            break;
    }

    // Apply new scaling immediately by triggering resize
    const canvas = document.getElementById('emote-canvas');
    if (canvas) {
        window.dispatchEvent(new Event('resize'));
    }
}

/**
 * 加载新模型。
 * @param {string} modelUrl - 模型的 emote:// URL
 */
window.loadNewModel = async function(modelUrl, loadId) {
    console.log(`JS: Received command, loading model URL: '${modelUrl}'`);
    const previousPlayer = window.emotePlayer;
    let candidatePlayer = null;
    // 提交后，后续桥接通知即使抛错也不能把已提交的实例回滚并销毁。
    let playerCommitted = false;
    window.modelLoadState = 'loading';
    try {
        if (window.emoteRuntimeFatal) {
            throw new Error('Emote WASM runtime is in a fatal state and must be reloaded.');
        }
        const canvas = document.getElementById('emote-canvas');
        
        // 每次加载使用候选实例。旧实例保持 active，直到候选模型完整成功。
        if (!previousPlayer) {
            console.log(`JS: First load, creating EmotePlayer instance...`);
            
            // Initial resolution setup
            if (window.currentScaleMode === 'auto') {
                window.currentScaleFactor = Math.max(window.devicePixelRatio || 1.0, 1.0); 
            }
            
            // Calculate physical pixel size
            const w = Math.floor((canvas.clientWidth || window.RENDER_WIDTH) * window.currentScaleFactor);
            const h = Math.floor((canvas.clientHeight || window.RENDER_HEIGHT) * window.currentScaleFactor);
            
            console.log(`[Render] Creating canvas: ${w}x${h} (Scale: ${window.currentScaleFactor})`);

            canvas.width = w;
            canvas.height = h;
            
            // Initialize EmotePlayer runtime
            EmotePlayer.createRenderCanvas(w, h);
            candidatePlayer = new EmotePlayer(canvas);
        } else {
            candidatePlayer = new EmotePlayer(canvas);
        }

        // Load data asynchronously
        await candidatePlayer.promiseLoadDataFromURL(modelUrl);

        // Re-attach listeners (e.g., sync dialog position when model moves)
        if (typeof window.debouncedUpdateDialogPosition === 'function') {
            candidatePlayer.on('transformchange', window.debouncedUpdateDialogPosition);
        }
        
        console.log("JS: Model data loaded successfully!");
        
        // Get available animations
        const timelines = candidatePlayer.mainTimelineLabels || [];

        // Ensure Bridge is ready before calling Python
        if (!window.py_api && window.bridgeReadyPromise) {
            await window.bridgeReadyPromise; 
        }

        window.emotePlayer = candidatePlayer;
        window.modelLoadState = 'ready';
        playerCommitted = true;
        // 提交候选实例后再释放旧实例，避免切换期间短暂没有可用 player。
        if (previousPlayer && previousPlayer !== candidatePlayer) {
            previousPlayer.destroy();
        }
        if (window.py_api && typeof window.py_api.on_model_load_succeeded === 'function') {
            window.py_api.on_model_load_succeeded(loadId, JSON.stringify({ timelines }));
        } else if (window.py_api && typeof window.py_api.on_player_ready === 'function') {
            window.py_api.on_player_ready(timelines);
        }
        
    } catch (err) {
        const message = (err && err.message) ? err.message : String(err || 'Unknown model load error');
        const stack = (err && err.stack) ? err.stack : '';
        const fatal = /abort(?:\(\d*\))?|fatal state|EmotePlayer_Initialize/i.test(message + '\n' + stack);
        const code = fatal ? 'WASM_ABORT' : 'MODEL_RUNTIME_LOAD_FAILED';
        if (playerCommitted) {
            // 模型已经成功提交；这里只报告桥接层异常，绝不销毁 active player。
            window.modelLoadState = 'ready';
            window.emoteRuntimeFatal = false;
        } else if (!fatal) {
            // 非致命模型错误不应摧毁当前可用的 player。
            // Controller 会恢复旧模型的 Python 状态；这里保持实例和 ready 状态，
            // 这样后续正常模型仍可继续加载。
            window.modelLoadState = 'ready';
            window.emoteRuntimeFatal = false;
            window.emotePlayer = previousPlayer;
            if (candidatePlayer && candidatePlayer !== previousPlayer) {
                candidatePlayer.destroy();
            }
        } else {
            window.modelLoadState = 'fatal';
            window.emoteRuntimeFatal = true;
            if (previousPlayer) {
                previousPlayer.destroy();
            }
            if (candidatePlayer && candidatePlayer !== previousPlayer) {
                candidatePlayer.destroy();
            }
            window.emotePlayer = null;
        }
        if (window.py_api && typeof window.py_api.on_model_load_failed === 'function') {
            window.py_api.on_model_load_failed(loadId, code, message, stack, fatal);
        } else if (typeof window.handleJsError === 'function') {
            window.handleJsError(err, `loadNewModel('${modelUrl}')`);
        }
    }
}

window.setBackgroundColor = function(r, g, b, a) {
    try {
        document.body.style.backgroundColor = `rgba(${r}, ${g}, ${b}, ${a})`;
    } catch (err) {
        if (typeof window.handleJsError === 'function') window.handleJsError(err, 'setBackgroundColor');
    }
}

window.setBackgroundImage = function(imageUrl) {
    try {
        const bgDiv = document.getElementById('bg-div');
        bgDiv.style.backgroundImage = imageUrl ? `url('${imageUrl}')` : 'none';
    } catch (err) {
        if (typeof window.handleJsError === 'function') window.handleJsError(err, 'setBackgroundImage');
    }
}

/**
 * 自动居中模型。
 * 计算模型的 AABB 包围盒，自动缩放和平移以适应当前窗口大小。
 */
window.autoCenterPlayer = function(duration) {
    try {
        if (!window.emotePlayer || !window.emotePlayer.isCharaProfileAvailable) return;
        const canvas = document.getElementById('emote-canvas');
        const bounds = window.emotePlayer.charaBounds;
        if (!bounds || bounds.right === bounds.left) return;

        const modelWidth = bounds.right - bounds.left;
        const modelHeight = bounds.bottom - bounds.top;
        if (modelWidth <= 0 || modelHeight <= 0) return;
        
        // Calculate fit scale (contain mode)
        const scaleX = canvas.width / modelWidth;
        const scaleY = canvas.height / modelHeight;
        const scale = Math.min(scaleX, scaleY) * 0.95; // 5% padding

        const centerX = (bounds.left + bounds.right) / 2;
        const centerY = (bounds.top + bounds.bottom) / 2;

        window.emotePlayer.setScale(scale, duration);
        window.emotePlayer.setCoord(-centerX * scale, -centerY * scale, duration);
    } catch (err) {
        if (typeof window.handleJsError === 'function') window.handleJsError(err, 'autoCenterPlayer');
    }
}

window.setMirror = function(enable) {
    window.isMirrored = enable;
    const canvas = document.getElementById('emote-canvas');
    if (enable) {
        canvas.classList.add('mirrored'); // Apply CSS transform: scaleX(-1)
    } else {
        canvas.classList.remove('mirrored');
    }
}

// ==========================================================
// ==  Window Resize Handling
// ==========================================================

window.addEventListener('resize', () => {
    // Debounce: Wait for resize to finish before re-allocating buffers
    clearTimeout(resizeTimeout);
    resizeTimeout = setTimeout(() => {
        // Recalculate scale factor if in auto mode
        if (window.currentScaleMode === 'auto') {
                window.currentScaleFactor = Math.max(window.devicePixelRatio || 1.0, 1.0);
        }

        const canvas = document.getElementById('emote-canvas');
        if (!canvas) return;

        // Calculate new physical resolution
        const w = Math.floor(canvas.clientWidth * window.currentScaleFactor);
        const h = Math.floor(canvas.clientHeight * window.currentScaleFactor);
        
        // Resize WebGL Context
        if (w && h && (Math.abs(canvas.width - w) > 1 || Math.abs(canvas.height - h) > 1)) {
            console.log(`[Render] Resizing canvas to: ${w}x${h} (Scale: ${window.currentScaleFactor})`);
            canvas.width = w;
            canvas.height = h;
            if (!window.emoteRuntimeFatal && typeof EmotePlayer !== 'undefined' && typeof EmotePlayer.createRenderCanvas === 'function') {
                    EmotePlayer.createRenderCanvas(w, h);
            }
        }

        if (window.emotePlayer) {
            // Re-center player to fit new window
            window.autoCenterPlayer(0); 
        }
        
        // Update dialog position
        if (typeof window.updateDialogPosition === 'function') {
            window.updateDialogPosition();
        }
    }, 100);
});
