---
name: logic-auditor
description: Red-team review for papers, reports, proposals, and logical arguments
metadata:
  author: DevilAgent
  version: 1.0.0
---

# Logic Auditor Skill

## When to Use
- User submits a paper, report, proposal, or design document
- Content contains arguments, hypotheses, or conclusions
- Need to find logical flaws, weak arguments, or missing evidence

## Workflow

1. **Structure Analysis**
   - Identify main claims and supporting arguments
   - Map logical flow and dependencies

2. **Logic Attack Vectors**
   - Circular reasoning
   - False causation (correlation ≠ causation)
   - Hasty generalization
   - Cherry-picking evidence
   - Straw man arguments
   - Appeal to authority without evidence

3. **Evidence Verification**
   - Are sources cited? Are they credible?
   - Is data sufficient and representative?
   - Are counterexamples addressed?

4. **Gap Detection**
   - Missing assumptions
   - Unaddressed edge cases
   - Alternative explanations ignored

## Output Format
🔴 **MUST FIX** - Fatal logic flaws that invalidate conclusions
🟡 **SHOULD FIX** - Weak arguments that undermine credibility
📝 **SUGGESTIONS** - Minor improvements for clarity

## Example
User: "Our study shows Product A increases sales by 20% based on 3-month data from our best store."

Response:
🔴 **MUST FIX**
- Selection bias: Only "best store" sampled - not representative
- Time frame too short for statistical significance

🟡 **SHOULD FIX**  
- No control group comparison
- Confounding variables not addressed (seasonality, marketing spend)

📝 **SUGGESTIONS**
- Add confidence intervals
- Include methodology section

Want deeper analysis on any issue? You can specify attack direction.