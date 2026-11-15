"""The AI layer, with the network replaced: every kind of service is asked correctly and its answer is read
correctly. Nothing leaves this machine and no key is needed."""
import json
import os
import sys
import tempfile

os.environ["PEAKCUT_DATA"] = tempfile.mkdtemp(prefix="pc-ai-")
os.environ["DATABASE_URL"] = ""
os.environ.update(PEAKCUT_AI_PROVIDER="gemini", PEAKCUT_AI_MODELS="model-a, model-b", PEAKCUT_AI_KEY="test-key-123456", PEAKCUT_AI_BASE_URL="")
sys.path.insert(0, ".")
from studio import ai, auth, brain, config, ctx, db, usage  # noqa: E402

db.init()
fails = []


def check(name, ok, extra=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  {extra}" if extra and not ok else ""))
    ok or fails.append(name)


class Reply:
    def __init__(self, status, data):
        self.status_code, self._data, self.text = status, data, json.dumps(data)

    def json(self):
        return self._data


CLIP = {"start": 1, "end": 20, "score": 80, "hook": "WOW", "title": "t", "description": "d", "hashtags": ["a"], "reason": "r"}
seen = []


def fake_post(url, json=None, headers=None, timeout=None, **_k):  # noqa: A002
    seen.append((url, json, headers or {}))
    if url.endswith(":generateContent"):
        return Reply(200, {"candidates": [{"content": {"parts": [{"text": globals()["json_text"]([CLIP])}]}}],
                           "usageMetadata": {"promptTokenCount": 100, "totalTokenCount": 130}})
    if url.endswith("/chat/completions"):
        if "temperature" in json:                      # a model that refuses an extra setting: asked again without it
            return Reply(400, {"error": {"message": "temperature is not supported"}})
        return Reply(200, {"choices": [{"message": {"content": "```json\n" + globals()["json_text"]({"items": [CLIP]}) + "\n```"}}],
                           "usage": {"prompt_tokens": 90, "completion_tokens": 20}})
    if url.endswith("/responses"):
        return Reply(200, {"output": [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": globals()["json_text"]({"items": [CLIP]})}]}],
                           "usage": {"input_tokens": 90, "output_tokens": 20}})
    if url.endswith("/messages"):
        return Reply(200, {"content": [{"type": "text", "text": "Here you go: " + globals()["json_text"]({"items": [CLIP]})}],
                           "usage": {"input_tokens": 70, "output_tokens": 10}})
    return Reply(404, {})


def json_text(x):
    return json.dumps(x)


ai.httpx.post = fake_post


def use(provider, base=""):
    config.AI_PROVIDER, config.AI_BASE_URL = provider, base
    seen.clear()


use("gemini")
out, sent, wrote = ai.call("model-a", "hello", brain.SCHEMA)
check("gemini: answer and tokens", out == [CLIP] and (sent, wrote) == (100, 30), str((out, sent, wrote)))
check("gemini: key in the header, schema passed as is", seen[0][2].get("x-goog-api-key") == "test-key-123456"
      and seen[0][1]["generationConfig"]["responseSchema"] is brain.SCHEMA and seen[0][0].endswith("/model-a:generateContent"))

for name, host in (("openai", "api.openai.com"), ("xai", "api.x.ai"), ("grok", "api.x.ai"), ("groq", "api.groq.com"), ("openrouter", "openrouter.ai")):
    use(name)
    out, sent, wrote = ai.call("model-a", "hello", brain.SCHEMA)
    check(f"{name}: answer unwrapped from a code fence, tokens read", out == [CLIP] and (sent, wrote) == (90, 20), str((out, sent, wrote)))
    check(f"{name}: right address, key as a bearer token", host in seen[0][0] and seen[0][2].get("Authorization") == "Bearer test-key-123456")
check("a refused extra setting is dropped and asked again", len(seen) == 2 and "temperature" not in seen[1][1])
check("the schema is told in the prompt for chat models", '"type": "array"' in seen[1][1]["messages"][0]["content"])

use("anthropic")
out, sent, wrote = ai.call("model-a", "hello", brain.SCHEMA)
check("anthropic: answer found inside a sentence, tokens read", out == [CLIP] and (sent, wrote) == (70, 10), str((out, sent, wrote)))
check("anthropic: key and version headers", seen[0][2].get("x-api-key") == "test-key-123456" and "anthropic-version" in seen[0][2])

use("agentrouter")
out, sent, wrote = ai.call("gpt-6.1-sol", "hello", brain.SCHEMA)
check("agentrouter: uses agentrouter gateway and bearer auth", "agentrouter.org" in seen[0][0] and seen[0][2].get("Authorization") == "Bearer test-key-123456" and out == [CLIP])

use("agentrouter", "https://agentrouter.org")
out, _s, _w = ai.call("gpt-6.1-sol", "hello", brain.SCHEMA)
check("agentrouter: base URL normalized with /v1", seen[0][0].startswith("https://agentrouter.org/v1") and out == [CLIP])
ar_models = ai.list_models("agentrouter")
check("agentrouter: active models returned even on unauthenticated/error", "gpt-6.1-sol" in ar_models and "gpt-6-astra" in ar_models and "gpt-5.6-sol" in ar_models)

use("custom", "http://127.0.0.1:1234/v1")
out, _s, _w = ai.call("model-a", "hello", brain.SCHEMA)
check("custom: uses the address from settings", seen[0][0] == "http://127.0.0.1:1234/v1/chat/completions" and out == [CLIP])

use("custom")
check("custom without an address is not ready", not ai.ready())
use("nonsense")
check("an unknown provider is not ready", not ai.ready())
use("ollama")
os.environ["PEAKCUT_AI_KEY"] = ""
config._kept.clear()
check("ollama needs no key", ai.ready() and ai.label().startswith("Ollama"))
out, _s, _w = ai.call("model-a", "hello", brain.SCHEMA)
check("ollama: no key header is sent", "Authorization" not in seen[0][2] and out == [CLIP])
use("gemini")
check("gemini without a key is not ready", not ai.ready())
os.environ["PEAKCUT_AI_KEY"] = "test-key-123456"
config._kept.clear()

# ---- the whole path: a call is made for a user and shows up in their usage, and only theirs
u1, _ = auth._create("ai-one@example.com", "One", password_hash="x")
u2, _ = auth._create("ai-two@example.com", "Two", password_hash="x")
words = [{"w": f"word{i}", "s": i * 0.5, "e": i * 0.5 + 0.4} for i in range(120)]
with ctx.as_user(u1.id):
    usage.set_context(None, "A test video")
    import numpy as np
    clips, info = brain.find_clips(words, np.zeros(60), 60.0, title="T", uploader="U")
    check("clips come back through the whole path", len(clips) == 1 and clips[0]["hook"] == "WOW" and info["model"] == "model-a", str((clips, info)))
    s = usage.summary({})
    check("the call is in this user's usage", s["calls_total"] == 1 and s["tokens_total"] == 130 and s["recent"][0]["where"] == "A test video", str(s))
    check("usage says which AI is set", s["ready"] and s["provider"] == "Gemini" and s["model"] == "model-a")
with ctx.as_user(u2.id):
    check("another user sees none of it", usage.summary({})["calls_total"] == 0)

# ---- fallback chain: Provider 1 fails with 429, switches to Provider 2 automatically
orig_post = ai.httpx.post
orig_sleep = brain.time.sleep
brain.time.sleep = lambda _: None

def fallback_post(url, json=None, headers=None, **k):
    if "generateContent" in url:
        return Reply(429, {"error": {"message": "Resource exhausted"}})
    return orig_post(url, json=json, headers=headers, **k)

ai.httpx.post = fallback_post
ai.save_chain([
    {"provider": "gemini", "models": ["gemini-2.5-flash"], "key": "key1"},
    {"provider": "openai", "models": ["gpt-4o-mini"], "key": "key2"}
])
fallback_out, fallback_model, _tokens = brain.ask_ai("hello", brain.SCHEMA)
check("fallback chain: switches to secondary provider when primary fails", fallback_out == [CLIP] and fallback_model == "gpt-4o-mini")

# ---- removing old AI and promoting new provider to primary
ai.save_chain([
    {"provider": "openai", "models": ["gpt-4o-mini"], "key": "key2"}
])
ch = ai.chain()
check("removing old AI provider: secondary becomes primary", len(ch) == 1 and ch[0]["provider"] == "openai")

# ---- clear saved key
ai.save_chain([
    {"provider": "openai", "models": ["gpt-4o-mini"], "clear_key": True, "key": "new-key-789"}
])
ch = ai.chain()
check("updating key with new key", ch[0]["key"] == "new-key-789")

# ---- duplicate provider removal by ID
ai.save_chain([
    {"id": "c1", "provider": "agentrouter", "models": ["gpt-6-astra"], "key": "key-ar-1"},
    {"id": "c2", "provider": "agentrouter", "models": ["gpt-6.1-sol"], "key": "key-ar-2"},
])
ch = ai.chain()
check("two cards of same provider saved with separate keys", len(ch) == 2 and ch[0]["key"] == "key-ar-1" and ch[1]["key"] == "key-ar-2")

# Remove first card, keep second card without re-entering key
ai.save_chain([
    {"id": "c2", "provider": "agentrouter", "models": ["gpt-6.1-sol"]}
])
ch = ai.chain()
check("removing card 1 preserves card 2 key by ID", len(ch) == 1 and ch[0]["id"] == "c2" and ch[0]["key"] == "key-ar-2")

# ---- clear all AI
ai.clear()
check("clear all AI empties chain", len(ai.chain()) == 0)
check("test_all on empty chain returns safe error dict", ai.test_all()["ok"] is False)

ai.httpx.post = orig_post
brain.time.sleep = orig_sleep
ai.save("gemini", ["model-a", "model-b"], "", "test-key-123456")

print("ALL PASSED" if not fails else f"{len(fails)} failed")
import shutil  # noqa: E402
db.engine.dispose()
shutil.rmtree(os.environ["PEAKCUT_DATA"], ignore_errors=True)
sys.exit(1 if fails else 0)
