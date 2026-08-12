# backend/app/core/ai_models.py

from __future__ import annotations

from collections.abc import Mapping

from app.core.providers import AIProvider

# Models this application is allowed to run, grouped by the provider whose
# client serves them. AI_MODEL picks one and Settings derives AI_PROVIDER from
# it, so a model must appear under exactly one provider.
AI_PROVIDER_MODELS: Mapping[AIProvider, tuple[str, ...]] = {
    AIProvider.ANTHROPIC: (
        "claude-opus-5",
        "claude-sonnet-5",
        "claude-sonnet-4-6",
        "claude-haiku-4-5",
    ),
    AIProvider.OPENAI: ("gpt-5.6-terra",),
    AIProvider.GEMINI: ("gemini-3.5-flash",),
}


__all__ = ["AI_PROVIDER_MODELS"]
