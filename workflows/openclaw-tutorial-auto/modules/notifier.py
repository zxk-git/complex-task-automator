#!/usr/bin/env python3
"""
notifier.py — 通用 Webhook 通知模块
支持: 飞书 (Feishu) / 企业微信 (WeCom) / 钉钉 (DingTalk) / Slack / 自定义 Webhook
通过 OpenClaw delivery-queue 投递飞书，其他渠道直接 HTTP POST
"""
import hashlib
import hmac
import json
import os
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPT_DIR)

from modules.compat import setup_logger, cfg, load_json, save_json

log = setup_logger("notifier")

# ─── 常量 ────────────────────────────────────────────
DELIVERY_QUEUE_DIR = Path.home() / ".openclaw" / "delivery-queue"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 渠道适配器 (Channel Adapters)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class BaseAdapter:
    """渠道适配器基类"""
    name: str = "base"

    def __init__(self, config: dict):
        self.config = config
        self.enabled = config.get("enabled", True)

    def send(self, title: str, body: str, level: str = "info", extra: dict = None) -> bool:
        raise NotImplementedError


class FeishuAdapter(BaseAdapter):
    """飞书 — 通过 OpenClaw delivery-queue 投递"""
    name = "feishu"

    def send(self, title: str, body: str, level: str = "info", extra: dict = None) -> bool:
        chat_id = self.config.get("chat_id") or cfg("feishu.chat_id", "")
        account = self.config.get("account") or cfg("feishu.account", "default")
        if not chat_id:
            log.warning("[feishu] 未配置 chat_id，跳过")
            return False

        icon = {"info": "ℹ️", "success": "✅", "warning": "⚠️", "error": "❌"}.get(level, "📢")
        message = f"{icon} **{title}**\n\n{body}"

        DELIVERY_QUEUE_DIR.mkdir(parents=True, exist_ok=True)
        delivery = {
            "id": str(uuid.uuid4()),
            "enqueuedAt": int(time.time() * 1000),
            "channel": "feishu",
            "to": chat_id,
            "payloads": [{"text": message, "replyToTag": False,
                          "replyToCurrent": False, "audioAsVoice": False}],
            "gifPlayback": False, "silent": False, "retryCount": 0,
        }
        if account and account != "default":
            delivery["accountId"] = account

        out_path = DELIVERY_QUEUE_DIR / f"{delivery['id']}.json"
        save_json(out_path, delivery)
        log.info("[feishu] 已投递: %s", delivery["id"])
        return True


class WeComAdapter(BaseAdapter):
    """企业微信 — 群机器人 Webhook"""
    name = "wecom"

    def send(self, title: str, body: str, level: str = "info", extra: dict = None) -> bool:
        webhook_url = self.config.get("webhook_url") or os.getenv("WECOM_WEBHOOK_URL", "")
        if not webhook_url:
            log.warning("[wecom] 未配置 webhook_url，跳过")
            return False

        icon = {"info": "ℹ️", "success": "✅", "warning": "⚠️", "error": "❌"}.get(level, "📢")
        content = f"{icon} **{title}**\n\n{body}"

        payload = {
            "msgtype": "markdown",
            "markdown": {"content": content},
        }
        return self._post(webhook_url, payload)

    @staticmethod
    def _post(url: str, payload: dict) -> bool:
        try:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            req = Request(url, data=data, headers={"Content-Type": "application/json"})
            resp = urlopen(req, timeout=10)
            result = json.loads(resp.read())
            if result.get("errcode", 0) != 0:
                log.error("[wecom] 发送失败: %s", result)
                return False
            log.info("[wecom] 发送成功")
            return True
        except Exception as e:
            log.error("[wecom] 发送异常: %s", e)
            return False


class DingTalkAdapter(BaseAdapter):
    """钉钉 — 群机器人 Webhook (支持签名)"""
    name = "dingtalk"

    def send(self, title: str, body: str, level: str = "info", extra: dict = None) -> bool:
        webhook_url = self.config.get("webhook_url") or os.getenv("DINGTALK_WEBHOOK_URL", "")
        secret = self.config.get("secret") or os.getenv("DINGTALK_SECRET", "")
        if not webhook_url:
            log.warning("[dingtalk] 未配置 webhook_url，跳过")
            return False

        # 签名
        if secret:
            ts = str(int(time.time() * 1000))
            string_to_sign = f"{ts}\n{secret}"
            hmac_code = hmac.new(secret.encode(), string_to_sign.encode(), hashlib.sha256).digest()
            import base64
            sign = base64.b64encode(hmac_code).decode()
            sep = "&" if "?" in webhook_url else "?"
            webhook_url = f"{webhook_url}{sep}timestamp={ts}&sign={sign}"

        icon = {"info": "ℹ️", "success": "✅", "warning": "⚠️", "error": "❌"}.get(level, "📢")
        content = f"{icon} **{title}**\n\n{body}"

        at_all = (extra or {}).get("at_all", level == "error")
        payload = {
            "msgtype": "markdown",
            "markdown": {"title": title, "text": content},
            "at": {"isAtAll": at_all},
        }
        return self._post(webhook_url, payload)

    @staticmethod
    def _post(url: str, payload: dict) -> bool:
        try:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            req = Request(url, data=data, headers={"Content-Type": "application/json"})
            resp = urlopen(req, timeout=10)
            result = json.loads(resp.read())
            if result.get("errcode", 0) != 0:
                log.error("[dingtalk] 发送失败: %s", result)
                return False
            log.info("[dingtalk] 发送成功")
            return True
        except Exception as e:
            log.error("[dingtalk] 发送异常: %s", e)
            return False


