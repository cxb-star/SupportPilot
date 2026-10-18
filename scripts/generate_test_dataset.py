"""生成 1000 条测试数据集 — 参数化组合，覆盖全意图/边界/对抗/多轮。"""
import json
import random
from collections import Counter
from pathlib import Path

random.seed(42)

_TICKET_SIGNALS = ("人工", "转人工", "建单", "投诉", "找客服", "找管理员", "升级", "找负责人")


def ri(lo, hi): return random.randint(lo, hi)
def pick(*a): return random.choice(a[0]) if len(a)==1 and isinstance(a[0],(list,tuple)) else random.choice(a)
def rf(lo, hi): return round(random.uniform(lo, hi), 2)


def infer_intent(q):
    if not q.strip() or len(q.strip()) <= 2:
        return "clarify", [], True
    if any(s in q for s in _TICKET_SIGNALS):
        return "ticket", [], True
    if any(w in q for w in ("退款", "退钱", "退kuan", "腿款")):
        return "refund", ["退款"], True
    if any(w in q for w in ("退货", "退活")):
        kws = ["退货", "运费"] if "运费" in q else ["退货"]
        return "return", kws, True
    if any(w in q for w in ("补发", "补伐", "重新发", "没收到", "漏发", "少发", "丢件")):
        return "reship", ["补发"], False
    if any(w in q for w in ("破损", "质量", "赔偿", "赔", "陪付", "补尝", "假货", "瑕疵", "货不对板")):
        return "compensate", ["赔付", "质量"], True
    if any(w in q for w in ("满减", "活动", "优惠", "促销", "券", "双11", "618", "年货节")):
        return "promo", ["满减"], False
    return "clarify", [], True


# ──  refund：按天数×条件×商品类型×语气 组合爆炸 ──────────────────
def gen_refund(n):
    cases = []
    days = list(range(1, 61))
    states = ["未拆封", "已拆封", "吊牌在", "已使用", "包装破损", "洗过"]
    goods = ["衣服", "鞋子", "电子产品", "日用品", "化妆品", "食品", "图书", "玩具", "家居", "数码"]
    reasons = ["质量问题", "破损", "与描述不符", "颜色不对", "尺寸不合适", "不喜欢", "买错了", "发货太慢"]
    tones = ["请问", "能", "想", "要", "怎么", "可以吗", "怎么办", "紧急", "在线等"]
    for _ in range(n):
        d = pick(days)
        s = pick(states)
        g = pick(goods)
        r = pick(reasons)
        t = pick(tones)
        q = pick(
            f"{t}订单{ri(10000,99999)}签收{d}天{g}{s}能退款吗",
            f"{g}{r}，签收{d}天了可以退钱吗",
            f"{t}我想退款，买了{d}天{g}，{s}",
            f"{g}签收{d}天{r}，{pick('能不能','是否','如何')}退款",
            f"{pick('预售','定制')} {g}，{r}，{d}天了能退吗",
            f"{d}天前买的{g}，现在{r}要退款",
            f"{t}{g}{r}，{pick('全额退款','部分退款','原路退回')}",
        )
        cases.append(q)
    return cases


# ──  return ──────────────────────────────────────────────────────
def gen_return(n):
    cases = []
    states = ["未拆封", "已拆封", "吊牌完好", "吊牌剪了", "洗过", "穿过"]
    goods_restricted = ["生鲜", "定制", "内衣", "食品", "化妆品", "数码"]
    reasons = ["质量问题", "不想要了", "买错了", "尺寸不对", "颜色不对"]
    for _ in range(n):
        s = pick(states)
        g = pick(goods_restricted + ["衣服", "鞋子", "家居"])
        r = pick(reasons)
        q = pick(
            f"{g}{s}能退货吗",
            f"{r}，{g}签收{ri(1,30)}天要退货",
            f"退货运费{pick('谁承担','怎么算','多少','要钱吗')}",
            f"{g}{pick('退货流程','退货地址','退货条件')}是什么",
            f"{pick('7','10','14','30')}天内退货{g}{s}可以吗",
            f"{g}{r}，{pick('要退','想退','申请退')}",
            f"{pick('生鲜','定制','内衣')}类{g}可以无理由退货吗",
            f"退货超时{pick('会自动关闭','还来得及','还有多久')}",
            f"{ri(1,10)}件{g}要退，怎么操作",
            f"{pick('已签收','刚收到','三天前买的')}，要退{g}",
        )
        cases.append(q)
    return cases


