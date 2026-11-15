"""Talking to the AI service. You bring your own key, and choose the service and model in the dashboard
(Settings, AI) or in .env. What is saved from the dashboard is kept in ai.json in the data folder and wins.

    CLIPSX_AI_PROVIDER    gemini | openai | agentrouter | xai | groq | openrouter | anthropic | ollama | custom
    CLIPSX_AI_MODELS      one or more model ids, comma separated, tried in this order
    CLIPSX_AI_KEY         your key (or CLIPSX_AI_KEY_FILE, a file holding it)
    CLIPSX_AI_BASE_URL    only for "custom" (any service that speaks the OpenAI chat format), or to override

Supports multiple providers in an automatic fallback chain (e.g. Gemini -> OpenAI -> AgentRouter). If the
first provider fails or runs out of quota, Clips X switches to the next configured provider seamlessly.
"""
import json
import os
import re
import threading

import httpx

from . import config

AGENTROUTER_MODELS = ["gpt-6.1-sol", "gpt-6-astra", "gpt-5.6-sol"]

# name -> (label shown on the pages, address, how it is spoken to, where to get a key, an example model id)
PROVIDERS = {
    "gemini": ("Gemini", "https://generativelanguage.googleapis.com/v1beta/models", "gemini", "https://aistudio.google.com/apikey", "gemini-2.5-flash"),
    "openai": ("OpenAI", "https://api.openai.com/v1", "openai", "https://platform.openai.com/api-keys", "gpt-4o-mini"),
    "xai": ("Grok", "https://api.x.ai/v1", "openai", "https://console.x.ai", "grok-4"),
    "agentrouter": ("AgentRouter", "https://agentrouter.org/v1", "openai", "https://agentrouter.org", "gpt-6.1-sol"),
    "groq": ("Groq", "https://api.groq.com/openai/v1", "openai", "https://console.groq.com/keys", "llama-3.3-70b-versatile"),
    "openrouter": ("OpenRouter", "https://openrouter.ai/api/v1", "openai", "https://openrouter.ai/keys", "google/gemini-2.5-flash"),
    "anthropic": ("Claude", "https://api.anthropic.com/v1", "anthropic", "https://console.anthropic.com", ""),
    "ollama": ("Ollama (on this machine)", "http://127.0.0.1:11434/v1", "openai", "https://ollama.com", "llama3.1"),
    "custom": ("Custom (OpenAI-compatible)", "", "openai", "", ""),
}
ALIASES = {
    "google": "gemini",
    "grok": "xai",
    "claude": "anthropic",
    "local": "ollama",
    "agent_router": "agentrouter",
    "gamani": "gemini",
    "gamani senone": "gemini",
    "gemini senone": "gemini",
}
NO_KEY = {"ollama", "custom"}       # a model running on your own machine needs no key

# ---------------------------------------------------------------- the settings in use
_lock = threading.Lock()
_saved = {"at": None, "data": {}}


def _file():
    return config.DATA_DIR / "ai.json"


def _from_dashboard() -> dict:
    """What was saved from the dashboard, read again only when the file changes."""
    f = _file()
    try:
        at = f.stat().st_mtime_ns
    except OSError:
        at = 0
    if _saved["at"] != at:
        try:
            data = json.loads(f.read_text(encoding="utf-8")) if at else {}
        except (OSError, ValueError):
            data = {}
        _saved.update(at=at, data=data if isinstance(data, dict) else {})
    return _saved["data"]


def _clean_base(provider_id: str, address: str) -> str:
    p = ALIASES.get(str(provider_id or "").strip().lower(), str(provider_id or "").strip().lower())
    b = str(address or "").strip().rstrip("/")
    if not b and p in PROVIDERS:
        b = PROVIDERS[p][1]
    if "agentrouter.org" in b and not b.endswith("/v1"):
        b = f"{b}/v1"
    return b