class SlackAdapter(BaseAdapter):
    """Slack — Incoming Webhook"""
    name = "slack"

    def send(self, title: str, body: str, level: str = "info", extra: dict = None) -> bool:
        webhook_url = self.config.get("webhook_url") or os.getenv("SLACK_WEBHOOK_URL", "")
        if not webhook_url:
            log.warning("[slack] 未配置 webhook_url，跳过")
            return False

        color_map = {"info": "#3b82f6", "success": "#22c55e",
                     "warning": "#eab308", "error": "#ef4444"}
        color = color_map.get(level, "#94a3b8")

        payload = {
            "attachments": [{
                "color": color,
                "title": title,
                "text": body,
                "footer": "OpenClaw Tutorial Auto Pipeline v5.0",
                "ts": int(time.time()),
            }]
        }
        return self._post(webhook_url, payload)

    @staticmethod
    def _post(url: str, payload: dict) -> bool:
        try:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            req = Request(url, data=data, headers={"Content-Type": "application/json"})
            resp = urlopen(req, timeout=10)
            if resp.status == 200:
                log.info("[slack] 发送成功")
                return True
            log.error("[slack] 发送失败: HTTP %s", resp.status)
            return False
        except Exception as e:
            log.error("[slack] 发送异常: %s", e)
            return False


class GenericWebhookAdapter(BaseAdapter):
    """自定义 Webhook — JSON POST"""
    name = "webhook"

    def send(self, title: str, body: str, level: str = "info", extra: dict = None) -> bool:
        webhook_url = self.config.get("webhook_url") or os.getenv("GENERIC_WEBHOOK_URL", "")
        if not webhook_url:
            log.warning("[webhook] 未配置 webhook_url，跳过")
            return False

        payload = {
            "event": "openclaw.pipeline",
            "title": title,
            "body": body,
            "level": level,
            "timestamp": datetime.now().isoformat(),
            "extra": extra or {},
        }

        # 自定义 headers
        headers = {"Content-Type": "application/json"}
        for k, v in self.config.get("headers", {}).items():
            headers[k] = v

        try:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            req = Request(webhook_url, data=data, headers=headers)
            resp = urlopen(req, timeout=10)
            ok = 200 <= resp.status < 300
            if ok:
                log.info("[webhook] 发送成功 → %s", webhook_url)
            else:
                log.error("[webhook] HTTP %s", resp.status)
            return ok
        except Exception as e:
            log.error("[webhook] 异常: %s", e)
            return False


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 统一通知器 (Unified Notifier)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ADAPTER_MAP = {
    "feishu": FeishuAdapter,
    "wecom": WeComAdapter,
    "dingtalk": DingTalkAdapter,
    "slack": SlackAdapter,
    "webhook": GenericWebhookAdapter,
}


