"""生成模拟案例数据，结构与 CAIL 2018 / PDP-Bench 完全一致。

当真实数据集因网络原因无法下载时的开发用数据。
结构验证通过后可直接灌入 PostgreSQL。

用法: python scripts/generate_sample_data.py [--count 100]
"""

import json
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from random import Random

rng = Random(42)

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "samples"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# ============================================================================
# 罪名库（取自刑法常见罪名）
# ============================================================================

CHARGES = [
    {"name": "故意杀人罪", "article": "232", "min_term": 120, "max_term": 999},
    {"name": "故意伤害罪", "article": "234", "min_term": 6, "max_term": 180},
    {"name": "抢劫罪", "article": "263", "min_term": 36, "max_term": 999},
    {"name": "盗窃罪", "article": "264", "min_term": 3, "max_term": 180},
    {"name": "诈骗罪", "article": "266", "min_term": 3, "max_term": 180},
    {"name": "贪污罪", "article": "382", "min_term": 12, "max_term": 999},
    {"name": "受贿罪", "article": "385", "min_term": 12, "max_term": 999},
    {"name": "交通肇事罪", "article": "133", "min_term": 3, "max_term": 84},
    {"name": "危险驾驶罪", "article": "133之一", "min_term": 1, "max_term": 6},
    {"name": "非法吸收公众存款罪", "article": "176", "min_term": 6, "max_term": 120},
    {"name": "集资诈骗罪", "article": "192", "min_term": 36, "max_term": 999},
    {"name": "侵犯公民个人信息罪", "article": "253之一", "min_term": 3, "max_term": 84},
    {"name": "帮助信息网络犯罪活动罪", "article": "287之二", "min_term": 3, "max_term": 36},
    {"name": "掩饰、隐瞒犯罪所得罪", "article": "312", "min_term": 3, "max_term": 84},
    {"name": "走私、贩卖、运输、制造毒品罪", "article": "347", "min_term": 36, "max_term": 999},
    {"name": "寻衅滋事罪", "article": "293", "min_term": 3, "max_term": 60},
    {"name": "组织、领导传销活动罪", "article": "224之一", "min_term": 12, "max_term": 180},
    {"name": "开设赌场罪", "article": "303", "min_term": 6, "max_term": 120},
    {"name": "非法经营罪", "article": "225", "min_term": 6, "max_term": 180},
    {"name": "侵犯著作权罪", "article": "217", "min_term": 6, "max_term": 84},
]

# 检察院决定类型（PDP-Bench）
DECISIONS = [
    {"type": "P", "label": "起诉", "ratio": 55},
    {"type": "IENP", "label": "存疑不起诉", "ratio": 20},
    {"type": "DNP", "label": "酌定不起诉", "ratio": 15},
    {"type": "SNP", "label": "法定不起诉", "ratio": 10},
]

# 证据类型
EVIDENCE_TYPES = [
    "物证", "书证", "证人证言", "被害人陈述",
    "犯罪嫌疑人供述和辩解", "鉴定意见",
    "勘验检查笔录", "视听资料", "电子数据",
]

# 人名池
NAMES = ["王某", "李某", "张某", "刘某", "陈某", "杨某", "赵某", "黄某", "周某", "吴某",
         "徐某", "孙某", "马某", "朱某", "胡某", "郭某", "何某", "林某", "罗某", "梁某"]

LOCATIONS = ["北京市朝阳区", "上海市浦东新区", "广州市天河区", "深圳市南山区",
             "杭州市西湖区", "成都市武侯区", "武汉市洪山区", "南京市鼓楼区",
             "重庆市渝北区", "西安市雁塔区"]

BANKS = ["中国工商银行", "中国建设银行", "中国农业银行", "中国银行", "招商银行", "支付宝", "微信支付"]


# ============================================================================
# 事实模板（按罪名）
# ============================================================================

