#!/usr/bin/env python3
"""
scoring_engine.py — 自定义评分规则引擎
=========================================
允许用户通过 YAML/JSON 规则文件定义自己的评分维度、权重、阈值和评级。
取代硬编码的评分逻辑，让评分体系完全可配置。

## 规则文件格式 (YAML)

```yaml
# scoring-rules.yaml
version: "1.0"
name: "enterprise-tutorial"
description: "企业教程质量标准"

# 评分维度定义
dimensions:
  content_depth:
    weight: 30          # 满分权重 (所有维度权重之和建议 = 100)
    description: "内容深度"
    rules:
      - check: word_count_min
        value: 2000
        penalty: -15
        message: "字数不足 {value}"
      - check: has_code_blocks
        min_count: 3
        penalty: -10
        message: "代码示例不足"

  structure:
    weight: 25
    description: "文档结构"
    rules:
      - check: heading_hierarchy
        penalty: -8
        message: "标题层级跳跃"

# 评级阈值
grades:
  S: 95
  A: 85
  B: 75
  C: 60
  D: 40
  F: 0
```

## 使用方式

    from scoring_engine import ScoringEngine

    engine = ScoringEngine()
    engine.load_rules("scoring-rules.yaml")

    # 对扫描数据评分
    score = engine.evaluate(chapter_scan_data)
    print(score.total, score.grade, score.details)
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from modules.compat import setup_logger, cfg

log = setup_logger("scoring_engine")

_ROOT = os.path.dirname(os.path.abspath(__file__))
DEFAULT_RULES_DIR = os.path.join(_ROOT, "scoring-rules")
DEFAULT_RULES_FILE = os.path.join(DEFAULT_RULES_DIR, "default.yaml")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 数据类
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass
class RuleResult:
    """单条规则的评估结果。"""
    rule_name: str
    passed: bool
    penalty: float = 0.0
    bonus: float = 0.0
    message: str = ""
    actual_value: Any = None


@dataclass
class DimensionScore:
    """单个维度的评分结果。"""
    name: str
    weight: float
    raw_score: float        # 0-100 维度内部得分
    weighted_score: float   # 加权后的得分
    rules_passed: int = 0
    rules_failed: int = 0
    details: List[RuleResult] = field(default_factory=list)


@dataclass
class ScoreResult:
    """最终评分结果。"""
    total: float            # 0-100
    grade: str
    dimensions: Dict[str, DimensionScore] = field(default_factory=dict)
    rule_name: str = ""
    penalties: List[str] = field(default_factory=list)
    bonuses: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "total": round(self.total, 1),
            "grade": self.grade,
            "rule_name": self.rule_name,
            "dimensions": {
                k: {
                    "weight": v.weight,
                    "raw_score": round(v.raw_score, 1),
                    "weighted_score": round(v.weighted_score, 1),
                    "rules_passed": v.rules_passed,
                    "rules_failed": v.rules_failed,
                }
                for k, v in self.dimensions.items()
            },
            "penalties": self.penalties,
            "bonuses": self.bonuses,
        }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 内置检查函数
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class BuiltinChecks:
    """内置规则检查函数库 — 对应 rules[].check 字段。"""

    @staticmethod
    def word_count_min(data: dict, value: int = 0, **_) -> Tuple[bool, Any]:
        wc = data.get("word_count", 0)
        return wc >= value, wc

    @staticmethod
    def word_count_max(data: dict, value: int = 99999, **_) -> Tuple[bool, Any]:
        wc = data.get("word_count", 0)
        return wc <= value, wc

    @staticmethod
    def line_count_min(data: dict, value: int = 0, **_) -> Tuple[bool, Any]:
        lc = data.get("line_count", 0)
        return lc >= value, lc

    @staticmethod
    def has_code_blocks(data: dict, min_count: int = 1, **_) -> Tuple[bool, Any]:
        content = data.get("content", {})
        count = content.get("code_blocks", 0)
        return count >= min_count, count

    @staticmethod
    def has_labeled_code(data: dict, min_ratio: float = 0.5, **_) -> Tuple[bool, Any]:
        content = data.get("content", {})
        total = content.get("code_blocks", 0)
        unlabeled = content.get("unlabeled_code_blocks", 0)
        if total == 0:
            return True, 1.0
        ratio = (total - unlabeled) / total
        return ratio >= min_ratio, round(ratio, 2)

    @staticmethod
    def heading_hierarchy(data: dict, **_) -> Tuple[bool, Any]:
        structure = data.get("structure", {})
        jumps = structure.get("heading_jumps", [])
        return len(jumps) == 0, len(jumps)

    @staticmethod
    def has_toc(data: dict, **_) -> Tuple[bool, Any]:
        structure = data.get("structure", {})
        has = structure.get("has_toc", False)
        return has, has

    @staticmethod
    def has_nav(data: dict, **_) -> Tuple[bool, Any]:
        structure = data.get("structure", {})
        has = structure.get("has_nav", False)
        return has, has

    @staticmethod
    def has_section(data: dict, section: str = "", **_) -> Tuple[bool, Any]:
        """检查是否有指定类型的段落 (faq/summary/references)。"""
        content = data.get("content", {})
        key = f"has_{section}"
        has = content.get(key, False)
        return has, has

    @staticmethod
    def min_h2_sections(data: dict, value: int = 3, **_) -> Tuple[bool, Any]:
        structure = data.get("structure", {})
        h2 = structure.get("h2", 0)
        return h2 >= value, h2

    @staticmethod
    def has_images(data: dict, min_count: int = 1, **_) -> Tuple[bool, Any]:
        content = data.get("content", {})
        count = content.get("images", 0)
        return count >= min_count, count

    @staticmethod
    def has_tables(data: dict, min_count: int = 1, **_) -> Tuple[bool, Any]:
        content = data.get("content", {})
        count = content.get("tables", 0)
        return count >= min_count, count

    @staticmethod
    def has_links(data: dict, min_count: int = 1, **_) -> Tuple[bool, Any]:
        content = data.get("content", {})
        internal = content.get("links_internal", 0)
        external = content.get("links_external", 0)
        total = internal + external
        return total >= min_count, total

    @staticmethod
    def defect_count_max(data: dict, value: int = 10, **_) -> Tuple[bool, Any]:
        count = len(data.get("defects", []))
        return count <= value, count

    @staticmethod
    def defect_severity_max(data: dict, severity: str = "critical",
                            value: int = 0, **_) -> Tuple[bool, Any]:
        defects = data.get("defects", [])
        count = sum(1 for d in defects if d.get("severity") == severity)
        return count <= value, count

    @staticmethod
    def has_cli_examples(data: dict, **_) -> Tuple[bool, Any]:
        content = data.get("content", {})
        has = content.get("has_cli_examples", False)
        return has, has

    @staticmethod
    def has_blockquotes(data: dict, min_count: int = 1, **_) -> Tuple[bool, Any]:
        content = data.get("content", {})
        count = content.get("blockquotes", 0)
        return count >= min_count, count

    @staticmethod
    def regex_match(data: dict, field: str = "", pattern: str = "", **_) -> Tuple[bool, Any]:
        """检查指定字段是否匹配正则。"""
        val = _nested_get(data, field, "")
        if isinstance(val, str):
            return bool(re.search(pattern, val)), val
        return False, val

    # === 代码专用 ===

    @staticmethod
    def function_count_min(data: dict, value: int = 1, **_) -> Tuple[bool, Any]:
        count = data.get("function_count", 0)
        return count >= value, count

    @staticmethod
    def class_count_min(data: dict, value: int = 0, **_) -> Tuple[bool, Any]:
        count = data.get("class_count", 0)
        return count >= value, count


def _nested_get(d: dict, key: str, default=None):
    """支持 dot notation 的 dict 取值: 'content.code_blocks'。"""
    keys = key.split(".")
    for k in keys:
        if isinstance(d, dict):
            d = d.get(k, default)
        else:
            return default
    return d


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 引擎主类
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class ScoringEngine:
    """自定义评分规则引擎。"""

    def __init__(self):
        self.rules: Dict = {}
        self.name: str = "default"
        self._check_registry: Dict[str, callable] = {}
        self._grades: List[Tuple[str, float]] = []

        # 注册内置检查函数
        for attr in dir(BuiltinChecks):
            if not attr.startswith("_"):
                fn = getattr(BuiltinChecks, attr)
                if callable(fn):
                    self._check_registry[attr] = fn

    # ── 规则加载 ──────────────────────────────────────

    def load_rules(self, filepath: str) -> None:
        """加载 YAML 或 JSON 规则文件。"""
        filepath = os.path.abspath(filepath)
        ext = os.path.splitext(filepath)[1].lower()

        if ext in (".yaml", ".yml"):
            self.rules = self._load_yaml(filepath)
        elif ext == ".json":
            with open(filepath, encoding="utf-8") as f:
                self.rules = json.load(f)
        else:
            raise ValueError(f"不支持的规则格式: {ext}")

        self.name = self.rules.get("name", Path(filepath).stem)
        self._build_grades()
        log.info(f"加载评分规则: {self.name} v{self.rules.get('version', '?')} "
                 f"({len(self.rules.get('dimensions', {}))} 个维度)")

    def load_rules_dict(self, rules: dict) -> None:
        """从 dict 直接加载规则（方便测试）。"""
        self.rules = rules
        self.name = rules.get("name", "inline")
        self._build_grades()

    def load_default(self) -> None:
        """加载默认规则。"""
        if os.path.exists(DEFAULT_RULES_FILE):
            self.load_rules(DEFAULT_RULES_FILE)
        else:
            self.load_rules_dict(self._builtin_default_rules())

    @staticmethod
    def _load_yaml(filepath: str) -> dict:
        """加载 YAML 文件 (兼容无 PyYAML 环境)。"""
        try:
            import yaml
            with open(filepath, encoding="utf-8") as f:
                return yaml.safe_load(f)
        except ImportError:
            # 简单 YAML 解析 fallback (仅处理基本结构)
            log.warning("PyYAML 未安装，使用简化解析器")
            return ScoringEngine._simple_yaml_parse(filepath)

    @staticmethod
    def _simple_yaml_parse(filepath: str) -> dict:
        """极简 YAML 解析 — 仅支持 key: value 和简单列表。"""
        import re as _re
        result = {}
        with open(filepath, encoding="utf-8") as f:
            for line in f:
                line = line.rstrip()
                if not line or line.lstrip().startswith("#"):
                    continue
                m = _re.match(r"^(\w+):\s*(.+)$", line)
                if m:
                    k, v = m.group(1), m.group(2).strip()
                    try:
                        result[k] = json.loads(v)
                    except (json.JSONDecodeError, ValueError):
                        result[k] = v
        return result

    def _build_grades(self):
        """构建评级阈值列表 (降序排列)。"""
        grades_conf = self.rules.get("grades", {
            "S": 95, "A": 85, "B": 75, "C": 60, "D": 40, "F": 0,
        })
        self._grades = sorted(grades_conf.items(), key=lambda x: x[1], reverse=True)

    def _get_grade(self, score: float) -> str:
        """根据分数获取评级。"""
        for grade, threshold in self._grades:
            if score >= threshold:
                return grade
        return self._grades[-1][0] if self._grades else "F"

    # ── 自定义检查函数注册 ────────────────────────────

    def register_check(self, name: str, fn: callable) -> None:
        """注册自定义检查函数。

        fn 签名: (data: dict, **rule_params) -> Tuple[bool, Any]
        """
        self._check_registry[name] = fn
        log.debug(f"注册自定义检查: {name}")

    # ── 评分执行 ──────────────────────────────────────

    def evaluate(self, data: dict) -> ScoreResult:
        """对数据执行评分。

        Args:
            data: 扫描结果数据 (ChapterScanResult 或 CodeFileScanResult)

        Returns:
            ScoreResult 评分结果
        """
        dimensions_conf = self.rules.get("dimensions", {})
        if not dimensions_conf:
            log.warning(f"规则 {self.name} 没有定义维度，返回默认分数")
            return ScoreResult(total=0, grade="F", rule_name=self.name)

        total_weight = sum(d.get("weight", 0) for d in dimensions_conf.values())
        dimension_results: Dict[str, DimensionScore] = {}
        all_penalties = []
        all_bonuses = []

        for dim_name, dim_conf in dimensions_conf.items():
            dim_weight = dim_conf.get("weight", 0)
            dim_rules = dim_conf.get("rules", [])
            dim_score = 100.0  # 从满分开始扣
            rule_details = []
            passed = 0
            failed = 0

            for rule in dim_rules:
                check_name = rule.get("check", "")
                check_fn = self._check_registry.get(check_name)

                if not check_fn:
                    log.warning(f"未知检查函数: {check_name}，跳过")
                    continue

                # 提取规则参数 (除 check/penalty/bonus/message)
                params = {k: v for k, v in rule.items()
                          if k not in ("check", "penalty", "bonus", "message")}

                try:
                    ok, actual = check_fn(data, **params)
                except Exception as e:
                    log.warning(f"检查 {check_name} 异常: {e}")
                    ok, actual = True, None  # 异常时不扣分

                penalty = rule.get("penalty", 0)
                bonus = rule.get("bonus", 0)
                msg_template = rule.get("message", check_name)

                # 格式化消息
                fmt_vars = {k: v for k, v in params.items()
                            if isinstance(v, (str, int, float))}
                fmt_vars["actual"] = actual
                fmt_vars.setdefault("value", "")
                fmt_vars.setdefault("min_count", "")
                try:
                    msg = msg_template.format(**fmt_vars)
                except (KeyError, IndexError):
                    msg = msg_template

                rr = RuleResult(
                    rule_name=check_name,
                    passed=ok,
                    actual_value=actual,
                    message=msg,
                )

                if ok:
                    passed += 1
                    if bonus:
                        dim_score += bonus
                        rr.bonus = bonus
                        all_bonuses.append(f"{dim_name}.{check_name}: +{bonus}")
                else:
                    failed += 1
                    if penalty:
                        dim_score += penalty  # penalty 应为负数
                        rr.penalty = penalty
                        all_penalties.append(f"{dim_name}.{check_name}: {penalty} ({msg})")

                rule_details.append(rr)

            # 限制维度分数在 [0, 100]
            dim_score = max(0, min(100, dim_score))
            weighted = (dim_score * dim_weight / total_weight) if total_weight > 0 else 0

            dimension_results[dim_name] = DimensionScore(
                name=dim_name,
                weight=dim_weight,
                raw_score=dim_score,
                weighted_score=weighted,
                rules_passed=passed,
                rules_failed=failed,
                details=rule_details,
            )

        total = sum(d.weighted_score for d in dimension_results.values())
        total = max(0, min(100, total))
        grade = self._get_grade(total)

        return ScoreResult(
            total=total,
            grade=grade,
            dimensions=dimension_results,
            rule_name=self.name,
            penalties=all_penalties,
            bonuses=all_bonuses,
        )

    # ── 批量评分 ──────────────────────────────────────

    def evaluate_batch(self, items: List[dict]) -> List[ScoreResult]:
        """批量评分。"""
        return [self.evaluate(item) for item in items]

    # ── 内置默认规则 ──────────────────────────────────

    @staticmethod
    def _builtin_default_rules() -> dict:
        """返回内置默认评分规则 (与 tutorial_scanner 对齐)。"""
        return {
            "version": "1.0",
            "name": "default-tutorial",
            "description": "默认教程质量评分规则",
            "dimensions": {
                "content_depth": {
                    "weight": 25,
                    "description": "内容深度",
                    "rules": [
                        {"check": "word_count_min", "value": 2000, "penalty": -20,
                         "message": "字数不足 {value} (实际: {actual})"},
                        {"check": "word_count_min", "value": 1000, "penalty": -15,
                         "message": "字数严重不足 (实际: {actual})"},
                        {"check": "has_code_blocks", "min_count": 3, "penalty": -10,
                         "message": "代码示例不足 (最少 {min_count}, 实际: {actual})"},
                        {"check": "has_cli_examples", "penalty": -5,
                         "message": "缺少 CLI 示例"},
                    ],
                },
                "structure": {
                    "weight": 20,
                    "description": "文档结构",
                    "rules": [
                        {"check": "heading_hierarchy", "penalty": -10,
                         "message": "标题层级跳跃 ({actual} 处)"},
                        {"check": "has_toc", "penalty": -5,
                         "message": "缺少目录"},
                        {"check": "has_nav", "penalty": -5,
                         "message": "缺少导航链接"},
                        {"check": "min_h2_sections", "value": 3, "penalty": -8,
                         "message": "H2 段落过少 (最少 {value}, 实际: {actual})"},
                    ],
                },
                "code_quality": {
                    "weight": 15,
                    "description": "代码质量",
                    "rules": [
                        {"check": "has_code_blocks", "min_count": 1, "penalty": -15,
                         "message": "完全没有代码示例"},
                        {"check": "has_labeled_code", "min_ratio": 0.5, "penalty": -8,
                         "message": "过多未标注语言的代码块 (标注率: {actual})"},
                    ],
                },
                "pedagogy": {
                    "weight": 15,
                    "description": "教学设计",
                    "rules": [
                        {"check": "has_section", "section": "faq", "penalty": -5,
                         "message": "缺少 FAQ 段落"},
                        {"check": "has_section", "section": "summary", "penalty": -5,
                         "message": "缺少本章小结"},
                        {"check": "has_blockquotes", "min_count": 1, "penalty": -3,
                         "message": "缺少提示/警告引用块"},
                    ],
                },
                "references": {
                    "weight": 10,
                    "description": "参考来源",
                    "rules": [
                        {"check": "has_section", "section": "references", "penalty": -10,
                         "message": "缺少参考来源段落"},
                        {"check": "has_links", "min_count": 3, "penalty": -5,
                         "message": "链接过少 (最少 {min_count}, 实际: {actual})"},
                    ],
                },
                "readability": {
                    "weight": 15,
                    "description": "可读性",
                    "rules": [
                        {"check": "defect_count_max", "value": 5, "penalty": -10,
                         "message": "缺陷过多 (最多 {value}, 实际: {actual})"},
                        {"check": "defect_severity_max", "severity": "critical", "value": 0,
                         "penalty": -15, "message": "存在严重缺陷 ({actual} 个)"},
                        {"check": "has_images", "min_count": 1, "bonus": 5,
                         "message": "包含图片/示意图"},
                        {"check": "has_tables", "min_count": 1, "bonus": 3,
                         "message": "包含表格"},
                    ],
                },
            },
            "grades": {
                "S": 95,
                "A": 85,
                "B": 75,
                "C": 60,
                "D": 40,
                "F": 0,
            },
        }


# ── 便捷函数 ─────────────────────────────────────────
_engine: Optional[ScoringEngine] = None


def get_engine(rules_file: str = None) -> ScoringEngine:
    """获取全局 ScoringEngine 实例。"""
    global _engine
    if _engine is None:
        _engine = ScoringEngine()
        if rules_file:
            _engine.load_rules(rules_file)
        else:
            _engine.load_default()
    return _engine


def score(data: dict, rules_file: str = None) -> ScoreResult:
    """便捷评分函数。"""
    return get_engine(rules_file).evaluate(data)


# ── CLI ───────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="评分规则引擎")
    parser.add_argument("--rules", type=str, help="规则文件路径 (YAML/JSON)")
    parser.add_argument("--data", type=str, help="待评分数据文件 (JSON)")
    parser.add_argument("--list-checks", action="store_true", help="列出所有可用检查函数")
    parser.add_argument("--validate", type=str, help="验证规则文件是否合法")
    args = parser.parse_args()

    engine = ScoringEngine()

    if args.list_checks:
        print("可用检查函数:")
        for name in sorted(engine._check_registry.keys()):
            print(f"  - {name}")
        sys.exit(0)

    if args.validate:
        try:
            engine.load_rules(args.validate)
            dims = engine.rules.get("dimensions", {})
            total_weight = sum(d.get("weight", 0) for d in dims.values())
            print(f"✅ 规则文件合法: {engine.name}")
            print(f"   维度: {len(dims)}")
            print(f"   总权重: {total_weight}")
            for dname, dconf in dims.items():
                rules_count = len(dconf.get("rules", []))
                print(f"   - {dname}: 权重 {dconf.get('weight', 0)}, "
                      f"{rules_count} 条规则")
        except Exception as e:
            print(f"❌ 规则文件无效: {e}")
            sys.exit(1)
        sys.exit(0)

    if args.rules:
        engine.load_rules(args.rules)
    else:
        engine.load_default()

    if args.data:
        with open(args.data, encoding="utf-8") as f:
            data = json.load(f)
        result = engine.evaluate(data)
        print(f"\n评分结果: {result.total:.1f} ({result.grade})")
        print(f"规则集: {result.rule_name}")
        for dname, ds in result.dimensions.items():
            status = "✅" if ds.rules_failed == 0 else "⚠️"
            print(f"  {status} {dname}: {ds.raw_score:.0f} × {ds.weight} "
                  f"= {ds.weighted_score:.1f} "
                  f"({ds.rules_passed}✓ {ds.rules_failed}✗)")
        if result.penalties:
            print("\n扣分项:")
            for p in result.penalties:
                print(f"  - {p}")
        if result.bonuses:
            print("\n加分项:")
            for b in result.bonuses:
                print(f"  + {b}")
