"""
test_base_agent.py — base_agent 模块单元测试

覆盖：
- MessageType 枚举
- AgentMessage 数据类（序列化/反序列化/默认值）
- LLMClient._extract_json（4 级 JSON 解析策略）
- LLMClient.chat_json（首次成功、重试逻辑、全部失败）
- BaseAgent.run（正常路径、异常捕获、ERROR 消息格式）
"""
import json
import pytest
from unittest.mock import MagicMock, patch, call

from base_agent import (
    MessageType,
    AgentMessage,
    LLMClient,
    BaseAgent,
)


# ══════════════════════════════════════════════
# MessageType 枚举
# ══════════════════════════════════════════════

class TestMessageType:
    def test_task_value(self):
        assert MessageType.TASK.value == "task"

    def test_result_value(self):
        assert MessageType.RESULT.value == "result"

    def test_feedback_value(self):
        assert MessageType.FEEDBACK.value == "feedback"

    def test_error_value(self):
        assert MessageType.ERROR.value == "error"

    def test_from_string(self):
        assert MessageType("task") is MessageType.TASK


# ══════════════════════════════════════════════
# AgentMessage 数据类
# ══════════════════════════════════════════════

class TestAgentMessage:
    def test_basic_construction(self):
        msg = AgentMessage(
            sender="a",
            receiver="b",
            msg_type=MessageType.TASK,
            payload={"key": "val"},
        )
        assert msg.sender == "a"
        assert msg.receiver == "b"
        assert msg.msg_type is MessageType.TASK
        assert msg.payload == {"key": "val"}

    def test_metadata_default_is_empty_dict(self):
        msg1 = AgentMessage("a", "b", MessageType.TASK, {})
        msg2 = AgentMessage("c", "d", MessageType.TASK, {})
        # 两个不同实例的 metadata 应是不同对象（default_factory）
        assert msg1.metadata is not msg2.metadata

    def test_to_dict_serializes_msg_type_as_string(self):
        msg = AgentMessage("src", "dst", MessageType.RESULT, {"x": 1})
        d = msg.to_dict()
        assert d["msg_type"] == "result"
        assert isinstance(d["msg_type"], str)

    def test_from_dict_restores_msg_type_enum(self):
        original = AgentMessage("s", "r", MessageType.FEEDBACK, {"note": "ok"})
        d = original.to_dict()
        restored = AgentMessage.from_dict(d)
        assert restored.msg_type is MessageType.FEEDBACK
        assert restored.sender == "s"
        assert restored.payload == {"note": "ok"}

    def test_roundtrip_to_dict_from_dict(self):
        msg = AgentMessage(
            sender="orchestrator",
            receiver="writer",
            msg_type=MessageType.ERROR,
            payload={"error": "oops"},
            metadata={"retry": 1},
        )
        restored = AgentMessage.from_dict(msg.to_dict())
        assert restored.sender == msg.sender
        assert restored.receiver == msg.receiver
        assert restored.msg_type is msg.msg_type
        assert restored.payload == msg.payload
        assert restored.metadata == msg.metadata

    def test_repr_contains_sender_receiver_type(self):
        msg = AgentMessage("alice", "bob", MessageType.TASK, {})
        r = repr(msg)
        assert "alice" in r
        assert "bob" in r
        assert "task" in r


# ══════════════════════════════════════════════
# LLMClient._extract_json — JSON 解析策略
# ══════════════════════════════════════════════

class TestExtractJson:
    """_extract_json 是静态方法，直接通过类调用测试"""

    # ── 策略 2: 纯 JSON ──
    def test_plain_json(self):
        result = LLMClient._extract_json('{"key": "value"}')
        assert result == {"key": "value"}

    def test_plain_json_with_whitespace(self):
        result = LLMClient._extract_json('  \n{"a": 1}\n  ')
        assert result == {"a": 1}

    # ── 策略 1: markdown 代码块 ──
    def test_markdown_json_block(self):
        raw = '```json\n{"key": "value"}\n```'
        assert LLMClient._extract_json(raw) == {"key": "value"}

    def test_markdown_block_without_lang(self):
        raw = '```\n{"key": "value"}\n```'
        assert LLMClient._extract_json(raw) == {"key": "value"}

    # ── 策略 3: 前后有说明文字 ──
    def test_json_with_prefix_and_suffix(self):
        raw = '以下是结果：{"answer": 42} 希望对你有帮助。'
        assert LLMClient._extract_json(raw) == {"answer": 42}

    # ── 策略 4: 尾随逗号 ──
    def test_trailing_comma_in_object(self):
        raw = '{"a": 1, "b": 2,}'
        assert LLMClient._extract_json(raw) == {"a": 1, "b": 2}

    def test_trailing_comma_in_array(self):
        raw = '{"items": [1, 2, 3,]}'
        assert LLMClient._extract_json(raw) == {"items": [1, 2, 3]}

    # ── 策略 4: 行注释 ──
    def test_line_comment_removed(self):
        raw = '{"key": "val"} // 这是注释'
        assert LLMClient._extract_json(raw) == {"key": "val"}

    # ── 策略 4: 中文引号替换 ──
    def test_chinese_double_quotes(self):
        raw = '\u201ckey\u201d: \u201cvalue\u201d'
        # 替换后变成 "key": "value"，但还需要 {} 包裹才能是合法 JSON
        raw_wrapped = '{\u201ckey\u201d: \u201cvalue\u201d}'
        assert LLMClient._extract_json(raw_wrapped) == {"key": "value"}

    # ── 嵌套对象 ──
    def test_nested_object(self):
        raw = '{"outer": {"inner": [1, 2]}}'
        assert LLMClient._extract_json(raw) == {"outer": {"inner": [1, 2]}}

    # ── 无效输入 → JSONDecodeError ──
    def test_invalid_json_raises(self):
        with pytest.raises(json.JSONDecodeError):
            LLMClient._extract_json("not json at all")

    def test_empty_string_raises(self):
        with pytest.raises(json.JSONDecodeError):
            LLMClient._extract_json("")


