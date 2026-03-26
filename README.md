# The Observability Gap: Why Output-Level Human Feedback Fails for LLM Coding Agents

**CHI 26 Workshop Paper** | Barcelona, Spain April 13, 2026

[Yinghao Wang](mailto:yw623@cam.ac.uk)<sup>1</sup>, [Cheng Wang](mailto:Cheng.C.Wang@uea.ac.uk)<sup>2</sup>

<sup>1</sup> University of Cambridge &nbsp; <sup>2</sup> University of East Anglia

---

## Abstract

We propose *earned autonomy*, a framework in which an LLM-based coding agent starts with zero pre-defined capabilities and progressively builds its function library through iterative human feedback on output. We evaluate this framework through a 3D scene generation case study in Blender and identify the **observability gap**, a structural mismatch between the code layer where bugs originate and the output layer where humans evaluate, and the resulting **feedback paradox**.

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
