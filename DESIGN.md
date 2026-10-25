---
version: alpha
name: agent-psm-design
description: 浅色数据密集的统计工具界面。单一靛蓝 accent 用于主操作与链接，语义绿/红/琥珀只留给「配平通过/未通过/告警」这类统计判定；卡片用发丝线边框而非重阴影；表格数据用等宽数字，紧凑但不拥挤。整体克制、技术、耐读。
colors:
  primary: "#4f5bd5"
  primary-hover: "#3f49b8"
  primary-subtle: "#eef0fd"
  ink: "#17181c"
  ink-muted: "#4a4f57"
  ink-subtle: "#8a8f98"
  canvas: "#f7f8fa"
  surface-1: "#ffffff"
  surface-2: "#f1f2f5"
  hairline: "#e6e8eb"
  hairline-strong: "#d0d3d8"
  success: "#16a34a"
  warning: "#d97706"
  error: "#dc2626"
typography:
  display:
    fontFamily: "Inter, -apple-system, Segoe UI, system-ui, sans-serif"
    fontSize: 24px
    fontWeight: 600
    lineHeight: 1.25
  title:
    fontFamily: "Inter, -apple-system, Segoe UI, system-ui, sans-serif"
    fontSize: 17px
    fontWeight: 600
    lineHeight: 1.35
  body:
    fontFamily: "Inter, -apple-system, Segoe UI, system-ui, sans-serif"
    fontSize: 14px
    fontWeight: 400
    lineHeight: 1.55
  body-sm:
    fontFamily: "Inter, -apple-system, Segoe UI, system-ui, sans-serif"
    fontSize: 13px
    fontWeight: 400
    lineHeight: 1.5
  caption:
    fontFamily: "Inter, -apple-system, Segoe UI, system-ui, sans-serif"
    fontSize: 12px
    fontWeight: 500
    lineHeight: 1.4
  button:
    fontFamily: "Inter, -apple-system, Segoe UI, system-ui, sans-serif"
    fontSize: 14px
    fontWeight: 500
    lineHeight: 1
  number:
    fontFamily: "Inter, -apple-system, Segoe UI, system-ui, sans-serif"
    fontSize: 14px
    fontWeight: 500
    fontVariantNumeric: tabular-nums
  mono:
    fontFamily: "JetBrains Mono, ui-monospace, SF Mono, Consolas, monospace"
    fontSize: 13px
    fontWeight: 400
    lineHeight: 1.5
rounded:
  sm: 6px
  md: 10px
  lg: 14px
  pill: 9999px
spacing:
  xs: 4px
  sm: 8px
  md: 12px
  lg: 16px
  xl: 24px
  xxl: 32px
---

## Overview

一个浅色、克制、数据密集的内部统计工具界面。默认画布 `{colors.canvas}`（#f7f8fa，带极淡冷调的近白），卡片落在 `{colors.surface-1}`（纯白）上，用 1px `{colors.hairline}` 发丝线分隔——**靠表面层级与边框，而非阴影**，营造精确、可扫描的工具感。

**单一靛蓝 accent**（`{colors.primary}` #4f5bd5）只用于：主操作按钮、链接、选中态、聚焦环。**语义色（绿/琥珀/红）严格留给统计判定**：`{colors.success}` 配平通过/正效应、`{colors.warning}` 告警、`{colors.error}` 未通过/负效应。除此之外不引入任何装饰色。

界面主体是**数据**：配平表、Love plot、倾向分布直方图、三法对拍表。这些是主角，chrome 尽量退后。

**Key Characteristics:**
- 浅色画布 + 白卡片 + 发丝线边框，无阴影、无渐变。
- 单一靛蓝 accent；绿/红/琥珀仅表语义判定。
- 数字一律 `tabular-nums` 等宽，右对齐，便于扫读对比。
- 密度高但留白有纪律：表格行高紧凑，卡片内边距固定。

## Colors

