# The Observability Gap: Why Output-Level Human Feedback Fails for LLM Coding Agents

**CHI 26 Workshop Paper** | Barcelona, Spain April 13, 2026

[Yinghao Wang](mailto:yw623@cam.ac.uk)<sup>1</sup>, [Cheng Wang](mailto:Cheng.C.Wang@uea.ac.uk)<sup>2</sup>

<sup>1</sup> University of Cambridge &nbsp; <sup>2</sup> University of East Anglia

---

## Abstract

Large language model (LLM) multi-agent coding systems typically fix agent capabilities at design time. We study an alternative setting, earned autonomy, in which a coding agent starts with zero pre-defined functions and incrementally builds a reusable function library through lightweight human feedback on visual output alone. We evaluate this setup in a Blender-based 3D scene generation task requiring both spatial reasoning and programmatic geometric control. Although the agent rediscovered core utility functions comparable to a human reference implementation, it achieved 0% full-scene success under output-only feedback across multiple instruction granularities, where success required satisfying object completeness, ground contact, collision avoidance, and scale plausibility simultaneously. Our analysis identifies a structural observability gap: bugs originate in code logic and execution state, while human evaluation occurs only at the output layer, and the many-to-one mapping from internal states to visible outcomes prevents symptom-level feedback from reliably identifying root causes. This mismatch leads to persistent failure mode oscillation rather than convergence. A diagnostic intervention that injected minimal code-level knowledge restored convergence, strongly supporting the interpretation that the main bottleneck lies in feedback observability rather than programming competence. We formalize this phenomenon as a feedback paradox in domains with deep causal chains between internal code logic and perceptual outcomes, and argue that effective human–agent collaboration in such settings requires intermediate observability beyond output-only evaluation.

<p align="center">
  <img src="framework.png" alt="Generate-Evaluate-Evolve Loop" width="700"/>
</p>

## Framework Overview

The system operates as a **Generate -- Evaluate -- Evolve** loop:

1. **Coding Agent** generates Blender Python scripts, drawing from an evolving function library.
2. **Execution Agent** runs the scripts in Blender and captures rendered output.
3. **Human Evaluator** provides lightweight pass/fail feedback on the rendered output only.
4. **Review Agent** selects validated functions to promote into the persistent library for future cycles.

## Code Availability

> **Code coming soon.** We are currently cleaning up the codebase and preparing documentation. The full implementation will be released as a public repository after the review process is complete.