def _normalize_item(item: dict, idx: int = 0) -> dict:
    p = str(item.get("provider") or "").strip().lower()
    p = ALIASES.get(p, p)
    raw_models = item.get("models") or []
    if isinstance(raw_models, str):
        raw_models = [m.strip() for m in raw_models.split(",") if m.strip()]
    ms = [str(m).strip()[:120] for m in (raw_models or []) if str(m).strip()]
    b = _clean_base(p, item.get("base_url") or "")
    k = str(item.get("key") or "").strip()
    is_ready = bool(p in PROVIDERS and ms and b and (k or p in NO_KEY))
    lbl = PROVIDERS.get(p, ("",))[0] or p.title()
    item_id = str(item.get("id") or "").strip() or f"card_{idx}_{p}"
    return {
        "id": item_id,
        "provider": p,
        "label": lbl,
        "models": ms,
        "base_url": b,
        "key": k,
        "ready": is_ready,
    }


def chain() -> list:
    """Ordered list of configured AI providers for fallback."""
    d = _from_dashboard()
    items = []
    if "chain" in d and isinstance(d["chain"], list):
        for idx, it in enumerate(d["chain"]):
            if isinstance(it, dict) and it.get("provider"):
                items.append(_normalize_item(it, idx))
        return items
    elif d.get("provider"):
        items.append(_normalize_item(d, 0))
        return items
    elif d.get("cleared"):
        return []
    else:
        # Check env configs
        cfg_json = config.env("CLIPSX_AI_CONFIGS") or config.env("PEAKCUT_AI_CONFIGS")
        if cfg_json:
            try:
                parsed = json.loads(cfg_json)
                if isinstance(parsed, list):
                    for idx, it in enumerate(parsed):
                        if isinstance(it, dict) and it.get("provider"):
                            items.append(_normalize_item(it, idx))
            except Exception:
                pass
        if not items:
            # Check numbered env vars (1 to 9)
            for i in range(1, 10):
                p = config.env(f"CLIPSX_AI_PROVIDER_{i}") or config.env(f"PEAKCUT_AI_PROVIDER_{i}")
                if p:
                    ms = config.env(f"CLIPSX_AI_MODELS_{i}") or config.env(f"PEAKCUT_AI_MODELS_{i}") or ""
                    k = config.env(f"CLIPSX_AI_KEY_{i}") or config.env(f"PEAKCUT_AI_KEY_{i}") or ""
                    b = config.env(f"CLIPSX_AI_BASE_URL_{i}") or config.env(f"PEAKCUT_AI_BASE_URL_{i}") or ""
                    items.append(_normalize_item({"provider": p, "models": ms.split(","), "key": k, "base_url": b}, len(items)))
        if not items and (config.AI_PROVIDER or config.ai_key()):
            items.append(_normalize_item({
                "provider": config.AI_PROVIDER,
                "models": list(config.AI_MODELS),
                "key": config.ai_key(),
                "base_url": config.AI_BASE_URL,
            }, 0))
    return items


def current() -> dict:
    """Active/primary provider, models, address and key."""
    ch = chain()
    for c in ch:
        if c["ready"]:
            return c
    return ch[0] if ch else _normalize_item({})


def provider() -> str:
    return current()["provider"]


def models() -> list:
    return current()["models"]


def key() -> str:
    return current()["key"]


def label() -> str:
    return PROVIDERS.get(provider(), ("",))[0]


def base_url() -> str:
    return current()["base_url"] or PROVIDERS.get(current()["provider"], ("", ""))[1]


def ready() -> bool:
    return any(c["ready"] for c in chain())


def public() -> dict:
    """What the settings page may see."""
    c = current()
    ch = chain()
    d = _from_dashboard()
    return {
        "provider": c["provider"],
        "models": c["models"],
        "base_url": c["base_url"],
        "has_key": bool(c["key"]),
        "key_hint": c["key"][-4:] if len(c["key"]) >= 12 else "",
        "ready": ready(),
        "label": label(),
        "saved_here": bool(d.get("provider") or d.get("chain")),
        "providers": [
            {"id": k, "label": v[0], "address": v[1], "needs_key": k not in NO_KEY, "key_url": v[3], "example": v[4]}
            for k, v in PROVIDERS.items()
        ],
        "chain": [
            {
                "id": x["id"],
                "provider": x["provider"],
                "label": x["label"],
                "models": x["models"],
                "base_url": x["base_url"],
                "has_key": bool(x["key"]),
                "key_hint": x["key"][-4:] if len(x["key"]) >= 12 else "",
                "ready": x["ready"],
            }
            for x in ch
        ],
    }


