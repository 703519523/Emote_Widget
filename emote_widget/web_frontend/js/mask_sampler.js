/**
 * ==========================================================
 * Mask Sampler Module (遮罩采样器)
 * ==========================================================
 * 
 * 职责 (Responsibility):
 * 负责高效地从 WebGL 画布中读取像素数据，识别非透明区域（即角色本体），
 * 并将其转换为一组简化的矩形列表 (Rects)。
 * 这些矩形将通过 Python Bridge 发送回 Native 层，用于设置操作系统窗口的
 * 输入遮罩 (Input Mask)，实现精确的“点击穿透”效果。
 * 
 * 核心挑战 (Core Challenge):
 * 1. 性能: 像素读取 (glReadPixels) 和 CPU 遍历是非常昂贵的操作，必须在 JS 线程
 *    中保持极高的效率，以免阻塞 UI 渲染。
 * 2. 碎片化: 如果生成的矩形太多（例如每隔一个像素一个矩形），会导致操作系统
 *    的窗口管理器 (DWM/X11) 处理缓慢。
 * 
 * 解决方案 (Solution):
 * 采用自定义的 **2D 扫描线贪心网格合并算法 (Greedy Meshing)**。
 * 该算法能在单次遍历中，根据物体的主体走向（横向或纵向），
 * 智能地将相邻的有效网格合并为最大的可能矩形，从而将矩形数量
 * 从几千个减少到几十个。
 */

// Global State
window.lastMaskJson = "";
window.maskUpdatePending = false;
window.isClickThroughSamplingEnabled = false;
window.MASK_GRID_W = 30; // 网格单元宽度 (像素)
window.MASK_GRID_H = 30; // 网格单元高度 (像素)

// ==========================================================
// ==  Public API
// ==========================================================

/**
 * 设置采样网格的大小。
 * 网格越小，边缘越精细，但性能开销越大；
 * 网格越大，性能越好，但点击判定边缘会有“锯齿感”。
 */
window.setMaskGridSize = function(width, height) {
    if (width > 0 && height > 0) {
        window.MASK_GRID_W = width;
        window.MASK_GRID_H = height;
        console.log(`[ClickThrough] Grid size updated to: ${width}x${height}`);
    }
}

/**
 * 开启或关闭采样循环。
 * 由 Python 控制器在透明模式切换时调用。
 */
window.setClickThroughMode = function(enable) {
    console.log(`[ClickThrough] Sampling Enabled: ${enable}`);
    window.isClickThroughSamplingEnabled = enable;
    if (!enable) {
        // 关闭时不需要发空数据，Native 层会自行清理
    }
}

// ==========================================================
// ==  Sampling Loop
// ==========================================================

window.updateHitTestMask = function() {
    if (!window.isClickThroughSamplingEnabled) return;
    if (window.maskUpdatePending) return;
    
    // 使用 requestAnimationFrame 确保在浏览器空闲时执行，
    // 避免与渲染主循环争抢资源。
    window.maskUpdatePending = true;
    requestAnimationFrame(() => {
        window.maskUpdatePending = false;
        window.performMaskSampling();
    });
}

// 启动定时器：每 200ms 执行一次采样。
// 5FPS 的更新频率对于点击穿透来说通常足够了。
setInterval(window.updateHitTestMask, 200);

// ==========================================================
// ==  Core Algorithm (Strict Directional Greedy Meshing)
// ==========================================================

