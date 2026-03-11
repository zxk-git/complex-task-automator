# 优化报告模板

## OpenClaw 教程自动优化报告

**生成时间**: {{timestamp}}
**项目路径**: {{project_dir}}

---

## 📊 总体概览

| 指标 | 值 |
|------|-----|
| 已完成章节 | {{completed}}/{{expected}} |
| 平均质量分 | {{avg_score}}/100 |
| 总字数 | {{total_words}} |
| 缺失章节 | {{missing_count}} |
| 本轮优化 | {{refined_count}} 章 |
| 格式修复 | {{format_fixes}} 处 |

---

## 🔍 扫描结果

{{scan_summary}}

---

## 📉 质量分析

### 优先级分布

| 优先级 | 章节数 | 说明 |
|--------|--------|------|
| 🔴 高 | {{high_priority}} | 评分<60 或缺失≥3个必须段落 |
| 🟡 中 | {{medium_priority}} | 评分 60-85 |
| 🟢 低 | {{low_priority}} | 评分>85，仅需微调 |

### 待优化队列

{{optimization_queue}}

---

## ✅ 精炼结果

{{refine_summary}}

---

## 🔗 参考来源

{{references_summary}}

---

## 📝 格式化结果

{{format_summary}}

---

## 📋 建议和下一步

{{recommendations}}

---

> 本报告由 OpenClaw Tutorial Auto Skill v3.0 自动生成
