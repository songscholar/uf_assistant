"""
UF Stock Assistant — 信号通知系统
支持 Telegram / Email / Webhook / Discord / Browser 五种渠道
"""

from __future__ import annotations

import hashlib
import hmac
import json
import smtplib
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from enum import StrEnum
from typing import Any

import httpx

from app.core.logging import get_logger

logger = get_logger("app.strategies.notifier")


class NotificationChannel(StrEnum):
    """通知渠道枚举"""
    TELEGRAM = "telegram"
    EMAIL = "email"
    WEBHOOK = "webhook"
    DISCORD = "discord"
    BROWSER = "browser"


# ── Multilingual Templates ──────────────────────────────────────────────

TEMPLATES: dict[str, dict[str, str]] = {
    "zh": {
        "signal_open": "🟢 开仓信号\n策略: {strategy_name}\n标的: {symbol}\n方向: {signal_type}\n价格: {price}\n置信度: {confidence}\n原因: {reason}",
        "signal_close": "🔴 平仓信号\n策略: {strategy_name}\n标的: {symbol}\n方向: {signal_type}\n价格: {price}\n原因: {reason}",
        "alert_price": "⚠️ 价格告警\n标的: {symbol}\n当前价: {current_price}\n触发条件: {condition}",
        "alert_pnl": "📊 盈亏告警\n策略: {strategy_name}\n标的: {symbol}\n未实现盈亏: {pnl}",
    },
    "en": {
        "signal_open": "🟢 Open Signal\nStrategy: {strategy_name}\nSymbol: {symbol}\nType: {signal_type}\nPrice: {price}\nConfidence: {confidence}\nReason: {reason}",
        "signal_close": "🔴 Close Signal\nStrategy: {strategy_name}\nSymbol: {symbol}\nType: {signal_type}\nPrice: {price}\nReason: {reason}",
        "alert_price": "⚠️ Price Alert\nSymbol: {symbol}\nCurrent: {current_price}\nCondition: {condition}",
        "alert_pnl": "📊 PnL Alert\nStrategy: {strategy_name}\nSymbol: {symbol}\nUnrealized PnL: {pnl}",
    },
}


def render_template(
    template_key: str,
    language: str = "zh",
    **kwargs: Any,
) -> str:
    """Render a notification template in the specified language."""
    lang = "zh" if language.startswith("zh") else "en"
    tpl = TEMPLATES.get(lang, TEMPLATES["en"]).get(template_key, "")
    try:
        return tpl.format(**kwargs)
    except KeyError:
        return tpl


@dataclass
class SignalMessage:
    """交易信号通知消息"""
    strategy_id: int
    strategy_name: str
    symbol: str
    signal_type: str  # open_long, close_long, open_short, close_short, etc.
    price: float
    confidence: float
    reason: str
    timestamp: str


class BaseNotifier(ABC):
    """通知器基类"""

    @property
    @abstractmethod
    def channel(self) -> NotificationChannel:
        """通知渠道类型"""
        ...

    @abstractmethod
    def send(self, message: SignalMessage) -> bool:
        """发送通知，返回是否成功"""
        ...