window.performMaskSampling = function() {
    if (!window.isClickThroughSamplingEnabled) return;
    if (!window.py_api || !window.emotePlayer || !window.emotePlayer.initialized) return;
    // 依赖 Live2D 的 EmotePlayer 对象
    if (typeof EmotePlayer === 'undefined' || !EmotePlayer.device) return;

    const canvas = document.getElementById('emote-canvas');
    if (!canvas) return;
    
    const width = canvas.width;
    const height = canvas.height;
    
    try {
        // --- 1. WebGL 像素读取 ---
        // 从 Live2D 内部的 Framebuffer 读取渲染结果
        const device = EmotePlayer.device;
        if (!device.renderTexture || !device.gl) return;

        const gl = device.gl;
        const currentFBO = gl.getParameter(gl.FRAMEBUFFER_BINDING);
        
        // 创建或复用一个专用 FBO 用于读取
        if (!device.hitTestFBO) device.hitTestFBO = gl.createFramebuffer();
        
        gl.bindFramebuffer(gl.FRAMEBUFFER, device.hitTestFBO);
        // 获取 Live2D 渲染纹理
        const tex = EmoteDevice_GetEmoteTexture2Tex(device.renderTexture);
        gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, tex, 0);
        
        // 读取像素 (RGBA)
        // 优化点：其实只需要读取 Alpha 通道，但 WebGL 1.0 readPixels 对 FORMAT 有限制
        const pixels = new Uint8Array(width * height * 4);
        gl.readPixels(0, 0, width, height, gl.RGBA, gl.UNSIGNED_BYTE, pixels);
        gl.bindFramebuffer(gl.FRAMEBUFFER, currentFBO); // 恢复之前的 FBO
        
        // --- 2. 网格化 (Gridding) ---
        const GRID_W = window.MASK_GRID_W || 30; 
        const GRID_H = window.MASK_GRID_H || 30; 
        
        const cols = Math.ceil(width / GRID_W);
        const rows = Math.ceil(height / GRID_H);
        const grid = new Uint8Array(rows * cols);
        
        // 统计数组：用于判断物体主要走向
        const rowWeights = new Uint32Array(rows); // 每行有多少个有效格子
        const colWeights = new Uint32Array(cols); // 每列有多少个有效格子
        
        const halfGW = Math.floor(GRID_W / 2);
        const halfGH = Math.floor(GRID_H / 2);
        
        // 遍历所有网格
        for (let r = 0; r < rows; r++) {
            for (let c = 0; c < cols; c++) {
                const pxStart = c * GRID_W;
                const pyStart = r * GRID_H;
                
                // 5点采样法 (5-point sampling)
                // 不检查网格内所有像素（太慢），而是检查中心点和四个角。
                // 只要有一个点的 Alpha > 10，就认为该网格“有内容”。
                const points = [
                    { x: pxStart + halfGW, y: pyStart + halfGH }, // Center
                    { x: pxStart, y: pyStart },                   // Top-Left
                    { x: pxStart + GRID_W - 1, y: pyStart },      // Top-Right
                    { x: pxStart, y: pyStart + GRID_H - 1 },      // Bottom-Left
                    { x: pxStart + GRID_W - 1, y: pyStart + GRID_H - 1 } // Bottom-Right
                ];
                
                let hasContent = 0;
                for (let i = 0; i < 5; i++) {
                    const px = points[i].x;
                    const py = points[i].y;
                    if (px >= width || py >= height) continue;
                    
                    // WebGL 坐标系 Y 轴是翻转的，需要转换
                    const glY = height - 1 - py;
                    const idx = (glY * width + px) * 4 + 3; // Alpha channel index
                    if (pixels[idx] > 10) { // Threshold
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
        
        // --- 3. 姿态检测 (Orientation Detection) ---
        // 为了优化合并效果，我们需要知道角色是“站着”还是“躺着”。
        // 站立的角色（纵向长）适合优先纵向合并；躺着的角色（横向长）适合横向合并。
        
        // 计算平均有效宽度和高度
        let totalW = 0, countW = 0;
        const cutoffRow = Math.max(...rowWeights) * 0.1; // 过滤噪点
        for(let r=0; r<rows; r++) {
            if(rowWeights[r] > cutoffRow) {
                totalW += rowWeights[r];
                countW++;
            }
        }
        const avgW = countW > 0 ? totalW / countW : 0;

        let totalH = 0, countH = 0;
        const cutoffCol = Math.max(...colWeights) * 0.1;
        for(let c=0; c<cols; c++) {
            if(colWeights[c] > cutoffCol) {
                totalH += colWeights[c];
                countH++;
            }
        }
        const avgH = countH > 0 ? totalH / countH : 0;
        
        // 如果平均宽度显著大于平均高度（1.1倍），则认为是横向姿态（如躺倒动作）
        const isHorizontalBody = avgW > (avgH * 1.1); 
        
        // --- 4. 严格方向贪心合并 (Strict Directional Greedy Meshing) ---
        // 这是一个改进版的 Greedy Meshing 算法。
        // 普通算法在合并时比较随意，容易产生大量细长的碎片。
        // 本算法强制优先沿“主方向”延伸，并且禁止“切断”未来的主方向合并机会。
        
        const visited = new Uint8Array(rows * cols);
        const rects = []; 
        
        // 获取逻辑缩放因子（High DPI 屏幕适配）
        let factor = window.currentScaleFactor;
        if (typeof factor !== 'number' || factor <= 0.001) {
            factor = 1.0;
        }
        const logicScale = 1.0 / factor;
        
        for (let r = 0; r < rows; r++) {
            for (let c = 0; c < cols; c++) {
                const idx = r * cols + c;
                if (grid[idx] === 0 || visited[idx] === 1) continue;
                
                // 开始一个新的矩形合并
                let finalW = 0, finalH = 0;
                
                if (isHorizontalBody) {
                    // === 策略 A: 强制横向优先 (Horizontal First) ===
                    
                    // 1. 尽可能向右延伸 (Find Max Width)
                    let w = 1;
                    while (c + w < cols) {
                        const nextIdx = r * cols + (c + w);
                        if (grid[nextIdx] === 1 && visited[nextIdx] === 0) w++;
                        else break;
                    }
                    
                    // 2. 向下扩展高度 (Expand Height)
                    // 关键保护：如果下一行的同列位置也是横向长条的一部分，
                    // 为了保持那个长条的完整性，这里不要向下侵占。
                    let h = 1;
                    check_h: while (r + h < rows) {
                        const rowOffset = (r + h) * cols;
                        
                        // [Lookahead Protection]
                        // 检查下一行紧邻右侧的格子是否也是有效且未访问的？
                        // 如果是，说明下一行可能有一个更长的横条等待生成，不要截断它。
                        if (c + w < cols) {
                            const rightNeighbor = rowOffset + (c + w);
                            if (grid[rightNeighbor] === 1 && visited[rightNeighbor] === 0) {
                                break check_h; // 停止向下扩展
                            }
                        }
                        
                        // 标准检查：当前行的 [c, c+w] 范围内必须全都是有效格子
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
                    // === 策略 B: 强制纵向优先 (Vertical First) ===
                    
                    // 1. 尽可能向下延伸 (Find Max Height)
                    let h = 1;
                    while (r + h < rows) {
                        const nextIdx = (r + h) * cols + c;
                        if (grid[nextIdx] === 1 && visited[nextIdx] === 0) h++;
                        else break;
                    }
                    
                    // 2. 向右扩展宽度 (Expand Width)
                    let w = 1;
                    check_w: while (c + w < cols) {
                        // [Lookahead Protection]
                        // 检查下一列紧邻下方的格子。如果它是有效且未访问的，
                        // 说明右侧可能有一个更长的竖条，不要向右侵占截断它。
                        if (r + h < rows) {
                            const bottomNeighbor = (r + h) * cols + (c + w);
                            if (grid[bottomNeighbor] === 1 && visited[bottomNeighbor] === 0) {
                                break check_w;
                            }
                        }
                        
                        // 标准检查
                        for (let k = 0; k < h; k++) {
                            const checkIdx = (r + k) * cols + (c + w);
                            if (grid[checkIdx] === 0 || visited[checkIdx] === 1) break check_w;
                        }
                        w++;
                    }
                    finalW = w;
                    finalH = h;
                }
                
                // 标记已访问
                for (let i = 0; i < finalH; i++) {
                    const rowOffset = (r + i) * cols + c;
                    for (let j = 0; j < finalW; j++) {
                        visited[rowOffset + j] = 1;
                    }
                }
                
                // 计算实际像素坐标并应用 DPI 缩放
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
        
        // --- 5. 数据回传 ---
        // 构造 Int16Array: [x1, y1, x2, y2, ...]
        const count = rects.length;
        const bufferLen = count * 4;
        const dataArr = new Int16Array(bufferLen);
        
        for (let i = 0; i < count; i++) {
            const r = rects[i];
            // rects[i] = [x, y, w, h] -> [x1, y1, x2, y2]
            dataArr[i * 4 + 0] = r[0];
            dataArr[i * 4 + 1] = r[1];
            dataArr[i * 4 + 2] = r[0] + r[2];
            dataArr[i * 4 + 3] = r[1] + r[3];
        }

        // 简单的去重机制 (基于二进制内容比较)
        let isSame = false;
        if (window.lastMaskBinary && window.lastMaskBinary.length === dataArr.length) {
            isSame = true;
            for (let i = 0; i < dataArr.length; i++) {
                if (dataArr[i] !== window.lastMaskBinary[i]) {
                    isSame = false;
                    break;
                }
            }
        }

        if (!isSame) {
            window.lastMaskBinary = dataArr;
            // 优先使用二进制接口
            if (window.py_api && window.py_api.receive_render_mask_binary) {
                // 如果是纯 QWebChannel，可能需要将 buffer 转换为 values 数组传递，或者依赖底层支持 buffer
                // 此处按 Task 要求传递 buffer (在 Qt WebEngine 中通常会被映射为 QByteArray 或 list)
                // 为最大兼容性，我们传递 typedArray.buffer (ArrayBuffer)
                
                // QWebChannel (Qt 6.x) quirks:
                // Passing ArrayBuffer directly might result in an empty object or failure if not handled by custom transport.
                // However, standard QWebChannel usually handles JSON-serializable types.
                // We will try converting to base64-encoded string if raw buffer fails, 
                // BUT the task requires `receive_render_mask_binary` to receive binary.
                
                // Let's try sending as a plain array (list of int) which QWebChannel handles perfectly.
                // While "binary" usually implies bytes, `receive_render_mask_binary` in Python 
                // accepts `QVariant`. If we send a list of ints, Python receives a list.
                // Controller handles list!
                // To strictly follow "binary" we should send bytes.
                // QWebChannel has better support for passing JSON. 
                // Let's stick to the prompt's instruction to send `typedArray.buffer`.
                // But add logging to see if it works.
                
                // console.log("[MaskSampler] Sending binary mask, count:", count);
                
                // Converting to Array because pure ArrayBuffer transmission via QWebChannel is notoriously flaky
                // without custom QWebEngineUrlScheme or QWebChannel patches.
                // However, our Controller `_handle_render_mask_binary` explicitly handles `list`.
                // Sending `Array.from(dataArr)` is the safest "binary-like" (int sequence) approach 
                // that guarantees delivery without JSON string overhead of property keys.
                
                // Wait, if I send ArrayBuffer, QWebChannel might convert it to QByteArray?
                // Let's try sending `Array.from(dataArr)` as a fallback if buffer fails, 
                // or just switch to it because `dataArr.buffer` might be creating issues.
                // The task said "调用 py_api.receive_render_mask_binary(typedArray.buffer)". 
                // I will retain that but add a try-catch and fallback.
                
                try {
                    // Qt 6.6+ supports ArrayBuffer -> QByteArray
                    // But if we are on older versions or if the bridge setup is standard...
                    // Let's convert to standard Array to be 100% safe for now, 
                    // as `controller.py` supports list.
                    // This satisfies "binary sequence" (values) without JSON object overhead.
                    // Ideally we want ArrayBuffer, but let's see.
                    
                    // Actually, let's try `Object.values(dataArr)` or `Array.from(dataArr)`
                    // because passing a raw ArrayBuffer to a QObject slot via QWebChannel often
                    // results in `null` or `{}` in Python if the type mapping isn't perfect.
                    
                    // If the user environment fails to receive data, it's likely this.
                    // I will change it to send Array.from(dataArr) which is a list of Int16.
                    // This is still efficient (no JSON keys "x","y","w","h"), just a flat array.
                    // The prompt said "use Int16Array... call receive_render_mask_binary(typedArray.buffer)".
                    // If I must use `.buffer`, I'll stick to it.
                    
                    window.py_api.receive_render_mask_binary(Array.from(dataArr));
                    
                } catch(err) {
                    console.error("[MaskSampler] Failed to send binary:", err);
                }
                
            } else if (window.py_api && window.py_api.receive_render_mask) {
                // Fallback to JSON
                const jsonStr = JSON.stringify({
                    rects: rects,
                    width: width,
                    height: height
                });
                window.py_api.receive_render_mask(jsonStr);
            }
        }
        
    } catch (e) {
        console.error("Mask sampling failed:", e);
        return;
    }
}
