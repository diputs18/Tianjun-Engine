from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Iterator


@dataclass(frozen=True, slots=True)
class LLMSettings:
    """Connection settings for an OpenAI-compatible chat-completions endpoint."""

    base_url: str | None = "https://api.deepseek.com"
    model: str | None = "deepseek-v4-flash"
    api_key: str | None = None
    api_key_source: str | None = None
    timeout_seconds: float = 30.0
    temperature: float = 0.2
    max_tokens: int = 700
    required: bool = True
    offline: bool = False

    @classmethod
    def from_env(cls) -> "LLMSettings":
        key, source = _first_env_key("TIANJUN_LLM_API_KEY", "DEEPSEEK_API_KEY")
        return cls(
            base_url=os.environ.get("TIANJUN_LLM_BASE_URL"),
            model=os.environ.get("TIANJUN_LLM_MODEL"),
            api_key=key,
            api_key_source=source,
            timeout_seconds=float(os.environ.get("TIANJUN_LLM_TIMEOUT_SECONDS", "30")),
            required=os.environ.get("TIANJUN_LLM_REQUIRED", "true").strip().lower() not in {"0", "false", "no", "off"},
            offline=os.environ.get("TIANJUN_OFFLINE", "false").strip().lower() in {"1", "true", "yes", "on"},
        )

    def enabled(self) -> bool:
        return not self.offline and bool(self.base_url and self.model)

    def validate_for_chat(self) -> None:
        if self.offline:
            return
        missing = []
        if not self.base_url:
            missing.append("llm.base_url")
        if not self.model:
            missing.append("llm.model")
        if missing and self.required:
            joined = ", ".join(missing)
            raise ValueError(f"LLM is required by configuration but missing: {joined}. Set them in tianjun.toml or use --offline for local-only development.")

    def endpoint(self) -> str:
        if not self.base_url:
            raise ValueError("LLM base_url is not configured.")
        base = self.base_url.rstrip("/")
        if base.endswith("/chat/completions"):
            return base
        if base.endswith("/v1"):
            return f"{base}/chat/completions"
        if "api.deepseek.com" in base:
            return f"{base}/chat/completions"
        return f"{base}/v1/chat/completions"

    def key_fingerprint(self) -> str | None:
        if not self.api_key:
            return None
        if len(self.api_key) <= 8:
            return "*" * len(self.api_key)
        return f"{self.api_key[:4]}...{self.api_key[-4:]}"

    def describe(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled(),
            "base_url": self.base_url,
            "endpoint": self.endpoint() if self.base_url else None,
            "model": self.model,
            "timeout_seconds": self.timeout_seconds,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "required": self.required,
            "offline": self.offline,
            "api_key_present": bool(self.api_key),
            "api_key_source": self.api_key_source,
            "api_key_fingerprint": self.key_fingerprint(),
        }


class OpenAICompatibleClient:
    """Tiny stdlib-only client for grounded chat response generation.

    The policy engine remains the source of truth. If this client is unavailable or the
    endpoint fails, callers fall back to deterministic responses without mutating state.
    """

    def __init__(self, settings: LLMSettings) -> None:
        self.settings = settings

    def is_enabled(self) -> bool:
        return self.settings.enabled()

    def chat(self, messages: list[dict[str, str]], *, timeout_seconds: float | None = None) -> str:
        if not self.settings.enabled():
            raise ValueError("LLM client is not enabled; configure base_url and model.")
        payload = {
            "model": self.settings.model,
            "messages": messages,
            "temperature": self.settings.temperature,
            "max_tokens": self.settings.max_tokens,
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.settings.api_key:
            headers["Authorization"] = f"Bearer {self.settings.api_key}"
        request = urllib.request.Request(self.settings.endpoint(), data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(
                request,
                timeout=timeout_seconds or self.settings.timeout_seconds,
            ) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            hint = self._http_error_hint(exc.code)
            raise RuntimeError(f"LLM endpoint returned HTTP {exc.code}: {details}{hint}") from exc
        data = json.loads(raw)
        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError("LLM endpoint returned no choices.")
        message = choices[0].get("message") or {}
        content = str(message.get("content") or "").strip()
        if not content:
            raise RuntimeError("LLM endpoint returned an empty message.")
        return content


    def chat_stream(self, messages: list[dict[str, str]], *, timeout_seconds: float | None = None) -> Iterator[str]:
        """Yield OpenAI-compatible streaming chat deltas.

        This method performs a real provider stream by sending ``stream: true``
        and parsing the provider's SSE response. Callers receive token deltas as
        the upstream model emits them; this is intentionally different from
        splitting a fully generated message after the fact.
        """
        if not self.settings.enabled():
            raise ValueError("LLM client is not enabled; configure base_url and model.")
        payload = {
            "model": self.settings.model,
            "messages": messages,
            "temperature": self.settings.temperature,
            "max_tokens": self.settings.max_tokens,
            "stream": True,
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json", "Accept": "text/event-stream"}
        if self.settings.api_key:
            headers["Authorization"] = f"Bearer {self.settings.api_key}"
        request = urllib.request.Request(self.settings.endpoint(), data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(
                request,
                timeout=timeout_seconds or self.settings.timeout_seconds,
            ) as response:
                for raw_line in response:
                    delta = self._parse_stream_line(raw_line.decode("utf-8", errors="replace").strip())
                    if delta is None:
                        continue
                    if delta == "__DONE__":
                        return
                    yield delta
        except urllib.error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            hint = self._http_error_hint(exc.code)
            raise RuntimeError(f"LLM endpoint returned HTTP {exc.code}: {details}{hint}") from exc

    def _parse_stream_line(self, line: str) -> str | None:
        if not line or line.startswith(":"):
            return None
        if line.startswith("data:"):
            line = line.removeprefix("data:").strip()
        if not line:
            return None
        if line == "[DONE]":
            return "__DONE__"
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            return None
        choices = data.get("choices") or []
        if choices:
            choice = choices[0]
            delta = choice.get("delta") or {}
            if isinstance(delta, dict):
                content = delta.get("content")
                if content:
                    return str(content)
            # Some OpenAI-compatible endpoints include the final message in a
            # streaming-shaped response; accept it as a fallback.
            message = choice.get("message") or {}
            if isinstance(message, dict) and message.get("content"):
                return str(message["content"])
        # Responses API style fallback: output_text.delta events.
        if data.get("type") in {"response.output_text.delta", "output_text.delta"} and data.get("delta"):
            return str(data["delta"])
        return None

    def _http_error_hint(self, status_code: int) -> str:
        if status_code == 401:
            source = self.settings.api_key_source or "not set"
            fingerprint = self.settings.key_fingerprint() or "missing"
            return (
                f" [auth diagnosis: api_key_source={source}, api_key_fingerprint={fingerprint}; "
                "DeepSeek 401 means the provider rejected the Bearer token. "
                "Check that DEEPSEEK_API_KEY is set in the same shell running tianjun, "
                "that no stale TIANJUN_LLM_API_KEY is overriding it, and that the key has API access.]"
            )
        if status_code == 402:
            return " [billing diagnosis: provider reports insufficient balance or payment quota.]"
        return ""


def _first_env_key(*names: str) -> tuple[str | None, str | None]:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value, name
    return None, None
