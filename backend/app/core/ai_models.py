from __future__ import annotations

from collections.abc import Mapping

from app.core.providers import AIProvider

# Models this application is allowed to run, grouped by the provider whose
# client serves them. AI_MODEL picks one and AISettings derives its PROVIDER
# from it, so a model must appear under exactly one provider.
#
# Each provider offers the same three tiers, marked below: the default is the
# balanced choice AI_MODEL falls back to, cheap trades accuracy for cost on
# high-volume extraction, and premium is for documents the default misreads.
# The tiers are a naming convention, not a structure — nothing selects a model
# by tier, so this stays a flat list of what is allowed to run.
AI_PROVIDER_MODELS: Mapping[AIProvider, tuple[str, ...]] = {
    AIProvider.ANTHROPIC: (
        "claude-sonnet-5",  # default
        "claude-haiku-4-5",  # cheap
        "claude-opus-5",  # premium
    ),
    AIProvider.OPENAI: (
        "gpt-5.6-terra",  # default
        "gpt-5.6-luna",  # cheap
        "gpt-5.6-sol",  # premium
    ),
    AIProvider.GEMINI: (
        "gemini-3.6-flash",  # default
        "gemini-3.5-flash-lite",  # cheap
        "gemini-3-pro",  # premium
    ),
}


__all__ = ["AI_PROVIDER_MODELS"]
