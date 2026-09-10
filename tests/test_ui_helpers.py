from kwangsung_agent import KwangsungRepository, QUESTION_GROUPS, risk_label, user_question_history, work_order_snapshot

def test_cockpit_helpers(tmp_path):
    repo=KwangsungRepository(tmp_path/"demo.db")
    snap=work_order_snapshot(repo,"WO-260901")
    assert snap["job"]["press_id"]=="PRS-01"
    assert risk_label(snap)[0] in {"주의","높음"}
    assert set(QUESTION_GROUPS) == {"지식베이스", "DB", "룰"}
    assert all(len(questions) == 10 for questions in QUESTION_GROUPS.values())
    assert user_question_history([{"role":"user","content":"정비","created_at":"10:00"}])[0]["content"]=="정비"
