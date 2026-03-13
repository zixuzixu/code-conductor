# Findings: 日间/夜间模式

## CSS 架构发现

### 双重颜色系统冲突
- `@theme inline` (Tailwind v4 token) 硬编码暗色值 → 组件永远渲染暗色
- `:root` 定义浅色 CSS 变量，`.dark` 定义深色 CSS 变量 → 但没被 Tailwind 引用
- **修复方案**：让 `@theme inline` 引用 `var(--xxx)` 变量

### 组件颜色引用方式
- 大部分组件使用语义化 Tailwind 类：`bg-background`, `text-foreground`, `bg-primary` 等
- `task-card.tsx` 使用硬编码 Tailwind 颜色：`bg-red-500/20`, `text-blue-400` 等（状态色，两种模式下都能工作）
- 部分组件有 `dark:` 前缀的样式覆盖

### 技术栈
- Tailwind CSS v4.2.1 + `@tailwindcss/vite`
- shadcn/ui (base-nova style)
- OKLCH 色彩空间
- CVA 管理组件变体
- lucide-react（已有 Sun/Moon 图标）

### index.html
- `theme-color` meta 设为 `#0a0a0a`（暗色）→ 需改为浅色默认
