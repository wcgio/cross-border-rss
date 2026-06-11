# 设计：日报聚焦 Amazon / eBay / Etsy 卖家视角

日期：2026-06-11
状态：已与用户确认（方案 B：中调）

## 背景

用户最初表述想关注「外贸」，澄清概念后确认：主业是**跨境电商平台零售**（Amazon + eBay + Etsy），市场为**美国 + 欧洲**。现有系统框架正确，但内容焦点偏泛：Temu/TikTok Shop/Shein 等无关平台占比偏高，eBay/Etsy 专属内容供给不足，欧洲视角缺失。

用户决策：

| 决策点 | 选择 |
|---|---|
| 业务形态 | 跨境电商（Amazon + eBay + Etsy） |
| 目标市场 | 美国 + 欧洲 |
| 无关平台资讯 | 降级保留：不剔除、永不标重点、归入大盘趋势 |
| 调整深度 | 方案 B 中调：prompt 聚焦 + 源补强；分类体系与 UI 不动 |

## 1. 渠道源调整（sources.yml）

**新增（platform 类，实施时联网核实 feed 真实地址）：**

- ChannelX（原 Tamebay）：欧洲电商/eBay/亚马逊欧洲站资讯，原生 RSS
- Value Added Resource：eBay/Etsy 深度独立博客，原生 RSS

**保留不动**：Marketplace Pulse、EcommerceBytes、雨果跨境、亿邦动力、The Loadstar、FreightWaves、Splash247、gCaptain、USTR、海关总署、Modern Retail、Retail Dive。

**微调**：

- 36氪 include 关键词追加：eBay、Etsy、欧盟、VAT
- 卖家通知邮件转 RSS 占位注释扩展为 Amazon/eBay/Etsy 三平台

## 2. AI 提示词调整（summarizer.py）

- **编辑视角**（MAP_PROMPT 开头）：改为「为主营 Amazon、eBay、Etsy、面向美国与欧洲市场的跨境电商卖家筛选资讯」
- **重点判定**：high 仅限直接影响 Amazon/eBay/Etsy 卖家收入/成本/合规的确定性重大变动，或美欧关税、海运、平台监管重大政策；**其他平台（Temu/TikTok Shop/沃尔玛/Shein 等）资讯一律 normal**；每批最多 1-2 条 high 的约束保留
- **relevant 判定**：保持宽松，无关平台资讯不剔除（作为经营环境背景信息）
- **分组规则**（REDUCE_PROMPT）：platform 分类仅收 Amazon/eBay/Etsy 及行业通用平台政策；其他平台动态归 market

## 3. 分类体系与渲染：不动

四分类（platform/logistics/compliance/market）语义不变，CATEGORIES、Tab UI、卡片、来源标签、重点角标全部保持现状。

## 4. 测试与生效

- 更新 summarizer 测试：prompt 内容断言（含三平台聚焦语句）、其他平台归 market 的行为依赖 AI 输出故不做单测（reduce 的兜底逻辑已有测试覆盖）
- 全量 pytest 须保持绿色；改动自次日日报生效；`data/seen.json` 不动，无重复风险

## 非目标

- 不按平台重构分类体系（方案 C 已否决：物流/合规与平台维度正交）
- 不删除任何现有源（无关平台内容走 AI 降级，不走源剔除）
- 不调整 UI
