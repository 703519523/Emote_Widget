// ==========================================================
// ==  Bridge Manager Module
// ==  Handles communication between Python (QWebChannel) and JavaScript
// ==========================================================

// Global Variables
window.py_api = null;
window._bridgeResolver = null;
window.bridgeReadyPromise = new Promise((resolve) => {
    window._bridgeResolver = resolve;
});

// ==========================================================
// ==  Error Handling
// ==========================================================

window.handleJsError = function(error, context = 'General') {
    console.error(`[JS Error in ${context}]`, error);
    if (window.py_api && window.py_api.on_js_error) {
        const message = error.message || 'Unknown error occurred.';
        const stack = error.stack || 'No stack trace available.';
        window.py_api.on_js_error(message, stack);
    }
}

window.addEventListener('unhandledrejection', event => {
    window.handleJsError(event.reason, 'Unhandled Promise');
});

// ==========================================================
// ==  Initialization & Handshake
// ==========================================================

window.addEventListener('DOMContentLoaded', () => {
    // 1. Initialize QWebChannel
    if (typeof qt !== 'undefined' && qt.webChannelTransport) {
        new QWebChannel(qt.webChannelTransport, function (channel) {
            window.py_api = channel.objects.py_api;
            if (window._bridgeResolver) window._bridgeResolver(window.py_api);
            console.log("[Bridge] Python API connected.");
        });
    } else {
        console.error("JS Critical: qt.webChannelTransport not found! Communication impossible.");
    }

    // 2. Setup Interaction Listeners (if available)
    if (typeof window.setupEventListeners === 'function') {
        window.setupEventListeners();
    } else {
        console.warn("[Bridge] setupEventListeners not found. Interaction module might be missing.");
    }
});
