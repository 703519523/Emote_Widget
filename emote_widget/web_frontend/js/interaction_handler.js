// ==========================================================
// ==  Interaction Handler Module
// ==  Manages mouse inputs, drag/zoom, and gaze tracking
// ==========================================================

// Configuration & State
window.isDragEnabled = false;
window.isZoomEnabled = false;
window.isGazeControlEnabled = false;
window.isDragging = false;
window.isConsideredDrag = false;
window.dragStartX = 0;
window.dragStartY = 0;
window.DRAG_THRESHOLD = 5;
window.hoverTimeoutId = null;
window.HOVER_DELAY = 1000;
window.gazeVariableMap = null;

// ==========================================================
// ==  Public API
// ==========================================================

window.enableGazeControl = function(enable, paramsFromPython) {
    try {
        const canvas = document.getElementById('emote-canvas');
        if (enable) {
            window.gazeVariableMap = paramsFromPython;
            canvas.addEventListener('mousemove', onGazeMouseMove);
            window.isGazeControlEnabled = true;
        } else {
            canvas.removeEventListener('mousemove', onGazeMouseMove);
            if (window.gazeVariableMap && window.emotePlayer) {
                const map = window.gazeVariableMap;
                Object.values(map).forEach(paramInfo => {
                    if (paramInfo && paramInfo.name && paramInfo.range) {
                        const middleValue = (paramInfo.range[0] + paramInfo.range[1]) / 2.0;
                        window.emotePlayer.setVariable(paramInfo.name, middleValue, 300);
                    }
                });
            }
            window.isGazeControlEnabled = false;
        }
    } catch (err) {
        if (typeof window.handleJsError === 'function') window.handleJsError(err, 'enableGazeControl');
    }
}

window.enablePlayerDrag = function(enable) {
    window.isDragEnabled = enable;
    const canvas = document.getElementById('emote-canvas');
    if (enable) {
        canvas.classList.add('draggable');
    } else {
        canvas.classList.remove('draggable');
    }
}

window.enablePlayerZoom = function(enable) {
    window.isZoomEnabled = enable;
}

// ==========================================================
// ==  Event Listeners & Handlers
// ==========================================================

window.setupEventListeners = function() {
    console.log("[Interaction] Setting up event listeners...");
    const canvas = document.getElementById('emote-canvas');
    if (!canvas) {
        console.error("[Interaction] Canvas #emote-canvas not found!");
        return;
    }

    canvas.addEventListener('mousedown', onMouseDown);
    canvas.addEventListener('wheel', onWheel);
    canvas.addEventListener('click', (event) => {
        if (window.isConsideredDrag) return;
        if (window.isOverCharacter(event.offsetX, event.offsetY)) {
            if (window.py_api) window.py_api.js_on_character_click();
        }
    });
    canvas.addEventListener('mousemove', (event) => {
        clearTimeout(window.hoverTimeoutId);
        if (window.isOverCharacter(event.offsetX, event.offsetY)) {
            window.hoverTimeoutId = setTimeout(() => {
                if (window.py_api) window.py_api.js_on_character_hover();
            }, window.HOVER_DELAY);
        }
    });
    canvas.addEventListener('mouseleave', () => clearTimeout(window.hoverTimeoutId));
}

function onMouseDown(event) {
    if (!window.isDragEnabled || event.button !== 0) return;
    window.isDragging = true;
    window.isConsideredDrag = false;
    window.dragStartX = event.clientX;
    window.dragStartY = event.clientY;
    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('mouseup', onMouseUp);
    document.addEventListener('mouseleave', onMouseUp); 
    const canvas = document.getElementById('emote-canvas');
    canvas.classList.add('dragging');
}

function onMouseMove(event) {
    if (!window.isDragging) return;
    const dx = event.clientX - window.dragStartX;
    const dy = event.clientY - window.dragStartY;
    if (!window.isConsideredDrag && Math.sqrt(dx * dx + dy * dy) > window.DRAG_THRESHOLD) {
        window.isConsideredDrag = true;
    }
    if (window.emotePlayer) {
        const currentCoord = window.emotePlayer.coord;
        window.emotePlayer.setCoord(currentCoord[0] + dx, currentCoord[1] + dy);
    }
    window.dragStartX = event.clientX;
    window.dragStartY = event.clientY;
}

function onMouseUp(event) {
    if (!window.isDragging) return;
    window.isDragging = false;
    document.removeEventListener('mousemove', onMouseMove);
    document.removeEventListener('mouseup', onMouseUp);
    document.removeEventListener('mouseleave', onMouseUp);
    const canvas = document.getElementById('emote-canvas');
    canvas.classList.remove('dragging');
}

function onWheel(event) {
    if (!window.isZoomEnabled) return;
    event.preventDefault();
    if (window.emotePlayer) {
        const scaleDelta = event.deltaY > 0 ? 0.8 : 1.1;
        window.emotePlayer.setScale(window.emotePlayer.scale * scaleDelta, 100);
    }
}

function onGazeMouseMove(event) {
    try {
        if (!window.isGazeControlEnabled || !window.emotePlayer || !window.gazeVariableMap) return;
        const map = window.gazeVariableMap;
        const rect = event.target.getBoundingClientRect();
        
        const x = (event.clientX - rect.left) / rect.width * 2 - 1;
        const y = (event.clientY - rect.top) / rect.height * 2 - 1;
        
        Object.values(map).forEach(paramInfo => {
            let targetValue;
            if (paramInfo.special_usage.includes('HEAD_LR') || paramInfo.special_usage.includes('EYE_LR')) {
                targetValue = mapToRange(x, paramInfo.range);
            } else if (paramInfo.special_usage.includes('HEAD_UD') || paramInfo.special_usage.includes('EYE_UD')) {
                targetValue = mapToRange(y, paramInfo.range);
            }
            if (targetValue !== undefined) {
                window.emotePlayer.setVariable(paramInfo.name, targetValue, 100);
            }
        });
    } catch (err) {
        if (typeof window.handleJsError === 'function') window.handleJsError(err, 'onGazeMouseMove');
    }
}

// ==========================================================
// ==  Helpers
// ==========================================================

window.isOverCharacter = function(x, y) {
    try {
        if (!window.emotePlayer || !window.emotePlayer.initialized || !EmotePlayer.device) {
            return false;
        }
        const canvas = document.getElementById('emote-canvas');
        
        const scaleX = canvas.width / canvas.clientWidth;
        const scaleY = canvas.height / canvas.clientHeight;

        const textureX = Math.floor(x * scaleX);
        const textureY = Math.floor(y * scaleY);
        
        if (textureX < 0 || textureX >= canvas.width || textureY < 0 || textureY >= canvas.height) {
            return false;
        }
        
        if (typeof EmotePlayer.device.readPixelAlpha !== 'function') {
            console.warn("isOverCharacter requires 'readPixelAlpha' method in EmoteDevice class.");
            EmotePlayer.device.readPixelAlpha = () => 0; 
            return false;
        }

        const alpha = EmotePlayer.device.readPixelAlpha(textureX, textureY);
        return alpha > 10;
    } catch(err) {
        if (typeof window.handleJsError === 'function') window.handleJsError(err, 'isOverCharacter');
        return false;
    }
}

function mapToRange(value, range) {
    const [min, max] = range;
    const center = (max + min) / 2;
    const amplitude = (max - min) / 2;
    return center + value * amplitude;
}
