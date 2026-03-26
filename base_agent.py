"""
base_agent.py — 智能体基类 & 消息协议

多智能体协作系统的核心抽象层：
- AgentMessage: 智能体之间传递的统一消息格式
- BaseAgent: 所有智能体的基类，定义统一接口
- LLMClient: 封装大模型调用（支持 OpenAI 兼容 API）
"""

from __future__ import annotations

import json
import re
import time
import httpx
from enum import Enum
from dataclasses import dataclass, field, asdict
from typing import Any, Optional
from abc import ABC, abstractmethod

from config import LLMClientConfig


# ──────────────────────────────────────────────
# 1. 消息协议
# ──────────────────────────────────────────────

class MessageType(Enum):
    """消息类型枚举"""
    TASK = "task"              # 任务指令
    RESULT = "result"          # 任务结果
    FEEDBACK = "feedback"      # 反馈/修改意见
    ERROR = "error"            # 错误信息


@dataclass
class AgentMessage:
    """
    智能体间通信的标准消息格式。
    
    设计原则：
    - 每条消息有唯一来源(sender)和目标(receiver)
    - payload 承载实际数据，格式由智能体自行约定
    - metadata 存放附加信息（如重试次数、时间戳等）
    """
    sender: str                          # 发送方智能体名称
    receiver: str                        # 接收方智能体名称
    msg_type: MessageType                # 消息类型
    payload: dict[str, Any]              # 消息主体数据
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["msg_type"] = self.msg_type.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "AgentMessage":
        d["msg_type"] = MessageType(d["msg_type"])
        return cls(**d)

    def __repr__(self) -> str:
        return (
            f"📨 [{self.sender} → {self.receiver}] "
            f"type={self.msg_type.value} | "
            f"keys={list(self.payload.keys())}"
        )


# ──────────────────────────────────────────────
# 2. LLM 客户端封装
# ──────────────────────────────────────────────