class TelegramNotifier(BaseNotifier):
    """Telegram Bot 通知器"""

    def __init__(self, bot_token: str, chat_id: str) -> None:
        self._bot_token = bot_token
        self._chat_id = chat_id
        self._api_base = f"https://api.telegram.org/bot{bot_token}"

    @property
    def channel(self) -> NotificationChannel:
        return NotificationChannel.TELEGRAM

    def _format_message(self, message: SignalMessage) -> str:
        """格式化 Telegram 消息（支持 Markdown）"""
        signal_emoji = {
            "open_long": "\U0001F7E2",   # green circle
            "close_long": "\U0001F534",   # red circle
            "open_short": "\U0001F534",   # red circle
            "close_short": "\U0001F7E2",  # green circle
        }
        emoji = signal_emoji.get(message.signal_type, "\U000026A0")  # warning as default

        return (
            f"{emoji} *Strategy Signal*\n\n"
            f"*Strategy:* {message.strategy_name}\n"
            f"*Symbol:* `{message.symbol}`\n"
            f"*Signal:* `{message.signal_type}`\n"
            f"*Price:* `{message.price:.4f}`\n"
            f"*Confidence:* `{message.confidence:.0%}`\n"
            f"*Reason:* {message.reason}\n"
            f"*Time:* {message.timestamp}"
        )

    def send(self, message: SignalMessage) -> bool:
        text = self._format_message(message)
        url = f"{self._api_base}/sendMessage"

        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.post(
                    url,
                    json={
                        "chat_id": self._chat_id,
                        "text": text,
                        "parse_mode": "Markdown",
                    },
                )
            if resp.status_code == 200:
                logger.info("telegram_sent", symbol=message.symbol, signal=message.signal_type)
                return True

            logger.error(
                "telegram_send_failed",
                status=resp.status_code,
                body=resp.text,
                symbol=message.symbol,
            )
            return False

        except httpx.HTTPError as exc:
            logger.error("telegram_send_error", error=str(exc), symbol=message.symbol, exc_info=True)
            return False


class EmailNotifier(BaseNotifier):
    """SMTP 邮件通知器"""

    def __init__(
        self,
        smtp_host: str,
        smtp_port: int,
        username: str,
        password: str,
        to_address: str,
    ) -> None:
        self._smtp_host = smtp_host
        self._smtp_port = smtp_port
        self._username = username
        self._password = password
        self._to_address = to_address

    @property
    def channel(self) -> NotificationChannel:
        return NotificationChannel.EMAIL

    def _build_html(self, message: SignalMessage) -> str:
        """构建 HTML 邮件内容"""
        return (
            "<html><body>"
            f"<h2>Strategy Signal: {message.strategy_name}</h2>"
            "<table style='border-collapse:collapse;' border='1' cellpadding='8'>"
            f"<tr><td><b>Symbol</b></td><td>{message.symbol}</td></tr>"
            f"<tr><td><b>Signal</b></td><td>{message.signal_type}</td></tr>"
            f"<tr><td><b>Price</b></td><td>{message.price:.4f}</td></tr>"
            f"<tr><td><b>Confidence</b></td><td>{message.confidence:.0%}</td></tr>"
            f"<tr><td><b>Reason</b></td><td>{message.reason}</td></tr>"
            f"<tr><td><b>Time</b></td><td>{message.timestamp}</td></tr>"
            "</table>"
            "</body></html>"
        )

    def send(self, message: SignalMessage) -> bool:
        subject = f"[{message.signal_type.upper()}] {message.symbol} - {message.strategy_name}"
        html = self._build_html(message)

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self._username
        msg["To"] = self._to_address
        msg.attach(MIMEText(html, "html", "utf-8"))

        try:
            with smtplib.SMTP(self._smtp_host, self._smtp_port) as server:
                server.starttls()
                server.login(self._username, self._password)
                server.sendmail(self._username, [self._to_address], msg.as_string())

            logger.info("email_sent", symbol=message.symbol, to=self._to_address)
            return True

        except (smtplib.SMTPException, OSError) as exc:
            logger.error("email_send_error", error=str(exc), symbol=message.symbol, exc_info=True)
            return False


