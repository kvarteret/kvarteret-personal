---
name: writing-skills
description: Create or update focused agent skills under .agents/skills for this repository.
---

# Writing Skills

Use this skill when creating or editing `.agents/skills/*/SKILL.md`.

## Rules

- Keep skills generic enough for repeated use, but include verified local
  boundaries when they prevent common mistakes.
- Prefer short workflows, checklists, and source paths over broad policy text.
- Do not copy vendor- or repo-specific workflow names unless the same tool exists
  in this repo.
- Put shared guidance in `.agents`; use `.claude`, `.codex`, or `.pi` only for
  adapter-specific runtime instructions.
- When adapting upstream material, remove assumptions about upstream services,
  dashboards, teams, and package managers unless verified locally.
