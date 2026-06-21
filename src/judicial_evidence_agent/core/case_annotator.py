"""案例自动标注模块。

LLM 自动提取核心争议、罪名、适用法条、证据类型。
输出写入 annotated_cases 表，人工复核后确认入库。
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field

CASE_ANNOTATION_PROMPT = """你是一位法律案件标注员。基于以下案件信息，提取结构化标注。

## 标注字段
1. core_disputes: 核心争议点（数组，如 ["刑讯逼供", "证据不足", "自首认定"]）
2. charges: 涉嫌罪名（数组，如 ["故意伤害罪"]）
3. applicable_articles: 适用法条（数组，如 ["刑法第234条", "刑诉法第56条"]）
4. evidence_types: 涉及的证据类型（数组，如 ["鉴定意见", "证人证言", "电子数据"]）
5. case_summary: 案情摘要（50字以内）
6. judgment_key: 裁判要旨（30字以内）

## 输出格式（纯 JSON，不要其他文字）
{
  "core_disputes": [...],
  "charges": [...],
  "applicable_articles": [...],
  "evidence_types": [...],
  "case_summary": "...",
  "judgment_key": "..."
}"""


@dataclass
class AnnotatedCase:
    case_id: str
    case_name: str
    court: str = ""
    decision_date: str = ""
    core_disputes: list[str] = field(default_factory=list)
    charges: list[str] = field(default_factory=list)
    applicable_articles: list[str] = field(default_factory=list)
    evidence_types: list[str] = field(default_factory=list)
    case_summary: str = ""
    judgment_key: str = ""
    full_text_url: str = ""
    labeled_by: str = "AI"
    review_status: str = "pending"


class CaseAnnotator:
    """案例自动标注器。

    用法:
        annotator = CaseAnnotator()
        result = await annotator.annotate(case_text)
        annotator.save(result)
    """

    def __init__(self, db_path: str = "data/judicial_evidence.db"):
        self._db_path = db_path
        self._llm = None

    async def _get_llm(self):
        if self._llm is None:
            from judicial_evidence_agent.core.llm import LLMClient
            self._llm = LLMClient()
        return self._llm

    async def annotate(self, case_id: str, case_name: str, case_text: str) -> AnnotatedCase:
        """LLM 自动标注一条案例。"""
        llm = await self._get_llm()

        prompt = f"""## 案件信息
案件名称：{case_name}
案件内容：
{case_text[:3000]}

