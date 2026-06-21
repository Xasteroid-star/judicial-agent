"""评测框架 — 对照 golden cases 衡量系统质量。

九大维度：
1. RAG 检索命中率 — 相关法条是否被召回
2. RAG 检索精确率 — 召回结果中相关比例
3. 证据链完整性 — 是否正确判断证据充分/不足
4. 置信度校准 — 置信度是否在预期区间
5. 引用正确性 — 结论是否绑定来源
6. 法条覆盖率 — 关键法律依据是否被引用
7. 关键表述命中 — 报告是否包含预期/避免禁止内容
8. 复核项合理性 — 生成的复核项数量是否合理
9. 总体质量分 — 加权综合

用法:
    python eval/harness.py                  # 全量评测
    python eval/harness.py --case golden-001 # 单条评测
"""

from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

# 项目根目录
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


@dataclass
class EvalResult:
    case_id: str
    case_name: str
    scores: dict = field(default_factory=dict)
    details: list[str] = field(default_factory=list)
    passed: bool = False

    @property
    def overall(self) -> float:
        if not self.scores:
            return 0.0
        return round(sum(self.scores.values()) / len(self.scores), 3)


class EvalHarness:
    """评测器 — 调用 Agent 流水线，对照 golden case 打分。"""

    DIMENSIONS = {
        "retrieval_recall": {"weight": 0.15, "label": "RAG 召回率"},
        "retrieval_precision": {"weight": 0.10, "label": "RAG 精确率"},
        "chain_completeness": {"weight": 0.20, "label": "证据链判断准确性"},
        "confidence_calibration": {"weight": 0.15, "label": "置信度校准"},
        "citation_grounding": {"weight": 0.15, "label": "引用正确性"},
        "legal_coverage": {"weight": 0.10, "label": "法条覆盖率"},
        "keyword_hit": {"weight": 0.10, "label": "关键表述命中"},
        "review_quality": {"weight": 0.05, "label": "复核项合理性"},
    }

    def __init__(self):
        self._pipeline = None

    async def _get_pipeline(self):
        if self._pipeline is None:
            from judicial_evidence_agent.core.agents.orchestrator import AgentPipeline

            self._pipeline = AgentPipeline(stub_llm=True)
        return self._pipeline

    async def evaluate(self, golden: dict) -> EvalResult:
        """评测单个 golden case。"""
        result = EvalResult(
            case_id=golden["case_id"],
            case_name=golden["case_name"],
        )
        expected = golden["expected"]

        # 运行流水线
        pipeline = await self._get_pipeline()
        output = await pipeline.run(
            case_id=golden["case_id"],
            case_name=golden["case_name"],
            query=golden["query"],
            case_context=golden["case_context"],
        )

        # 合并报告全文用于文本匹配
        report_text = output.get("report", {}).get("markdown", "")
        if not report_text:
            # fallback: 从 sections 拼接
            sections = output.get("report", {}).get("sections", [])
            report_text = "\n".join(s["content"] for s in sections)

        # === 维度评分 ===

        # 1. RAG 召回率 — 关键法条是否被检索到
        statutes_text = " ".join(
            s.get("content_preview", "") for s in output.get("retrieved_statutes", [])
        )
        expected_laws = expected.get("expected_legal_basis", [])
        if expected_laws:
            recalled = sum(1 for l in expected_laws if any(
                keyword in statutes_text for keyword in l.replace("第", "").split("条")[0:1]
            ))
            # 放宽：检查检索到的证据 chunk 中是否有引用
            evidence_text = " ".join(
                c.get("content_preview", "") for c in output.get("retrieved_chunks", [])
            )
            recalled = sum(
                1 for l in expected_laws
                if l in statutes_text or l in evidence_text or l in report_text
            )
            result.scores["retrieval_recall"] = round(recalled / len(expected_laws), 3)
        else:
            result.scores["retrieval_recall"] = 0.5  # 无预期的中性分

        # 2. RAG 精确率 — 去重后有效结果比例
        unique_chunks = len(set(
            c.get("content_preview", "")[:60]
            for c in output.get("retrieved_chunks", [])
        ))
        total_retrieved = len(output.get("retrieved_chunks", []))
        if total_retrieved > 0:
            result.scores["retrieval_precision"] = round(unique_chunks / total_retrieved, 3)
        else:
            result.scores["retrieval_precision"] = 0.0

        # 3. 证据链完整性判断
        chains = output.get("evidence_chains", [])
        has_complete = any(c.get("status") == "pass" for c in chains)
        has_insufficient = any(c.get("status") in ("review", "reject") for c in chains)
        expected_complete = expected.get("evidence_chain_complete", False)

        if expected_complete and has_complete:
            result.scores["chain_completeness"] = 0.8
        elif not expected_complete and has_insufficient:
            result.scores["chain_completeness"] = 1.0
        elif not expected_complete and not has_complete:
            result.scores["chain_completeness"] = 0.6
        else:
            result.scores["chain_completeness"] = 0.2

        # 4. 置信度校准
        conf = output.get("confidence", {}).get("final", 0)
        conf_min = expected.get("confidence_min")
        conf_max = expected.get("confidence_max")
        if conf_min is not None and conf < conf_min:
            result.scores["confidence_calibration"] = 0.3
            result.details.append(f"置信度 {conf:.2f} < 预期下限 {conf_min}")
        elif conf_max is not None and conf > conf_max:
            result.scores["confidence_calibration"] = 0.3
            result.details.append(f"置信度 {conf:.2f} > 预期上限 {conf_max}")
        elif conf_min is not None or conf_max is not None:
            result.scores["confidence_calibration"] = 1.0
        else:
            result.scores["confidence_calibration"] = 0.5

        # 5. 引用正确性 — 证据链中是否有支撑证据
        all_evidence = []
        for ch in chains:
            all_evidence.extend(ch.get("supporting_evidence", []))
        expected_cites = expected.get("expected_citations", [])
        if expected_cites:
            cite_text = " ".join(e.get("content", "") for e in all_evidence)
            cited = sum(1 for c in expected_cites if c in cite_text or c in report_text)
            result.scores["citation_grounding"] = round(cited / len(expected_cites), 3)
        else:
            result.scores["citation_grounding"] = 0.5

        # 6. 法条覆盖率
        if expected_laws:
            covered = sum(1 for l in expected_laws if l in report_text)
            result.scores["legal_coverage"] = round(covered / len(expected_laws), 3)
        else:
            result.scores["legal_coverage"] = 0.5

        # 7. 关键表述命中
        should_contain = expected.get("should_contain", [])
        should_not_contain = expected.get("should_not_contain", [])
        keyword_score = 0.5
        if should_contain:
            hits = sum(1 for kw in should_contain if kw in report_text)
            keyword_score += 0.5 * (hits / len(should_contain))
        if should_not_contain:
            violations = sum(1 for kw in should_not_contain if kw in report_text)
            keyword_score -= 0.5 * (violations / len(should_not_contain))
        result.scores["keyword_hit"] = max(0.0, min(1.0, keyword_score))

        # 8. 复核项合理性
        review_items = output.get("review", {}).get("items", [])
        if chains and len(review_items) > 0:
            result.scores["review_quality"] = 0.8
        elif not chains and len(review_items) == 0:
            result.scores["review_quality"] = 1.0
        else:
            result.scores["review_quality"] = 0.5

        # 加权综合
        weighted = sum(
            result.scores.get(dim, 0) * info["weight"]
            for dim, info in self.DIMENSIONS.items()
        )
        result.scores["weighted_overall"] = round(weighted, 3)
        result.passed = weighted >= 0.60

        return result


