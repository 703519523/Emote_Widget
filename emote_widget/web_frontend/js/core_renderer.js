// ==========================================================
// ==  Core Renderer Module
// ==  Responsible for EmotePlayer lifecycle, rendering quality, and canvas management
// ==========================================================

// [HOOK] Force WebGL Antialiasing (MSAA)
(function() {
    const originalGetContext = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function(type, attributes) {
        if (type === 'webgl' || type === 'experimental-webgl' || type === 'webgl2') {
            attributes = attributes || {};
            attributes.antialias = true;
            attributes.alpha = true;
            attributes.preserveDrawingBuffer = true; // Required to avoid flickering
            // console.log(`[Hook] WebGL Context created with antialias=true for ${type}`);
        }
        return originalGetContext.call(this, type, attributes);
    };
})();

// Global Variables (Exposed for Python API and other modules)
window.emotePlayer = null;
window.RENDER_WIDTH = 2048;
window.RENDER_HEIGHT = 2048 * (16/9); 
window.currentScaleMode = 'auto';
window.currentScaleFactor = 1.0;
window.isMirrored = false;

// Internal state
let resizeTimeout = null;

// ==========================================================
// ==  Public API (Called by Python)
// ==========================================================

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
            // Auto mode: follow system scaling, at least 1.0
            window.currentScaleFactor = Math.max(window.devicePixelRatio || 1.0, 1.0);
            break;
    }

    // Apply new scaling immediately
    const canvas = document.getElementById('emote-canvas');
    if (canvas) {
        // Trigger resize logic to apply new resolution
        window.dispatchEvent(new Event('resize'));
    }
}

window.loadNewModel = async function(modelUrl) {
    console.log(`JS: Received command, loading model URL: '${modelUrl}'`);
    try {
        const canvas = document.getElementById('emote-canvas');
        
        // Remove listener if player exists to avoid memory leaks or duplicate calls
        if (window.emotePlayer) {
            // Note: debouncedUpdateDialogPosition comes from dialog_system.js
            if (typeof window.debouncedUpdateDialogPosition === 'function') {
                window.emotePlayer.off('transformchange', window.debouncedUpdateDialogPosition);
            }
        }

        if (!window.emotePlayer) {
            console.log(`JS: First load, creating EmotePlayer instance...`);
            
            // Dynamic resolution adaptation
            if (window.currentScaleMode === 'auto') {
                window.currentScaleFactor = Math.max(window.devicePixelRatio || 1.0, 1.0); 
            }
            
            const w = Math.floor((canvas.clientWidth || window.RENDER_WIDTH) * window.currentScaleFactor);
            const h = Math.floor((canvas.clientHeight || window.RENDER_HEIGHT) * window.currentScaleFactor);
            
            console.log(`[Render] Creating canvas: ${w}x${h} (Scale: ${window.currentScaleFactor})`);

            canvas.width = w;
            canvas.height = h;
            
            EmotePlayer.createRenderCanvas(w, h);
            window.emotePlayer = new EmotePlayer(canvas);
        }

        await window.emotePlayer.promiseLoadDataFromURL(modelUrl);

        // Re-attach listener if dialog system is present
        if (typeof window.debouncedUpdateDialogPosition === 'function') {
            window.emotePlayer.on('transformchange', window.debouncedUpdateDialogPosition);
        }
        
        console.log("JS: Model data loaded successfully!");
        const timelines = window.emotePlayer.mainTimelineLabels || [];

        // Wait for bridge if not ready (bridgeReadyPromise from bridge_manager.js)
        if (!window.py_api && window.bridgeReadyPromise) {
            await window.bridgeReadyPromise; 
        }

        if (window.py_api && typeof window.py_api.on_player_ready === 'function') {
            window.py_api.on_player_ready(timelines);
        }
        
    } catch (err) {
        if (typeof window.handleJsError === 'function') {
            window.handleJsError(err, `loadNewModel('${modelUrl}')`);
        } else {
            console.error(err);
        }
        window.emotePlayer = null;
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

window.autoCenterPlayer = function(duration) {
    try {
        if (!window.emotePlayer || !window.emotePlayer.isCharaProfileAvailable) return;
        const canvas = document.getElementById('emote-canvas');
        const bounds = window.emotePlayer.charaBounds;
        if (!bounds || bounds.right === bounds.left) return;

        const modelWidth = bounds.right - bounds.left;
        const modelHeight = bounds.bottom - bounds.top;
        if (modelWidth <= 0 || modelHeight <= 0) return;
        
        const scaleX = canvas.width / modelWidth;
        const scaleY = canvas.height / modelHeight;
        const scale = Math.min(scaleX, scaleY) * 0.95;

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
        canvas.classList.add('mirrored');
    } else {
        canvas.classList.remove('mirrored');
    }
}

// Window Resize Handler
window.addEventListener('resize', () => {
    // Debounce to avoid frequent calculations
    clearTimeout(resizeTimeout);
    resizeTimeout = setTimeout(() => {
        // Dynamic Canvas Resolution Adjustment
        if (window.currentScaleMode === 'auto') {
                window.currentScaleFactor = Math.max(window.devicePixelRatio || 1.0, 1.0);
        }

        const canvas = document.getElementById('emote-canvas');
        if (!canvas) return;

        const w = Math.floor(canvas.clientWidth * window.currentScaleFactor);
        const h = Math.floor(canvas.clientHeight * window.currentScaleFactor);
        
        // Only reset if size actually changed (tolerance check)
        if (w && h && (Math.abs(canvas.width - w) > 1 || Math.abs(canvas.height - h) > 1)) {
            console.log(`[Render] Resizing canvas to: ${w}x${h} (Scale: ${window.currentScaleFactor})`);
            canvas.width = w;
            canvas.height = h;
            if (typeof EmotePlayer !== 'undefined' && typeof EmotePlayer.createRenderCanvas === 'function') {
                    EmotePlayer.createRenderCanvas(w, h);
            }
        }

        if (window.emotePlayer) {
            // Re-center player to fit new window
            window.autoCenterPlayer(0); 
        }
        
        // Update dialog position if the function exists
        if (typeof window.updateDialogPosition === 'function') {
            window.updateDialogPosition();
        }
    }, 100);
});
