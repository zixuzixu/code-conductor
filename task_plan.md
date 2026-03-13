# Task Plan: 日间/夜间模式切换

## Goal
为 Code Conductor 前端添加日间/夜间模式切换功能，默认日间模式。

## Current State Analysis

### 问题诊断
项目存在**两套冲突的颜色系统**：

1. **`@theme inline` 块 (globals.css L8-51)**：Tailwind v4 颜色 token，硬编码为**暗色值**
2. **`:root` / `.dark` 块 (globals.css L58-125)**：shadcn CSS 变量系统，浅色/深色都定义好了

**核心问题**：`@theme inline` 的 `--color-background: oklch(0.145 0 0)` 是固定暗色，没有引用 `var(--background)`。所以 Tailwind 工具类永远渲染暗色，`:root`/`.dark` 的 CSS 变量根本不生效。

### 需要修复的内容
1. `@theme inline` → 改为引用 CSS 变量（`var(--background)` 等）
2. 创建 ThemeProvider + useTheme hook
3. 添加主题切换按钮
4. `index.html` 的 `theme-color` meta 标签需动态更新
5. 默认浅色模式（移除默认 dark class）
6. localStorage 持久化用户偏好

---

## Phases

### Phase 1: 修复 CSS 变量引用 `[status: complete]`
**Files:** `web/src/globals.css`
- 将 `@theme inline` 中的硬编码颜色值改为引用 `:root`/`.dark` 中定义的 CSS 变量
- 确保 `var(--background)`, `var(--foreground)` 等变量被正确引用
- 验证浅色模式（默认）颜色显示正确

### Phase 2: 创建 ThemeProvider `[status: complete]`
**Files:** `web/src/hooks/use-theme.ts` (新建)
- 创建 React Context + Provider
- 支持 "light" | "dark" | "system" 三种模式
- localStorage 持久化
- 默认 "light"
- 操作 `document.documentElement.classList` 添加/移除 `.dark`
- 动态更新 `<meta name="theme-color">`

### Phase 3: 添加主题切换按钮 `[status: complete]`
**Files:** `web/src/App.tsx`, `web/src/main.tsx`
- 在 App.tsx 中添加 Sun/Moon 图标切换按钮
- 放在顶部导航栏或侧边栏
- 在 main.tsx 中包裹 ThemeProvider
- 移动端也要能访问到

### Phase 4: 修复 index.html 和闪烁防护 `[status: complete]`
**Files:** `web/index.html`
- 添加内联脚本在 `<head>` 中，页面加载前读取 localStorage 设置主题
- 防止浅色→深色闪烁（FOUC）
- 默认 theme-color 改为浅色值

### Phase 5: 验证和修复 `[status: complete]`
- 检查所有组件在两种模式下的显示效果
- 修复硬编码颜色的兼容性
- 确保 PWA manifest 兼容
- 构建测试

---

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| (none yet) | | |

## Decisions
| Decision | Rationale |
|----------|-----------|
| 默认浅色模式 | 用户需求 |
| 支持 system 选项 | 尊重用户系统偏好 |
| localStorage 持久化 | 跨会话保持用户选择 |
| 内联脚本防闪烁 | 标准做法，避免 FOUC |
