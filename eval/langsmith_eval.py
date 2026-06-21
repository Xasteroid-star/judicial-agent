"""LangSmith 评测入口 — DeepSeek 驱动的证据链 Agent。

用法:
    python eval/langsmith_eval.py                          # 跑全部 golden case
    python eval/langsmith_eval.py --experiment deepseek-v4-v2  # 自定义实验名
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

# 必须最先：把 .env 中的 LANGCHAIN_API_KEY 等注入 os.environ
from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from langsmith import evaluate, traceable
from judicial_evidence_agent.core.agents.orchestrator import AgentPipeline


# ═══════════════════════════════════════════════════════════
# Target Function
# ═══════════════════════════════════════════════════════════

pipeline = AgentPipeline(stub_llm=False)  # 走真实 DeepSeek API


@traceable(run_type="chain", name="evidence-chain-agent")
def target(inputs: dict) -> dict:
    """评测入口：接收 LangSmith Dataset 的 inputs，返回 outputs。"""

    async def _run():
        return await pipeline.run(
            query=inputs["query"],
            case_context=inputs.get("case_context", ""),
            case_name=inputs.get("case_name", ""),
        )

    result = asyncio.run(_run())

    # 提取置信度
    conf = result.get("confidence", {})
    final_conf = conf.get("final", 0)

    # 提取报告
    report_text = result.get("report", {}).get("markdown", "")

    print(f"\n  📋 [target] case={inputs.get('case_name', '?')[:20]}")
    print(f"     confidence={final_conf:.3f}, chains={len(result.get('evidence_chains', []))}")
    print(f"     report_len={len(report_text)} chars")

    return {
        "report_text": report_text,
        "confidence": final_conf,
        "evidence_chains": result.get("evidence_chains", []),
        "retrieved_chunks": result.get("retrieved_chunks", []),
        "confidence_detail": conf,
    }


# ═══════════════════════════════════════════════════════════
# Evaluators（4 个核心维度）
# ═══════════════════════════════════════════════════════════

def _parse_pipe(value: str) -> list[str]:
    return [s.strip() for s in value.split("|") if s.strip()]


def eval_citation(run, example) -> dict:
    """引用正确性：检查输出中命中了多少预期引用来源。"""
    expected_list = _parse_pipe(example.outputs.get("expected_citations", ""))
    if not expected_list:
        return {"key": "citation", "score": 0.5,
                "comment": "无预期引用，跳过"}

    report = run.outputs.get("report_text", "")
    hits = [c for c in expected_list if c in report]
    score = round(len(hits) / len(expected_list), 3)

    return {
        "key": "citation",
        "score": score,
        "comment": f"命中 {len(hits)}/{len(expected_list)}: {', '.join(hits) or '无'}",
    }


def eval_confidence(run, example) -> dict:
    """置信度校准：实际置信度是否在预期区间内。"""
    conf = float(run.outputs.get("confidence", 0))

    try:
        c_min = float(example.outputs.get("confidence_min", "")) if example.outputs.get("confidence_min", "") else None
        c_max = float(example.outputs.get("confidence_max", "")) if example.outputs.get("confidence_max", "") else None
    except (ValueError, TypeError):
        return {"key": "confidence", "score": 0.5, "comment": "预期区间未定义"}

    if c_min is not None and conf < c_min:
        return {"key": "confidence", "score": 0.0,
                "comment": f"置信度 {conf:.2f} < 预期下限 {c_min}"}
    if c_max is not None and conf > c_max:
        return {"key": "confidence", "score": 0.0,
                "comment": f"置信度 {conf:.2f} > 预期上限 {c_max}"}
    return {"key": "confidence", "score": 1.0,
            "comment": f"置信度 {conf:.2f} 在 [{c_min or '?', c_max or '?'}] 内"}


def eval_keywords(run, example) -> dict:
    """关键表述检查：应包含 / 不应包含的关键词。"""
    report = run.outputs.get("report_text", "")
    should = _parse_pipe(example.outputs.get("should_contain", ""))
    should_not = _parse_pipe(example.outputs.get("should_not_contain", ""))

    comments = []

    # 应含得分
    if should:
        hits = sum(1 for kw in should if kw in report)
        should_score = hits / len(should)
        comments.append(f"应有命中 {hits}/{len(should)}")
    else:
        should_score = None  # 未定义

    # 禁止得分
    if should_not:
        violations = [kw for kw in should_not if kw in report]
        not_score = 1.0 - len(violations) / len(should_not)
        if violations:
            comments.append(f"违禁词出现: {violations}")
        else:
            comments.append("无违禁词")
    else:
        not_score = None  # 未定义

    # 综合
    if should_score is not None and not_score is not None:
        score = 0.5 * should_score + 0.5 * not_score
    elif should_score is not None:
        score = should_score
    elif not_score is not None:
        score = not_score
    else:
        score = 0.5

    return {"key": "keywords", "score": round(score, 3),
            "comment": "; ".join(comments) or "无关键表述要求"}


def eval_chain_completeness(run, example) -> dict:
    """证据链完整性判断：Agent 对证据充分性的判断是否正确。"""
    chains = run.outputs.get("evidence_chains", [])
    expected_complete = example.outputs.get("evidence_chain_complete", "") == "True"

    has_complete = any(c.get("status") == "pass" for c in chains)
    chain_statuses = [c.get("status") for c in chains]

    if expected_complete == has_complete:
        score = 1.0
    else:
        score = 0.2

    return {
        "key": "chain_completeness",
        "score": score,
        "comment": f"预期={'完整' if expected_complete else '不足'}，"
                   f"实际={chain_statuses}",
    }


# ═══════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="LangSmith 评测 — DeepSeek 证据链 Agent")
    parser.add_argument(
        "--experiment",
        default="deepseek-v4-llm",
        help="实验前缀",
    )
    parser.add_argument(
        "--dataset",
        default="Judicial Evidence Golden Cases v2",
        help="LangSmith Dataset 名称",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=1,
        help="并发数（建议 1，避免 API 限流）",
    )
    args = parser.parse_args()

    print(f"🔬 评测开始")
    print(f"   Dataset:    {args.dataset}")
    print(f"   Experiment: {args.experiment}")
    print(f"   模型:       DeepSeek V4")
    print(f"   并发:       {args.concurrency}")
    print()

    results = evaluate(
        target,
        data=args.dataset,
        evaluators=[
            eval_citation,
            eval_confidence,
            eval_keywords,
            eval_chain_completeness,
        ],
        experiment_prefix=args.experiment,
        max_concurrency=args.concurrency,
    )

    # 打印本地汇总
    print(f"\n{'=' * 60}")
    print(f"  评测完成: {len(results)} 条")
    print(f"{'=' * 60}")
    for r in results:
        fb = r.get("evaluation_results", {})
        if isinstance(fb, dict):
            fb_list = fb.get("results", [])
        else:
            fb_list = fb if isinstance(fb, list) else []

        scores = {}
        for f in fb_list:
            scores[f.key] = f.score

        avg = round(sum(scores.values()) / max(len(scores), 1), 3) if scores else 0
        run_name = r["run"].name or "?"
        bar = "█" * int(avg * 10) + "░" * (10 - int(avg * 10))
        print(f"\n  [{bar}] {run_name}")
        for k, v in scores.items():
            print(f"    {k:20s}: {v:.3f}")
        print(f"    {'avg':20s}: {avg:.3f}")

    total_avg = round(
        sum(
            sum(f.score for f in (r.get("evaluation_results", {}).get("results", []) if isinstance(r.get("evaluation_results"), dict) else r.get("evaluation_results", [])))
            / max(len(r.get("evaluation_results", {}).get("results", []) if isinstance(r.get("evaluation_results"), dict) else r.get("evaluation_results", [])), 1)
            for r in results
        ) / max(len(results), 1),
        3,
    )
    print(f"\n  📊 总体平均: {total_avg:.3f}")
    print(f"\n🔗 LangSmith: https://smith.langchain.com/experiments")


if __name__ == "__main__":
    main()