def clear() -> dict:
    """Delete the saved AI settings completely."""
    with _lock:
        f = _file()
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps({"chain": [], "cleared": True}), encoding="utf-8")
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        tmp.replace(f)
        _saved["at"] = None
    return public()


def save_chain(chain_data: list) -> dict:
    """Save an ordered list of providers for fallback."""
    if not isinstance(chain_data, list):
        raise ValueError("AI chain must be a list.")
    if len(chain_data) == 0:
        return clear()
    existing_items = chain()
    existing_by_id = {c["id"]: c.get("key", "") for c in existing_items if c.get("id")}
    existing_by_provider = {c["provider"]: c.get("key", "") for c in existing_items}
    validated = []
    for idx, item in enumerate(chain_data):
        if not isinstance(item, dict):
            continue
        p = ALIASES.get(str(item.get("provider") or "").strip().lower(), str(item.get("provider") or "").strip().lower())
        if p not in PROVIDERS:
            raise ValueError(f"Provider #{idx + 1}: Choose one of the AI services in the list.")
        raw_models = item.get("models")
        if isinstance(raw_models, str):
            raw_models = raw_models.split(",")
        ms = [str(m).strip()[:120] for m in (raw_models or []) if str(m).strip()][:5]
        if not ms:
            raise ValueError(f"Provider #{idx + 1} ({p}): Enter the model to use.")
        if any(not re.fullmatch(r"[\w.\-:/@]+", m) for m in ms):
            raise ValueError(f"Provider #{idx + 1} ({p}): A model id has letters, digits and . - : / only.")
        b = _clean_base(p, item.get("base_url") or "")
        if b and not re.fullmatch(r"https?://[^\s]+", b):
            raise ValueError(f"Provider #{idx + 1} ({p}): The address has to start with http:// or https://")
        if p == "custom" and not b:
            raise ValueError("A custom service needs its address, for example http://127.0.0.1:1234/v1")
        item_id = str(item.get("id") or "").strip()
        new_k = item.get("key")
        if new_k is not None and str(new_k).strip():
            k = str(new_k).strip()[:400]
        elif item.get("clear_key") or item.get("remove_key"):
            k = ""
        else:
            if item_id and item_id in existing_by_id:
                k = existing_by_id[item_id]
            else:
                k = existing_by_provider.get(p, "")
        if not k and p not in NO_KEY:
            raise ValueError(f"Provider #{idx + 1} ({p}): Paste the key for this service.")
        card_id = item_id or f"card_{idx}_{p}"
        validated.append({"id": card_id, "provider": p, "models": ms, "base_url": b, "key": k})
    if not validated:
        return clear()
    primary = validated[0]
    with _lock:
        f = _file()
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps({
            "chain": validated,
            "provider": primary["provider"],
            "models": primary["models"],
            "base_url": primary["base_url"],
            "key": primary["key"],
        }), encoding="utf-8")
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        tmp.replace(f)
        _saved["at"] = None
    return public()


def save(provider_id: str, model_ids, address: str = "", new_key=None, chain_data=None) -> dict:
    """Save provider choices. Accepts either single provider parameters or full chain_data list."""
    if chain_data:
        return save_chain(chain_data)
    p = ALIASES.get(str(provider_id or "").strip().lower(), str(provider_id or "").strip().lower())
    if p not in PROVIDERS:
        raise ValueError("Choose one of the AI services in the list.")
    if isinstance(model_ids, str):
        model_ids = model_ids.split(",")
    ms = [str(m).strip()[:120] for m in (model_ids or []) if str(m).strip()][:5]
    if not ms:
        raise ValueError("Enter the model to use.")
    if any(not re.fullmatch(r"[\w.\-:/@]+", m) for m in ms):
        raise ValueError("A model id has letters, digits and . - : / only.")
    address = _clean_base(p, address)
    if address and not re.fullmatch(r"https?://[^\s]+", address):
        raise ValueError("The address has to start with http:// or https://")
    if p == "custom" and not address:
        raise ValueError("A custom service needs its address, for example http://127.0.0.1:1234/v1")
    old = current()
    k = old["key"] if new_key is None and old["provider"] == p else str(new_key or "").strip()[:400]
    if not k and p not in NO_KEY:
        raise ValueError("Paste the key for this service.")
    entry = {"provider": p, "models": ms, "base_url": address, "key": k}
    with _lock:
        f = _file()
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps({"chain": [entry], "provider": p, "models": ms, "base_url": address, "key": k}), encoding="utf-8")
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        tmp.replace(f)
        _saved["at"] = None
    return public()


