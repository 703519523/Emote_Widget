pragma Singleton
import QtQuick 2.15

QtObject {
    // 主题颜色
    readonly property color backgroundColor: "#FAFAFA"
    readonly property color sidebarBackground: "#F5F5F5"
    readonly property color cardBackground: "#FFFFFF"
    readonly property color accentColor: "#0078D4"
    readonly property color accentHover: "#106EBE"
    readonly property color accentPressed: "#005A9E"
    
    // 文字颜色
    readonly property color textPrimary: "#1A1A1A"
    readonly property color textSecondary: "#666666"
    readonly property color textTertiary: "#999999"
    readonly property color textOnAccent: "#FFFFFF"
    
    // 边框和分割线
    readonly property color borderColor: "#E5E5E5"
    readonly property color dividerColor: "#EBEBEB"
    
    // 控件颜色
    readonly property color controlBackground: "#FFFFFF"
    readonly property color controlHover: "#F0F0F0"
    readonly property color controlPressed: "#E0E0E0"
    readonly property color switchTrackOff: "#CCCCCC"
    readonly property color switchTrackOn: accentColor
    readonly property color sliderTrack: "#E0E0E0"
    readonly property color sliderHandle: accentColor
    
    // 按钮颜色
    readonly property color buttonSecondary: "#666666"      // 深灰色背景
    readonly property color buttonSecondaryHover: "#555555" // 更深的灰色
    readonly property color buttonSecondaryPressed: "#444444" // 最深的灰色
    readonly property color buttonBorder: "#555555"        // 深灰色边框
    
    // 阴影
    readonly property color shadowColor: "#1A000000"
    readonly property color shadowColorLight: "#0D000000"
    
    // 圆角
    readonly property int radiusSmall: 4
    readonly property int radiusMedium: 8
    readonly property int radiusLarge: 12
    readonly property int radiusXLarge: 16
    
    // 间距
    readonly property int spacingTiny: 4
    readonly property int spacingSmall: 8
    readonly property int spacingMedium: 12
    readonly property int spacingLarge: 16
    readonly property int spacingXLarge: 24
    
    // 字体
    readonly property int fontSizeSmall: 11
    readonly property int fontSizeMedium: 13
    readonly property int fontSizeLarge: 15
    readonly property int fontSizeTitle: 18
    readonly property int fontSizeHeader: 22
    
    // 动画持续时间
    readonly property int animationFast: 100
    readonly property int animationNormal: 200
    readonly property int animationSlow: 300
    
    // 侧边栏宽度
    readonly property int sidebarWidth: 280
    readonly property int sidebarCollapsedWidth: 60
}