class WebhookNotifier(BaseNotifier):
    """Webhook POST 通知器，支持 HMAC-SHA256 签名"""

    def __init__(self, webhook_url: str, signing_secret: str = "") -> None:
        self._webhook_url = webhook_url
        self._signing_secret = signing_secret

    @property
    def channel(self) -> NotificationChannel:
        return NotificationChannel.WEBHOOK

    def _sign_payload(self, body: bytes) -> str:
        """Generate HMAC-SHA256 signature for the payload."""
        if not self._signing_secret:
            return ""
        return hmac.new(
            self._signing_secret.encode("utf-8"),
            body,
            hashlib.sha256,
        ).hexdigest()

    def send(self, message: SignalMessage) -> bool:
        payload = {
            "strategy_id": message.strategy_id,
            "strategy_name": message.strategy_name,
            "symbol": message.symbol,
            "signal_type": message.signal_type,
            "price": message.price,
            "confidence": message.confidence,
            "reason": message.reason,
            "timestamp": message.timestamp,
        }

        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers: dict[str, str] = {"Content-Type": "application/json"}

        signature = self._sign_payload(body)
        if signature:
            headers["X-Signature"] = f"sha256={signature}"

        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.post(self._webhook_url, content=body, headers=headers)
            if resp.status_code < 300:
                logger.info("webhook_sent", symbol=message.signal_type, url=self._webhook_url)
                return True

            logger.error(
                "webhook_send_failed",
                status=resp.status_code,
                body=resp.text,
                url=self._webhook_url,
            )
            return False

        except httpx.HTTPError as exc:
            logger.error("webhook_send_error", error=str(exc), url=self._webhook_url, exc_info=True)
            return False


