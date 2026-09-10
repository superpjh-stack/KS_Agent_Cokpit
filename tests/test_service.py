from types import SimpleNamespace

import pytest

from kwangsung_agent import ManufacturingAgent


class FakeResponses:
    def __init__(self):
        self.requests = []

    def create(self, **kwargs):
        self.requests.append(kwargs)
        if len(self.requests) == 1:
            call = SimpleNamespace(type="function_call", name="get_maintenance_risks", arguments='{"press_id":"PRS-01","urgent_only":true}', call_id="call-1")
            return SimpleNamespace(id="resp-1", output=[call], output_text="")
        return SimpleNamespace(id="resp-2", output=[], output_text="정비 책임자의 점검이 필요합니다.")


class FakeRegistry:
    definitions = [{"type": "function", "name": "get_maintenance_risks", "description": "test", "parameters": {"type": "object", "properties": {}}}]

    def execute(self, name, arguments):
        assert name == "get_maintenance_risks"
        return '{"status":"ok","demo_data":true}'


def test_function_call_loop():
    responses = FakeResponses()
    answer = ManufacturingAgent(SimpleNamespace(responses=responses), factory_tools=FakeRegistry()).ask("정비위험은?")
    assert answer.data_tools == ["get_maintenance_risks"]
    assert answer.text.startswith("정비 책임자")
    assert responses.requests[1]["input"][0]["call_id"] == "call-1"


def test_empty_question_rejected():
    with pytest.raises(ValueError):
        ManufacturingAgent(SimpleNamespace(responses=FakeResponses()), factory_tools=FakeRegistry()).ask(" ")