# ══════════════════════════════════════════════
# LLMClient.chat_json — 重试逻辑
# ══════════════════════════════════════════════

class TestChatJson:
    """通过 patch LLMClient.chat 来测试 chat_json 的重试逻辑"""

    def _make_client(self):
        return LLMClient(api_key="test", base_url="http://test", model="test", api_style="openai")

    def test_success_on_first_try(self):
        client = self._make_client()
        with patch.object(client, "chat", return_value='{"result": "ok"}'):
            result = client.chat_json("sys", "user")
        assert result == {"result": "ok"}

    def test_retry_on_invalid_json(self):
        """首次返回无效 JSON，第二次（重试）返回合法 JSON"""
        client = self._make_client()
        responses = ["not json", '{"fixed": true}']
        with patch.object(client, "chat", side_effect=responses):
            result = client.chat_json("sys", "user", max_retries=1)
        assert result == {"fixed": True}

    def test_raises_after_all_retries_exhausted(self):
        """所有尝试都返回无效 JSON 时抛出 JSONDecodeError"""
        client = self._make_client()
        always_invalid = ["not json"] * 10
        with patch.object(client, "chat", side_effect=always_invalid):
            with pytest.raises(json.JSONDecodeError):
                client.chat_json("sys", "user", max_retries=2)

    def test_zero_retries_only_one_attempt(self):
        """max_retries=0 时只尝试一次，失败即抛异常"""
        client = self._make_client()
        with patch.object(client, "chat", return_value="not json"):
            with pytest.raises(json.JSONDecodeError):
                client.chat_json("sys", "user", max_retries=0)


# ══════════════════════════════════════════════
# BaseAgent.run — 错误处理 & 日志
# ══════════════════════════════════════════════

class ConcreteAgent(BaseAgent):
    """用于测试的最小化具体实现"""

    def __init__(self, llm, response=None, raise_exc=None, verbose=False):
        super().__init__(name="TestAgent", llm=llm, verbose=verbose)
        self._response = response
        self._raise_exc = raise_exc

    def process(self, message: AgentMessage) -> AgentMessage:
        if self._raise_exc:
            raise self._raise_exc
        return self._response


class TestBaseAgentRun:
    def _make_agent(self, response=None, raise_exc=None, verbose=False):
        llm = MagicMock()
        return ConcreteAgent(llm=llm, response=response, raise_exc=raise_exc, verbose=verbose)

    def _make_task_msg(self):
        return AgentMessage(
            sender="orchestrator",
            receiver="TestAgent",
            msg_type=MessageType.TASK,
            payload={"data": "x"},
        )

    def test_run_returns_process_result_on_success(self):
        expected = AgentMessage("TestAgent", "orchestrator", MessageType.RESULT, {"out": 1})
        agent = self._make_agent(response=expected)
        result = agent.run(self._make_task_msg())
        assert result is expected

    def test_run_returns_error_message_on_exception(self):
        agent = self._make_agent(raise_exc=ValueError("boom"))
        result = agent.run(self._make_task_msg())
        assert result.msg_type is MessageType.ERROR
        assert "boom" in result.payload["error"]

    def test_error_message_sender_is_agent_name(self):
        agent = self._make_agent(raise_exc=RuntimeError("fail"))
        result = agent.run(self._make_task_msg())
        assert result.sender == "TestAgent"

    def test_log_buffer_records_entries(self):
        expected = AgentMessage("TestAgent", "orchestrator", MessageType.RESULT, {})
        agent = self._make_agent(response=expected, verbose=False)
        agent.run(self._make_task_msg())
        assert len(agent._log_buffer) >= 2  # 至少记录 "收到消息" 和 "处理完成"

    def test_log_buffer_records_error_entry(self):
        agent = self._make_agent(raise_exc=Exception("err"), verbose=False)
        agent.run(self._make_task_msg())
        # 应记录失败日志
        assert any("失败" in entry or "err" in entry for entry in agent._log_buffer)

    def test_log_method_stores_to_buffer(self):
        llm = MagicMock()
        agent = ConcreteAgent(llm=llm, verbose=False)
        agent.log("test message")
        assert any("test message" in entry for entry in agent._log_buffer)
