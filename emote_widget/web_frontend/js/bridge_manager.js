// ==========================================================
// ==  Bridge Manager Module (通信桥接管理器)
// ==  Responsibility: 建立与 Python (Qt) 的通信通道
// ==========================================================

/**
 * 本模块负责初始化 QWebChannel，建立 JavaScript 与 Python 之间的双向通信。
 * 
 * 工作流程:
 * 1. 监听 DOMContentLoaded 事件。
 * 2. 检查 `qt.webChannelTransport` 是否存在 (由 QtWebEngine 注入)。
 * 3. 实例化 QWebChannel，绑定 Python 注入的对象 `py_api`。
 * 4. 触发全局 Promise `bridgeReadyPromise`，通知其他模块通信已就绪。
 * 
 * 依赖:
 * - qwebchannel.js (必须先于本脚本加载)
 */

// Global Variables
window.py_api = null; // Python 注入的全局 API 对象
window._bridgeResolver = null;

// 提供一个 Promise，供其他模块 (如 core_renderer.js) 等待通信就绪
window.bridgeReadyPromise = new Promise((resolve) => {
    window._bridgeResolver = resolve;
});

// ==========================================================
// ==  Error Handling (错误处理)
// ==========================================================

/**
 * 全局错误处理函数。
 * 捕获 JS 运行时的异常，并通过 Bridge 发回 Python 端记录日志。
 * 这对于调试 WebEngine 内部的隐蔽错误至关重要。
 */
window.handleJsError = function(error, context = 'General') {
    console.error(`[JS Error in ${context}]`, error);
    if (window.py_api && window.py_api.on_js_error) {
        const message = error.message || 'Unknown error occurred.';
        const stack = error.stack || 'No stack trace available.';
        // 调用 Python: emote_widget.core.python_api_bridge.PythonApiBridge.on_js_error
        window.py_api.on_js_error(message, stack);
    }
}

// 捕获未处理的 Promise Rejection (如 async 函数中的错误)
window.addEventListener('unhandledrejection', event => {
    window.handleJsError(event.reason, 'Unhandled Promise');
});

// ==========================================================
// ==  Initialization & Handshake (初始化与握手)
// ==========================================================

window.addEventListener('DOMContentLoaded', () => {
    // 1. Initialize QWebChannel
    if (typeof qt !== 'undefined' && qt.webChannelTransport) {
        new QWebChannel(qt.webChannelTransport, function (channel) {
            // 'py_api' 必须与 Python 端 register_python_bridge 中注册的名字一致
            window.py_api = channel.objects.py_api;
            
            // 解锁 Promise，通知依赖模块
            if (window._bridgeResolver) window._bridgeResolver(window.py_api);
            console.log("[Bridge] Python API connected.");
        });
    } else {
        console.error("JS Critical: qt.webChannelTransport not found! Communication impossible.");
    }

    // 2. Setup Interaction Listeners (if available)
    // 确保 interaction_handler.js 已加载
    if (typeof window.setupEventListeners === 'function') {
        window.setupEventListeners();
    } else {
        console.warn("[Bridge] setupEventListeners not found. Interaction module might be missing.");
    }
});