# ──  reship ──────────────────────────────────────────────────────
def gen_reship(n):
    cases = []
    missing = ["漏发", "少发", "缺件", "少了", "没收到", "丢件", "空包"]
    goods = ["商品", "配件", "赠品", "袜子", "帽子", "配件", "说明书"]
    times = ["24小时内", "48小时内", "几天", "多久", "什么时候"]
    for _ in range(n):
        m = pick(missing)
        g = pick(goods)
        t = pick(times)
        q = pick(
            f"订单{ri(10000,99999)}{m}了{g}，{t}能补发",
            f"{m}{ri(1,5)}件{g}，怎么处理",
            f"{pick('补发','重新发','再寄')}要{t}",
            f"同一订单补发{ri(1,5)}次了还能补吗",
            f"{pick('运输破损','快递丢了','快递显示签收但没收到')}",
            f"{pick('生鲜','食品')}漏发{t}能补",
            f"补发{pick('运费谁承担','要不要钱','免费吗')}",
            f"{m}了{g}，{pick('申请补发','要补发','怎么补')}",
        )
        cases.append(q)
    return cases


# ──  compensate ──────────────────────────────────────────────────
def gen_compensate(n):
    cases = []
    issues = ["破损", "质量问题", "假货", "瑕疵", "货不对板", "过期", "变质", "划伤", "开裂"]
    actions = ["怎么赔", "赔多少", "赔付标准", "如何赔偿", "要求赔偿"]
    values = [ri(50, 2000)]
    for _ in range(n):
        issue = pick(issues)
        v = pick(values)
        q = pick(
            f"收到的{pick('商品','东西','货物')}{issue}，{pick('怎么赔','要赔偿','怎么处理')}",
            f"{issue}{pick('投诉','举报','反馈')}",
            f"商品价值{v}元，{issue}赔多少",
            f"{pick('超时发货','未按时发货')}要赔吗",
            f"{pick('需要提交','要不要准备','得准备')}质检报告吗",
            f"{pick('赔付要等','多久出结果','处理时限')}",
            f"假货{pick('投诉','维权','举报')}怎么赔",
            f"{issue}{pick('严重','轻微')}，{pick('退款还是赔偿','怎么办')}",
        )
        cases.append(q)
    return cases


# ──  promo ───────────────────────────────────────────────────────
def gen_promo(n):
    cases = []
    events = ["双11", "618", "年货节", "新品日", "情人节", "黑五", "店庆", "周末特惠"]
    combos = ["满减", "优惠券", "店铺券", "平台券", "折扣", "秒杀", "团购"]
    for _ in range(n):
        e = pick(events)
        c = pick(combos)
        q = pick(
            f"{e}{c}规则是什么",
            f"{c}{pick('怎么用','使用条件','门槛')}",
            f"{c}可以{pick('叠加','一起用','同时用')}吗",
            f"{pick('预售','定制','生鲜')}商品能参加{c}吗",
            f"{e}期间{c}怎么算",
            f"满{ri(100,1000)}减{ri(10,200)}的活动有哪些",
            f"{c}{pick('有效期','使用时间','什么时间用')}",
            f"{c}和{pick('积分','红包','余额')}{pick('能一起用吗','冲突吗')}",
        )
        cases.append(q)
    return cases


# ──  ticket ──────────────────────────────────────────────────────
def gen_ticket(n):
    cases = []
    contexts = ["", "这个问题", "我要投诉", "客服", "你们"]
    intensities = ["", "非常", "特别", "实在", ""]
    for _ in range(n):
        ctx = pick(contexts)
        intens = pick(intensities)
        q = pick(
            f"{pick('帮我','请','帮')}{pick('转人工','找个客服','联系人工')}",
            f"{intens}生气，{pick('我要投诉','要找负责人','要升级')}",
            f"{pick('人工','真人','专员')}{pick('在哪','怎么找','联系方式','电话')}",
            f"{pick('建单','开工单','提交反馈','记录问题')}",
            f"{pick('一直','反复','多次')}{pick('自动回复','机器人回答')}没用，{pick('转人工','让人来处理')}",
            f"{pick('联系不上','找不到','没人理')}{pick('客服','你们')}",
            f"{pick('这服务','你们这','平台')}太差了，{pick('投诉','换人处理')}",
            f"人工呢？{pick('出来','在哪')}",
            f"{pick('叫','让')}你们{pick('领导','主管','负责人')}来",
            f"{pick('解决不了','没法接受','无法忍受')}，{pick('必须投诉','要升级','必须转人工')}",
        )
        cases.append(q)
    return cases


