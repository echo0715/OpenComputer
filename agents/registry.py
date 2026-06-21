"""
Model registry — maps friendly model names to agent classes + defaults.
"""

from typing import Dict, List, Optional, Tuple, Type

from .base import BaseAgent


def _qwen_inferred_defaults(model: str) -> dict:
    """
    Infer sensible defaults for Qwen model IDs that are not explicitly registered.

    Hugging Face-style Qwen3.5 IDs are typically served behind an OpenAI-compatible
    endpoint rather than DashScope-native APIs, so default them to `api_backend=openai`.
    """
    model_lower = model.lower()
    if "qwen3.5" in model_lower or "qwen35" in model_lower:
        return {
            "api_backend": "openai",
            "temperature": 0.0,
            "top_p": 0.9,
            "max_tokens": 32768,
            "history_n": 100,
        }
    return {}

# ── Model registry ──────────────────────────────────────────────────────
# Each entry: model_alias -> (agent_class_path, default_kwargs)
# agent_class_path is lazy-imported to avoid pulling in all SDKs at once.

_REGISTRY: Dict[str, dict] = {
    # ── Claude ──────────────────────────────────────────────────────────
    "claude-sonnet-4-5": {
        "cls": "agents.claude_agent.ClaudeAgent",
        "defaults": {"model": "claude-sonnet-4-5-20250929"},
    },
    "claude-sonnet-4": {
        "cls": "agents.claude_agent.ClaudeAgent",
        "defaults": {"model": "claude-sonnet-4-20250514"},
    },
    "claude-opus-4": {
        "cls": "agents.claude_agent.ClaudeAgent",
        "defaults": {"model": "claude-opus-4-20250514"},
    },
    "claude-opus-4-1": {
        "cls": "agents.claude_agent.ClaudeAgent",
        "defaults": {"model": "claude-opus-4-1-20250805"},
    },
    "claude-opus-4-5": {
        "cls": "agents.claude_agent.ClaudeAgent",
        "defaults": {"model": "claude-opus-4-5"},
    },
    "claude-opus-4-6": {
        "cls": "agents.claude_agent.ClaudeAgent",
        "defaults": {"model": "claude-opus-4-6"},
    },
    "claude-sonnet-4-6": {
        "cls": "agents.claude_agent.ClaudeAgent",
        "defaults": {"model": "claude-sonnet-4-6"},
    },
    "claude-3-7-sonnet": {
        "cls": "agents.claude_agent.ClaudeAgent",
        "defaults": {"model": "claude-3-7-sonnet-20250219"},
    },
    # ── Kimi ────────────────────────────────────────────────────────────
    "kimi-k2.5": {
        "cls": "agents.kimi_agent.KimiAgent",
        "defaults": {"model": "kimi-k2.5", "temperature": 1.0, "top_p": 0.95},
    },
    "kimi-k2.6": {
        "cls": "agents.kimi_agent.KimiAgent",
        "defaults": {"model": "kimi-k2.6", "temperature": 1.0, "top_p": 0.95},
    },
    # ── Qwen ────────────────────────────────────────────────────────────
    "qwen3-vl": {
        "cls": "agents.qwen_agent.QwenAgent",
        "defaults": {
            "model": "qwen3-vl",
            "api_backend": "dashscope",
            "temperature": 0.0,
            "top_p": 0.9,
            "max_tokens": 32768,
        },
    },
    "qwen2.5-vl-72b": {
        "cls": "agents.qwen_agent.QwenAgent",
        "defaults": {
            "model": "qwen2.5-vl-72b-instruct",
            "api_backend": "dashscope",
            "temperature": 0.5,
            "top_p": 0.9,
            "max_tokens": 1500,
        },
    },
    "qwen3.5-35b-a3b": {
        "cls": "agents.qwen_agent.QwenAgent",
        "defaults": {
            "model": "Qwen/Qwen3.5-35B-A3B",
            "api_backend": "openai",
            "temperature": 0.0,
            "top_p": 0.9,
            "max_tokens": 32768,
            "history_n": 100,
        },
    },
    "qwen3.5-27b": {
        "cls": "agents.qwen_agent.QwenAgent",
        "defaults": {
            "model": "Qwen/Qwen3.5-27B",
            "api_backend": "openai",
            "temperature": 0.0,
            "top_p": 0.9,
            "max_tokens": 32768,
            "history_n": 100,
        },
    },
    "qwen3.5-4b": {
        "cls": "agents.qwen_agent.QwenAgent",
        "defaults": {
            "model": "Qwen/Qwen3.5-4B",
            "api_backend": "openai",
            "temperature": 0.0,
            "top_p": 0.9,
            "max_tokens": 32768,
            "history_n": 100,
        },
    },
    "qwen3.5-9b": {
        "cls": "agents.qwen_agent.QwenAgent",
        "defaults": {
            "model": "Qwen/Qwen3.5-9B",
            "api_backend": "openai",
            "temperature": 0.0,
            "top_p": 0.9,
            "max_tokens": 32768,
            "history_n": 100,
        },
    },
    "Qwen/Qwen3.5-35B-A3B": {
        "cls": "agents.qwen_agent.QwenAgent",
        "defaults": {
            "model": "Qwen/Qwen3.5-35B-A3B",
            "api_backend": "openai",
            "temperature": 0.0,
            "top_p": 0.9,
            "max_tokens": 32768,
            "history_n": 100,
        },
    },
    "Qwen/Qwen3.5-27B": {
        "cls": "agents.qwen_agent.QwenAgent",
        "defaults": {
            "model": "Qwen/Qwen3.5-27B",
            "api_backend": "openai",
            "temperature": 0.0,
            "top_p": 0.9,
            "max_tokens": 32768,
            "history_n": 100,
        },
    },
    "Qwen/Qwen3.5-4B": {
        "cls": "agents.qwen_agent.QwenAgent",
        "defaults": {
            "model": "Qwen/Qwen3.5-4B",
            "api_backend": "openai",
            "temperature": 0.0,
            "top_p": 0.9,
            "max_tokens": 32768,
            "history_n": 100,
        },
    },
    "Qwen/Qwen3.5-9B": {
        "cls": "agents.qwen_agent.QwenAgent",
        "defaults": {
            "model": "Qwen/Qwen3.5-9B",
            "api_backend": "openai",
            "temperature": 0.0,
            "top_p": 0.9,
            "max_tokens": 32768,
            "history_n": 100,
        },
    },

    # ── EvoCUA ──────────────────────────────────────────────────────────
    "evocua-s1": {
        "cls": "agents.evocua_agent.EvoCUAAgent",
        "defaults": {"model": "EvoCUA-S1", "prompt_style": "S1", "temperature": 0.0},
    },
    "evocua-s2": {
        "cls": "agents.evocua_agent.EvoCUAAgent",
        "defaults": {"model": "EvoCUA-S2", "prompt_style": "S2", "temperature": 0.0},
    },
    # ── Mano ────────────────────────────────────────────────────────────
    "mano": {
        "cls": "agents.mano_agent.ManoAgent",
        "defaults": {"model": "mano", "temperature": 0.0},
    },
    # ── OpenCUA ─────────────────────────────────────────────────────────
    "opencua": {
        "cls": "agents.opencua_agent.OpenCUAAgent",
        "defaults": {"model": "opencua", "temperature": 0.0},
    },
    # ── Dart ────────────────────────────────────────────────────────────
    "dart": {
        "cls": "agents.dart_agent.DartAgent",
        "defaults": {"model": "dart", "temperature": 0.0},
    },
    # ── Holo-3.1 (Hcompany) ─────────────────────────────────────────────
    "holo-3.1": {
        "cls": "agents.holo3_agent.Holo3Agent",
        "defaults": {
            "model": "holo-3.1",
            "temperature": 0.8,
            "max_tokens": 4096,
            "history_n": 2,
        },
    },
    "Hcompany/Holo-3.1-35B-A3B": {
        "cls": "agents.holo3_agent.Holo3Agent",
        "defaults": {
            "model": "holo-3.1",
            "temperature": 0.8,
            "max_tokens": 4096,
            "history_n": 2,
        },
    },
    # ── GUI-Owl 1.5 ─────────────────────────────────────────────────────
    "owl1.5": {
        "cls": "agents.owl15_agent.Owl15Agent",
        "defaults": {
            "model": "gui-owl-1.5",
            "api_backend": "openai",
            "temperature": 0.0,
            "top_p": 0.9,
            "max_tokens": 4096,
            "history_n": 5,
        },
    },
    "gui-owl-1.5": {
        "cls": "agents.owl15_agent.Owl15Agent",
        "defaults": {
            "model": "gui-owl-1.5",
            "api_backend": "openai",
            "temperature": 0.0,
            "top_p": 0.9,
            "max_tokens": 4096,
            "history_n": 5,
        },
    },
    # ── ChatGPT (OpenAI computer-use) ───────────────────────────────────
    "chatgpt": {
        "cls": "agents.chatgpt_agent.ChatGPTAgent",
        "defaults": {"model": "gpt-5.4", "environment": "linux"},
    },
    "gpt-5.4": {
        "cls": "agents.chatgpt_agent.ChatGPTAgent",
        "defaults": {"model": "gpt-5.4", "environment": "linux"},
    },
    "gpt-5": {
        "cls": "agents.chatgpt_agent.ChatGPTAgent",
        "defaults": {"model": "gpt-5", "environment": "linux"},
    },
    "computer-use-preview": {
        "cls": "agents.chatgpt_agent.ChatGPTAgent",
        "defaults": {
            "model": "computer-use-preview",
            "environment": "linux",
            "truncation": "auto",
        },
    },
    # ── Gemini (Google AI Studio) ───────────────────────────────────────
    "gemini-3-flash": {
        "cls": "agents.gemini_agent.GeminiAgent",
        "defaults": {"model": "gemini-3-flash-preview"},
    },
    "gemini-3-flash-preview": {
        "cls": "agents.gemini_agent.GeminiAgent",
        "defaults": {"model": "gemini-3-flash-preview"},
    },
    "gemini-2.5-computer-use": {
        "cls": "agents.gemini_agent.GeminiAgent",
        "defaults": {"model": "gemini-2.5-computer-use-preview-10-2025"},
    },
    # ── Azure-hosted ChatGPT deployments ────────────────────────────────
    # `model` here is the *deployment name* on the Azure resource. For the
    # computer tool the deployment must be a computer-use-capable model
    # (computer-use-preview or gpt-5.4); chat-only deployments such as
    # gpt-5.3-chat will reject the tool.
    "azure-chatgpt": {
        "cls": "agents.chatgpt_agent.ChatGPTAgent",
        "defaults": {
            "model": "computer-use-preview",
            "api_backend": "azure",
            "environment": "linux",
        },
    },
    "azure-gpt-5.4": {
        "cls": "agents.chatgpt_agent.ChatGPTAgent",
        "defaults": {
            "model": "gpt-5.4",
            "api_backend": "azure",
            "environment": "linux",
        },
    },
    "azure-computer-use-preview": {
        "cls": "agents.chatgpt_agent.ChatGPTAgent",
        "defaults": {
            "model": "computer-use-preview",
            "api_backend": "azure",
            "environment": "linux",
        },
    },
    "azure-gpt-5.3-chat": {
        "cls": "agents.chatgpt_agent.ChatGPTAgent",
        "defaults": {
            "model": "gpt-5.3-chat",
            "api_backend": "azure",
            "environment": "linux",
        },
    },
}