class Notifier:
    """
    统一通知器 — 根据 config.yaml 的 notify 配置自动分发到多渠道

    config.yaml 示例:
        notify:
          channels:
            feishu:
              enabled: true
              chat_id: "chat:oc_xxx"
            wecom:
              enabled: true
              webhook_url: "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx"
            dingtalk:
              enabled: false
              webhook_url: "https://oapi.dingtalk.com/robot/send?access_token=xxx"
              secret: "SECxxx"
            slack:
              enabled: false
              webhook_url: "https://hooks.slack.com/services/xxx/yyy/zzz"
    """

    def __init__(self, config: dict = None):
        if config is None:
            config = self._load_from_yaml()
        self.adapters: list[BaseAdapter] = []
        for name, adapter_cls in ADAPTER_MAP.items():
            ch_cfg = config.get(name, {})
            if ch_cfg.get("enabled", name == "feishu"):  # 飞书默认启用
                self.adapters.append(adapter_cls(ch_cfg))
        log.info("通知渠道: %s", [a.name for a in self.adapters])

    @staticmethod
    def _load_from_yaml() -> dict:
        """从 config.yaml 的 notify.channels 加载"""
        notify_cfg = {}
        for name in ADAPTER_MAP:
            ch_cfg = {}
            # 尝试从 notify.channels.{name} 读取
            enabled = cfg(f"notify.channels.{name}.enabled", None)
            if enabled is not None:
                ch_cfg["enabled"] = enabled
            url = cfg(f"notify.channels.{name}.webhook_url", "")
            if url:
                ch_cfg["webhook_url"] = url
            secret = cfg(f"notify.channels.{name}.secret", "")
            if secret:
                ch_cfg["secret"] = secret
            chat_id = cfg(f"notify.channels.{name}.chat_id", "")
            if chat_id:
                ch_cfg["chat_id"] = chat_id
            account = cfg(f"notify.channels.{name}.account", "")
            if account:
                ch_cfg["account"] = account
            # 兼容旧 feishu 节点
            if name == "feishu" and not ch_cfg:
                ch_cfg = {
                    "enabled": True,
                    "chat_id": cfg("feishu.chat_id", ""),
                    "account": cfg("feishu.account", "default"),
                }
            notify_cfg[name] = ch_cfg
        return notify_cfg

    def send(self, title: str, body: str, level: str = "info",
             extra: dict = None, channels: list = None) -> dict:
        """
        发送通知到所有已启用渠道

        Args:
            title: 通知标题
            body: 通知正文 (Markdown)
            level: info / success / warning / error
            channels: 指定渠道列表 (None = 全部)
            extra: 额外数据 (传给各适配器)

        Returns:
            {"ok": bool, "results": {"feishu": True, "wecom": False, ...}}
        """
        results = {}
        for adapter in self.adapters:
            if channels and adapter.name not in channels:
                continue
            try:
                results[adapter.name] = adapter.send(title, body, level, extra)
            except Exception as e:
                log.error("[%s] 未捕获异常: %s", adapter.name, e)
                results[adapter.name] = False

        ok = any(results.values()) if results else False
        return {"ok": ok, "results": results}

    def notify_pipeline_result(self, mode: str, result: dict) -> dict:
        """便捷方法 — 发送 pipeline 完成通知"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        version = result.get("version", "5.0")
        duration = result.get("duration", 0)

        if mode == "tutorial":
            summary = result.get("summary", {})
            completed = summary.get("completed", 0)
            avg = summary.get("avg_score", 0)
            defects = summary.get("total_defects", 0)
            title = f"教程优化完成 ({now})"
            body = (
                f"📚 **Tutorial Pipeline v{version}** 完成\n\n"
                f"- 章节: {completed}\n"
                f"- 平均分: {avg}/100\n"
                f"- 缺陷: {defects}\n"
                f"- 耗时: {duration:.1f}s\n"
            )
            level = "success" if avg >= 75 else "warning"
        elif mode == "code":
            summary = result.get("summary", {})
            files = summary.get("total_files", 0)
            avg = summary.get("avg_score", 0)
            defects = summary.get("total_defects", 0)
            title = f"代码分析完成 ({now})"
            body = (
                f"🔧 **Code Pipeline v{version}** 完成\n\n"
                f"- 文件: {files}\n"
                f"- 平均分: {avg}/100\n"
                f"- 缺陷: {defects}\n"
                f"- 耗时: {duration:.1f}s\n"
            )
            level = "success" if avg >= 75 else "warning"
        else:
            title = f"Pipeline 完成 ({now})"
            body = f"模式: {mode}\n耗时: {duration:.1f}s"
            level = "info"

        return self.send(title, body, level, extra={"mode": mode, "result_summary": result.get("summary")})

    def notify_error(self, error: str, context: str = "") -> dict:
        """便捷方法 — 发送错误通知"""
        title = "Pipeline 错误"
        body = f"❌ **错误**: {error}"
        if context:
            body += f"\n📍 上下文: {context}"
        return self.send(title, body, level="error")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 便捷函数
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_default_notifier: Notifier = None

def get_notifier() -> Notifier:
    global _default_notifier
    if _default_notifier is None:
        _default_notifier = Notifier()
    return _default_notifier

def notify(title: str, body: str, level: str = "info", **kw) -> dict:
    """全局便捷通知函数"""
    return get_notifier().send(title, body, level, **kw)

def notify_pipeline(mode: str, result: dict) -> dict:
    """全局便捷 pipeline 通知函数"""
    return get_notifier().notify_pipeline_result(mode, result)

def notify_error(error: str, context: str = "") -> dict:
    """全局便捷错误通知函数"""
    return get_notifier().notify_error(error, context)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CLI
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="通用通知器 CLI")
    parser.add_argument("--title", "-t", default="测试通知")
    parser.add_argument("--body", "-b", default="这是一条来自通知器的测试消息。")
    parser.add_argument("--level", "-l", choices=["info", "success", "warning", "error"], default="info")
    parser.add_argument("--channel", "-c", nargs="*", help="指定渠道 (默认全部)")
    args = parser.parse_args()

    result = notify(args.title, args.body, args.level, channels=args.channel)
    print(json.dumps(result, indent=2, ensure_ascii=False))