# ──  clarify ─────────────────────────────────────────────────────
def gen_clarify(n):
    cases = []
    greetings = ["你好", "在吗", "在不在", "嗨", "hello", "hey", "喂", "嗯", "啊", "请问"]
    random_q = ["今天天气怎么样", "推荐部电影", "讲个笑话", "你怎么看AI", "1+1等于几", "谁先有鸡还是蛋"]
    nonsense = ["", " ", "。", "...", "？？？", "。。。。", "……", "！？"]
    short = ["嗯", "哦", "好", "啊", "行", "ok", "1", "2", "test", "abc"]
    meta = ["你是什机器人", "你能做什么", "你是谁", "你干嘛的", "你聪明吗"]
    followup = ["刚才那个不算", "换个说法", "重来", "不管了"]
    for _ in range(n):
        q = pick(
            pick(greetings),
            pick(random_q),
            pick(nonsense),
            pick(short),
            pick(meta),
            f"{pick(followup)}：{pick(short)}",
            f"帮我{pick('写首诗','算个数','画个图','编故事','唱首歌','解方程')}",
            f"{pick('你们公司','平台')}叫什么名字",
            f"有{pick('活人','真人','客服')}在吗",
        )
        cases.append(q)
    return cases


# ──  boundary ────────────────────────────────────────────────────
def gen_boundary():
    qs = []
    for d in list(range(5, 21)) + [30, 60]:
        qs.append(f"签收{d}天了能退款吗")
    for d in list(range(13, 21)):
        qs.append(f"买了{d}天有质量问题能退吗")
    for n in range(1, 6):
        qs.append(f"同一订单补发了{n}次还能再补吗")
    qs += [
        "退款和退货有什么区别", "买了破损的东西是退款还是补发",
        "质量问题能退还能赔吗", "活动商品有问题怎么处理",
        "优惠券买了的东西能退吗", "补发和退货哪个划算",
    ]
    return qs


# ──  adversarial ─────────────────────────────────────────────────
def gen_adversarial():
    qs = []
    typos = [("退款","退kuan"),("退款","腿款"),("退货","退活"),("补发","补伐"),
             ("投诉","头诉"),("人工","人功"),("补偿","补尝"),("赔付","陪付"),
             ("质量问题","质 liang"),("破损","破sen"),("满减","manjian")]
    for _, typo in typos:
        qs.append(typo)
    qs += [
        "refund my order", "i want to return", "转 ren gong",
        "怎么 tui kuan", "help me complaint", "I need a refund ASAP",
        "转人工 please", "can i get money back",
    ]
    qs += [
        "你好我前天买的收到了发现有问题想要退款但是不知道流程怎么办着急在线等",
        "订单号12345678签收五天商品破损想要申请退款或者换货请问应该走什么流程需要准备哪些材料",
    ]
    qs += ["", " ", "。", "...", "？？？", "。。。。"]
    for _ in range(30):
        qs.append("".join(random.choices("abcdefghijklmnopqrstuvwxyz0123456789", k=ri(3, 12))))
    for _ in range(20):
        qs.append("".join(random.choices("一二三四五六七八九十百千万", k=ri(2, 6))))
    return qs


# ──  multi_turn ──────────────────────────────────────────────────
def gen_multi_turn():
    qs = []
    firsts = {
        "refund": ["我想退款", "申请退款", "要退钱", "这单退款"],
        "return": ["我要退货", "想退回去", "申请退货"],
        "reship": ["漏发了", "少发了", "没收到"],
        "compensate": ["东西破损了", "质量有问题", "要赔偿"],
        "promo": ["满减规则是什么", "优惠券怎么用", "活动规则"],
        "ticket": ["我要投诉", "转人工", "找客服"],
    }
    follows = [
        "那具体怎么操作", "还需要什么材料", "多久能到账", "能不能快点",
        "换一个方案", "还有其他办法吗", "你说的对但是", "不行我还有问题",
        "好的明白了谢谢", "那就这样吧", "然后呢", "下一步是什么",
        "确认一下", "再问一个", "还有疑问",
    ]
    for intent, starts in firsts.items():
        for s in starts:
            for f in follows:
                qs.append(f"{s}。{f}")
    return qs