### 品牌 accent
- **Primary** (`{colors.primary}` #4f5bd5)：主按钮、链接、聚焦环、选中态。
- **Primary Hover** (`{colors.primary-hover}` #3f49b8)：主按钮 hover/pressed。
- **Primary Subtle** (`{colors.primary-subtle}` #eef0fd)：选中行、浅色高亮背景。

### 表面
- **Canvas** (`{colors.canvas}` #f7f8fa)：应用默认背景。
- **Surface 1** (`{colors.surface-1}` #ffffff)：卡片、面板、表格容器。
- **Surface 2** (`{colors.surface-2}` #f1f2f5)：hover 态、代码块、表头底。
- **Hairline** (`{colors.hairline}` #e6e8eb)：1px 边框、分隔线。
- **Hairline Strong** (`{colors.hairline-strong}` #d0d3d8)：聚焦边框、强调分隔。

### 文本
- **Ink** (`{colors.ink}` #17181c)：标题与主要文本。
- **Ink Muted** (`{colors.ink-muted}` #4a4f57)：次要文本、表格正文。
- **Ink Subtle** (`{colors.ink-subtle}` #8a8f98)：caption、脚注、表头标签。

### 语义（仅统计判定）
- **Success** (`{colors.success}` #16a34a)：配平通过、正效应、达标。
- **Warning** (`{colors.warning}` #d97706)：告警、overlap 不足、underpowered。
- **Error** (`{colors.error}` #dc2626)：配平未通过、负效应、越界。

## Typography

单一无衬线家族（Inter，回退 system-ui/Segoe UI），配合 JetBrains Mono 处理代码与 id。**不用衬线**——统计工具要的是中性、可扫描，不是编辑感。

| Token | Size | Weight | 用途 |
|---|---|---|---|
| `{typography.display}` | 24px | 600 | 页面主标题 |
| `{typography.title}` | 17px | 600 | 区块标题、卡片标题 |
| `{typography.body}` | 14px | 400 | 默认正文 |
| `{typography.body-sm}` | 13px | 400 | 表格正文 |
| `{typography.caption}` | 12px | 500 | 标签、caption、表头 |
| `{typography.button}` | 14px | 500 | 按钮 |
| `{typography.number}` | 14px | 500 | 统计数字（`font-variant-numeric: tabular-nums`） |
| `{typography.mono}` | 13px | 400 | 代码、id、路径 |

**原则**：数字用等宽数字并右对齐；表头用 caption 大写小号、灰字；标题只用 600，不引入 700+。

## Layout

- **间距**：4px 基准，token `{spacing.xs}` 4 · `sm` 8 · `md` 12 · `lg` 16 · `xl` 24 · `xxl` 32。
- **容器**：内容最大宽 ~1200px，居中；顶部一条简洁 header（工具名 + 主操作）。
- **卡片内边距**：`{spacing.lg}` 16px（紧凑卡片）/ `{spacing.xl}` 24px（大卡片、报告页）。
- **表格**：行高紧凑，行与行之间用 hairline 分隔；数字列右对齐、等宽数字。
- **图表区**：SVG 图表放在 `{colors.surface-1}` 卡片里，四周留 `{spacing.lg}` 以上空白。

## Elevation & Depth

**不用阴影。** 层级由「表面色 + 发丝线边框」表达：

| Level | Treatment | Use |
|---|---|---|
| 0 flat | canvas 背景，无边框 | 页面主体 |
| 1 card | surface-1 白卡片 + 1px hairline | 卡片、表格容器、图表卡 |
| 2 lifted | surface-2 底 + hairline-strong | hover、下拉、弹出 |
| 3 focus | 2px primary 聚焦环（50% 透明度） | 聚焦输入/按钮 |

## Shapes

| Token | Value | Use |
|---|---|---|
| `{rounded.sm}` | 6px | 按钮、输入框 |
| `{rounded.md}` | 10px | 卡片 |
| `{rounded.lg}` | 14px | 大卡片、报告区块 |
| `{rounded.pill}` | 9999px | 状态徽章 |

## Components

### 按钮
- **button-primary**：`{colors.primary}` 底、白字、`{rounded.sm}` 6px、`padding 8px 16px`、高 36px。用于「运行分析」「下一步」等主操作。
- **button-secondary**：`{colors.surface-1}` 底、`{colors.ink}` 字、1px hairline 边框，其余同主按钮。
- **button-ghost**：透明底、`{colors.ink-muted}` 字，hover 到 `{colors.surface-2}`。

### 卡片
- **card**：`{colors.surface-1}` 底 + 1px `{colors.hairline}`，`{rounded.md}`，内边距 `{spacing.lg}`。
- **stat-card**（KPI 卡）：顶部 `{typography.caption}` 灰标签，下面 `{typography.number}` 大号等宽数字。用于配平证书、ESS、AUC、MDE 等关键指标。

### 表格
- **data-table**：`{colors.surface-1}` 底，表头 `{colors.surface-2}` 底 + `{typography.caption}` 灰字，行间 hairline，数字列右对齐 + `tabular-nums`。配平平衡表、三法对拍表用它。

### 徽章
- **badge-success / badge-warning / badge-error**：`{rounded.pill}`，语义色做底（浅色）或文字色，配 caption。配平「通过/未通过」、overlap 告警用它。

### 告警条
- **alert**：`{colors.warning}` 浅底 + 深琥珀字 + 1px 边框，`{rounded.md}`。用于「结论依赖建模选择」「underpowered」「overlap 不足」等告警。**告警是工具的一等公民，必须醒目。**

### 表单
- **text-input / select**：`{colors.surface-1}` 底、1px hairline、`{rounded.sm}`、高 36px；聚焦时 2px `{colors.primary}` 环。
- **step-wizard**（目标试验声明 → 上传 → 映射列 → 跑）：顶部横向步骤条，当前步用 `{colors.primary}`，已完成用 success 勾。

### 图表（SVG）
- 所有图表手写内联 SVG，配色只用：primary（主数据线）、surface-2（对比）、hairline（参考线）、success/error（判定）。Love plot 的 `|SMD|=0.1` 参考线用 `{colors.error}` 虚线。

## Do's and Don'ts

### Do
- 画布永远浅色 `{colors.canvas}`，卡片白 `{colors.surface-1}`。
- 单一靛蓝 accent 只用于主操作/链接/聚焦/选中。
- 绿/红/琥珀**只用于统计判定**，不用于装饰。
- 数字用 `tabular-nums` 右对齐。
- 配平证书、告警、三法对拍放在报告最显眼处——它们是用户信任的来源。
- 用 hairline 边框表达层级，不要阴影。

### Don't
- 不要用纯黑 `#000000` 文字或画布。
- 不要加渐变、投影、毛玻璃。
- 不要引入第四个色相（不要紫色卡片、不要蓝色 section）。
- 不要把语义色（绿/红）用在非判定场景（如把按钮涂绿）。
- 不要让表格行高失控——数据密集 ≠ 拥挤，但也要紧凑。

## Responsive Behavior

- 桌面（>1024px）：内容 1200px 居中，多列卡片。
- 平板（768–1024px）：卡片 2 列。
- 移动（<768px）：单列，表格横向滚动（不折行），图表按容器缩放。
- 表格在窄屏**横向滚动**，绝不换行折行——保数据对齐。

## Agent Prompt Guide

给 AI agent 的现成提示：**「按 DESIGN.md 生成界面：浅色画布 #f7f8fa，白卡片 + 1px #e6e8eb 边框无阴影，主操作用靛蓝 #4f5bd5，绿/红/琥珀只用于配平通过/未通过/告警判定，所有统计数字等宽右对齐，图表手写内联 SVG，密度高但留白有纪律。」**
