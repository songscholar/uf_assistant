# UF Stock Assistant — 前端 UI/UX 设计文档

> 版本：v1.0  
> 日期：2026-05-06  
> 状态：设计完成，待实现

---

## 1. 设计概述

本项目为 UF Stock Assistant（优富股票助手）设计并构建一套完整的前端用户界面。

### 1.1 设计目标

- **专业金融感**：界面传达专业、可信赖的金融工具形象
- **对话优先**：以 AI 对话为核心交互方式，其他功能围绕对话展开
- **信息密度适中**：金融数据展示清晰，不过度拥挤
- **沉浸体验**：参考 daily 项目的视觉质感，营造精致、沉浸的使用体验

### 1.2 参考来源

| 来源 | 参考维度 |
|------|---------|
| [豆包](https://www.doubao.com/chat/) | 整体布局架构：侧边栏+主内容区、对话界面结构、消息气泡设计 |
| [trae-solo/daily](../daily) | 视觉风格：配色方案、字体系统、毛玻璃效果、动画曲线、暖色调 |

### 1.3 核心原则

1. **温暖专业**：不使用冰冷的纯灰/纯白，采用暖白底色 + 陶土红强调色
2. **层次分明**：通过背景色、阴影、边框建立清晰的信息层级
3. **动效克制**：动画用于引导注意力，不过度炫技
4. **响应优先**：移动端体验不打折，核心功能随时可用

---

## 2. 技术选型

| 类别 | 技术 | 理由 |
|------|------|------|
| 框架 | React 19 + TypeScript | 类型安全，组件化开发，生态成熟 |
| 构建工具 | Vite 6 | 极速 HMR，现代打包 |
| 样式 | Tailwind CSS 4 | 原子化 CSS，快速开发，易维护 |
| UI 组件 | shadcn/ui + 自定义 | 基础组件用 shadcn，业务组件自定义 |
| 状态管理 | Zustand | 轻量，无样板代码，适合本项目规模 |
| 路由 | React Router v7 | 声明式路由，懒加载支持 |
| HTTP 客户端 | Axios | 拦截器、自动 JSON 解析 |
| Markdown 渲染 | react-markdown + remark-gfm | 支持表格、代码块等 |
| 代码高亮 | prism-react-renderer | 轻量，主题可定制 |
| 图表 | Lightweight Charts (TradingView) | 金融级 K 线图，轻量高性能 |
| 图标 | Lucide React | 统一风格，树摇优化 |
| 字体 | 霞鹜文楷 (LXGW WenKai) + Inter | 中文温暖感 + 西文现代感 |

### 2.1 为什么不使用纯静态方案

daily 项目是纯静态网站的典范，但股票助手需要：
- 实时对话交互（WebSocket/SSE）
- 复杂状态管理（会话历史、持仓数据）
- 动态数据可视化（K线图、实时行情）
- 多页面路由（对话/行情/交易/策略）

React + Vite 是现代前端的最佳实践组合，同时我们吸收 daily 项目的视觉设计精髓。

---

## 3. 视觉设计系统

### 3.1 配色方案

继承 daily 项目的三套主题系统，为金融场景优化：

#### Light（默认）

```css
--bg-primary: #fafaf8;        /* 暖白纸色 — 页面主背景 */
--bg-secondary: #f2f1ee;      /* 浅灰 — 侧边栏、卡片背景 */
--bg-card: #ffffff;           /* 纯白 — 弹窗、浮层、消息气泡 */
--bg-hover: #ebeae6;          /* 悬停背景 */
--bg-active: #e4e3df;         /* 激活/选中背景 */

--text-primary: #1a1a1a;      /* 近黑 — 主标题、重要文字 */
--text-secondary: #6b6b6b;    /* 中灰 — 副标题、描述 */
--text-tertiary: #a0a0a0;     /* 浅灰 — 辅助信息、时间戳 */
--text-inverse: #ffffff;      /* 反色 — 深色按钮上的文字 */

--accent: #c8553d;            /* 陶土红 — 主强调色（CTA、选中态） */
--accent-light: #e8a090;      /* 浅陶土 — hover 态 */
--accent-bg: rgba(200, 85, 61, 0.08);  /* 强调色背景（如选中项） */

--border: #e8e6e2;            /* 分割线、边框 */
--border-light: #f0eeea;      /* 极淡边框 */
--border-focus: #c8553d;      /* focus 状态边框 */

--success: #22c55e;           /* 上涨、成功 */
--success-bg: rgba(34, 197, 94, 0.08);
--danger: #ef4444;            /* 下跌、错误 */
--danger-bg: rgba(239, 68, 68, 0.08);
--warning: #f59e0b;           /* 警告、中性 */
--info: #3b82f6;              /* 信息提示 */

--shadow-sm: 0 1px 3px rgba(0,0,0,0.04);
--shadow-md: 0 4px 20px rgba(0,0,0,0.06);
--shadow-lg: 0 12px 40px rgba(0,0,0,0.08);
--shadow-xl: 0 20px 60px rgba(0,0,0,0.12);
```

#### Dark

```css
--bg-primary: #0c0e12;        /* 深夜黑 */
--bg-secondary: #14161c;      /* 侧边栏 */
--bg-card: #1a1d24;           /* 卡片 */
--bg-hover: #22252e;
--bg-active: #2a2e38;

--text-primary: #ececec;
--text-secondary: #9ca3af;
--text-tertiary: #6b7280;
--text-inverse: #1a1a1a;

--accent: #c8553d;            /* 强调色保持一致，增强品牌识别 */
--accent-light: #e07a65;
--accent-bg: rgba(200, 85, 61, 0.12);

--border: #2a2e38;
--border-light: #1f2229;
--border-focus: #c8553d;

--success: #4ade80;
--danger: #f87171;
--warning: #fbbf24;
--info: #60a5fa;

--shadow-sm: 0 1px 3px rgba(0,0,0,0.3);
--shadow-md: 0 4px 20px rgba(0,0,0,0.4);
--shadow-lg: 0 12px 40px rgba(0,0,0,0.5);
```

### 3.2 字体系统

```css
--font-sans: "LXGW WenKai", "Inter", "PingFang SC", "Microsoft YaHei", sans-serif;
--font-mono: "JetBrains Mono", "Menlo", "Monaco", "Consolas", monospace;

/* 字号层级 */
--text-xs: 12px;      /* 辅助标签、时间戳 */
--text-sm: 13px;      /* 次要文字、按钮 */
--text-base: 14px;    /* 正文 */
--text-lg: 16px;      /* 稍大正文、消息内容 */
--text-xl: 18px;      /* 小标题 */
--text-2xl: 20px;     /* 模块标题 */
--text-3xl: 24px;     /* 页面标题 */
--text-4xl: 32px;     /* 大标题（欢迎页） */

/* 字重 */
--font-normal: 400;
--font-medium: 500;
--font-semibold: 600;
--font-bold: 700;

/* 行高 */
--leading-tight: 1.25;
--leading-normal: 1.5;
--leading-relaxed: 1.625;
```

### 3.3 间距系统

基于 4px 基数：

```css
--space-1: 4px;
--space-2: 8px;
--space-3: 12px;
--space-4: 16px;
--space-5: 20px;
--space-6: 24px;
--space-8: 32px;
--space-10: 40px;
--space-12: 48px;
--space-16: 64px;
```

### 3.4 圆角系统

```css
--radius-sm: 6px;     /* 小标签、徽章 */
--radius-md: 10px;    /* 按钮、输入框 */
--radius-lg: 14px;    /* 卡片、面板 */
--radius-xl: 18px;    /* 大卡片、弹窗 */
--radius-full: 9999px; /* 头像、圆形按钮 */
```

### 3.5 过渡与动画

```css
/* 主缓动曲线 — 优雅 */
--ease-out: cubic-bezier(0.25, 0.1, 0.25, 1);
/* 弹性 — 弹出面板 */
--ease-spring: cubic-bezier(0.34, 1.56, 0.64, 1);
/* 顺滑 — 卡片 hover */
--ease-smooth: cubic-bezier(0.22, 0.8, 0.24, 1);

--duration-fast: 150ms;
--duration-normal: 250ms;
--duration-slow: 400ms;
```

### 3.6 毛玻璃效果

```css
.glass {
  background: rgba(250, 250, 248, 0.85);
  backdrop-filter: blur(20px) saturate(180%);
  -webkit-backdrop-filter: blur(20px) saturate(180%);
}

.glass-dark {
  background: rgba(12, 14, 18, 0.85);
  backdrop-filter: blur(20px) saturate(180%);
}
```

---

## 4. 布局架构

整体采用豆包式的 **侧边栏 + 主内容区** 布局。

### 4.1 全局布局

```
┌─────────────────────────────────────────────────────────────┐
│  App Layout                                                  │
│  ┌─────────────┬─────────────────────────────────────────┐   │
│  │             │  ┌───────────────────────────────────┐   │   │
│  │  Sidebar    │  │  Header (~52px)                    │   │   │
│  │  (260px)    │  ├───────────────────────────────────┤   │   │
│  │             │  │                                   │   │   │
│  │  导航+历史   │  │  Main Content                      │   │   │
│  │             │  │  (flex: 1, 路由切换)                │   │   │
│  │             │  │                                   │   │   │
│  │             │  │                                   │   │   │
│  │             │  └───────────────────────────────────┘   │   │
│  └─────────────┴─────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 布局规则

| 区域 | 宽度 | 高度 | 定位 | 行为 |
|------|------|------|------|------|
| Sidebar | 260px | 100vh | fixed left | 桌面常驻，移动端抽屉 |
| Header | calc(100% - 260px) | 52px | sticky top | 随主内容滚动吸附 |
| Main | calc(100% - 260px) | calc(100vh - 52px) | static | 内部滚动 |

### 4.3 断点设计

```css
/* 移动端 */
@media (max-width: 768px) {
  Sidebar: 隐藏，通过汉堡菜单触发抽屉
  Main: 100vw
}

/* 平板 */
@media (min-width: 769px) and (max-width: 1024px) {
  Sidebar: 可折叠为图标模式 (72px)
  Main: calc(100% - 72px)
}

/* 桌面 */
@media (min-width: 1025px) {
  Sidebar: 260px 常驻
}
```

---

## 5. 页面设计

### 5.1 页面清单

| 页面 | 路由 | 说明 |
|------|------|------|
| 对话中心 | `/chat` | AI 对话主界面（默认页） |
| 股票详情 | `/stock/:symbol` | 个股信息、K线、财务 |
| 市场行情 | `/market` | 大盘指数、板块、龙虎榜 |
| 选股策略 | `/strategy` | 策略列表、选股、回测 |
| 模拟交易 | `/trading` | 下单、持仓、订单、组合 |
| 加密货币 | `/crypto` | 币价、K线、排行 |

### 5.2 对话中心（默认页）

布局参考豆包聊天界面：

```
┌─────────────────────────────────────────────────────────────┐
│  Header                                                      │
│  ┌────────────────────┬───────────────────────────────┐     │
│  │  💬 新对话            │  [分享] [模型选择▼] [⋮]       │     │
│  └────────────────────┴───────────────────────────────┘     │
├─────────────────────────────────────────────────────────────┤
│  Message Area                                                │
│  ┌───────────────────────────────────────────────────────┐   │
│  │                                                       │   │
│  │  [欢迎状态] 或 [消息列表]                                │   │
│  │                                                       │   │
│  │  用户消息 ───────────────────────────────► 右侧对齐     │   │
│  │                                                       │   │
│  │  ◉ AI消息                               左侧对齐      │   │
│  │  ┌─────────────────────────────────────┐              │   │
│  │  │  内容...                            │              │   │
│  │  └─────────────────────────────────────┘              │   │
│  │  [👍] [👎] [复制] [重新生成]                          │   │
│  │                                                       │   │
│  └───────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────┤
│  Input Area                                                  │
│  ┌───────────────────────────────────────────────────────┐   │
│  │  [📎] [联网搜索] [深度思考] ...  工具栏                  │   │
│  │  ┌─────────────────────────────────────────────────┐   │   │
│  │  │  给优富助手发送消息...                            │   │   │
│  │  │                                                  │   │   │
│  │  └─────────────────────────────────────────────────┘   │   │
│  │                                    [发送按钮 ➤]        │   │
│  └───────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

#### 欢迎状态设计

空对话时显示：
- 中央：助手 Logo + "你好，我是优富" + "你的智能股票助手"
- 下方：6 个快捷功能卡片（2行×3列）
  - 📈 股票分析、📊 市场概览、💡 策略建议
  - 🔄 模拟交易、📉 加密货币、📄 文档解析
- 点击卡片自动填充对应提示词

#### 消息气泡设计

| 类型 | 背景 | 文字颜色 | 对齐 | 圆角 |
|------|------|---------|------|------|
| 用户 | `#c8553d` (accent) | `#ffffff` | 右侧 | 14px（左下18px） |
| AI | `#ffffff` | `#1a1a1a` | 左侧 | 14px（右下18px） |
| AI (dark) | `#1a1d24` | `#ececec` | 左侧 | 14px（右下18px） |

消息最大宽度：`min(680px, 85%)`

#### 输入区域设计

- 背景：卡片色 + 轻微阴影
- 圆角：18px
- 内边距：16px
- 工具栏：图标按钮行，hover 显示 tooltip
- 输入框：textarea，自动增高（min 48px, max 200px）
- 发送按钮：圆形，accent 背景，hover scale(1.05)

### 5.3 市场行情页

```
┌─────────────────────────────────────────────────────────────┐
│  Header: 市场行情                                             │
├─────────────────────────────────────────────────────────────┤
│  ┌───────────────────────────────────────────────────────┐   │
│  │  大盘指数卡片（横向排列，3-4个）                          │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐  │   │
│  │  │ 上证指数  │ │ 深证成指  │ │ 创业板指  │ │ 科创50   │  │   │
│  │  │ 3,456.78 │ │ 11,234.5 │ │ 2,345.67 │ │ 1,234.56 │  │   │
│  │  │ ▲ +0.45% │ │ ▼ -0.12% │ │ ▲ +1.23% │ │ ▼ -0.67% │  │   │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘  │   │
│  └───────────────────────────────────────────────────────┘   │
│  ┌───────────────────────┐  ┌─────────────────────────────┐  │
│  │  板块热点排行           │  │  龙虎榜                      │  │
│  │  ─────────────────     │  │  ─────────────────          │  │
│  │  1. 半导体 ▲+3.45%     │  │  买入最多...                 │  │
│  │  2. 新能源 ▲+2.87%     │  │  ...                        │  │
│  └───────────────────────┘  └─────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────┐   │
│  │  北向资金流向                                           │   │
│  │  [柱状图/折线图区域]                                     │   │
│  └───────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### 5.4 股票详情页

```
┌─────────────────────────────────────────────────────────────┐
│  Header: 贵州茅台 (600519)                    [关注] [分享]   │
├─────────────────────────────────────────────────────────────┤
│  ┌───────────────────────────────────────────────────────┐   │
│  │  当前价格: ¥1,688.00    ▲ +1.23% (+20.50)              │   │
│  │  今开: 1,670  最高: 1,695  最低: 1,665  昨收: 1,667.5  │   │
│  │  成交量: 25,432手  成交额: 4.28亿                        │   │
│  └───────────────────────────────────────────────────────┘   │
│  ┌───────────────────────────────────────────────────────┐   │
│  │  [日K] [周K] [月K]                                     │   │
│  │                                                       │   │
│  │              [K 线图区域]                              │   │
│  │                                                       │   │
│  └───────────────────────────────────────────────────────┘   │
│  ┌───────────────────────┐  ┌─────────────────────────────┐  │
│  │  基本信息              │  │  财务指标                    │  │
│  │  ─────────────────     │  │  ─────────────────          │  │
│  │  行业: 白酒            │  │  市盈率: 28.5               │  │
│  │  市值: 2.12万亿        │  │  市净率: 8.2                │  │
│  │  ...                  │  │  ...                        │  │
│  └───────────────────────┘  └─────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### 5.5 策略/选股页

```
┌─────────────────────────────────────────────────────────────┐
│  Header: 策略与选股                                           │
├─────────────────────────────────────────────────────────────┤
│  ┌───────────────────────────────────────────────────────┐   │
│  │  策略列表（卡片网格）                                     │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐  │   │
│  │  │ 均线交叉  │ │  MACD   │ │   RSI   │ │ 布林带   │  │   │
│  │  │ [运行]   │ │ [运行]   │ │ [运行]   │ │ [运行]   │  │   │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘  │   │
│  └───────────────────────────────────────────────────────┘   │
│  ┌───────────────────────────────────────────────────────┐   │
│  │  选股器                                                │   │
│  │  价格区间: [____] - [____]  涨跌幅: [____]% - [____]%   │   │
│  │  [🔍 开始选股]                                         │   │
│  └───────────────────────────────────────────────────────┘   │
│  ┌───────────────────────────────────────────────────────┐   │
│  │  选股结果表格                                          │   │
│  │  代码 | 名称 | 价格 | 涨跌幅 | 策略信号 | 操作           │   │
│  └───────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### 5.6 模拟交易页

```
┌─────────────────────────────────────────────────────────────┐
│  Header: 模拟交易                                             │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    │
│  │ 总资产    │  │ 可用资金  │  │ 持仓市值  │  │ 累计收益  │    │
│  │ ¥100万   │  │ ¥65.3万  │  │ ¥34.7万  │  │ +12.5%   │    │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘    │
│  ┌──────────────────────────┐  ┌─────────────────────────┐  │
│  │  下单面板                 │  │  持仓列表                │  │
│  │  股票代码: [________]     │  │  代码|名称|数量|成本|现价|盈亏│  │
│  │  买卖: [买入 ▼]           │  │  ...                   │  │
│  │  价格: [________]         │  │                        │  │
│  │  数量: [________]         │  │                        │  │
│  │  [确认下单]               │  │                        │  │
│  └──────────────────────────┘  └─────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────┐   │
│  │  订单历史                                              │   │
│  │  时间 | 代码 | 方向 | 价格 | 数量 | 状态                 │   │
│  └───────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### 5.7 加密货币页

类似股票详情页布局，展示：
- 币价概览卡片
- K 线图
- 市值排行表格
- 交易所选择器

---

## 6. 组件设计

### 6.1 侧边栏 (Sidebar)

```
┌─────────────────────────────┐
│  [Logo] 优富助手              │  ← Logo 区域 (~56px)
├─────────────────────────────┤
│  [+] 新建对话                 │  ← 新建按钮
├─────────────────────────────┤
│  今日                         │
│  ┌─────────────────────────┐│
│  │ 💬 分析茅台走势...       ││  ← 历史项
│  │ 💬 看看今天的市场        ││
│  └─────────────────────────┘│
│  昨天                         │
│  ┌─────────────────────────┐│
│  │ 💬 比亚迪怎么样          ││
│  └─────────────────────────┘│
│  更早                         │
│  ...                         │
├─────────────────────────────┤
│  [👤] 设置                   │  ← 底部操作区
│  [?] 帮助                    │
└─────────────────────────────┘
```

**历史项交互**：
- 默认态：单行文本截断，左侧 3px 透明边框
- Hover：背景变为 bg-hover，显示 ⋮ 更多菜单
- 选中态：左侧 3px accent 色边框，背景变为 accent-bg
- 更多菜单：重命名、置顶、删除

### 6.2 消息组件

```typescript
interface MessageProps {
  id: string;
  role: 'user' | 'assistant';
  content: string;           // Markdown 文本
  timestamp: Date;
  status?: 'sending' | 'streaming' | 'complete' | 'error';
  toolsUsed?: ToolInfo[];    // 工具调用信息
  onCopy?: () => void;
  onRetry?: () => void;
  onFeedback?: (type: 'up' | 'down') => void;
}
```

**AI 消息特殊状态**：
- `streaming`: 显示打字光标（闪烁竖线），内容逐字追加
- `tool_call`: 显示工具调用卡片（如"正在查询贵州茅台行情..."）
- `thinking`: 深度思考模式，显示思考过程折叠面板

### 6.3 工具调用卡片

当 AI 调用工具时，在消息中插入卡片：

```
┌─────────────────────────────────────┐
│  🔧 正在调用工具                      │
│  ┌───────────────────────────────┐  │
│  │  get_stock_realtime           │  │
│  │  参数: {"symbol": "600519"}    │  │
│  │  [查看结果 ▼]                  │  │
│  └───────────────────────────────┘  │
└─────────────────────────────────────┘
```

### 6.4 指数卡片

```
┌─────────────────────────────┐
│  上证指数                     │
│  ┌─────────────────────────┐│
│  │      [迷你折线图]        ││
│  └─────────────────────────┘│
│  3,456.78                   │
│  ▲ +12.45 (+0.36%)          │
└─────────────────────────────┘
```

### 6.5 K 线图容器

使用 Lightweight Charts，包装为 React 组件：
- 支持日/周/月切换
- 鼠标悬停显示十字准线和数据提示
- 支持缩放和拖拽

---

## 7. 交互设计

### 7.1 全局交互

| 交互 | 行为 |
|------|------|
| 主题切换 | 右上角设置按钮，下拉菜单选择 Light/Dark |
| 侧边栏折叠 | 平板端点击汉堡菜单，滑动动画 300ms ease-out |
| 页面切换 | React Router，淡入淡出 200ms |
| 滚动行为 | 消息区域自动滚动到底部，用户手动上滑时暂停 |

### 7.2 对话交互

| 交互 | 行为 |
|------|------|
| 发送消息 | Enter 发送（Shift+Enter 换行），按钮 loading 态 |
| 流式输出 | SSE 接收，逐字符渲染，底部自动跟随 |
| 停止生成 | 生成过程中显示「⏹ 停止」按钮 |
| 复制消息 | Hover 显示复制按钮，点击后图标变 ✓ |
| 重新生成 | 重新发送最后一条用户消息 |
| 文件上传 | 拖拽到输入区或点击附件按钮，支持多文件 |

### 7.3 数据交互

| 交互 | 行为 |
|------|------|
| 股票搜索 | 输入框实时搜索，下拉列表显示匹配结果 |
| 图表交互 | 鼠标悬停显示详细数据，滚轮缩放 |
| 表格排序 | 点击表头排序，三角箭头指示方向 |
| 刷新数据 | 下拉刷新或点击刷新按钮，显示 loading spinner |

### 7.4 动效规范

```
消息出现:    opacity 0→1, translateY(8px→0), 200ms ease-out
发送按钮:    hover scale(1.05), active scale(0.95), 150ms
卡片 hover:  translateY(-2px), shadow-md→shadow-lg, 200ms ease-smooth
侧边栏抽屉:  translateX(-100%→0), 300ms ease-out
Toast 通知:  translateY(-20px→0), opacity 0→1, 300ms, 自动消失 3s
加载骨架屏:  shimmer 动画, background-position 滑动
```

---

## 8. 响应式设计

### 8.1 移动端 (< 768px)

- 侧边栏隐藏，顶部显示汉堡菜单
- 消息气泡宽度 max-width: 90%
- 指数卡片横向滚动
- 表格转为卡片列表
- 输入框工具栏简化（仅保留附件）

### 8.2 平板 (768px - 1024px)

- 侧边栏可折叠为图标模式（72px 宽）
- Hover 展开显示文字
- 两列布局变为单列堆叠

### 8.3 桌面 (> 1024px)

- 完整侧边栏 + 主内容区
- 多列网格布局
- 快捷键支持（Cmd+K 搜索，/ 聚焦输入框）

---

## 9. API 对接规范

### 9.1 基础配置

```typescript
const API_BASE = '/api/v1';

const api = axios.create({
  baseURL: API_BASE,
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' }
});
```

### 9.2 核心接口映射

| 前端功能 | API 端点 | 方法 |
|---------|---------|------|
| 发送消息 | `/chat` | POST |
| 获取会话列表 | `/conversations` | GET |
| 获取会话详情 | `/conversations/:id` | GET |
| 删除会话 | `/conversations/:id` | DELETE |
| 搜索股票 | `/stock/search?q=` | GET |
| 股票详情 | `/stock/:symbol/info` | GET |
| 实时行情 | `/stock/:symbol/realtime` | GET |
| 历史K线 | `/stock/:symbol/history` | GET |
| 市场概况 | `/market/overview` | GET |
| 大盘指数 | `/market/indices` | GET |
| 板块热点 | `/market/sectors` | GET |
| 策略列表 | `/strategies` | GET |
| 执行策略 | `/strategies/:key/evaluate` | POST |
| 选股 | `/strategies/pick` | POST |
| 提交订单 | `/trading/order` | POST |
| 持仓列表 | `/trading/positions` | GET |
| 订单列表 | `/trading/orders` | GET |
| 取消订单 | `/trading/orders/:id` | DELETE |
| 投资组合 | `/trading/portfolio` | GET |
| 币价查询 | `/crypto/price` | GET |
| 上传文件 | `/upload` | POST |

### 9.3 SSE 流式对话

```typescript
// 使用 EventSource 接收流式响应
const eventSource = new EventSource(`/api/v1/chat/stream?message=${encodeURIComponent(msg)}`);

eventSource.onmessage = (event) => {
  const data = JSON.parse(event.data);
  // 追加到当前消息内容
};

eventSource.onerror = () => {
  eventSource.close();
};
```

### 9.4 错误处理

```typescript
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // 未授权，跳转登录
    } else if (error.response?.status === 429) {
      // 请求过于频繁
      toast.error('请求过于频繁，请稍后再试');
    } else {
      toast.error(error.response?.data?.detail || '请求失败');
    }
    return Promise.reject(error);
  }
);
```

---

## 10. 状态管理设计

### 10.1 Zustand Store 划分

```typescript
// stores/chatStore.ts
interface ChatStore {
  conversations: Conversation[];
  currentConversationId: string | null;
  messages: Message[];
  isStreaming: boolean;
  sendMessage: (content: string) => Promise<void>;
  loadConversations: () => Promise<void>;
  switchConversation: (id: string) => Promise<void>;
  deleteConversation: (id: string) => Promise<void>;
}

// stores/marketStore.ts
interface MarketStore {
  indices: IndexData[];
  sectors: SectorData[];
  longhu: LonghuData[];
  northbound: NorthboundData;
  isLoading: boolean;
  fetchOverview: () => Promise<void>;
}

// stores/tradingStore.ts
interface TradingStore {
  positions: Position[];
  orders: Order[];
  portfolio: Portfolio | null;
  submitOrder: (order: OrderRequest) => Promise<void>;
  fetchPositions: () => Promise<void>;
}

// stores/themeStore.ts
interface ThemeStore {
  theme: 'light' | 'dark';
  toggleTheme: () => void;
}
```

---

## 11. 项目文件结构

```
frontend/
├── public/
│   ├── fonts/
│   │   ├── LXGWWenKai-Regular.woff2
│   │   └── LXGWWenKai-Bold.woff2
│   └── favicon.svg
├── src/
│   ├── main.tsx                    # 应用入口
│   ├── App.tsx                     # 根组件
│   ├── index.css                   # 全局样式 + CSS Variables
│   ├── lib/
│   │   ├── api.ts                  # Axios 实例 + API 方法
│   │   ├── utils.ts                # 工具函数
│   │   └── constants.ts            # 常量
│   ├── stores/
│   │   ├── chatStore.ts
│   │   ├── marketStore.ts
│   │   ├── tradingStore.ts
│   │   └── themeStore.ts
│   ├── components/
│   │   ├── layout/
│   │   │   ├── Sidebar.tsx         # 侧边栏
│   │   │   ├── Header.tsx          # 顶部标题栏
│   │   │   ├── MainLayout.tsx      # 主布局容器
│   │   │   └── MobileNav.tsx       # 移动端导航
│   │   ├── chat/
│   │   │   ├── ChatContainer.tsx   # 聊天主容器
│   │   │   ├── MessageList.tsx     # 消息列表
│   │   │   ├── MessageBubble.tsx   # 消息气泡
│   │   │   ├── ChatInput.tsx       # 输入区域
│   │   │   ├── WelcomeScreen.tsx   # 欢迎页面
│   │   │   ├── ToolCallCard.tsx    # 工具调用卡片
│   │   │   └── StreamingCursor.tsx # 流式光标
│   │   ├── market/
│   │   │   ├── IndexCard.tsx       # 指数卡片
│   │   │   ├── SectorList.tsx      # 板块列表
│   │   │   └── MarketChart.tsx     # 市场图表
│   │   ├── stock/
│   │   │   ├── StockHeader.tsx     # 股票头部信息
│   │   │   ├── KlineChart.tsx      # K 线图
│   │   │   ├── StockInfo.tsx       # 基本信息
│   │   │   └── FinancialTable.tsx  # 财务数据表
│   │   ├── trading/
│   │   │   ├── OrderForm.tsx       # 下单表单
│   │   │   ├── PositionTable.tsx   # 持仓表格
│   │   │   ├── OrderTable.tsx      # 订单表格
│   │   │   └── PortfolioCard.tsx   # 组合概览
│   │   ├── strategy/
│   │   │   ├── StrategyCard.tsx    # 策略卡片
│   │   │   ├── StockScreener.tsx   # 选股器
│   │   │   └── StrategyResult.tsx  # 策略结果
│   │   ├── crypto/
│   │   │   ├── CryptoPrice.tsx     # 币价展示
│   │   │   └── CryptoChart.tsx     # 币价图表
│   │   └── ui/                     # shadcn/ui 组件
│   │       ├── button.tsx
│   │       ├── card.tsx
│   │       ├── dialog.tsx
│   │       ├── dropdown-menu.tsx
│   │       ├── input.tsx
│   │       ├── scroll-area.tsx
│   │       ├── skeleton.tsx
│   │       ├── table.tsx
│   │       ├── tabs.tsx
│   │       ├── textarea.tsx
│   │       ├── tooltip.tsx
│   ├── pages/
│   │   ├── ChatPage.tsx
│   │   ├── MarketPage.tsx
│   │   ├── StockPage.tsx
│   │   ├── StrategyPage.tsx
│   │   ├── TradingPage.tsx
│   │   └── CryptoPage.tsx
│   ├── hooks/
│   │   ├── useChat.ts              # 对话逻辑封装
│   │   ├── useSSE.ts               # SSE 流式接收
│   │   ├── useAutoScroll.ts        # 自动滚动
│   │   └── useMediaQuery.ts        # 响应式断点
│   └── types/
│       ├── chat.ts
│       ├── stock.ts
│       ├── market.ts
│       ├── trading.ts
│       └── index.ts
├── index.html
├── vite.config.ts
├── tailwind.config.ts
├── tsconfig.json
└── package.json
```

---

## 12. 实现顺序

1. **项目初始化** — Vite + React + Tailwind + shadcn/ui 配置
2. **全局样式** — CSS Variables、字体加载、主题切换
3. **布局框架** — Sidebar + Header + MainLayout
4. **对话页面** — 核心功能，消息列表 + 输入框 + SSE
5. **市场行情页** — 指数卡片 + 板块列表
6. **股票详情页** — 信息展示 + K线图
7. **策略/选股页** — 策略卡片 + 选股表单 + 结果表格
8. **交易页面** — 下单 + 持仓 + 订单
9. **加密货币页** — 币价 + K线
10. **响应式适配** — 移动端适配 + 抽屉菜单
11. ** polish ** — 动画优化、加载态、错误处理

---

## 13. 附录

### 13.1 快捷键

| 快捷键 | 功能 |
|--------|------|
| `Cmd/Ctrl + K` | 打开搜索/命令面板 |
| `/` | 聚焦到输入框 |
| `Esc` | 关闭弹窗/侧边栏 |
| `Cmd/Ctrl + Enter` | 发送消息 |
| `Cmd/Ctrl + Shift + L` | 切换主题 |
| `Cmd/Ctrl + N` | 新建对话 |

### 13.2 性能目标

- 首屏加载 < 2s（3G 网络）
- 交互响应 < 100ms
- 消息流式渲染 > 30fps
- Lighthouse 评分 > 90