FACT_TEMPLATES = {
    "故意伤害罪": [
        "{time}，被告人{name}在{location}因琐事与被害人{victim}发生争执，"
        "被告人{name}持{weapon}将被害人{victim}打伤。经鉴定，被害人{victim}的损伤程度为{level}。"
        "案发后，被告人{name}被公安机关抓获归案。",
    ],
    "盗窃罪": [
        "{time}，被告人{name}在{location}{place}，趁无人之际，"
        "盗窃被害人{victim}放置在{container}内的现金人民币{amount}元及{items}。"
        "经鉴定，被盗物品价值人民币{item_value}元。案发后，被盗财物已部分追回。",
    ],
    "诈骗罪": [
        "{time}，被告人{name}在{location}，通过{channel}联系被害人{victim}，"
        "虚构{pretext}，骗取被害人{victim}人民币{amount}元。"
        "被告人{name}将骗得的钱款用于{use}。",
    ],
    "抢劫罪": [
        "{time}，被告人{name}在{location}，持{tool}威胁被害人{victim}，"
        "当场劫取被害人{victim}现金人民币{amount}元及{items}。"
        "案发后，公安机关经侦查将被告人{name}抓获。",
    ],
    "帮助信息网络犯罪活动罪": [
        "{time}，被告人{name}明知他人利用信息网络实施犯罪，"
        "仍将其名下的{bank}银行卡（卡号：{card}）及配套U盾、手机卡提供给他人使用。"
        "经查，上述银行卡被用于电信网络诈骗，支付结算金额共计人民币{amount}元。",
    ],
}

FACT_TEMPLATES["贪污罪"] = [
    "{time}，被告人{name}在担任{position}期间，利用职务便利，"
    "通过虚列支出、伪造票据等手段，侵吞公款共计人民币{amount}元。"
]
FACT_TEMPLATES["受贿罪"] = [
    "{time}，被告人{name}在担任{position}期间，利用职务便利，"
    "为{wisher}在{thing}等方面谋取利益，非法收受{wisher}给予的财物共计人民币{amount}元。"
]
FACT_TEMPLATES["交通肇事罪"] = [
    "{time}，被告人{name}驾驶{vehicle}在{location}路段，"
    "违反交通运输管理法规，发生交通事故，致被害人{victim}{result}。"
    "经认定，被告人{name}负事故全部责任。"
]
FACT_TEMPLATES["危险驾驶罪"] = [
    "{time}，被告人{name}饮酒后驾驶{vehicle}在{location}路段行驶，"
    "被执勤民警查获。经鉴定，被告人{name}血液中乙醇含量为{alcohol}mg/100ml。"
]
FACT_TEMPLATES["非法吸收公众存款罪"] = [
    "{time}，被告人{name}在{location}，未经国家金融管理部门批准，"
    "以{company}的名义，通过{method}等方式向社会公开宣传，"
    "承诺在一定期限内还本付息，向社会不特定对象吸收资金共计人民币{amount}元。"
]
FACT_TEMPLATES["侵犯公民个人信息罪"] = [
    "{time}，被告人{name}在{location}，通过{method}等方式，"
    "非法获取公民个人信息共计{count}条，并非法出售给他人，获利人民币{amount}元。"
]
FACT_TEMPLATES["掩饰、隐瞒犯罪所得罪"] = [
    "{time}，被告人{name}明知是犯罪所得，"
    "仍通过{method}等方式，帮助上游犯罪人员转移资金共计人民币{amount}元。"
]
FACT_TEMPLATES["走私、贩卖、运输、制造毒品罪"] = [
    "{time}，被告人{name}在{location}，"
    "向吸毒人员{victim}贩卖{thing}共计{substance}克，获取毒资人民币{amount}元。"
    "公安机关在抓捕被告人{name}时，从其住处查获{substance}共计{substance2}克。"
]
FACT_TEMPLATES["寻衅滋事罪"] = [
    "{time}，被告人{name}在{location}，"
    "酒后滋事，{action}，致被害人{victim}{result}。"
]
FACT_TEMPLATES["集资诈骗罪"] = [
    "{time}，被告人{name}在{location}，"
    "以非法占有为目的，虚构{pretext}，以高息为诱饵，"
    "向{victim}等社会不特定对象非法集资共计人民币{amount}元，"
    "后用于{use}并逃匿。"
]
FACT_TEMPLATES["开设赌场罪"] = [
    "{time}，被告人{name}在{location}，"
    "租赁房屋作为赌博场所，通过{method}等方式组织他人赌博，"
    "从中抽头渔利共计人民币{amount}元。"
]
FACT_TEMPLATES["侵犯著作权罪"] = [
    "{time}，被告人{name}在{location}，"
    "未经著作权人许可，通过{method}等方式复制发行他人作品{count}件，"
    "非法经营数额共计人民币{amount}元。"
]
FACT_TEMPLATES["非法经营罪"] = [
    "{time}，被告人{name}在{location}，"
    "未取得{license_name}许可证，擅自从事{thing}经营活动，"
    "非法经营数额共计人民币{amount}元。"
]
FACT_TEMPLATES["组织、领导传销活动罪"] = [
    "{time}，被告人{name}在{location}，"
    "以{company}的名义，要求参加者以缴纳费用等方式获得加入资格，"
    "并按照一定顺序组成层级，直接或间接以发展人员的数量作为计酬依据，"
    "引诱、胁迫参加者继续发展他人参加，骗取财物共计人民币{amount}元。"
]


