"""评估：真实调用 graph，统计意图命中率 / 答案关键词命中 / 兜底正确率。

用法：
    python -m eval.run_eval              跑 dataset.jsonl
    python -m eval.run_eval --with-badcase  跑 dataset + badcase 合并
    python -m eval.run_eval --collect-badcase  先回流 badcase 再跑评估
"""
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATASET = BASE_DIR / "eval" / "dataset.jsonl"
BADCASE = BASE_DIR / "eval" / "badcase.jsonl"


def load_dataset(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def run(cases: list[dict]) -> dict:
    from agent.graph import AgentContext, build_graph
    from agent.state import init_state
    from config import settings

    ctx = AgentContext.default()
    graph = build_graph(ctx)
    settings.SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)

    total = len(cases)
    intent_checked = intent_hit = 0
    keyword_checked = keyword_hit = 0
    fallback_checked = fallback_ok = 0
    badcases: list[dict] = []

    for idx, case in enumerate(cases):
        state = init_state(
            question=case["question"],
            session_id=f"eval-{idx}",
            user_id="eval-user",
        )
        result = graph.invoke(state)

        expected_intent = case.get("expected_intent", "")
        if expected_intent:
            intent_checked += 1
            if result["intent"] == expected_intent:
                intent_hit += 1
            else:
                badcases.append({
                    "question": case["question"],
                    "observed_intent": result["intent"],
                    "expected_intent": expected_intent,
                    "confidence": result.get("confidence", 0.0),
                    "type": "intent_mismatch",
                })

        if case.get("expect_keywords"):
            keyword_checked += 1
            if all(k in result["answer"] for k in case["expect_keywords"]):
                keyword_hit += 1
            else:
                badcases.append({
                    "question": case["question"],
                    "missing_keywords": [k for k in case["expect_keywords"] if k not in result["answer"]],
                    "confidence": result.get("confidence", 0.0),
                    "type": "keyword_miss",
                })

        if case.get("should_ticket") is not None:
            fallback_checked += 1
            if bool(case["should_ticket"]) == bool(result["created_ticket"]):
                fallback_ok += 1
            else:
                badcases.append({
                    "question": case["question"],
                    "expected_ticket": case["should_ticket"],
                    "actual_ticket": result["created_ticket"],
                    "type": "fallback_mismatch",
                })

    metrics = {
        "cases": total,
        "intent_hit": intent_hit,
        "intent_checked": intent_checked,
        "intent_rate": (intent_hit / intent_checked) if intent_checked else None,
        "answer_keyword_hit": keyword_hit,
        "answer_keyword_checked": keyword_checked,
        "answer_keyword_rate": (keyword_hit / keyword_checked) if keyword_checked else None,
        "fallback_correct": fallback_ok,
        "fallback_checked": fallback_checked,
        "fallback_rate": (fallback_ok / fallback_checked) if fallback_checked else None,
        "badcase_count": len(badcases),
    }

    if badcases:
        existing_q: set = set()
        if BADCASE.exists():
            for line in BADCASE.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    try:
                        existing_q.add(json.loads(line).get("question", ""))
                    except json.JSONDecodeError:
                        pass
        new = [b for b in badcases if b["question"] not in existing_q]
        if new:
            with open(BADCASE, "a", encoding="utf-8") as f:
                for b in new:
                    b["source"] = "run_eval"
                    f.write(json.dumps(b, ensure_ascii=False) + "\n")
            metrics["new_badcase_appended"] = len(new)

    return metrics


def main() -> None:
    with_badcase = "--with-badcase" in sys.argv
    collect = "--collect-badcase" in sys.argv

    if collect:
        from eval.collect_badcase import collect_badcases, merge_into_dataset
        collect_badcases()
        merge_into_dataset()
        print("--- badcase collected, now running eval ---")

    cases = load_dataset(DATASET)
    if with_badcase:
        cases.extend(load_dataset(BADCASE))
        print(f"running with badcase, total cases: {len(cases)}")

    metrics = run(cases)
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    if metrics.get("badcase_count"):
        print(f"\n!! 本次产生 {metrics['badcase_count']} 条 badcase，已追加到 eval/badcase.jsonl")
        print("   建议人工标注 expected_intent 后，用 --with-badcase 回归验证")


if __name__ == "__main__":
    main()
