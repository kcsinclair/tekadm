# Plan: Copy implementation plans to plans/ folder

## Context
The user wants Claude Code implementation plan files (stored at `~/.claude/plans/`) to also be saved into the project's `plans/` folder so they're version-controlled in git. The current plan file for this project is `pure-knitting-wand.md`. Going forward, whenever a plan is created during a session, a copy should be included in `plans/` and committed with the related changes.

## Changes

### 1. Copy existing plan to `plans/`
- Copy `~/.claude/plans/pure-knitting-wand.md` to `plans/geolite2-country-lookup.md` (renamed descriptively)

### 2. Copy this plan to `plans/`
- Copy this plan file to `plans/copy-plans-to-project.md`

### 3. Update `plans/PROJECT_PLAN.md`
- Add note under Infrastructure that implementation plans are archived in `plans/`
- Add entry in Recent Changes

### 4. Update `CLAUDE.md` commit convention
- Add instruction: when a Claude Code plan was used for implementation, copy it into `plans/` with a descriptive name and include it in the commit

### 5. Commit and push
- Stage all changed/new files in `plans/` and `CLAUDE.md`
- Commit with updated project plan (per existing convention)
- Push to origin

## Files to modify
- `plans/geolite2-country-lookup.md` — new (copy of pure-knitting-wand.md)
- `plans/copy-plans-to-project.md` — new (copy of this plan)
- `plans/PROJECT_PLAN.md` — update infrastructure section and recent changes
- `CLAUDE.md` — update commit conventions

## Verification
- `ls plans/` shows PROJECT_PLAN.md, geolite2-country-lookup.md, copy-plans-to-project.md
- `git log --oneline -1` shows the new commit
- `git diff HEAD~1 --stat` shows the expected files