def fill_template(charge_name: str) -> str:
    """根据罪名随机填充事实模板。"""
    templates = FACT_TEMPLATES.get(
        charge_name,
        ["{time}，被告人{name}在{location}实施{charge}行为。"]
    )
    template = rng.choice(templates)

    params = {
        "time": f"{rng.randint(2020, 2025)}年{rng.randint(1,12)}月{rng.randint(1,28)}日",
        "name": rng.choice(NAMES),
        "victim": rng.choice([n for n in NAMES if n != "已选"]),
        "location": rng.choice(LOCATIONS),
        "place": rng.choice(["某小区", "某商场", "某写字楼", "某住宅", "某仓库"]),
        "container": rng.choice(["车内", "保险柜内", "办公桌抽屉内", "随身背包内"]),
        "amount": f"{rng.randint(1, 500):,}" if rng.random() < 0.5 else f"{rng.randint(1, 200)}万",
        "items": rng.choice(["手机一部", "笔记本电脑一台", "金项链一条", "手表一只", "高档烟酒若干"]),
        "item_value": f"{rng.randint(1000,100000):,}",
        "channel": rng.choice(["微信", "电话", "QQ", "短信", "互联网平台"]),
        "pretext": rng.choice(["能为他人办理取保候审", "有高收益理财产品", "能够低价购买房产",
                               "可以安排子女入学", "有能力帮助中标项目", "能够办理贷款"]),
        "use": rng.choice(["个人挥霍", "偿还债务", "购买房产", "投资亏损", "赌博"]),
        "tool": rng.choice(["刀", "仿真枪", "棍棒", "匕首"]),
        "weapon": rng.choice(["菜刀", "木棍", "砖头", "铁管", "水果刀"]),
        "level": rng.choice(["轻伤二级", "轻伤一级", "重伤二级"]),
        "bank": rng.choice(BANKS),
        "card": f"6222********{rng.randint(1000,9999)}",
        "position": rng.choice(["某局局长", "某国企总经理", "某街道办主任", "某银行支行行长"]),
        "wisher": rng.choice(NAMES),
        "thing": rng.choice(["工程承揽", "项目审批", "职务晋升", "资金拨付", "资质审批"]),
        "vehicle": rng.choice(["小型轿车", "重型货车", "摩托车", "轻型客车"]),
        "result": rng.choice(["死亡", "重伤", "轻伤"]),
        "alcohol": rng.randint(100, 300),
        "company": rng.choice(["某某投资有限公司", "某某信息科技有限公司", "某某文化传媒有限公司"]),
        "method": rng.choice(["口口相传", "微信群发", "发放宣传单", "召开推介会", "电话推销"]),
        "count": rng.randint(5000, 500000),
        "substance": rng.choice(["甲基苯丙胺", "海洛因", "氯胺酮"]),
        "substance2": rng.randint(10, 500),
        "action": rng.choice(["随意殴打他人", "任意损毁公私财物", "在公共场所起哄闹事",
                              "追逐拦截他人", "强拿硬要"]),
        "license_name": rng.choice(["烟草专卖", "药品经营", "证券", "期货", "保险"]),
        "charge": charge_name,
    }
    return template.format(**params)


