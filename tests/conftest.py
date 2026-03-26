"""
conftest.py — pytest 全局 fixtures
"""
import sys
import os

# 确保项目根目录在 sys.path 中，使 tests/ 下的文件能直接 import 源码模块
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
# 确保 tests/ 目录本身也在 sys.path 中
sys.path.insert(0, os.path.dirname(__file__))

import pytest
from base_agent import AgentMessage, MessageType
from mock_llm import MockLLMClient


@pytest.fixture
def mock_llm():
    """每个测试独立的 MockLLMClient 实例（_call_count 从 0 开始）"""
    return MockLLMClient()


@pytest.fixture
def make_message():
    """工厂 fixture：快速构造 AgentMessage"""
    def _factory(
        sender: str = "orchestrator",
        receiver: str = "agent",
        msg_type: MessageType = MessageType.TASK,
        payload: dict = None,
        metadata: dict = None,
    ) -> AgentMessage:
        return AgentMessage(
            sender=sender,
            receiver=receiver,
            msg_type=msg_type,
            payload=payload or {},
            metadata=metadata or {},
        )
    return _factory
