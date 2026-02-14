// ==========================================================
// ==  Interaction Handler Module (交互处理器)
// ==  Responsibility: 鼠标输入处理、拖拽、缩放、视线追踪
// ==========================================================

/**
 * 本模块负责将用户的鼠标/触摸操作转换为对模型的控制指令。
 * 
 * 功能:
 * 1. **模型拖拽**: 在 Canvas 上按住鼠标左键移动模型。
 * 2. **滚轮缩放**: 使用鼠标滚轮缩放模型。
 * 3. **视线追踪 (Gaze Control)**: 将鼠标位置映射到模型参数 (Head/Eye X/Y)，实现“注视”效果。
 * 4. **点击/悬停检测**: 检测鼠标是否在角色非透明区域上，并通知 Python。
 */

// Configuration & State
window.isDragEnabled = false;
window.isZoomEnabled = false;
window.isGazeControlEnabled = false;
window.isDragging = false;
window.isConsideredDrag = false; // 是否已触发拖拽阈值 (区分点击和拖拽)
window.dragStartX = 0;
window.dragStartY = 0;
window.DRAG_THRESHOLD = 5; // 像素阈值
window.hoverTimeoutId = null;
window.HOVER_DELAY = 1000;
window.gazeVariableMap = null; // Python 传入的参数映射表

// ==========================================================
// ==  Public API (Called by Python)
// ==========================================================

/**
 * 开启/关闭视线跟随。
 * @param {boolean} enable - 开关
 * @param {object} paramsFromPython - 包含 HEAD_LR, EYE_UD 等参数范围的配置对象
 */
window.enableGazeControl = function(enable, paramsFromPython) {
    try {
        const canvas = document.getElementById('emote-canvas');
        if (enable) {
            window.gazeVariableMap = paramsFromPython;
            canvas.addEventListener('mousemove', onGazeMouseMove);
            window.isGazeControlEnabled = true;
        } else {
            canvas.removeEventListener('mousemove', onGazeMouseMove);
            // Reset to center
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

/**
 * 开启/关闭模型拖拽。
 */
window.enablePlayerDrag = function(enable) {
    window.isDragEnabled = enable;
    const canvas = document.getElementById('emote-canvas');
    if (enable) {
        canvas.classList.add('draggable'); // Show 'grab' cursor
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

/**
 * 初始化所有事件监听器。
 * 在 bridge_manager.js 初始化完成后调用。
 */
window.setupEventListeners = function() {
    console.log("[Interaction] Setting up event listeners...");
    const canvas = document.getElementById('emote-canvas');
    if (!canvas) {
        console.error("[Interaction] Canvas #emote-canvas not found!");
        return;
    }

    canvas.addEventListener('mousedown', onMouseDown);
    canvas.addEventListener('wheel', onWheel);
    
    // Click Handling (with Drag Check)
    canvas.addEventListener('click', (event) => {
        if (window.isConsideredDrag) return; // 如果刚才发生了拖拽，则忽略此次点击
        if (window.isOverCharacter(event.offsetX, event.offsetY)) {
            if (window.py_api) window.py_api.js_on_character_click();
        }
    });
    
    // Hover Handling
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

// --- Drag Handlers ---

function onMouseDown(event) {
    if (!window.isDragEnabled || event.button !== 0) return;
    
    window.isDragging = true;
    window.isConsideredDrag = false;
    window.dragStartX = event.clientX;
    window.dragStartY = event.clientY;
    
    // Bind global listeners to capture drag outside canvas
    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('mouseup', onMouseUp);
    document.addEventListener('mouseleave', onMouseUp); 
    
    const canvas = document.getElementById('emote-canvas');
    canvas.classList.add('dragging'); // Show 'grabbing' cursor
}

function onMouseMove(event) {
    if (!window.isDragging) return;
    
    const dx = event.clientX - window.dragStartX;
    const dy = event.clientY - window.dragStartY;
    
    // Threshold Check
    if (!window.isConsideredDrag && Math.sqrt(dx * dx + dy * dy) > window.DRAG_THRESHOLD) {
        window.isConsideredDrag = true;
    }
    
    if (window.emotePlayer) {
        const currentCoord = window.emotePlayer.coord;
        // Update model position
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

// --- Zoom Handler ---

function onWheel(event) {
    if (!window.isZoomEnabled) return;
    event.preventDefault();
    
    if (window.emotePlayer) {
        const scaleDelta = event.deltaY > 0 ? 0.8 : 1.1; // Zoom Out / In
        window.emotePlayer.setScale(window.emotePlayer.scale * scaleDelta, 100);
    }
}

// --- Gaze Handler ---

function onGazeMouseMove(event) {
    try {
        if (!window.isGazeControlEnabled || !window.emotePlayer || !window.gazeVariableMap) return;
        const map = window.gazeVariableMap;
        
        // Normalize Mouse Position (-1.0 to 1.0) relative to element
        const rect = event.target.getBoundingClientRect();
        const x = (event.clientX - rect.left) / rect.width * 2 - 1;
        const y = (event.clientY - rect.top) / rect.height * 2 - 1;
        
        Object.values(map).forEach(paramInfo => {
            let targetValue;
            // Map normalized mouse pos to Live2D parameter range
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

/**
 * 像素级点击检测。
 * 读取 Canvas 某点的 Alpha 值来判断是否点击到了角色。
 */
window.isOverCharacter = function(x, y) {
    try {
        if (!window.emotePlayer || !window.emotePlayer.initialized || !EmotePlayer.device) {
            return false;
        }
        const canvas = document.getElementById('emote-canvas');
        
        // Handle High DPI scaling
        const scaleX = canvas.width / canvas.clientWidth;
        const scaleY = canvas.height / canvas.clientHeight;

        const textureX = Math.floor(x * scaleX);
        const textureY = Math.floor(y * scaleY);
        
        if (textureX < 0 || textureX >= canvas.width || textureY < 0 || textureY >= canvas.height) {
            return false;
        }
        
        // Requires custom 'readPixelAlpha' method on EmoteDevice
        // If not available, fallback to false
        if (typeof EmotePlayer.device.readPixelAlpha !== 'function') {
            console.warn("isOverCharacter requires 'readPixelAlpha' method in EmoteDevice class.");
            EmotePlayer.device.readPixelAlpha = () => 0; 
            return false;
        }

        const alpha = EmotePlayer.device.readPixelAlpha(textureX, textureY);
        return alpha > 10; // Threshold
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
