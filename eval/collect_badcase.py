"""badcase 回流：从 audit_log 拉取低置信度/兜底失败的请求，追加到评估集。

用法：
    python -m eval.run_eval --collect-badcase

逻辑：
    1. 查 audit_log 中 confidence < 0.5 或 created_ticket=1 的记录
    2. 提取 question / intent / confidence
    3. 追加到 eval/badcase.jsonl（去重：同 question 不重复写）
    4. 下次跑 run_eval 时可合并 badcase.jsonl 进 dataset.jsonl
"""
import json
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
BADCASE_FILE = BASE_DIR / "eval" / "badcase.jsonl"
CONFIDENCE_THRESHOLD = 0.5


def collect_badcases(limit: int = 50) -> int:
    """从 audit_log 拉 badcase，写入 badcase.jsonl，返回新增条数。"""
    db = BASE_DIR / "data" / "app.db"
    if not db.exists():
        print("no audit_log found, skip")
        return 0

    conn = sqlite3.connect(str(db))
    try:
        rows = conn.execute(
            """
            SELECT question, intent, confidence, created_at
            FROM audit_log
            WHERE confidence < ? OR created_ticket = 1
            ORDER BY id DESC
            LIMIT ?
            """,
            (CONFIDENCE_THRESHOLD, limit),
        ).fetchall()
    finally:
        conn.close()

    # 已存在的 question 集合（避免重复）
    existing_questions: set[str] = set()
    if BADCASE_FILE.exists():
        for line in BADCASE_FILE.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    existing_questions.add(json.loads(line).get("question", ""))
                except json.JSONDecodeError:
                    pass

    new_count = 0
    with open(BADCASE_FILE, "a", encoding="utf-8") as f:
        for q, intent, conf, created_at in rows:
            if q in existing_questions:
                continue
            existing_questions.add(q)
            entry = {
                "question": q,
                "observed_intent": intent,
                "confidence": conf,
                "captured_at": created_at,
                "expected_intent": intent,  # 默认认为观察到的意图就是期望，人工可改
                "expect_keywords": [],
                "should_ticket": conf < CONFIDENCE_THRESHOLD,
            }
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            new_count += 1

    print(f"badcase collected: {new_count} new, total {len(existing_questions)} in file")
    return new_count


def merge_into_dataset() -> int:
    """把 badcase.jsonl 合并进 dataset.jsonl（去重），返回新增条数。"""
    if not BADCASE_FILE.exists():
        return 0
    dataset_file = BASE_DIR / "eval" / "dataset.jsonl"
    existing: list[dict] = []
    if dataset_file.exists():
        for line in dataset_file.read_text(encoding="utf-8").splitlines():
            if line.strip():
                existing.append(json.loads(line))

    existing_questions = {c.get("question", "") for c in existing}
    new_cases = []
    next_id = max((c.get("id", 0) for c in existing), default=0) + 1

    for line in BADCASE_FILE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        case = json.loads(line)
        if case.get("question") in existing_questions:
            continue
        case["id"] = next_id
        next_id += 1
        new_cases.append(case)

    if new_cases:
        with open(dataset_file, "a", encoding="utf-8") as f:
            for c in new_cases:
                f.write(json.dumps(c, ensure_ascii=False) + "\n")
    print(f"merged {len(new_cases)} badcase into dataset.jsonl")
    return len(new_cases)


if __name__ == "__main__":
    import sys
    if "--collect-badcase" in sys.argv:
        collect_badcases()
        merge_into_dataset()
    else:
        print("usage: python -m eval.run_eval --collect-badcase")
