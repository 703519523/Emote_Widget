// ==========================================================
// ==  Mask Sampler Module
// ==  Handles pixel sampling for click-through transparency
// ==========================================================

// Global State
window.lastMaskJson = "";
window.maskUpdatePending = false;
window.isClickThroughSamplingEnabled = false;
window.MASK_GRID_W = 30;
window.MASK_GRID_H = 30;

// ==========================================================
// ==  Public API
// ==========================================================

window.setMaskGridSize = function(width, height) {
    if (width > 0 && height > 0) {
        window.MASK_GRID_W = width;
        window.MASK_GRID_H = height;
        console.log(`[ClickThrough] Grid size updated to: ${width}x${height}`);
    }
}

window.setClickThroughMode = function(enable) {
    console.log(`[ClickThrough] Sampling Enabled: ${enable}`);
    window.isClickThroughSamplingEnabled = enable;
    if (!enable) {
        // When disabled, we don't send anything. Controller decides fallback.
    }
}

// ==========================================================
// ==  Sampling Loop
// ==========================================================

window.updateHitTestMask = function() {
    if (!window.isClickThroughSamplingEnabled) return;
    if (window.maskUpdatePending) return;
    
    window.maskUpdatePending = true;
    // Use requestAnimationFrame to avoid blocking the UI thread
    requestAnimationFrame(() => {
        window.maskUpdatePending = false;
        window.performMaskSampling();
    });
}

// Start the sampling loop
setInterval(window.updateHitTestMask, 200);

// ==========================================================
// ==  Core Algorithm (Strict Directional Greedy Meshing)
// ==========================================================

