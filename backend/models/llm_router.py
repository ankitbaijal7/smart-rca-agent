"""
LLM Router — hybrid local (Ollama) / cloud LLM with automatic fallback.
Abstracts the LLM backend so all agents are backend-agnostic.
"""
import logging
import os
from enum import Enum
from typing import Optional

import httpx
from anthropic import Anthropic
from langchain_anthropic import ChatAnthropic
from langchain_ollama import ChatOllama
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger(__name__)


class LLMMode(str, Enum):
    LOCAL  = "local"
    CLOUD  = "cloud"
    HYBRID = "hybrid"


class LLMRouter:
    """
    Routes LLM calls to Ollama (local) or cloud LLM based on config.
    In hybrid mode: tries local first, falls back to cloud on failure.
    """

    def __init__(self):
        self.mode          = LLMMode(os.getenv("LLM_MODE", "hybrid"))
        self.ollama_url    = os.getenv("OLLAMA_URL", "http://localhost:11434")
        self.ollama_model  = os.getenv("OLLAMA_MODEL", "deepseek-r1:8b")
        self.anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
        self.anthropic_model = os.getenv("CLOUD_LLM_MODEL", "")
        self._local_healthy: Optional[bool] = None

    # ── Health check ─────────────────────────────────────────────────────
    async def check_local_health(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get(f"{self.ollama_url}/api/tags")
                self._local_healthy = r.status_code == 200
        except Exception:
            self._local_healthy = False
        return self._local_healthy

    # ── LangChain model instances ─────────────────────────────────────────
    def get_local_model(self) -> ChatOllama:
        return ChatOllama(
            base_url=self.ollama_url,
            model=self.ollama_model,
            temperature=0.1,
        )

    def get_cloud_model(self) -> ChatAnthropic:
        return ChatAnthropic(
            api_key=self.anthropic_key,
            model=self.anthropic_model,
            temperature=0.1,
            max_tokens=2048,
        )

    async def get_model(self) -> BaseChatModel:
        """Return appropriate LangChain chat model based on mode and health."""
        if self.mode == LLMMode.LOCAL:
            return self.get_local_model()
        if self.mode == LLMMode.CLOUD:
            return self.get_cloud_model()
        # Hybrid: prefer local, fall back to cloud
        healthy = await self.check_local_health()
        if healthy:
            logger.info("LLM Router: using local Ollama (%s)", self.ollama_model)
            return self.get_local_model()
        logger.warning("LLM Router: Ollama unreachable, falling back to cloud LLM")
        return self.get_cloud_model()

    # ── Simple invoke (non-streaming) ────────────────────────────────────
    @staticmethod
    def _strip_thinking(text: str) -> str:
        """Strip <think>...</think> blocks emitted by reasoning models like deepseek-r1."""
        import re
        return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

    async def invoke(self, system_prompt: str, user_prompt: str) -> str:
        """Invoke LLM with system + user prompt. Returns text response."""
        model = await self.get_model()
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
        try:
            response = await model.ainvoke(messages)
            return self._strip_thinking(response.content)
        except Exception as e:
            if self.mode == LLMMode.HYBRID and "ollama" in str(type(model)).lower():
                logger.warning("Local LLM failed (%s), trying cloud fallback", e)
                cloud = self.get_cloud_model()
                response = await cloud.ainvoke(messages)
                return self._strip_thinking(response.content)
            raise

    # ── Status ────────────────────────────────────────────────────────────
    async def status(self) -> dict:
        local_ok = await self.check_local_health()
        return {
            "mode":          self.mode,
            "local_healthy": local_ok,
            "local_model":   self.ollama_model,
            "cloud_model":   self.anthropic_model,
            "active":        "local" if (self.mode != LLMMode.CLOUD and local_ok) else "cloud",
        }


# Singleton
llm_router = LLMRouter()
