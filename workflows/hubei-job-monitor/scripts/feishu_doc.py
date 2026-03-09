#!/usr/bin/env python3
"""
飞书云文档工具 — 创建并填充岗位报告文档
"""
import re
import sys
import requests
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils import cfg, setup_logger, now_iso

log = setup_logger("feishu_doc")

FEISHU_BASE = "https://open.feishu.cn/open-apis"


def get_tenant_token() -> str:
    """获取飞书 tenant_access_token"""
    app_id = cfg("feishu_doc.app_id", "")
    app_secret = cfg("feishu_doc.app_secret", "")

    if not app_id or not app_secret:
        raise ValueError("未配置 feishu_doc.app_id / app_secret")

    resp = requests.post(f"{FEISHU_BASE}/auth/v3/tenant_access_token/internal", json={
        "app_id": app_id,
        "app_secret": app_secret,
    }, timeout=10)
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"获取 token 失败: {data}")
    return data["tenant_access_token"]


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def clean_major(major: str) -> str:
    """去掉专业名称中的数字代码"""
    if not major:
        return ""
    cleaned = re.sub(r'\b\d{2,6}', '', major)
    cleaned = re.sub(r'[，,]\s*[，,]', '，', cleaned)
    return cleaned.strip('，, ')


# ── 块构建器 ──────────────────────────────────────

def _text_block(content: str, bold=False) -> dict:
    """创建文本块"""
    style = {}
    if bold:
        style["bold"] = True
    elem = {"text_run": {"content": content}}
    if style:
        elem["text_run"]["text_element_style"] = style
    return {"block_type": 2, "text": {"elements": [elem]}}


def _heading_block(level: int, content: str) -> dict:
    """创建标题块 (level: 1-9)"""
    type_map = {1: 3, 2: 4, 3: 5, 4: 6, 5: 7, 6: 8, 7: 9, 8: 10, 9: 11}
    key_map = {1: "heading1", 2: "heading2", 3: "heading3", 4: "heading4",
               5: "heading5", 6: "heading6", 7: "heading7", 8: "heading8", 9: "heading9"}
    bt = type_map.get(level, 4)
    key = key_map.get(level, "heading2")
    return {"block_type": bt, key: {"elements": [{"text_run": {"content": content}}]}}


def _rich_text_block(parts: list[tuple[str, dict]]) -> dict:
    """创建富文本块：parts = [(text, style_dict), ...]"""
    elements = []
    for content, style in parts:
        elem = {"text_run": {"content": content}}
        if style:
            elem["text_run"]["text_element_style"] = style
        elements.append(elem)
    return {"block_type": 2, "text": {"elements": elements}}


def _bullet_block(content: str) -> dict:
    """创建无序列表项块"""
    return {
        "block_type": 13,
        "bullet": {"elements": [{"text_run": {"content": content}}]}
    }


def _divider_block() -> dict:
    """创建分割线"""
    return {"block_type": 22, "divider": {}}


# ── 文档操作 ──────────────────────────────────────

def create_document(token: str, title: str) -> tuple[str, str]:
    """创建文档，返回 (document_id, url)"""
    resp = requests.post(f"{FEISHU_BASE}/docx/v1/documents",
                         headers=_headers(token),
                         json={"title": title, "folder_token": ""},
                         timeout=15)
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"创建文档失败: {data}")
    doc_id = data["data"]["document"]["document_id"]
    url = f"https://bytedance.feishu.cn/docx/{doc_id}"
    return doc_id, url


def add_blocks(token: str, doc_id: str, blocks: list[dict], batch_size: int = 45) -> None:
    """批量添加内容块到文档（每批最多 50 个）"""
    for i in range(0, len(blocks), batch_size):
        batch = blocks[i:i + batch_size]
        resp = requests.post(
            f"{FEISHU_BASE}/docx/v1/documents/{doc_id}/blocks/{doc_id}/children",
            headers=_headers(token),
            params={"document_revision_id": -1},
            json={"children": batch},
            timeout=30
        )
        data = resp.json()
        if data.get("code") != 0:
            log.error("添加块失败 (batch %d-%d): %s", i, i + len(batch), data.get("msg"))
            raise RuntimeError(f"添加块失败: {data}")
    log.info("成功添加 %d 个内容块", len(blocks))


def set_public_readable(token: str, doc_id: str) -> None:
    """设置文档为链接可读"""
    resp = requests.patch(
        f"{FEISHU_BASE}/drive/v1/permissions/{doc_id}/public",
        headers=_headers(token),
        params={"type": "docx"},
        json={
            "external_access_entity": "open",
            "security_entity": "anyone_can_view",
            "comment_entity": "anyone_can_view",
            "share_entity": "anyone",
            "link_share_entity": "anyone_readable",
        },
        timeout=10
    )
    data = resp.json()
    if data.get("code") != 0:
        log.warning("设置分享权限失败: %s", data.get("msg"))