def list_models(provider_id=None, address=None, with_key=None, item_id=None, idx=None) -> list:
    """The model ids a service offers, so the settings page can show a list to pick from."""
    ch = chain()
    matched_item = None
    if item_id:
        matched_item = next((c for c in ch if c.get("id") == item_id), None)
    if matched_item is None and idx is not None:
        try:
            i = int(idx)
            if 0 <= i < len(ch):
                matched_item = ch[i]
        except (ValueError, TypeError):
            pass
    c = matched_item if matched_item is not None else current()
    p = ALIASES.get(str(provider_id or c["provider"]).lower(), str(provider_id or c["provider"]).lower())
    if p not in PROVIDERS:
        raise ValueError("Choose one of the AI services in the list.")
    k = str(with_key or "").strip() or (c["key"] if c.get("provider") == p else "")
    base = _clean_base(p, address or (c.get("base_url") if c.get("provider") == p else "") or PROVIDERS[p][1])
    if not base:
        raise ValueError("Enter the service's address first.")
    how = PROVIDERS[p][2]
    if p == "agentrouter":
        found = list(AGENTROUTER_MODELS)
        ar_headers = {"User-Agent": "claude-cli/1.0.108 (external, cli)", "x-app": "cli"}
        if k:
            ar_headers["Authorization"] = f"Bearer {k}"
        try:
            r = httpx.get(f"{base}/models", headers=ar_headers, timeout=10)
            if r.status_code == 200:
                data = r.json()
                for m in data.get("data", []):
                    if isinstance(m, dict) and m.get("id"):
                        found.append(m["id"])
        except Exception:
            pass
        ordered = []
        for m in AGENTROUTER_MODELS:
            if m not in ordered:
                ordered.append(m)
        for m in sorted(set(found)):
            if m not in ordered:
                ordered.append(m)
        return ordered
    if how == "gemini":
        r = httpx.get(base, params={"pageSize": 200}, headers={"x-goog-api-key": k}, timeout=20)
    elif how == "anthropic":
        r = httpx.get(f"{base}/models", params={"limit": 200}, headers={"x-api-key": k, "anthropic-version": "2023-06-01"}, timeout=20)
    else:
        r = httpx.get(f"{base}/models", headers={"Authorization": f"Bearer {k}"} if k else {}, timeout=20)
    if r.status_code != 200:
        raise AIError(f"HTTP {r.status_code} {r.text[:200].replace(k or chr(0), '<key>')}")
    data = r.json()
    if how == "gemini":
        found = [m.get("name", "").split("/")[-1] for m in data.get("models", [])
                 if "generateContent" in (m.get("supportedGenerationMethods") or [])]
    else:
        found = [m.get("id", "") for m in data.get("data", []) if isinstance(m, dict)]
    return sorted({m for m in found if m})[:400]


def test(cfg=None) -> dict:
    """One tiny request with the settings in use, to prove the key, the address and the model all work."""
    c = cfg or current()
    ms = c.get("models") or []
    if not c or not c.get("ready") or not ms:
        raise ValueError(f"Save a valid service, model and key for {c.get('label') or 'the AI'} first.")
    out, sent, wrote = call(ms[0], 'Answer with a JSON array that holds the single string "ok".',
                            {"type": "ARRAY", "items": {"type": "STRING"}}, cfg=c)
    return {"ok": True, "provider": c.get("label"), "model": ms[0], "tokens": sent + wrote, "answer": str(out)[:80]}