def generate_evidence_list(charge_name: str, decision_type: str) -> list[dict]:
    """生成结构化证据列表（PDP-Bench 格式）。"""
    evidence = []
    # 书证
    evidence.append({
        "type": "书证",
        "name": "受案登记表、立案决定书",
        "description": "证实案件来源及立案侦查经过。",
        "collector": rng.choice(["公安局刑警大队", "经侦支队"]),
        "collect_date": f"{rng.randint(2020,2025)}-{rng.randint(1,12):02d}-{rng.randint(1,28):02d}",
    })
    evidence.append({
        "type": "书证",
        "name": "户籍证明",
        "description": f"证实被告人的身份信息及刑事责任年龄。",
        "collector": "公安局户政科",
        "collect_date": "",
    })
    # 证人证言
    for _ in range(rng.randint(1, 3)):
        evidence.append({
            "type": "证人证言",
            "name": f"{rng.choice(NAMES)}的证言",
            "description": f"证实{rng.choice(['案发经过', '被告人作案情况', '赃款去向', '被告人行踪'])}。",
            "collector": "公安局刑警大队",
            "collect_date": f"{rng.randint(2020,2025)}-{rng.randint(1,12):02d}-{rng.randint(1,28):02d}",
        })
    # 被害人陈述
    if decision_type != "SNP":
        evidence.append({
            "type": "被害人陈述",
            "name": f"{rng.choice(NAMES)}的陈述",
            "description": f"证实被{rng.choice(['伤害', '诈骗', '盗窃', '抢劫'])}的经过及损失情况。",
            "collector": "公安局刑警大队",
            "collect_date": "",
        })
    # 被告人供述
    if decision_type != "SNP":
        evidence.append({
            "type": "犯罪嫌疑人供述和辩解",
            "name": "讯问笔录",
            "description": "被告人对犯罪事实的供述与辩解。",
            "collector": "公安局刑警大队",
            "collect_date": "",
        })
    # 鉴定意见
    if charge_name in ["故意伤害罪", "危险驾驶罪", "交通肇事罪"]:
        evidence.append({
            "type": "鉴定意见",
            "name": "司法鉴定意见书",
            "description": f"证实{rng.choice(['损伤程度', '血液酒精含量', '死亡原因'])}的鉴定结论。",
            "collector": "司法鉴定中心",
            "collect_date": "",
        })
    # 电子数据
    if charge_name in ["诈骗罪", "帮助信息网络犯罪活动罪", "侵犯公民个人信息罪",
                       "非法吸收公众存款罪", "集资诈骗罪"]:
        evidence.append({
            "type": "电子数据",
            "name": "电子数据检查笔录",
            "description": f"证实{rng.choice(['银行流水', '微信聊天记录', '转账记录', '服务器日志'])}的提取与固定情况。",
            "collector": "网安支队",
            "collect_date": "",
        })
    # 物证
    if charge_name in ["故意伤害罪", "抢劫罪", "盗窃罪"]:
        evidence.append({
            "type": "物证",
            "name": "物证登记表",
            "description": f"证实{rng.choice(['作案工具', '被盗物品', '现场提取的痕迹物证'])}的扣押与固定情况。",
            "collector": "公安局刑警大队",
            "collect_date": "",
        })

    return evidence


def generate_case(index: int) -> dict:
    """生成一条完整案件记录（对应 cases 表 + evidence_chunks 表）。"""
    charge = rng.choices(CHARGES, k=1)[0]
    decision = rng.choices(
        DECISIONS,
        weights=[d["ratio"] for d in DECISIONS],
        k=1
    )[0]

    case = {
        "case_id": str(uuid.uuid4()),
        "case_name": f"({index:04d}){rng.choice(NAMES)}{charge['name']}案",
        "case_number": f"京{rng.randint(100,999)}刑初{rng.randint(1,9999)}号",
        "case_type": "刑事",
        "description": "",
        "source": "synthetic",
        "source_id": f"synth-{index:05d}",
        "charge": charge["name"],
        "article": charge["article"],
        "decision_type": decision["type"],
        "decision_label": decision["label"],
        "fact": fill_template(charge["name"]),
        "term_months": rng.randint(charge["min_term"], charge["max_term"]),
        "evidence_list": generate_evidence_list(charge["name"], decision["type"]),
        "created_at": (datetime.utcnow() - timedelta(days=rng.randint(1, 365))).isoformat(),
    }
    return case


def main(count: int = 100):
    cases = []
    for i in range(count):
        cases.append(generate_case(i + 1))

    # 统计
    charges_count = {}
    decisions_count = {}
    for c in cases:
        charges_count[c["charge"]] = charges_count.get(c["charge"], 0) + 1
        decisions_count[c["decision_label"]] = decisions_count.get(c["decision_label"], 0) + 1

    print(f"生成 {len(cases)} 条案件")
    print(f"\n罪名分布:")
    for ch, n in sorted(charges_count.items(), key=lambda x: -x[1]):
        print(f"  {ch}: {n}")
    print(f"\n决定类型分布:")
    for d, n in decisions_count.items():
        print(f"  {d}: {n}")

    # 写入 JSONL
    train_size = int(count * 0.7)
    val_size = int(count * 0.15)

    for split, start, end in [("train", 0, train_size),
                               ("validation", train_size, train_size + val_size),
                               ("test", train_size + val_size, count)]:
        out = DATA_DIR / f"{split}.jsonl"
        with open(out, "w", encoding="utf-8") as f:
            for c in cases[start:end]:
                f.write(json.dumps(c, ensure_ascii=False) + "\n")
        print(f"\n{out.name}: {end - start} 条")

    print(f"\n数据在: {DATA_DIR}")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--count", type=int, default=100)
    args = p.parse_args()
    main(args.count)
