# 优化计划模板

## 第{{chapter_num}}章 优化计划

**文件**: {{file}}
**当前评分**: {{current_score}} → 目标: {{target_score}}
**优先级**: {{priority}}

---

### 待执行优化项

{{#improvements}}
#### {{index}}. [{{type}}] {{target}}

- **描述**: {{description}}
- **预估影响**: {{estimated_impact}}
- **工作量**: {{effort}}

{{/improvements}}

---

### 缺失段落

{{#missing_sections}}
- ❌ {{section}}
{{/missing_sections}}

### 薄弱段落

{{#weak_sections}}
- ⚠️ {{section}} — {{reason}} ({{word_count}}字)
{{/weak_sections}}

---

> 此计划由 quality_analyzer 自动生成
