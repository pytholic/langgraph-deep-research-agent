"""Model providers, enums, and factory for chat model instantiation.

Created by @pytholic on 2026.05.03
"""

from enum import StrEnum
from typing import Protocol

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from langchain_ollama import ChatOllama


class Provider(StrEnum):
    """Supported LLM provider identifiers."""

    OLLAMA = "ollama"
    OPENAI = "openai"


class OllamaModel(StrEnum):
    """Available Ollama model identifiers."""

    GEMMA4_E2B = "gemma4:e2b"
    PHI4_MINI = "phi4-mini:3.8b"


class OpenAIModel(StrEnum):
    """Available OpenAI model identifiers."""

    GPT5_NANO = "gpt-5-nano"
    GPT4O_MINI = "gpt-4o-mini"
    GPT5_1 = "gpt-5.1"


# Mapping of provider → available model names. Single source of truth for the UI.
MODELS_BY_PROVIDER: dict[str, list[str]] = {
    Provider.OLLAMA: [m.value for m in OllamaModel],
    Provider.OPENAI: [m.value for m in OpenAIModel],
}


class _ModelFactory(Protocol):
    """Strategy interface for provider-specific model instantiation."""

    def create(self, model_name: str) -> BaseChatModel:
        """Instantiate a chat model by name.

        Args:
            model_name: Provider-specific model identifier.

        Returns:
            Configured ``BaseChatModel`` instance.
        """
        ...


class _OllamaFactory:
    """Creates Ollama models with local inference settings."""

    def create(self, model_name: str) -> BaseChatModel:
        """Instantiate a ChatOllama model with context window and keep_alive=0.

        Args:
            model_name: Ollama model tag (e.g. ``"gemma4:e2b"``).

        Returns:
            Configured ``ChatOllama`` instance.
        """
        return ChatOllama(model=model_name, temperature=0.0, num_ctx=65536, keep_alive=0)


class _OpenAIFactory:
    """Creates OpenAI models via LangChain's init_chat_model."""

    def create(self, model_name: str) -> BaseChatModel:
        """Instantiate an OpenAI model via ``init_chat_model``.

        Args:
            model_name: OpenAI model identifier (e.g. ``"gpt-5-nano"``).

        Returns:
            Configured chat model instance.
        """
        return init_chat_model(model=model_name, temperature=0.0)


_FACTORIES: dict[str, _ModelFactory] = {
    Provider.OLLAMA: _OllamaFactory(),
    Provider.OPENAI: _OpenAIFactory(),
}


def create_model(provider: str, model_name: str) -> BaseChatModel:
    """Instantiate a chat model for the given provider and model name.

    Args:
        provider: LLM provider — one of the ``Provider`` enum values.
        model_name: Model identifier string for that provider.

    Returns:
        Configured ``BaseChatModel`` instance ready for inference.

    Raises:
        ValueError: If ``provider`` is not a recognised provider key.
    """
    factory = _FACTORIES.get(provider)
    if factory is None:
        raise ValueError(f"Unknown provider {provider!r}. Choose from: {list(_FACTORIES)}")
    return factory.create(model_name)