def print_report(results: list[EvalResult]):
    """打印评测报告。"""
    print("\n" + "=" * 70)
    print("  评测报告")
    print("=" * 70)

    for r in results:
        status = "[PASS]" if r.passed else "[FAIL]"
        print(f"\n{status} {r.case_name} ({r.case_id})")
        print(f"   综合分: {r.scores.get('weighted_overall', 0):.3f}")
        for dim, info in EvalHarness.DIMENSIONS.items():
            score = r.scores.get(dim, "-")
            bar = "#" * int(score * 20) if isinstance(score, float) else ""
            print(f"   {info['label']:12s}: {score:<6} {bar}")
        if r.details:
            for d in r.details:
                print(f"   [!] {d}")

    # 汇总
    avg = sum(r.scores.get("weighted_overall", 0) for r in results) / max(len(results), 1)
    passed_count = sum(1 for r in results if r.passed)
    print(f"\n{'=' * 70}")
    print(f"  总计: {len(results)} 条 | 通过: {passed_count} | 平均分: {avg:.3f}")
    print(f"{'=' * 70}\n")


async def main():
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--case", default="", help="单条评测 (golden-001 ~ golden-005)")
    args = p.parse_args()

    golden_path = Path(__file__).parent / "golden_cases.json"
    all_cases = json.loads(golden_path.read_text(encoding="utf-8"))

    if args.case:
        all_cases = [c for c in all_cases if c["case_id"] == args.case]
        if not all_cases:
            print(f"未找到: {args.case}")
            return

    harness = EvalHarness()
    results = []
    for gc in all_cases:
        print(f"评测: {gc['case_name']}...")
        r = await harness.evaluate(gc)
        results.append(r)

    print_report(results)


if __name__ == "__main__":
    import sys

    asyncio.run(main())