class DiscordNotifier(BaseNotifier):
    """Discord Webhook 通知器 — 使用 Embed 格式"""

    def __init__(self, webhook_url: str) -> None:
        self._webhook_url = webhook_url

    @property
    def channel(self) -> NotificationChannel:
        return NotificationChannel.DISCORD

    def _build_embed(self, message: SignalMessage) -> dict[str, Any]:
        """Build Discord embed with color coding."""
        is_open = "open" in message.signal_type.lower()
        color = 0x2ECC71 if is_open else 0xE74C3C  # green for open, red for close

        fields = [
            {"name": "Symbol", "value": f"`{message.symbol}`", "inline": True},
            {"name": "Signal", "value": f"`{message.signal_type}`", "inline": True},
            {"name": "Price", "value": f"`{message.price:.4f}`", "inline": True},
            {"name": "Confidence", "value": f"`{message.confidence:.0%}`", "inline": True},
            {"name": "Reason", "value": message.reason[:256], "inline": False},
        ]

        return {
            "title": f"Strategy: {message.strategy_name}",
            "color": color,
            "fields": fields,
            "footer": {"text": f"ID: {message.strategy_id}"},
            "timestamp": message.timestamp,
        }

    def send(self, message: SignalMessage) -> bool:
        embed = self._build_embed(message)
        payload = {"embeds": [embed]}

        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.post(
                    self._webhook_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
            if resp.status_code < 300:
                logger.info("discord_sent", symbol=message.symbol, signal=message.signal_type)
                return True

            logger.error(
                "discord_send_failed",
                status=resp.status_code,
                body=resp.text,
                symbol=message.symbol,
            )
            return False

        except httpx.HTTPError as exc:
            logger.error("discord_send_error", error=str(exc), symbol=message.symbol, exc_info=True)
            return False


class BrowserNotifier(BaseNotifier):
    """Browser 通知器 — 写入 DB，前端轮询拉取"""

    def __init__(self, db_session_factory: Any = None) -> None:
        self._session_factory = db_session_factory

    @property
    def channel(self) -> NotificationChannel:
        return NotificationChannel.BROWSER

    def send(self, message: SignalMessage) -> bool:
        if not self._session_factory:
            logger.warning("browser_notifier_no_db", symbol=message.symbol)
            return False

        try:
            from app.strategies.models import SignalNotification

            session = self._session_factory()
            try:
                notification = SignalNotification(
                    strategy_id=str(message.strategy_id),
                    signal_type=message.signal_type,
                    symbol=message.symbol,
                    price=message.price,
                    message=(
                        f"{message.strategy_name}: {message.signal_type} "
                        f"{message.symbol} @ {message.price:.4f} — {message.reason}"
                    ),
                    channel="browser",
                    sent=True,
                    is_read=False,
                )
                session.add(notification)
                session.commit()
                logger.info("browser_notification_stored", symbol=message.symbol)
                return True
            finally:
                session.close()

        except Exception as exc:
            logger.error("browser_notifier_error", error=str(exc), symbol=message.symbol, exc_info=True)
            return False


class NotifierManager:
    """通知管理器 — 统一调度多个通知渠道"""

    def __init__(self) -> None:
        self._notifiers: list[BaseNotifier] = []

    def add_notifier(self, notifier: BaseNotifier) -> None:
        """注册一个通知器"""
        self._notifiers.append(notifier)
        logger.info("notifier_added", channel=notifier.channel.value, total=len(self._notifiers))

    def remove_notifier(self, channel: NotificationChannel) -> None:
        """移除指定渠道的通知器"""
        self._notifiers = [n for n in self._notifiers if n.channel != channel]
        logger.info("notifier_removed", channel=channel.value, remaining=len(self._notifiers))

    def notify(self, message: SignalMessage) -> dict[str, bool]:
        """
        向所有已注册渠道发送通知。

        Returns:
            {channel_name: success} 字典
        """
        if not self._notifiers:
            logger.warning("no_notifiers_registered", symbol=message.symbol)
            return {}

        results: dict[str, bool] = {}
        for notifier in self._notifiers:
            channel_name = notifier.channel.value
            try:
                success = notifier.send(message)
                results[channel_name] = success
            except Exception:
                logger.error("notifier_unexpected_error", channel=channel_name, exc_info=True)
                results[channel_name] = False

        logger.info(
            "notify_completed",
            symbol=message.symbol,
            signal=message.signal_type,
            results=results,
        )
        return results

    def notify_signal(
        self,
        *,
        strategy_id: str,
        strategy_name: str,
        symbol: str,
        signal_type: str,
        price: float,
        stake_amount: float = 0.0,
        direction: str = "long",
        confidence: float = 0.0,
        reason: str = "",
        language: str = "zh",
        notification_config: dict[str, Any] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, dict[str, Any]]:
        """
        Unified signal dispatch method called by PendingOrderWorker.

        Converts parameters to SignalMessage and dispatches to all registered
        channels (or only channels specified in notification_config).

        Returns:
            {channel_name: {"ok": bool, "error": str_or_empty}} dict.
        """
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Use multilingual template if no custom reason provided
        if not reason:
            template_key = "signal_open" if "open" in signal_type else "signal_close"
            reason = render_template(
                template_key,
                language=language,
                strategy_name=strategy_name or f"Strategy_{strategy_id}",
                symbol=symbol,
                signal_type=signal_type,
                price=f"{price:.4f}",
                confidence=f"{confidence:.0%}",
                reason=f"Amount: {stake_amount:.4f} | Direction: {direction}",
            )

        message = SignalMessage(
            strategy_id=int(strategy_id) if strategy_id else 0,
            strategy_name=strategy_name or f"Strategy_{strategy_id}",
            symbol=symbol,
            signal_type=signal_type,
            price=price,
            confidence=confidence,
            reason=reason,
            timestamp=now_str,
        )

        results: dict[str, dict[str, Any]] = {}
        for notifier in self._notifiers:
            channel_name = notifier.channel.value
            try:
                success = notifier.send(message)
                results[channel_name] = {"ok": success, "error": "" if success else "send_failed"}
            except Exception as exc:
                results[channel_name] = {"ok": False, "error": str(exc)}

        return results


# ── Module-level singleton ─────────────────────────────────────────────────

_notifier_manager: NotifierManager | None = None


def get_notifier_manager() -> NotifierManager:
    """Return the module-level NotifierManager singleton."""
    global _notifier_manager
    if _notifier_manager is None:
        _notifier_manager = NotifierManager()
    return _notifier_manager
