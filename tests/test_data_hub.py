import json

from kwangsung_agent import KwangsungRepository, KwangsungToolRegistry


def test_dashboard_and_predictive_maintenance_demo(tmp_path):
    repo = KwangsungRepository(tmp_path / "demo.db")
    assert repo.dashboard()["maintenance_risks"] == 2
    risks = repo.get_maintenance_risks(urgent_only=True)
    assert risks[0]["risk_level"] == "긴급"
    assert all("미검증" in row["model_status"] for row in risks)


def test_process_trace_and_inspection_controls(tmp_path):
    repo = KwangsungRepository(tmp_path / "demo.db")
    trace = repo.get_process_trace("WO-260901")
    assert trace["incoming"][0]["result"] == "합격"
    assert [row["process"] for row in trace["processes"]] == ["입고·수입검사", "프레스", "전착", "마킹"]
    assert trace["shipment"][0]["status"] == "승인대기"
    assert any(row["certificate_attached"] == 0 for row in repo.get_incoming_inspection(issues_only=True))


def test_tools_are_strict_read_only(tmp_path):
    registry = KwangsungToolRegistry(KwangsungRepository(tmp_path / "demo.db"))
    assert len(registry.definitions) == 12
    for tool in registry.definitions:
        assert tool["strict"] is True
        assert tool["parameters"]["required"] == list(tool["parameters"]["properties"])
        assert not tool["name"].startswith(("create_", "update_", "delete_", "stop_"))
    blocked = json.loads(registry.execute("stop_press", "{}"))
    assert "허용되지 않은" in blocked["error"]