## 任务
{CASE_ANNOTATION_PROMPT}"""

        try:
            response = await llm.generate(
                prompt=prompt,
                system="你是法律案件标注专家。只输出 JSON，不要其他内容。",
                max_tokens=1024,
                temperature=0.1,
            )
            # 提取 JSON
            data = self._parse_json(response)
        except Exception:
            # LLM 不可用时用规则降级
            data = self._rule_based_annotate(case_text)

        return AnnotatedCase(
            case_id=case_id,
            case_name=case_name,
            core_disputes=data.get("core_disputes", []),
            charges=data.get("charges", []),
            applicable_articles=data.get("applicable_articles", []),
            evidence_types=data.get("evidence_types", []),
            case_summary=data.get("case_summary", ""),
            judgment_key=data.get("judgment_key", ""),
            labeled_by="AI",
            review_status="pending",
        )

    @staticmethod
    def _parse_json(text: str) -> dict:
        """从 LLM 输出中提取 JSON。"""
        import re
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            return json.loads(match.group())
        return {}

    @staticmethod
    def _rule_based_annotate(text: str) -> dict:
        """规则降级：关键词匹配做基础标注。"""
        disputes = []
        if "刑讯" in text or "逼供" in text:
            disputes.append("刑讯逼供")
        if "证据不足" in text or "无法认定" in text:
            disputes.append("证据不足")
        if "自首" in text:
            disputes.append("自首认定")
        if "正当防卫" in text:
            disputes.append("正当防卫")

        charges = []
        for kw, charge in [
            ("伤害", "故意伤害罪"), ("杀人", "故意杀人罪"),
            ("盗窃", "盗窃罪"), ("诈骗", "诈骗罪"),
            ("抢劫", "抢劫罪"), ("毒品", "走私贩卖运输制造毒品罪"),
        ]:
            if kw in text:
                charges.append(charge)

        evidence_types = []
        for kw, ev in [
            ("鉴定", "鉴定意见"), ("证人", "证人证言"),
            ("监控", "视听资料"), ("微信", "电子数据"),
            ("聊天记录", "电子数据"), ("银行流水", "电子数据"),
            ("DNA", "鉴定意见"), ("指纹", "物证"),
        ]:
            if kw in text and ev not in evidence_types:
                evidence_types.append(ev)

        return {
            "core_disputes": disputes,
            "charges": charges,
            "applicable_articles": [],
            "evidence_types": evidence_types,
            "case_summary": text[:50],
            "judgment_key": "",
        }

    def save(self, case: AnnotatedCase) -> None:
        """保存标注结果到数据库。"""
        conn = sqlite3.connect(self._db_path)
        self._ensure_table(conn)

        conn.execute(
            """INSERT OR REPLACE INTO annotated_cases
               (case_id, case_name, court, decision_date,
                core_disputes, charges, applicable_articles, evidence_types,
                case_summary, judgment_key, full_text_url, labeled_by, review_status)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                case.case_id, case.case_name, case.court, case.decision_date,
                json.dumps(case.core_disputes, ensure_ascii=False),
                json.dumps(case.charges, ensure_ascii=False),
                json.dumps(case.applicable_articles, ensure_ascii=False),
                json.dumps(case.evidence_types, ensure_ascii=False),
                case.case_summary, case.judgment_key,
                case.full_text_url, case.labeled_by, case.review_status,
            ),
        )
        conn.commit()
        conn.close()

    @staticmethod
    def _ensure_table(conn: sqlite3.Connection) -> None:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS annotated_cases (
                case_id TEXT PRIMARY KEY,
                case_name TEXT NOT NULL,
                court TEXT DEFAULT '',
                decision_date TEXT DEFAULT '',
                core_disputes TEXT DEFAULT '[]',
                charges TEXT DEFAULT '[]',
                applicable_articles TEXT DEFAULT '[]',
                evidence_types TEXT DEFAULT '[]',
                case_summary TEXT DEFAULT '',
                judgment_key TEXT DEFAULT '',
                full_text_url TEXT DEFAULT '',
                labeled_by TEXT DEFAULT 'AI',
                review_status TEXT DEFAULT 'pending'
            );
        """)
        conn.commit()

    def search_by_dispute(self, dispute: str, limit: int = 10) -> list[dict]:
        """按核心争议检索相似案例。"""
        conn = sqlite3.connect(self._db_path)
        rows = conn.execute(
            """SELECT case_id, case_name, core_disputes, charges,
                      case_summary, judgment_key, review_status
               FROM annotated_cases
               WHERE core_disputes LIKE ? AND review_status = 'confirmed'
               LIMIT ?""",
            (f"%{dispute}%", limit),
        ).fetchall()
        conn.close()

        return [
            {
                "case_id": r[0], "case_name": r[1],
                "core_disputes": json.loads(r[2]),
                "charges": json.loads(r[3]),
                "case_summary": r[4], "judgment_key": r[5],
                "review_status": r[6],
            }
            for r in rows
        ]

    def get_pending_reviews(self) -> list[dict]:
        """获取待人工复核的标注列表。"""
        conn = sqlite3.connect(self._db_path)
        rows = conn.execute(
            """SELECT case_id, case_name, core_disputes, charges,
                      case_summary, labeled_by
               FROM annotated_cases WHERE review_status = 'pending'"""
        ).fetchall()
        conn.close()

        return [
            {
                "case_id": r[0], "case_name": r[1],
                "core_disputes": json.loads(r[2]),
                "charges": json.loads(r[3]),
                "case_summary": r[4], "labeled_by": r[5],
            }
            for r in rows
        ]

    def confirm(self, case_id: str) -> None:
        """人工确认标注。"""
        conn = sqlite3.connect(self._db_path)
        conn.execute(
            "UPDATE annotated_cases SET review_status='confirmed' WHERE case_id=?",
            (case_id,),
        )
        conn.commit()
        conn.close()

    def reject(self, case_id: str, reason: str = "") -> None:
        """驳回标注。"""
        conn = sqlite3.connect(self._db_path)
        conn.execute(
            "UPDATE annotated_cases SET review_status='rejected', judgment_key=? WHERE case_id=?",
            (f"驳回: {reason[:100]}", case_id),
        )
        conn.commit()
        conn.close()
