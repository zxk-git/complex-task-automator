# Tutorial Scanner Prompt

你是一名教程质量分析专家。请扫描并分析以下教程仓库的内容状态。

## 扫描任务

对每个章节文件，提取以下信息：

### 基础元数据
- 文件名和章节编号
- 标题（H1）
- 字数统计（中文字符 + 英文单词）
- 行数
- 最后修改时间

### 结构分析
- 标题层级结构（H1-H6 数量和嵌套关系）
- 是否有标题层级跳跃（如 H1 直接到 H3）
- 小节数量和列表
- 是否有目录/导航元素
- 是否有章首导航（上一章/下一章）

### 内容质量指标
- 代码块数量和语言标注
- 表格数量
- 图片/链接数量（内部/外部）
- 是否有 FAQ 段落
- 是否有"本章小结"
- 是否有"参考来源"或"延伸阅读"
- 是否有实际 CLI 命令示例
- 引用块（blockquote）使用情况

### 缺陷检测
- 占位符文本（TODO、TBD、待补充 等）
- 空段落或过短段落（<50字的 H2 小节）
- 连续密排（>20行无空行分隔）
- 重复内容（跨章节的大段相似文本）
- 断裂链接（引用不存在的文件或锚点）

## 输出格式

```json
{
  "scan_time": "ISO8601",
  "total_chapters": N,
  "chapters": [
    {
      "file": "01-xxx.md",
      "number": 1,
      "title": "...",
      "word_count": N,
      "line_count": N,
      "structure": {
        "h1": N, "h2": N, "h3": N, "h4": N,
        "has_toc": bool,
        "has_nav": bool,
        "heading_jumps": ["H1→H3 at line X"]
      },
      "content": {
        "code_blocks": N,
        "tables": N,
        "images": N,
        "links_internal": N,
        "links_external": N,
        "has_faq": bool,
        "has_summary": bool,
        "has_references": bool,
        "has_cli_examples": bool
      },
      "defects": [
        {"type": "placeholder", "line": N, "text": "..."},
        {"type": "short_section", "section": "...", "word_count": N}
      ],
      "quality_score": 0-100
    }
  ],
  "missing_chapters": [N, N, ...],
  "global_issues": ["..."]
}
```

## 评分标准

| 维度 | 权重 | 标准 |
|------|------|------|
| 内容充实度 | 25% | 字数≥1500，无占位符，H2小节≥5 |
| 结构完整性 | 20% | 标题不跳级，有目录/导航/FAQ/小结 |
| 代码示例 | 20% | ≥3个代码块，有语言标注，有CLI示例 |
| 可读性 | 15% | 段落适中，有表格/列表辅助，空行分隔 |
| 教学价值 | 10% | 有渐进式讲解，有练习/思考题 |
| 参考来源 | 10% | 有外部链接，有官方文档引用 |
