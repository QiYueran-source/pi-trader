---
name: stss
description: 收紧面向读者文本中的无效免责声明、叠加保守措辞和内部过程叙述；保留影响理解或决策的事实与限制。起草、改写或审查读者可见文案时使用，不用于普通代码与配置工作。
license: MIT
---

# Stop That Shit Slop

别再废话。

Make the point without writing for an imaginary critic. Preserve limitations that change what the reader understands or decides.

## Stay in scope

Reduce defensive wording in reader-facing prose, including captions and introductions. Do not classify text as AI-written, promise to remove an "AI voice," humanize unrelated prose, or perform a general style cleanup.

Judge sentences by their reader use, including sentences introduced during drafting. A request to describe a project's evolution calls for that history; it does not by itself call for an account of how the article's sources were checked.

## 项目协作边界

- 工程方案、代码、配置、部署与执行范围由 `stop-that-shit` 处理；本技能只处理读者可见文本。
- 交易计划、复盘、摘要和通知可按需使用本技能，但数据日期、来源、证据强度、失败阶段、风险条件、触发阈值、账户性质及模拟/真实交易范围属于读者的决策信息，必须 `KEEP` 或精确 `CALIBRATE`。
- `summary` 与 `knowledge-management` 负责文档路径、事实分类和留存规范；本技能不改变这些规范。

## Select the mode

- `rewrite`: Return a tighter version. This is the default when the user provides text without a mode.
- `audit`: Identify defensive writing and propose the smallest useful fix. Do not rewrite the full text.

Follow an explicit mode. Infer the mode from the request only when none is given.

For a drafting request, create the requested artifact from the supplied material and apply the rewrite checks before returning it.

## Record the claims

Before editing, build a private Claim Ledger from the supplied material:

- facts and numbers;
- named actors and sources;
- evidence strength;
- stated uncertainty and scope;
- what the reader needs to understand or do.

Do not print the ledger unless the user asks for it. Do not add facts, sources, numbers, certainty, or causality.

Keeping facts accurate does not require printing every editorial note. Keep verification logs and source-checking process in working notes unless the reader needs them. Preserve useful attribution, actual methods, and conditions that affect a claim.

## Test each defensive sentence

Apply the Sentence Consumer Test:

1. Who will use this sentence?
2. What understanding or decision does it change for this reader?
3. What becomes false or misleading if it is removed?

Choose one action:

- `DROP`: It only narrates diligence, anticipates criticism, apologizes, or says what the document does not attempt.
- `CALIBRATE`: It contains real uncertainty but uses stacked hedges. Keep one precise limitation.
- `RELOCATE`: The reader needs it beside a particular claim, or only the editor needs it in working notes. Choose the destination by its consumer; moving an unnecessary disclaimer to a footnote does not make it useful.
- `KEEP`: It changes the meaning, evidence strength, attribution, or a legal, safety, financial, methodological, contractual, or scope decision.

Do not decide from a keyword alone. The same phrase can be waste in one context and necessary in another.

## Rewrite

1. Lead with the requested subject, claim, decision, or proposal.
2. State scope positively: say what the work covers.
3. Replace stacked hedges with one evidence-matched qualifier.
4. Remove internal process narration unless the process is requested or material.
5. Put a necessary limitation beside the claim it limits.
6. Check the complete artifact, including captions and assistant-added prefaces, against the Claim Ledger and Sentence Consumer Test. Do not reintroduce dropped defenses in the delivery note.

Return only the requested artifact unless the user asks for commentary. If the text is already direct and faithful, return it unchanged.

## Audit

Report only actionable findings. For each finding, give:

- the span or sentence;
- `DROP`, `CALIBRATE`, `RELOCATE`, or `KEEP`;
- the reader's interpretation or decision affected;
- the smallest replacement when one is needed.

Use `NO_DECISION_CONSUMER` when a sentence serves neither reader understanding nor a decision. If there are no actionable findings, say so and stop.

## Check the claim diff

Before returning the result, verify:

- no supplied fact, number, source, or actor disappeared without reason;
- no new fact, number, source, or actor appeared;
- uncertainty did not become certainty;
- correlation did not become causation;
- a requested or meaning-changing limitation remains visible.

Run one claim-preserving pass. Do not add a score, a probability that text is AI-written, a change diary, or repeated self-review.

Read [references/examples.md](references/examples.md) when the boundary is ambiguous or the user asks for examples.
