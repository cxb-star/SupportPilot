from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DOCS_DIR = BASE_DIR / "docs"


def main() -> None:
    DOCS_DIR.mkdir(exist_ok=True)
    demo = DOCS_DIR / "demo_policy.txt"
    demo.write_text(
        "差旅报销需在 30 天内提交，超过 30 天需总监审批。\n"
        "机票仅限经济舱，住宿标准按城市等级执行。\n",
        encoding="utf-8",
    )
    faq = DOCS_DIR / "faq.txt"
    faq.write_text(
        "Q: 出差住宿报销标准是什么？\nA: 按城市等级执行，一线城市每晚不超过 500 元。\n"
        "Q: 报销单据需要准备哪些材料？\nA: 发票、行程单、审批单各一份。\n",
        encoding="utf-8",
    )
    print(f"seeded: {demo}")


if __name__ == "__main__":
    main()