# ──  seasonal ────────────────────────────────────────────────────
def gen_seasonal():
    qs = []
    scenes = [
        ("refund", ["双十一买的", "刚下单", "直播间买的", "团购的", "拼单买的", "秒杀抢的"]),
        ("return", ["快递到了", "还没签收", "送错地方了", "地址填错了", "放驿站了"]),
        ("reship", ["拆开看了", "孩子收到了", "公司签收的", "放前台了"]),
        ("compensate", ["送给人的", "自己用的", "急用", "送领导的", "结婚用的"]),
        ("promo", ["双11", "618", "年货节", "情人节", "双十一前", "店庆日"]),
        ("ticket", ["等了很久了", "太生气了", "忍无可忍", "客服不理人", "反复沟通无果"]),
    ]
    for intent, mods in scenes:
        for m in mods:
            qs.append(f"{m}，{pick('我想退款','我要投诉','问下规则','怎么处理','怎么办')}")
    return qs


# ──  main ────────────────────────────────────────────────────────
def generate(size=1000):
    cases = []
    uid = 0

    # 各意图均衡分配（各 ~120 条）
    n_per = size // 7
    generators = {
        "refund": gen_refund, "return": gen_return, "reship": gen_reship,
        "compensate": gen_compensate, "promo": gen_promo, "ticket": gen_ticket,
        "clarify": gen_clarify,
    }
    for source, fn in generators.items():
        for q in fn(n_per):
            uid += 1
            intent, kws, st = infer_intent(q)
            cases.append({"id": uid, "question": q, "expected_intent": intent,
                          "expect_keywords": kws, "should_ticket": st, "source": source})

    # 特殊覆盖集
    for q in gen_boundary():
        uid += 1
        intent, kws, st = infer_intent(q)
        cases.append({"id": uid, "question": q, "expected_intent": intent,
                       "expect_keywords": kws, "should_ticket": st, "source": "boundary"})
    for q in gen_adversarial():
        uid += 1
        intent, kws, st = infer_intent(q)
        cases.append({"id": uid, "question": q, "expected_intent": intent,
                       "expect_keywords": kws, "should_ticket": st, "source": "adversarial"})
    for q in gen_multi_turn():
        uid += 1
        intent, kws, st = infer_intent(q)
        cases.append({"id": uid, "question": q, "expected_intent": intent,
                       "expect_keywords": kws, "should_ticket": st, "source": "multi_turn"})
    for q in gen_seasonal():
        uid += 1
        intent, kws, st = infer_intent(q)
        cases.append({"id": uid, "question": q, "expected_intent": intent,
                       "expect_keywords": kws, "should_ticket": st, "source": "seasonal"})

    # 去重
    seen = set()
    unique = []
    for c in cases:
        if c["question"] not in seen:
            seen.add(c["question"])
            unique.append(c)

    # 补齐
    while len(unique) < size:
        uid += 1
        src = pick("refund", "return", "reship", "compensate", "promo", "ticket", "clarify")
        fn = generators[src]
        q = pick(*fn(20))
        intent, kws, st = infer_intent(q)
        unique.append({"id": uid, "question": q, "expected_intent": intent,
                        "expect_keywords": kws, "should_ticket": st, "source": f"{src}_fill"})

    unique = unique[:size]
    for i, c in enumerate(unique, 1):
        c["id"] = i
    return unique


def main():
    cases = generate(1000)
    out_path = Path(__file__).resolve().parent.parent / "eval" / "dataset_1000.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for c in cases:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    intent_cnt = Counter(c["expected_intent"] for c in cases)
    source_cnt = Counter(c["source"] for c in cases)
    print(f"Total cases: {len(cases)}")
    print(f"Intent distribution:")
    for k, v in sorted(intent_cnt.items(), key=lambda x: -x[1]):
        print(f"  {k}: {v}")
    print(f"Source distribution:")
    for k, v in sorted(source_cnt.items(), key=lambda x: -x[1]):
        print(f"  {k}: {v}")
    print(f"Output: {out_path}")


if __name__ == "__main__":
    main()