class LLMClient:
    """
    封装大模型 API 的调用。
    默认使用 Kimi Code API（Anthropic Messages 格式）。
    也支持 OpenAI 兼容 API（DeepSeek / Qwen / Ollama 等）。

    通过 api_style 参数切换：
    - "anthropic": Kimi Code / Anthropic Claude（默认）
    - "openai":    OpenAI / DeepSeek / Qwen 等兼容 API
    """

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        api_style: str,
        client_config: Optional[LLMClientConfig] = None,
    ):
        cfg = client_config or LLMClientConfig()
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_style = api_style
        self.temperature = cfg.default_temperature
        self.timeout = cfg.timeout
        self.max_tokens = cfg.max_tokens
        self.max_retries = cfg.max_retries
        self.anthropic_version = cfg.anthropic_version

    def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: Optional[float] = None,
        response_format: Optional[dict] = None,
    ) -> str:
        """同步调用 LLM，返回纯文本结果"""
        if self.api_style == "anthropic":
            return self._chat_anthropic(system_prompt, user_prompt, temperature)
        else:
            return self._chat_openai(system_prompt, user_prompt, temperature, response_format)

    # ── Anthropic Messages API（Kimi Code 使用此格式）──

    def _chat_anthropic(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: Optional[float] = None,
    ) -> str:
        headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
            "anthropic-version": self.anthropic_version,
        }
        body: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": system_prompt,
            "messages": [
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature or self.temperature,
        }

        resp = httpx.post(
            f"{self.base_url}/messages",
            headers=headers,
            json=body,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        # Anthropic 格式: content 是一个列表，取第一个 text block
        return data["content"][0]["text"]

    # ── OpenAI 兼容 API ──

    def _chat_openai(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: Optional[float] = None,
        response_format: Optional[dict] = None,
    ) -> str:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature or self.temperature,
        }
        if response_format:
            body["response_format"] = response_format

        resp = httpx.post(
            f"{self.base_url}/chat/completions",
            headers=headers,
            json=body,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    # ── JSON 解析 ──

    @staticmethod
    def _extract_json(raw: str) -> dict:
        """
        从 LLM 返回的原始文本中提取 JSON，支持多种常见情况：
        1. 纯 JSON 文本
        2. 包裹在 ```json ... ``` 代码块中
        3. 文本前后有多余说明
        4. 含有尾随逗号、注释等轻微格式问题
        """
        text = raw.strip()

        # ── 策略1: 去除 markdown 代码块包裹 ──
        # 匹配 ```json ... ``` 或 ``` ... ```
        md_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?\s*```', text, re.DOTALL)
        if md_match:
            text = md_match.group(1).strip()

        # ── 策略2: 直接尝试解析 ──
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # ── 策略3: 从文本中提取最外层 { ... } ──
        brace_match = re.search(r'\{', text)
        if brace_match:
            start = brace_match.start()
            # 从最后一个 } 往回找
            end = text.rfind('}')
            if end > start:
                candidate = text[start:end + 1]
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    pass

                # ── 策略4: 清理常见格式问题后重试 ──
                cleaned = candidate
                # 去除 JSON 中的单行注释 (// ...)
                cleaned = re.sub(r'//[^\n]*', '', cleaned)
                # 去除尾随逗号 (对象或数组结尾的多余逗号)
                cleaned = re.sub(r',\s*([}\]])', r'\1', cleaned)
                # 将中文引号替换为英文引号
                cleaned = cleaned.replace('\u201c', '"').replace('\u201d', '"')
                cleaned = cleaned.replace('\u2018', "'").replace('\u2019', "'")
                try:
                    return json.loads(cleaned)
                except json.JSONDecodeError:
                    pass

        # 所有策略都失败
        raise json.JSONDecodeError(
            f"无法从 LLM 输出中提取有效 JSON",
            text[:200],
            0,
        )

    def chat_json(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: Optional[float] = None,
        max_retries: Optional[int] = None,
    ) -> dict:
        """
        调用 LLM 并解析 JSON 返回。
        如果解析失败，会自动重试（将原始输出发回给 LLM 让其修复格式）。
        """
        retries = max_retries if max_retries is not None else self.max_retries
        raw = self.chat(
            system_prompt=system_prompt + "\n\n请严格以 JSON 格式输出，不要包含 markdown 代码块。不要在 JSON 中使用注释。",
            user_prompt=user_prompt,
            temperature=temperature,
        )

        # 首次尝试解析
        first_err: Exception | None = None
        try:
            return self._extract_json(raw)
        except json.JSONDecodeError as e:
            first_err = e

        # 自动重试：让 LLM 修复 JSON 格式
        for _attempt in range(retries):
            try:
                fix_raw = self.chat(
                    system_prompt="你是一个 JSON 格式修复助手。用户会给你一段格式有问题的 JSON 文本，请修复并仅输出合法的 JSON，不要包含任何其他说明文字、markdown 代码块或注释。",
                    user_prompt=f"请修复以下 JSON 格式错误并直接输出合法 JSON：\n\n{raw}",
                    temperature=0.1,
                )
                return self._extract_json(fix_raw)
            except json.JSONDecodeError:
                continue

        # 所有重试都失败，抛出原始错误
        raise first_err  # type: ignore[misc]


# ──────────────────────────────────────────────
# 3. 智能体基类
# ──────────────────────────────────────────────

class BaseAgent(ABC):
    """
    所有智能体的基类。
    
    子类只需实现 process() 方法，
    框架负责消息收发、日志、错误处理。
    """

    def __init__(self, name: str, llm: LLMClient, verbose: bool = True):
        self.name = name
        self.llm = llm
        self.verbose = verbose
        self._log_buffer: list[str] = []

    def log(self, msg: str):
        """记录日志"""
        entry = f"[{self.name}] {msg}"
        self._log_buffer.append(entry)
        if self.verbose:
            print(entry)

    @abstractmethod
    def process(self, message: AgentMessage) -> AgentMessage:
        """
        处理收到的消息，返回结果消息。
        这是子类必须实现的核心方法。
        """
        ...

    def run(self, message: AgentMessage) -> AgentMessage:
        """
        运行智能体：包装 process() 并添加错误处理和计时。
        """
        self.log(f"📥 收到消息: {message}")
        start = time.time()
        try:
            result = self.process(message)
            elapsed = time.time() - start
            self.log(f"✅ 处理完成 ({elapsed:.1f}s)")
            return result
        except Exception as e:
            elapsed = time.time() - start
            self.log(f"❌ 处理失败 ({elapsed:.1f}s): {e}")
            return AgentMessage(
                sender=self.name,
                receiver=message.sender,
                msg_type=MessageType.ERROR,
                payload={"error": str(e)},
            )
