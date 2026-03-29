# Codex Execution Plans

This repository uses execution plans as living implementation documents. Every substantial change must have a self-contained markdown file under `/plans/` that explains the purpose of the work, the concrete steps to implement it, the commands to run, the expected behavior, and the evidence that proves the feature works.

An execution plan must be written for a complete beginner to this repository. The reader should be able to start from the current working tree and the single plan file, then implement or continue the feature without any memory of earlier discussion. Plans must define non-obvious terms in plain language, must include validation steps, and must be updated continuously as work progresses.

Each execution plan must contain and maintain these sections:

- `Progress`
- `Surprises & Discoveries`
- `Decision Log`
- `Outcomes & Retrospective`

The `Progress` section must use checkboxes with timestamps and must always reflect the actual current state of the work. At every stopping point, split partially completed work into finished and remaining pieces rather than leaving ambiguous notes.

Plans must be outcome-focused. They must explain what a user can do after the change, how to run the code locally, what to expect from commands and HTTP requests, and how to tell success from failure. Prefer additive, testable milestones. If risky or uncertain work is involved, include a prototype milestone that proves feasibility before building the full feature.

When revising a plan, update all relevant sections and add a short revision note at the end describing what changed and why. Plans are part of the repository and are expected to remain useful after the original author is gone.

