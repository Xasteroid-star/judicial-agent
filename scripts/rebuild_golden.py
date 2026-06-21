"""重建 golden_cases.json，确保所有字符串正确转义。"""
import json
from pathlib import Path

cases = [
    # ── 原有 5 条 ──
    {
        "case_id": "golden-001",
        "case_name": "故意伤害案（证据完整）",
        "query": "该案证据链是否完整？",
        "case_context": "2024年王某用刀刺伤李某，有监控录像、DNA鉴定、目击证人3人、凶器已提取、被害人陈述、被告人供述一致。",
        "expected": {
            "evidence_chain_complete": True,
            "confidence_min": 0.80, "confidence_max": None,
            "expected_citations": ["鉴定意见", "证人证言", "物证", "监控录像"],
            "expected_legal_basis": ["刑法第234条"],
            "should_contain": [],
            "should_not_contain": ["证据不足", "无法认定"],
        },
    },
    {
        "case_id": "golden-002",
        "case_name": "盗窃案（证据严重不足）",
        "query": "该案能否定罪？",
        "case_context": "2024年3月某小区发生入室盗窃，仅有被害人报案记录，无现场勘查、无监控、无指纹、无目击证人。",
        "expected": {
            "evidence_chain_complete": False,
            "confidence_min": None, "confidence_max": 0.50,
            "expected_citations": [],
            "expected_legal_basis": ["刑法第264条"],
            "should_contain": ["证据不足", "无法认定", "补充侦查"],
            "should_not_contain": ["证据确实充分"],
        },
    },
    {
        "case_id": "golden-003",
        "case_name": "诈骗案（含非法证据主张）",
        "query": "能否排除非法证据？",
        "case_context": "2024年张某电信诈骗案，有银行流水、微信记录、被害人陈述。张某辩称讯问时遭威胁。讯问录音录像缺失。",
        "expected": {
            "evidence_chain_complete": True,
            "confidence_min": 0.40, "confidence_max": 0.75,
            "expected_citations": ["银行流水", "微信记录"],
            "expected_legal_basis": ["排除非法证据规定"],
            "should_contain": ["录音录像", "不能排除"],
            "should_not_contain": ["证据确实充分"],
        },
    },
    {
        "case_id": "golden-004",
        "case_name": "帮信罪（电子数据为主）",
        "query": "电子数据证据是否充分？",
        "case_context": "赵某出售银行卡给诈骗团伙使用。有银行卡交易流水、微信聊天记录、IP登录日志、服务器日志。无口供。",
        "expected": {
            "evidence_chain_complete": True,
            "confidence_min": 0.70, "confidence_max": None,
            "expected_citations": ["交易流水", "聊天记录", "登录日志"],
            "expected_legal_basis": ["电子数据规定", "刑法第287条之二"],
            "should_contain": ["电子数据", "完整性"],
            "should_not_contain": ["证据不足"],
        },
    },
    {
        "case_id": "golden-005",
        "case_name": "毒品案（仅有口供）",
        "query": "仅有口供能否定罪？",
        "case_context": "王某被举报贩毒，仅有本人供述和一名吸毒人员指认。未查获毒品实物，无交易记录，无监控。",
        "expected": {
            "evidence_chain_complete": False,
            "confidence_min": None, "confidence_max": 0.40,
            "expected_citations": [],
            "expected_legal_basis": ["刑诉法第55条"],
            "should_contain": ["不能认定", "口供", "补强"],
            "should_not_contain": ["证据确实充分", "可以认定"],
        },
    },
    # ── 新增 10 条 ──
    {
        "case_id": "golden-006",
        "case_name": "故意伤害案（正当防卫主张）",
        "query": "王某的行为是否构成正当防卫？证据能否支持这一主张？",
        "case_context": "2024年6月，王某在酒吧与李某发生口角，李某先持酒瓶砸向王某头部（有监控录像证实）。王某夺过酒瓶反击，致李某轻伤二级。王某辩称正当防卫。监控录像完整记录了全过程。现场证人张某、赵某均证实李某先动手。伤情鉴定显示王某头部有轻微伤，李某手臂有划伤。",
        "expected": {
            "evidence_chain_complete": True,
            "confidence_min": 0.80, "confidence_max": 0.95,
            "expected_citations": ["监控录像", "证人证言", "鉴定意见"],
            "expected_legal_basis": ["刑法第20条"],
            "should_contain": ["正当防卫", "防卫行为", "不法侵害"],
            "should_not_contain": ["证据不足", "无法认定"],
        },
    },
    {
        "case_id": "golden-007",
        "case_name": "共同贪污案（多人多层级）",
        "query": "能否认定三人构成贪污罪共犯？",
        "case_context": "2023年，某县财政局副局长赵某伙同会计孙某、出纳钱某，通过虚列项目支出方式贪污公款180万元。赵某指使孙某伪造项目合同和发票，钱某将款项转入个人账户后分配。三人到案后：赵某拒不认罪，孙某主动供述并提供账本记录，钱某供认不讳并退缴全部赃款。另有银行流水、虚假合同原件、审计报告佐证。",
        "expected": {
            "evidence_chain_complete": True,
            "confidence_min": 0.75, "confidence_max": 0.90,
            "expected_citations": ["银行流水", "合同", "审计报告", "账本记录"],
            "expected_legal_basis": ["刑法第382条", "刑法第383条"],
            "should_contain": ["共同犯罪", "贪污"],
            "should_not_contain": ["证据不足", "无法认定"],
        },
    },
    {
        "case_id": "golden-008",
        "case_name": "交通肇事案（肇事逃逸）",
        "query": "能否认定周某构成交通肇事罪且存在逃逸情节？",
        "case_context": "2024年9月，周某驾驶轿车在国道上超速行驶，撞倒行人吴某后驾车逃离。吴某经抢救无效死亡。现场有刹车痕迹、车辆碎片（已提取），交管部门出具事故责任认定书认定周某全责。路口监控拍到肇事车辆号牌。车辆维修记录显示案发次日周某更换了前保险杠。但周某辩称不知道撞了人，以为碰到了路障。",
        "expected": {
            "evidence_chain_complete": True,
            "confidence_min": 0.70, "confidence_max": 0.88,
            "expected_citations": ["事故责任认定书", "监控", "刹车痕迹", "车辆碎片", "维修记录"],
            "expected_legal_basis": ["刑法第133条"],
            "should_contain": ["逃逸", "全责", "死亡"],
            "should_not_contain": ["证据不足"],
        },
    },
    {
        "case_id": "golden-009",
        "case_name": "受贿案（仅有言语证据）",
        "query": "仅凭行贿人和受贿人的口供能否定罪？",
        "case_context": "2023年，某国企采购部经理陈某被举报收受供应商刘某回扣50万元。仅有刘某的证言（称在某咖啡厅将现金交给陈某）和陈某的口供（承认收钱但称是借款且有借条）。无转账记录、无监控录像、无其他证人。借条经鉴定是事发后补写的（纸张生产日期晚于借条日期）。",
        "expected": {
            "evidence_chain_complete": True,
            "confidence_min": 0.50, "confidence_max": 0.72,
            "expected_citations": ["鉴定意见", "借条", "口供"],
            "expected_legal_basis": ["刑法第385条"],
            "should_contain": ["口供", "补强", "不能仅凭"],
            "should_not_contain": ["证据确实充分"],
        },
    },
    {
        "case_id": "golden-010",
        "case_name": "贩毒案（仅有间接证据）",
        "query": "仅有间接证据能否认定贩毒罪？",
        "case_context": "2024年，警方在张某住所查获冰毒50克，但张某辩称毒品是朋友暂放的，自己不知情。警方提取的证据：1) 张某手机中有大量[出货][拿货]等黑话聊天记录；2) 多名吸毒人员指认从张某处购买毒品；3) 张某银行账户有频繁大额资金汇入；4) 未在毒品包装上提取到张某指纹。",
        "expected": {
            "evidence_chain_complete": True,
            "confidence_min": 0.60, "confidence_max": 0.78,
            "expected_citations": ["聊天记录", "证人证言", "银行流水"],
            "expected_legal_basis": ["刑法第347条"],
            "should_contain": ["间接证据", "印证", "不能仅凭口供"],
            "should_not_contain": ["证据确实充分"],
        },
    },
    {
        "case_id": "golden-011",
        "case_name": "强奸案（被告人翻供）",
        "query": "被害人陈述与被告人翻供冲突时，证据链是否完整？",
        "case_context": "2024年4月，被害人杨某报案称被同事郑某在KTV包间内强奸。关键证据：1) 被害人杨某的陈述，详细描述了事发经过；2) 案发后24小时内的伤情鉴定显示杨某手腕有抓痕、大腿内侧有淤青；3) KTV服务员证实郑某和杨某一同进入包间，约30分钟后杨某哭着跑出；4) 郑某先承认发生性关系（称双方自愿），后翻供称根本没有发生关系，只是在包间聊天；5) 包间内无监控。DNA检测因时间间隔未检出。",
        "expected": {
            "evidence_chain_complete": True,
            "confidence_min": 0.55, "confidence_max": 0.80,
            "expected_citations": ["被害人陈述", "伤情鉴定", "证人证言"],
            "expected_legal_basis": ["刑法第236条"],
            "should_contain": ["翻供", "被害人陈述", "伤情"],
            "should_not_contain": ["证据确实充分", "可以认定"],
        },
    },
    {
        "case_id": "golden-012",
        "case_name": "未成年人抢劫案（年龄存疑）",
        "query": "被告人年龄存疑时，证据链能否支持定罪？",
        "case_context": "2024年7月，刘某（自报年龄17岁）伙同他人在网吧门口抢劫一名学生，抢得手机一部和现金300元。刘某被抓获后，公安机关提取的证据：1) 被害人辨认笔录，确认刘某就是抢劫者；2) 同案犯供述一致，均指认刘某动手抢了手机；3) 案发现场监控录像清晰记录了刘某的面容和行为；4) 刘某的户籍登记出生日期为2007年2月，但刘某母亲称实际出生日期是2007年12月（晚10个月），系当年为了孩子早上学虚报了年龄。无出生医学证明，无法做骨龄鉴定（已超龄）。",
        "expected": {
            "evidence_chain_complete": True,
            "confidence_min": 0.65, "confidence_max": 0.85,
            "expected_citations": ["辨认笔录", "同案犯供述", "监控录像"],
            "expected_legal_basis": ["刑法第263条", "刑法第17条"],
            "should_contain": ["未成年人", "年龄", "户籍"],
            "should_not_contain": ["证据不足", "无法认定"],
        },
    },
    {
        "case_id": "golden-013",
        "case_name": "合同诈骗案（证据充分且完整）",
        "query": "该案证据链是否完整？能否认定合同诈骗罪？",
        "case_context": "2023年，某贸易公司法定代表人何某以虚假的仓单作抵押，与某银行贷款2000万元后失联。经查：1) 仓单对应的货物根本不存在，仓储公司出具了证明；2) 银行转账记录显示2000万元进入何某公司账户后迅速被转出至多个境外账户；3) 何某出境记录显示贷款到账后第三天即飞往境外；4) 公司员工、财务人员均作证何某是唯一决策人；5) 何某未被抓获，缺席审理。",
        "expected": {
            "evidence_chain_complete": True,
            "confidence_min": 0.85, "confidence_max": 0.95,
            "expected_citations": ["仓单", "仓储公司证明", "银行转账记录", "证人证言", "出境记录"],
            "expected_legal_basis": ["刑法第224条"],
            "should_contain": ["虚假仓单", "非法占有"],
            "should_not_contain": ["证据不足", "无法认定"],
        },
    },
    {
        "case_id": "golden-014",
        "case_name": "故意杀人案（证据矛盾）",
        "query": "现场证据与目击证言矛盾时，证据链是否成立？",
        "case_context": "2024年1月，某小区发生命案，死者陈某胸部中刀死亡。关键证据：1) 现场提取一把带血匕首，匕首上检出被告人马某的指纹和死者的血液；2) 法医鉴定死者胸部创口与匕首吻合；3) 唯一目击证人邻居刘某称[看到一个穿黑色外套的男子从死者家中跑出]，但马某当天穿着灰色羽绒服（有多名证人证实）；4) 小区门口监控显示案发时段马某确实进入了该小区，但未拍到离开画面；5) 马某辩称当天去找陈某还钱，到的时候陈某已经死亡，因为害怕才离开。",
        "expected": {
            "evidence_chain_complete": True,
            "confidence_min": 0.55, "confidence_max": 0.75,
            "expected_citations": ["匕首", "指纹", "法医鉴定", "监控", "证人证言"],
            "expected_legal_basis": ["刑法第232条"],
            "should_contain": ["矛盾", "不能排除", "需进一步核实"],
            "should_not_contain": ["证据确实充分", "足以认定"],
        },
    },
    {
        "case_id": "golden-015",
        "case_name": "跨境电信诈骗案（境外证据为主）",
        "query": "境外获取的电子证据能否支撑全案定罪？",
        "case_context": "2024年，某跨境电信诈骗团伙在缅甸设立窝点，对国内实施诈骗，涉案金额超5000万元。侦查取证情况：1) 缅甸警方配合搜查了诈骗窝点，查获电脑、手机、话术剧本等（移交时有交接清单和执法录像）；2) 从查获的电脑中提取了完整的诈骗话术、公民个人信息、转账记录等电子数据（已依法做电子数据检验笔录）；3) 已回国归案的3名底层话务员供述了在缅甸参与诈骗的事实，但均称[老板没抓到，我们只是打工的]；4) 多名国内被害人报案并提供了转账记录；5) 主犯仍在逃。",
        "expected": {
            "evidence_chain_complete": True,
            "confidence_min": 0.70, "confidence_max": 0.88,
            "expected_citations": ["电子数据", "检验笔录", "被告人供述", "移交清单", "执法录像"],
            "expected_legal_basis": ["刑法第266条", "电子数据规定"],
            "should_contain": ["境外证据", "电子数据", "主犯在逃"],
            "should_not_contain": ["证据不足"],
        },
    },
]

# 序列化为 JSON，确保 ensure_ascii=False 产生可读中文
fpath = Path(__file__).resolve().parent.parent / "eval" / "golden_cases.json"
text = json.dumps(cases, ensure_ascii=False, indent=2)
fpath.write_text(text, "utf-8")
print(f"OK: {len(cases)} cases written to {fpath}")