window.performMaskSampling = function() {
    if (!window.isClickThroughSamplingEnabled) return;
    if (!window.py_api || !window.emotePlayer || !window.emotePlayer.initialized) return;
    if (typeof EmotePlayer === 'undefined' || !EmotePlayer.device) return;

    const canvas = document.getElementById('emote-canvas');
    if (!canvas) return;
    
    const width = canvas.width;
    const height = canvas.height;
    
    try {
        const device = EmotePlayer.device;
        if (!device.renderTexture || !device.gl) return;

        const gl = device.gl;
        const currentFBO = gl.getParameter(gl.FRAMEBUFFER_BINDING);
        
        if (!device.hitTestFBO) device.hitTestFBO = gl.createFramebuffer();
        
        gl.bindFramebuffer(gl.FRAMEBUFFER, device.hitTestFBO);
        const tex = EmoteDevice_GetEmoteTexture2Tex(device.renderTexture);
        gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, tex, 0);
        
        const pixels = new Uint8Array(width * height * 4);
        gl.readPixels(0, 0, width, height, gl.RGBA, gl.UNSIGNED_BYTE, pixels);
        gl.bindFramebuffer(gl.FRAMEBUFFER, currentFBO);
        
        const GRID_W = window.MASK_GRID_W || 30; 
        const GRID_H = window.MASK_GRID_H || 30; 
        
        // Step 1: Build Grid & Statistics
        const cols = Math.ceil(width / GRID_W);
        const rows = Math.ceil(height / GRID_H);
        const grid = new Uint8Array(rows * cols);
        
        // Stats for orientation detection
        const rowWeights = new Uint32Array(rows);
        const colWeights = new Uint32Array(cols);
        
        const halfGW = Math.floor(GRID_W / 2);
        const halfGH = Math.floor(GRID_H / 2);
        
        for (let r = 0; r < rows; r++) {
            for (let c = 0; c < cols; c++) {
                const pxStart = c * GRID_W;
                const pyStart = r * GRID_H;
                
                // 5-point sampling
                const points = [
                    { x: pxStart + halfGW, y: pyStart + halfGH },
                    { x: pxStart, y: pyStart },
                    { x: pxStart + GRID_W - 1, y: pyStart },
                    { x: pxStart, y: pyStart + GRID_H - 1 },
                    { x: pxStart + GRID_W - 1, y: pyStart + GRID_H - 1 }
                ];
                
                let hasContent = 0;
                for (let i = 0; i < 5; i++) {
                    const px = points[i].x;
                    const py = points[i].y;
                    if (px >= width || py >= height) continue;
                    const glY = height - 1 - py;
                    const idx = (glY * width + px) * 4 + 3;
                    if (pixels[idx] > 10) {
                        hasContent = 1;
                        break;
                    }
                }
                if (hasContent) {
                    grid[r * cols + c] = 1;
                    rowWeights[r]++;
                    colWeights[c]++;
                }
            }
        }
        
        // Step 2: Determine Global Orientation
        let maxRowWeight = 0;
        for(let r=0; r<rows; r++) if(rowWeights[r] > maxRowWeight) maxRowWeight = rowWeights[r];
        
        let maxColWeight = 0;
        for(let c=0; c<cols; c++) if(colWeights[c] > maxColWeight) maxColWeight = colWeights[c];

        // Calculate average non-zero width/height
        let totalW = 0, countW = 0;
        const cutoffRow = maxRowWeight * 0.1; // Filter noise
        for(let r=0; r<rows; r++) {
            if(rowWeights[r] > cutoffRow) {
                totalW += rowWeights[r];
                countW++;
            }
        }
        const avgW = countW > 0 ? totalW / countW : 0;

        let totalH = 0, countH = 0;
        const cutoffCol = maxColWeight * 0.1;
        for(let c=0; c<cols; c++) {
            if(colWeights[c] > cutoffCol) {
                totalH += colWeights[c];
                countH++;
            }
        }
        const avgH = countH > 0 ? totalH / countH : 0;
        
        // Check if explicitly horizontal (e.g. lying down)
        // If avgW is significantly larger than avgH, we enforce Horizontal Greedy
        const isHorizontalBody = avgW > (avgH * 1.1); 
        
        // Step 3: Strict Directional Greedy Meshing
        const visited = new Uint8Array(rows * cols);
        const rects = []; 
        const logicScale = 1.0 / (window.currentScaleFactor || 1.0);
        
        for (let r = 0; r < rows; r++) {
            for (let c = 0; c < cols; c++) {
                const idx = r * cols + c;
                if (grid[idx] === 0 || visited[idx] === 1) continue;
                
                let finalW = 0, finalH = 0;
                
                if (isHorizontalBody) {
                    // --- FORCE HORIZONTAL STRATEGY ---
                    // 1. Find Max Width
                    let w = 1;
                    while (c + w < cols) {
                        const nextIdx = r * cols + (c + w);
                        if (grid[nextIdx] === 1 && visited[nextIdx] === 0) w++;
                        else break;
                    }
                    
                    // 2. Expand Height (With Strict Lookahead Protection)
                    let h = 1;
                    check_h: while (r + h < rows) {
                        const rowOffset = (r + h) * cols;
                        
                        // PROTECTION: If next row is wider than current w, STOP.
                        // We do not want to vertically merge into a longer horizontal strip.
                        if (c + w < cols) {
                            const rightNeighbor = rowOffset + (c + w);
                            if (grid[rightNeighbor] === 1 && visited[rightNeighbor] === 0) {
                                break check_h;
                            }
                        }
                        
                        // Standard Check
                        for (let k = 0; k < w; k++) {
                            const checkIdx = rowOffset + (c + k);
                            if (grid[checkIdx] === 0 || visited[checkIdx] === 1) break check_h;
                        }
                        h++;
                    }
                    finalW = w;
                    finalH = h;
                } 
                else {
                    // --- FORCE VERTICAL STRATEGY ---
                    // 1. Find Max Height
                    let h = 1;
                    while (r + h < rows) {
                        const nextIdx = (r + h) * cols + c;
                        if (grid[nextIdx] === 1 && visited[nextIdx] === 0) h++;
                        else break;
                    }
                    
                    // 2. Expand Width (With Strict Lookahead Protection)
                    let w = 1;
                    check_w: while (c + w < cols) {
                        // PROTECTION: If next col is taller than current h, STOP.
                        if (r + h < rows) {
                            const bottomNeighbor = (r + h) * cols + (c + w);
                            if (grid[bottomNeighbor] === 1 && visited[bottomNeighbor] === 0) {
                                break check_w;
                            }
                        }
                        
                        // Standard Check
                        for (let k = 0; k < h; k++) {
                            const checkIdx = (r + k) * cols + (c + w);
                            if (grid[checkIdx] === 0 || visited[checkIdx] === 1) break check_w;
                        }
                        w++;
                    }
                    finalW = w;
                    finalH = h;
                }
                
                // Mark Visited
                for (let i = 0; i < finalH; i++) {
                    const rowOffset = (r + i) * cols + c;
                    for (let j = 0; j < finalW; j++) {
                        visited[rowOffset + j] = 1;
                    }
                }
                
                // Output
                const startX = Math.floor(c * GRID_W * logicScale);
                const startY = Math.floor(r * GRID_H * logicScale);
                const endX = Math.floor((c + finalW) * GRID_W * logicScale);
                const endY = Math.floor((r + finalH) * GRID_H * logicScale);
                
                rects.push([
                    startX, 
                    startY, 
                    Math.max(1, endX - startX), 
                    Math.max(1, endY - startY)
                ]);
            }
        }
        
        const jsonStr = JSON.stringify(rects);
        if (jsonStr !== window.lastMaskJson) {
            window.lastMaskJson = jsonStr;
            if (window.py_api && window.py_api.receive_render_mask) {
                window.py_api.receive_render_mask(jsonStr);
            }
        }
        
    } catch (e) {
        console.error("Mask sampling failed:", e);
        return;
    }
}
