# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**tekadm** is a collection of shell scripts and utilities for Linux and Mac system administration. Scripts should detect the OS and either work accordingly or report incompatibility.

Planned scope includes: swap/memory analysis, security audit and hardening, SAR data visualization (TUI), cron-based monitoring (e.g., top every 5 minutes), and potentially Python-based tools via pyenv.

## Repository Structure

- `bin/` — Executable scripts (e.g., `swap.sh` for per-process swap usage on Linux via `/proc`)
- `notes.md` — Project roadmap and ideas (git-ignored)

## Conventions

- **Language**: Bash shell scripts primarily; Python may be added later
- **OS detection**: Every script should check the OS and handle unsupported platforms gracefully
- **Philosophy**: "Simple effective works" — minimal dependencies, maximum compatibility
- **Scripts go in `bin/`** and should be executable with a proper shebang line (`#!/bin/env bash` or similar)

## No Build System

This is a collection of standalone scripts with no build, lint, or test tooling configured yet. Scripts are run directly (e.g., `./bin/swap.sh`).
