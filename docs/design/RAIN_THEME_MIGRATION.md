# 雨天模式迁移方案

> 来源：trae-solo/daily 项目的 Rain Theme  
> 目标：uf_assistant-main React + Vite 前端

---

## 1. 现状分析

### 1.1 原实现（daily 项目）

| 维度 | 原实现 |
|------|--------|
| 技术 | 原生 WebGL + GLSL Fragment Shader（447行） |
| 效果 | 三层水滴（静态+动态×2）+ 折射 + 模糊 + 高光 |
| 背景 | 支持静态图/视频/用户上传作为折射源 |
| 配置 | 5个实时可调参数（雨势/雾气/折射率/透明度/速度） |
| 性能 | DPR上限1.5，离屏Canvas纹理中转，RAF可控启停 |

### 1.2 当前前端架构

- React 19 + Vite + Tailwind CSS v4
- 主题系统：CSS Variables + `html.dark` class 切换
- 状态管理：Zustand `themeStore`
- 构建产物：约 510KB JS（已包含 react-markdown）

---

## 2. 迁移策略

### 2.1 核心决策：简化版 Canvas 2D 雨滴

**理由**：
1. 原 WebGL shader 447行 GLSL 代码移植成本高，需完整复制 vertex/fragment shader + WebGL 上下文管理
2. React 应用已有 510KB JS，加入完整 WebGL 实现将进一步增大包体积
3. 当前项目核心是金融工具，雨滴是氛围增强，非核心功能
4. Canvas 2D 方案在现代浏览器上性能足够，且更易维护

**保留原项目精髓**：
- 深蓝 slate 背景 + 天蓝强调色的雨天配色
- 雨滴下落动画（多层、不同速度、景深）
- 玻璃质感氛围（通过配色和背景模糊暗示）
- 文字可读性增强（text-shadow、暗角遮罩）

### 2.2 不实现的内容

| 原功能 | 决策 | 理由 |
|--------|------|------|
| WebGL GLSL Shader | ❌ 不移植 | 复杂度太高，Canvas 2D 可替代 |
| 折射/模糊后处理 | ❌ 不移植 | 需要 WebGL，Canvas 2D 性能不足 |
| 媒体背景（图/视频） | ❌ 不移植 | 非核心，可用 CSS 渐变替代 |
| 5个可调参数面板 | ❌ 不移植 | 简化配置，固定预设参数 |
| 高光 specular | ❌ 不移植 | Canvas 2D 难以实现 |

### 2.3 新增/改造内容

| 功能 | 方案 |
|------|------|
| 雨滴动画 | Canvas 2D，分层粒子系统（前景/中景/背景） |
| 三态主题 | light → dark → rain 循环 |
| Rain 配色 | slate 深蓝 `#0f172a` + 天蓝 `#60a5fa` |
| 文字可读性 | text-shadow + 降低雨滴透明度 + 卡片暗底衬 |
| 性能控制 | DPR 限制、RAF 启停、组件卸载清理 |

---

## 3. 技术方案

### 3.1 主题系统改造

```
当前：theme: 'light' | 'dark'
改造后：theme: 'light' | 'dark' | 'rain'
```

切换逻辑：
```
light → dark → rain → light (循环)
```

CSS 类名：
```
light:  html (默认)
dark:   html.dark
rain:   html.rain
```

Rain 与 Dark 的互斥：
```
html.rain 时自动移除 html.dark
html.dark 时自动移除 html.rain
```

### 3.2 雨滴组件设计

```typescript
interface RainCanvasProps {
  intensity?: number;   // 雨势 0-1，默认 0.5
  speed?: number;       // 速度倍率 0-2，默认 1
  enabled: boolean;     // 是否启用
}
```

粒子系统设计：
```
前景层：20% 粒子，大水滴，快速度，高透明度
中景层：35% 粒子，中水滴，中速度，中透明度  
背景层：45% 粒子，小水滴，慢速度，低透明度
```

### 3.3 文件变更清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `src/index.css` | 修改 | 添加 `.rain` CSS 变量覆盖 |
| `src/stores/themeStore.ts` | 修改 | 三态主题 + 循环切换 |
| `src/components/effects/RainCanvas.tsx` | 新增 | Canvas 2D 雨滴组件 |
| `src/components/layout/Sidebar.tsx` | 修改 | 主题按钮显示当前主题名称 |
| `src/App.tsx` | 修改 | 全局挂载 RainCanvas，按主题条件渲染 |
| `src/index.css` | 修改 | rain 模式下文字 text-shadow 增强可读性 |

---

## 4. 实现步骤

1. **扩展 CSS 变量**：在 `index.css` 中添加 `.rain` 主题变量
2. **改造 ThemeStore**：支持三态切换
3. **实现 RainCanvas**：Canvas 2D 分层雨滴粒子系统
4. **集成到 App**：按 rain 主题条件渲染 RainCanvas
5. **可读性增强**：rain 模式下卡片加暗底衬、文字加 shadow
6. **性能优化**：DPR 限制、RAF 管理、卸载清理
7. **测试验证**：主题切换流畅、雨天动画不卡顿、深色文字可读

---

## 5. 性能预算

| 指标 | 目标 |
|------|------|
| 雨滴 Canvas | 60fps 在主流设备 |
| 内存占用 | < 20MB（粒子系统） |
| 包体积增加 | < 5KB（RainCanvas 组件） |
| 低电量模式 | 自动降低粒子数量或暂停动画 |

---

## 6. 回退方案

若 Canvas 2D 雨滴在某些设备上性能不足：
1. 自动检测帧率，低于 30fps 时减少粒子数量
2. 提供 "静态雨天背景" 选项（CSS 渐变 + 无动画）
3. 用户可在设置中完全关闭雨天动画
