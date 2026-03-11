# Chapter Template

以下是标准章节模板。新生成和优化教程时必须遵循此结构。

---

```markdown
> **📖 OpenClaw 中文实战教程** | [← 上一章：{prev_title}]({prev_file}) | [目录](README.md) | [下一章：{next_title} →]({next_file})

---

# 第{N}章 {title}

> **难度**: {difficulty} | **阅读时间**: ~{minutes}分钟 | **前置要求**: {prerequisites}

{brief_intro_paragraph}

## 📑 本章目录

- [{N}.1 {section1_title}](#{n}1-{anchor1})
- [{N}.2 {section2_title}](#{n}2-{anchor2})
- [{N}.3 {section3_title}](#{n}3-{anchor3})
- [{N}.4 {section4_title}](#{n}4-{anchor4})
- [{N}.5 {section5_title}](#{n}5-{anchor5})
- [常见问题 (FAQ)](#常见问题-faq)
- [本章小结](#本章小结)
- [参考来源](#参考来源)


## {N}.1 {section1_title}

### 概述

{section1_overview_2to3_sentences}

### 工作原理

{explanation_of_how_it_works}

### 操作步骤

1. **步骤一**：{step1_description}

   ```bash
   {command1}
   ```

   预期输出：
   ```text
   {expected_output1}
   ```

2. **步骤二**：{step2_description}

   ```bash
   {command2}
   ```

> **💡 提示**：{helpful_tip}


## {N}.2 {section2_title}

{section2_content}


## {N}.3 {section3_title}

{section3_content}

### 配置示例

```yaml
# 配置文件示例
{config_example}
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| {param1} | {type1} | {default1} | {desc1} |
| {param2} | {type2} | {default2} | {desc2} |


## {N}.4 实战案例

### 案例：{use_case_title}

**场景描述**：{scenario}

**实现步骤**：

```bash
# Step 1: {step1}
{command1}

# Step 2: {step2}
{command2}

# Step 3: {step3}
{command3}
```

**结果验证**：

```bash
{verify_command}
```

> **📌 关键**：{important_note}


## {N}.5 高级用法

{advanced_usage_content}

### 进阶技巧

- **技巧 1**：{tip1}
- **技巧 2**：{tip2}
- **技巧 3**：{tip3}

> **⚠️ 注意**：{warning}


## 故障排查

| 问题 | 可能原因 | 解决方法 |
|------|---------|---------|
| {problem1} | {cause1} | {solution1} |
| {problem2} | {cause2} | {solution2} |
| {problem3} | {cause3} | {solution3} |


## 常见问题 (FAQ)

### Q: {question1}？

**A:** {answer1}

```bash
{example_command_if_applicable}
```

### Q: {question2}？

**A:** {answer2}

### Q: {question3}？

**A:** {answer3}

---

## 本章小结

本章介绍了 {topic_summary}。核心要点：

- ✅ {key_point_1}
- ✅ {key_point_2}
- ✅ {key_point_3}
- ✅ {key_point_4}

**下一步**：在 [第{N+1}章]({next_file}) 中，我们将学习 {next_topic}。

---

## 参考来源

| 来源 | 链接 | 说明 |
|------|------|------|
| OpenClaw 官方文档 | https://docs.openclaw.com/{topic} | {desc} |
| GitHub 仓库 | https://github.com/anthropics/openclaw | 源码参考 |
| {source3} | {url3} | {desc3} |

---

> **📖 章节导航** | [← 上一章：{prev_title}]({prev_file}) | [目录](README.md) | [下一章：{next_title} →]({next_file})
```

## 模板使用说明

| 占位符 | 说明 | 示例 |
|--------|------|------|
| `{N}` | 章节编号 | `03` |
| `{title}` | 章节标题 | `Skills 插件体系与批量开发` |
| `{difficulty}` | 难度星级 | `⭐⭐⭐` (1-5星) |
| `{minutes}` | 预估阅读时间 | `25` |
| `{prerequisites}` | 前置要求 | `第2章` |
| `{prev_file}` | 上一章文件名 | `02-xxx.md` |
| `{next_file}` | 下一章文件名 | `04-xxx.md` |

## 段落数量要求

| 章节部分 | 最少 H2 段落 | 说明 |
|---------|------------|------|
| 核心内容 | 5 | 主题相关的 H2 小节 |
| FAQ | 1 | 至少 3 个问答对 |
| 小结 | 1 | 要点回顾 + 下一步 |
| 参考来源 | 1 | 至少 3 个来源 |
| **总计** | **≥ 8 个 H2** | |
