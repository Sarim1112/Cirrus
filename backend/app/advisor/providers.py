"""Model providers. Ollama is the default; add another by implementing ChatProvider."""

import json
import threading
import time
from dataclasses import dataclass, field
from typing import Protocol

import httpx

from ..config import get_settings


class ProviderError(RuntimeError):
    pass


@dataclass
class ToolCall:
    name: str
    arguments: dict


@dataclass
class ProviderReply:
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)


class ChatProvider(Protocol):
    name: str

    def available(self) -> bool: ...

    def chat(
        self, messages: list[dict], tools: list[dict] | None = None, temperature: float = 0.2
    ) -> ProviderReply: ...


class NoProvider:
    """Used when AI is switched off. The advisor still answers from the calculation tools."""

    name = "none"

    def available(self) -> bool:
        return False

    def chat(self, messages, tools=None, temperature=0.2) -> ProviderReply:
        raise ProviderError("No model is configured")


class OllamaProvider:
    name = "ollama"

    def __init__(
        self,
        base_url: str,
        model: str,
        timeout: float = 90.0,
        max_concurrency: int = 2,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self._client = httpx.Client(transport=transport, timeout=timeout)
        self._slots = threading.BoundedSemaphore(max(1, max_concurrency))
        self._status: tuple[float, bool] = (0.0, False)

    def available(self) -> bool:
        """Cached for 30 seconds, so every chat turn doesn't ping the server."""
        checked_at, status = self._status
        if time.monotonic() - checked_at < 30 and checked_at:
            return status
        try:
            response = self._client.get(f"{self.base_url}/api/tags", timeout=2.0)
            response.raise_for_status()
            names = {m.get("name", "") for m in response.json().get("models", [])}
            status = self.model in names or f"{self.model}:latest" in names
        except (httpx.HTTPError, ValueError):
            status = False
        self._status = (time.monotonic(), status)
        return status

    def chat(self, messages, tools=None, temperature=0.2) -> ProviderReply:
        # A shared CPU model handles few requests at a time. If it's busy, answer without it
        # immediately instead of queueing visitors behind one another.
        if not self._slots.acquire(timeout=1.0):
            raise ProviderError("The model is busy")
        try:
            payload = {
                "model": self.model,
                "messages": messages,
                "stream": False,
                "options": {"temperature": temperature, "num_ctx": 4096},
            }
            if tools:
                payload["tools"] = tools
            response = self._client.post(f"{self.base_url}/api/chat", json=payload)
            response.raise_for_status()
            message = response.json().get("message") or {}
        except (httpx.HTTPError, ValueError) as exc:
            self._status = (0.0, False)
            raise ProviderError(str(exc)) from exc
        finally:
            self._slots.release()
        calls = []
        for call in message.get("tool_calls") or []:
            function = call.get("function") or {}
            arguments = function.get("arguments") or {}
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except ValueError:
                    arguments = {}
            if function.get("name"):
                calls.append(ToolCall(function["name"], arguments))
        return ProviderReply(content=(message.get("content") or "").strip(), tool_calls=calls)


_provider: ChatProvider | None = None
_lock = threading.Lock()


def get_provider() -> ChatProvider:
    global _provider
    with _lock:
        if _provider is None:
            settings = get_settings()
            if settings.ai_enabled:
                _provider = OllamaProvider(
                    settings.ollama_url,
                    settings.ollama_model,
                    settings.ollama_timeout_seconds,
                    settings.ollama_max_concurrency,
                )
            else:
                _provider = NoProvider()
        return _provider


def set_provider(provider: ChatProvider | None) -> None:
    """Testing hook."""
    global _provider
    with _lock:
        _provider = provider