def test_all() -> dict:
    """Test all configured services in the fallback chain."""
    results = []
    ch = chain()
    if not ch:
        return {"ok": False, "results": [], "error": "No AI services configured."}
    for c in ch:
        if not c["ready"]:
            results.append({"provider": c.get("label"), "ok": False, "error": "Not configured"})
            continue
        try:
            r = test(c)
            results.append({"provider": c.get("label"), "model": c["models"][0], "ok": True, "tokens": r["tokens"]})
        except Exception as e:
            results.append({"provider": c.get("label"), "model": (c.get("models") or [""])[0], "ok": False, "error": str(e)})
    return {"ok": any(r["ok"] for r in results), "results": results}


class AIError(RuntimeError):
    pass


problem = {"text": "", "at": 0.0}       # why the AI last failed, for the dashboard; cleared when it answers again


def explain(e) -> str:
    """What went wrong with an AI call, in words the owner can act on."""
    text, low = str(e), str(e).lower()
    name = (models() or ["?"])[0]
    lbl = label()
    if "404" in text or "not found" in low or "does not exist" in low or "unknown model" in low or "not_found" in low:
        return f"{lbl} doesn't know the model \"{name}\". Open Settings, AI, press Find models and pick one from the list."
    if "401" in text or "403" in text or "api key" in low or "api_key" in low or "unauthorized" in low or "permission" in low:
        return f"{lbl} refused the key. Paste a working key under Settings, AI."
    if "429" in text or "quota" in low or "rate limit" in low or "exhausted" in low:
        return f"{lbl} says the key has hit its limit or has no credit left. Check the account with {lbl}, or try again later."
    if "connect" in low or "timed out" in low or "timeout" in low or "getaddrinfo" in low or "refused" in low:
        return f"Clips X couldn't reach {lbl}. Check the internet connection" + (" and that Ollama is running." if provider() == "ollama" else ".")
    return ""


def note_problem(e):
    import time
    why = explain(e)
    if why:
        problem.update(text=why, at=time.time())


def clear_problem():
    problem.update(text="", at=0.0)


def _fail(r, model, auth_key=None):
    k = auth_key or key() or "\0"
    text = r.text[:300].replace(k, "<key>")
    raise AIError(f"HTTP {r.status_code} {text}")
    raise AIError(f"HTTP {r.status_code} {text}")


# ---------------------------------------------------------------- the schema, said in words for chat models
def _json_schema(s):
    """Gemini's schema spelling (ARRAY, OBJECT...) as ordinary JSON Schema."""
    if isinstance(s, dict):
        return {k: (v.lower() if k == "type" and isinstance(v, str) else _json_schema(v)) for k, v in s.items()}
    if isinstance(s, list):
        return [_json_schema(x) for x in s]
    return s


def _wrapped(prompt, schema):
    return (prompt + "\n\nAnswer with JSON only, no other text and no code fences: one object with a single key "
            "\"items\", whose value follows this JSON Schema:\n" + json.dumps(_json_schema(schema)))


def _parse(text):
    """The JSON in an answer, even if the model wrapped it in a code fence or a sentence."""
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        out = json.loads(text)
    except ValueError:
        m = re.search(r"[\[{].*[\]}]", text, re.S)
        if not m:
            raise AIError("The AI did not answer with JSON.")
        out = json.loads(m.group(0))
    if isinstance(out, dict) and "items" in out:
        out = out["items"]
    return out


# ---------------------------------------------------------------- one call
def call(model: str, prompt: str, schema: dict, cfg: dict = None):
    """Ask one model. Returns (the parsed JSON answer, tokens sent, tokens written back)."""
    c = cfg or current()
    p = c["provider"]
    if p == "agentrouter":
        return _agentrouter(model, prompt, schema, base=c.get("base_url"), auth_key=c.get("key"))
    how = PROVIDERS.get(p, ("", "", "openai"))[2]
    fn = {"gemini": _gemini, "openai": _openai, "anthropic": _anthropic}[how]
    return fn(model, prompt, schema, base=c.get("base_url"), auth_key=c.get("key"))