def _import_class(dotted_path: str) -> Type[BaseAgent]:
    """Import a class from a dotted path like 'agents.claude_agent.ClaudeAgent'."""
    import importlib

    module_path, class_name = dotted_path.rsplit(".", 1)
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


def create_agent(model: str, **kwargs) -> BaseAgent:
    """
    Create an agent by model name.

    Args:
        model: A model alias (e.g. "claude-sonnet-4-5", "kimi-k2.5", "qwen3-vl",
               "evocua-s1", "mano", "opencua", "dart")
               or any full model ID supported by an agent class.
        **kwargs: Override any default parameter.

    Returns:
        An initialized agent ready for predict() calls.

    Example:
        agent = create_agent("claude-sonnet-4-5", platform="ubuntu")
        agent.reset()
        reasoning, actions = agent.predict("Open Firefox", {"screenshot": img_bytes})
    """
    if model in _REGISTRY:
        entry = _REGISTRY[model]
        cls = _import_class(entry["cls"])
        merged = {**entry["defaults"], **kwargs}
        return cls(**merged)

    # If not in registry, try to infer the agent family from the name
    model_lower = model.lower()
    if "claude" in model_lower:
        cls = _import_class("agents.claude_agent.ClaudeAgent")
        return cls(model=model, **kwargs)
    elif "kimi" in model_lower:
        cls = _import_class("agents.kimi_agent.KimiAgent")
        return cls(model=model, **kwargs)
    elif "qwen" in model_lower:
        cls = _import_class("agents.qwen_agent.QwenAgent")
        inferred = _qwen_inferred_defaults(model)
        merged = {**inferred, **kwargs}
        return cls(model=model, **merged)
    elif "evocua" in model_lower:
        cls = _import_class("agents.evocua_agent.EvoCUAAgent")
        return cls(model=model, **kwargs)
    elif "mano" in model_lower:
        cls = _import_class("agents.mano_agent.ManoAgent")
        return cls(model=model, **kwargs)
    elif "opencua" in model_lower:
        cls = _import_class("agents.opencua_agent.OpenCUAAgent")
        return cls(model=model, **kwargs)
    elif "dart" in model_lower:
        cls = _import_class("agents.dart_agent.DartAgent")
        return cls(model=model, **kwargs)
    elif "holo" in model_lower:
        cls = _import_class("agents.holo3_agent.Holo3Agent")
        return cls(model=model, **kwargs)
    elif "owl" in model_lower:
        cls = _import_class("agents.owl15_agent.Owl15Agent")
        return cls(model=model, **kwargs)
    elif "gemini" in model_lower:
        cls = _import_class("agents.gemini_agent.GeminiAgent")
        return cls(model=model, **kwargs)
    elif model_lower.startswith("azure-") or model_lower.startswith("azure/"):
        bare = model.split("-", 1)[1] if model_lower.startswith("azure-") else model.split("/", 1)[1]
        cls = _import_class("agents.chatgpt_agent.ChatGPTAgent")
        merged = {"api_backend": "azure", **kwargs}
        return cls(model=bare, **merged)
    elif (
        "chatgpt" in model_lower
        or model_lower.startswith("gpt-")
        or "computer-use-preview" in model_lower
    ):
        cls = _import_class("agents.chatgpt_agent.ChatGPTAgent")
        return cls(model=model, **kwargs)

    raise ValueError(
        f"Unknown model '{model}'. Available: {list(_REGISTRY.keys())}. "
        f"Or use a full model ID containing one of: claude, kimi, qwen, evocua, mano, opencua, dart, owl, gemini, chatgpt/gpt-."
    )


def list_models() -> List[str]:
    """Return all registered model aliases."""
    return sorted(_REGISTRY.keys())