def delete_document(token: str, doc_id: str) -> None:
    """删除文档（清理测试用）"""
    requests.delete(
        f"{FEISHU_BASE}/drive/v1/files/{doc_id}",
        headers=_headers(token),
        params={"type": "docx"},
        timeout=10
    )


# ── 报告生成 ──────────────────────────────────────

def build_job_report_blocks(dedup_data: dict) -> list[dict]:
    """将岗位数据构建为文档内容块列表"""
    items = dedup_data.get("items", [])
    matched_jobs = dedup_data.get("matched_jobs", [])
    today = now_iso()[:10]

    blocks = []

    # 标题与时间
    blocks.append(_text_block(f"自动生成 · {now_iso()[:19]}"))

    if not matched_jobs:
        blocks.append(_text_block("今日未发现新的工科硕士岗位。"))
        return blocks

    # 按单位分组
    by_employer = {}
    for job in matched_jobs:
        emp = job.get("employer_display", "") or job.get("employer", "未知单位")
        by_employer.setdefault(emp, []).append(job)

    blocks.append(_heading_block(2, f"🔧 工科匹配岗位：{len(matched_jobs)} 个（{len(by_employer)} 个单位）"))

    # 公告链接
    by_announcement = {}
    for job in matched_jobs:
        ann = job.get("_announcement_title", "")
        if ann and ann not in by_announcement:
            by_announcement[ann] = {
                "url": job.get("_announcement_url", ""),
                "date": job.get("_announcement_date", ""),
            }

    if by_announcement:
        for ann_title, ann_info in by_announcement.items():
            date_str = f" ({ann_info['date']})" if ann_info.get('date') else ""
            url = ann_info.get("url", "")
            if url:
                # 使用链接元素
                blocks.append({
                    "block_type": 2,
                    "text": {
                        "elements": [
                            {"text_run": {"content": "📢 "}},
                            {"text_run": {
                                "content": ann_title,
                                "text_element_style": {"link": {"url": url}}
                            }},
                            {"text_run": {"content": date_str}},
                        ]
                    }
                })
            else:
                blocks.append(_text_block(f"📢 {ann_title}{date_str}"))

    blocks.append(_divider_block())

    # 按单位岗位数降序输出
    sorted_employers = sorted(by_employer.items(), key=lambda x: -len(x[1]))

    for emp_name, emp_jobs in sorted_employers:
        blocks.append(_heading_block(3, f"🏢 {emp_name}（{len(emp_jobs)}个）"))

        for job in emp_jobs:
            pos = job.get("position", "—")
            num = job.get("headcount", "")
            edu = job.get("education", "")
            major = clean_major(job.get("major", ""))

            detail_parts = []
            if num:
                detail_parts.append(f"{num}人")
            if edu:
                detail_parts.append(edu)

            detail = f" · ".join(detail_parts)
            line = f"• {pos}"
            if detail:
                line += f"  [{detail}]"

            blocks.append(_text_block(line))

            if major:
                blocks.append(_rich_text_block([
                    ("  专业：", {"bold": True}),
                    (major, {}),
                ]))

    # 其他公告
    no_excel_items = [it for it in items if not it.get("excel_jobs")]
    if no_excel_items:
        blocks.append(_divider_block())
        blocks.append(_heading_block(2, f"📄 其他相关公告（{len(no_excel_items)} 条）"))

        for item in no_excel_items:
            title = item["title"]
            url = item.get("url", "")
            date = item.get("date", "")
            src = item.get("source_name", "")
            date_str = f" ({date})" if date else ""
            src_str = f" — {src}" if src else ""

            if url:
                blocks.append({
                    "block_type": 2,
                    "text": {
                        "elements": [
                            {"text_run": {
                                "content": title,
                                "text_element_style": {"link": {"url": url}}
                            }},
                            {"text_run": {"content": f"{date_str}{src_str}"}},
                        ]
                    }
                })
            else:
                blocks.append(_text_block(f"{title}{date_str}{src_str}"))

    blocks.append(_divider_block())
    blocks.append(_text_block("🤖 自动监控 · 每日 05:00 更新"))

    return blocks


def create_job_report(dedup_data: dict) -> str | None:
    """
    创建飞书云文档报告。
    返回文档 URL，失败返回 None。
    """
    today = now_iso()[:10]
    title = f"📋 湖北硕士岗位监控（工科）— {today}"

    try:
        token = get_tenant_token()
        doc_id, url = create_document(token, title)
        log.info("文档已创建: %s (%s)", doc_id, url)

        blocks = build_job_report_blocks(dedup_data)
        add_blocks(token, doc_id, blocks)

        set_public_readable(token, doc_id)
        log.info("文档已设置为链接可读: %s", url)

        return url

    except Exception as e:
        log.error("创建飞书云文档失败: %s", e)
        return None