def _agentrouter(model, prompt, schema, base=None, auth_key=None):
    b = (base or base_url()).rstrip("/")
    if "agentrouter.org" in b and not b.endswith("/v1"):
        b = f"{b}/v1"
    k = auth_key if auth_key is not None else key()
    headers = {
        "Authorization": f"Bearer {k}" if k else "",
        "User-Agent": "claude-cli/1.0.108 (external, cli)",
        "x-app": "cli",
    }
    wrapped = _wrapped(prompt, schema)
    # AgentRouter models (gpt-6.1-sol, gpt-6-astra, gpt-5.6-sol) speak the OpenAI Responses API
    r = httpx.post(f"{b}/responses", json={"model": model, "input": wrapped}, headers=headers, timeout=180)
    if r.status_code == 200:
        data = r.json()
        text = ""
        for item in data.get("output", []):
            if isinstance(item, dict) and (item.get("type") == "message" or item.get("role") == "assistant"):
                for part in item.get("content", []):
                    if isinstance(part, dict) and part.get("text"):
                        text += part["text"]
                    elif isinstance(part, str):
                        text += part
        if not text:
            if isinstance(data.get("output"), str):
                text = data["output"]
            elif "choices" in data:
                text = data["choices"][0]["message"].get("content", "")
        u = data.get("usage") or {}
        return _parse(text), int(u.get("input_tokens") or 0), int(u.get("output_tokens") or 0)

    # Fallback to chat/completions if /responses is not supported
    if r.status_code in (400, 404, 405):
        body_chat = {"model": model, "messages": [{"role": "user", "content": wrapped}]}
        r_chat = httpx.post(f"{b}/chat/completions", json=body_chat, headers=headers, timeout=180)
        if r_chat.status_code == 200:
            data = r_chat.json()
            u = data.get("usage") or {}
            return _parse(data["choices"][0]["message"].get("content")), int(u.get("prompt_tokens") or 0), int(u.get("completion_tokens") or 0)
        _fail(r_chat if r.status_code in (404, 405) else r, model, k)

    _fail(r, model, k)


def _gemini(model, prompt, schema, base=None, auth_key=None):
    b = (base or base_url()).rstrip("/")
    k = auth_key if auth_key is not None else key()
    body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.4, "responseMimeType": "application/json", "responseSchema": schema}}
    r = httpx.post(f"{b}/{model}:generateContent", json=body, headers={"x-goog-api-key": k}, timeout=120)
    if r.status_code != 200:
        _fail(r, model, k)
    data = r.json()
    text = "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"])
    u = data.get("usageMetadata", {})
    sent = int(u.get("promptTokenCount") or 0)
    return json.loads(text), sent, max(0, int(u.get("totalTokenCount") or 0) - sent)


def _openai(model, prompt, schema, base=None, auth_key=None):
    b = (base or base_url()).rstrip("/")
    if "agentrouter.org" in b and not b.endswith("/v1"):
        b = f"{b}/v1"
    k = auth_key if auth_key is not None else key()
    headers = {"Authorization": f"Bearer {k}"} if k else {}
    body = {"model": model, "messages": [{"role": "user", "content": _wrapped(prompt, schema)}]}
    extras = [{"temperature": 0.4, "response_format": {"type": "json_object"}}, {"response_format": {"type": "json_object"}}, {}]
    r = None
    for extra in extras:
        r = httpx.post(f"{b}/chat/completions", json={**body, **extra}, headers=headers, timeout=180)
        if r.status_code not in (400, 422):
            break
    if r.status_code != 200:
        _fail(r, model, k)
    data = r.json()
    u = data.get("usage") or {}
    return _parse(data["choices"][0]["message"].get("content")), int(u.get("prompt_tokens") or 0), int(u.get("completion_tokens") or 0)


def _anthropic(model, prompt, schema, base=None, auth_key=None):
    b = (base or base_url()).rstrip("/")
    k = auth_key if auth_key is not None else key()
    body = {"model": model, "max_tokens": 8192, "messages": [{"role": "user", "content": _wrapped(prompt, schema)}]}
    r = httpx.post(f"{b}/messages", json=body, timeout=180,
                   headers={"x-api-key": k, "anthropic-version": "2023-06-01"})
    if r.status_code != 200:
        _fail(r, model, k)
    data = r.json()
    text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
    u = data.get("usage") or {}
    return _parse(text), int(u.get("input_tokens") or 0), int(u.get("output_tokens") or 0)
