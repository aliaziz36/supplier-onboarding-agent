"""The single Claude client. Every model call in the project goes through call().

Cache: each request is keyed by a SHA-256 of its canonical JSON (model, system,
messages, tools, output_config, thinking, max_tokens). Responses are stored as
JSON under cache/llm/ and committed, so anyone can replay the evaluation.

Env switches:
  REPLAY=1    cache only; a miss raises CacheMiss (no key needed)
  NO_CACHE=1  ignore the cache and do not write to it (stability runs)

Note: `temperature` is not sent. The API rejects sampling parameters on
claude-sonnet-5-5 (and on every model since 2026-10-21); determinism for
reruns comes from this cache instead.
"""
import hashlib
import json
import os
import threading
import time
from dataclasses import dataclass, field

from app.config import CACHE_DIR, MODEL, env_flag


class CacheMiss(RuntimeError):
    pass


@dataclass
class LLMResult:
    content: list[dict]             # content blocks as plain dicts (pass back unchanged)
    stop_reason: str
    usage: dict = field(default_factory=dict)
    cached: bool = False
    seconds: float = 0.0
    key: str = ""

    @property
    def text(self) -> str:
        return "".join(b.get("text", "") for b in self.content if b.get("type") == "text")

    def tool_uses(self) -> list[dict]:
        return [b for b in self.content if b.get("type") == "tool_use"]


_client = None


def _get_client():
    global _client
    if _client is None:
        import anthropic
        _client = anthropic.Anthropic(max_retries=4, timeout=300.0)
    return _client


def cache_key(request: dict) -> str:
    blob = json.dumps(request, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()


def _cache_path(key: str):
    return CACHE_DIR / key[:2] / f"{key}.json"


_live = threading.local()


def set_live(on: bool) -> None:
    """Dashboard 'process a new email': this thread calls the API for real (no cache read, no replay)."""
    _live.on = on


def call(*, messages: list[dict], system: str | None = None, tools: list[dict] | None = None,
         output_format: dict | None = None, effort: str = "low", thinking: str = "between_tools",
         max_tokens: int = 8000, purpose: str = "", model: str | None = None) -> LLMResult:
    """One Messages API call, cached by input hash.

    thinking: "between_tools" (lowest setting, no extended thinking) or "adaptive".
    """
    request: dict = {
        "model": model or MODEL,
        "max_tokens": max_tokens,
        "messages": messages,
        "thinking": {"type": thinking},
        "output_config": {"effort": effort},
    }
    if system:
        request["system"] = system
    if tools:
        request["tools"] = tools
    if output_format:
        request["output_config"]["format"] = output_format

    key = cache_key(request)
    path = _cache_path(key)
    live = getattr(_live, "on", False)
    use_cache = not env_flag("NO_CACHE") and not live

    if use_cache and path.exists():
        saved = json.loads(path.read_text())
        r = saved["response"]
        return LLMResult(content=r["content"], stop_reason=r["stop_reason"], usage=r.get("usage", {}),
                         cached=True, seconds=0.0, key=key)
    if env_flag("REPLAY") and not live:
        raise CacheMiss(f"REPLAY=1 and no cached response for {purpose or 'call'} ({key[:12]})")

    started = time.time()
    response = _get_client().messages.create(**request)
    seconds = time.time() - started
    data = response.to_dict()
    if data.get("stop_reason") == "refusal":
        raise RuntimeError(f"Model refused ({purpose}): {data.get('stop_details')}")

    usage = data.get("usage") or {}
    result = LLMResult(content=data["content"], stop_reason=data["stop_reason"],
                       usage={"input_tokens": usage.get("input_tokens", 0),
                              "output_tokens": usage.get("output_tokens", 0)},
                       cached=False, seconds=seconds, key=key)
    if use_cache:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "purpose": purpose,
            "model": request["model"],
            "seconds": round(seconds, 2),
            "response": {"content": result.content, "stop_reason": result.stop_reason, "usage": result.usage},
        }, ensure_ascii=False, indent=1))
    return result


if __name__ == "__main__":
    # Smoke test: python -m app.llm
    r = call(messages=[{"role": "user", "content": "Reply with exactly: ready"}],
             max_tokens=200, purpose="smoke-test")
    print(repr(r.text), "cached" if r.cached else f"live {r.seconds:.1f}s", r.usage)
