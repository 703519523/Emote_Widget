import QtQuick
import QtWebEngine
import QtWebChannel

Item {
    id: root
    
    // [公共API] 后端对象 (EmoteWidgetQml 实例)
    property var backend: null
    
    // 转发 WebEngineView 的一些常用属性
    property alias url: webView.url
    property alias backgroundColor: webView.backgroundColor
    
    WebChannel {
        id: internalChannel
    }
    
    WebEngineView {
        id: webView
        anchors.fill: parent
        backgroundColor: "transparent"
        webChannel: internalChannel
        
        settings.javascriptEnabled: true
        settings.allowRunningInsecureContent: true
        settings.showScrollBars: false
        
        onLoadingChanged: function(loadRequest) {
            if (!backend) return
            
            if (loadRequest.status === WebEngineView.LoadSucceededStatus) {
                backend.notifyPageLoadFinished(true)
            } else if (loadRequest.status === WebEngineView.LoadFailedStatus) {
                console.error("EmoteWidget: Page load failed")
                backend.notifyPageLoadFinished(false)
            }
        }
        
        Component.onCompleted: {
            initialize()
        }
    }
    
    // 当 backend 属性改变时，或者组件初始化时尝试连接
    onBackendChanged: initialize()
    
    function initialize() {
        if (!backend) return
        
        // 如果 URL 为空，说明尚未初始化连接
        if (webView.url == "") {
            // 1. 注册 Bridge
            backend.registerWebChannel(internalChannel)
            
            // 2. 绑定 View
            backend.targetView = webView
            
            // 3. 设置 URL 启动加载
            webView.url = backend.mainPageUrl
        }
    }
}