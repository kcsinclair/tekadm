# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**tekadm** is a collection of shell scripts and utilities for Linux and Mac system administration. Scripts should detect the OS and either work accordingly or report incompatibility.

Planned scope includes: swap/memory analysis, security audit and hardening, SAR data visualization (TUI), cron-based monitoring (e.g., top every 5 minutes), and potentially Python-based tools via pyenv.

## Repository Structure

- `bin/` — Executable scripts (e.g., `swap.sh` for per-process swap usage on Linux via `/proc`)
- `htdocs/` — Web-facing scripts (PHP etc.) for deployment to web servers
- `plans/` — Project plan, roadmap, and archived implementation plans (kept up to date with each commit)
- `test/` — Test scripts and test data
- `notes.md` — Project roadmap and ideas (git-ignored)

## Conventions

- **Language**: Bash shell scripts primarily; Python may be added later
- **OS detection**: Every script should check the OS and handle unsupported platforms gracefully
- **Philosophy**: "Simple effective works" — minimal dependencies, maximum compatibility
- **Scripts go in `bin/`** and should be executable with a proper shebang line (`#!/bin/env bash` or similar)

## Commit Conventions

- **Plans**: Every git commit must include an updated `plans/PROJECT_PLAN.md` reflecting what changed and the current project state. Update the "Recent Changes" section and any affected "Completed" or "Planned" items before committing.
- **Implementation plans**: When a Claude Code plan file (`~/.claude/plans/*.md`) was used for implementation, copy it into `plans/` with a descriptive name (e.g., `plans/geolite2-country-lookup.md`) and include it in the commit.

## No Build System

This is a collection of standalone scripts with no build, lint, or test tooling configured yet. Scripts are run directly (e.g., `./bin/swap.sh`).
