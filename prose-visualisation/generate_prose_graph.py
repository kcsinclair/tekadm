#!/usr/bin/env python3
"""
Generate an interactive Cytoscape.js prose graph from markdown files.

Scans markdown files for wiki-links and inline tags, then produces a
self-contained HTML visualization where clicking a node opens a modal
displaying the prose content.

Usage:
    python3 generate_prose_graph.py
    python3 generate_prose_graph.py randomProse/
    python3 generate_prose_graph.py randomProse/ -o my-graph.html
"""

import argparse
import json
import os
import re
import sys


# ── Tag extraction ────────────────────────────────────────────────────────────

def extract_inline_tags(content: str) -> set[str]:
    """Extract inline hashtags from markdown content, skipping headings and code blocks."""
    tags = set()
    in_code_block = False

    # Skip frontmatter (YAML --- or TOML +++)
    lines = content.split("\n")
    start = 0
    if lines and lines[0].strip() in ("---", "+++"):
        delimiter = lines[0].strip()
        for i, line in enumerate(lines[1:], 1):
            if line.strip() == delimiter:
                start = i + 1
                break

    for line in lines[start:]:
        stripped = line.strip()

        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue

        # Skip markdown headings
        if re.match(r"^#{1,6}\s", stripped):
            continue

        for m in re.finditer(r"(?<![\\&/\w])#([A-Za-z][\w-]*)", line):
            tags.add(m.group(1))

    return tags


def normalize_tag(tag: str) -> str:
    """Normalize a tag to lowercase-hyphenated form."""
    tag = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1-\2", tag)
    tag = re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", tag)
    return tag.lower()


def extract_frontmatter_tags(content: str) -> set[str]:
    """Extract tags from YAML (---) or TOML (+++) frontmatter tags field.

    Supports:
      YAML block list:     tags:\n  - foo\n  - bar
      YAML inline array:   tags: [foo, bar]
      YAML scalar:         tags: foo
      TOML array:          tags = ["foo", "bar"]
    """
    tags = set()
    lines = content.split("\n")
    if not lines or lines[0].strip() not in ("---", "+++"):
        return tags

    delimiter = lines[0].strip()
    end = -1
    for i, line in enumerate(lines[1:], 1):
        if line.strip() == delimiter:
            end = i
            break
    if end == -1:
        return tags

    fm = lines[1:end]

    if delimiter == "+++":
        # TOML: tags = ["foo", "bar"]
        for line in fm:
            m = re.match(r"^\s*tags\s*=\s*\[(.*)\]\s*$", line)
            if m:
                for item in m.group(1).split(","):
                    item = item.strip().strip("\"'")
                    if item:
                        tags.add(item)
        return tags

    # YAML
    in_tags_block = False
    for line in fm:
        m = re.match(r"^tags\s*:\s*(.*)$", line)
        if m:
            rest = m.group(1).strip()
            if rest.startswith("[") and rest.endswith("]"):
                for item in rest[1:-1].split(","):
                    item = item.strip().strip("\"'")
                    if item:
                        tags.add(item)
                in_tags_block = False
            elif rest:
                tags.add(rest.strip("\"'"))
                in_tags_block = False
            else:
                in_tags_block = True
            continue

        if in_tags_block:
            m2 = re.match(r"^\s*-\s+(.+?)\s*$", line)
            if m2:
                tag = m2.group(1).strip().strip("\"'")
                if tag:
                    tags.add(tag)
            elif line.strip() and not line.startswith((" ", "\t")):
                in_tags_block = False

    return tags


# ── Wiki-link extraction ─────────────────────────────────────────────────────

def extract_wiki_links(content: str) -> list[tuple[str, str]]:
    """Extract wiki-links as (raw_target, display_text) tuples."""
    links = []
    in_code_block = False
    for line in content.split("\n"):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue
        for m in re.finditer(r"\[\[([^\]|]+?)(?:\|([^\]]*?))?\]\]", line):
            raw_target = m.group(1).strip()
            display = m.group(2).strip() if m.group(2) else raw_target
            if raw_target:
                links.append((raw_target, display))
    return links


# ── Body content extraction ──────────────────────────────────────────────────

def extract_body(content: str) -> str:
    """Extract display-ready prose body from markdown content.

    Strips: frontmatter, tag-only lines, wiki-link-only lines,
    first heading, and wiki-link syntax within remaining text.
    """
    lines = content.split("\n")
    start = 0

    # Skip TOML (+++) or YAML (---) frontmatter
    if lines and lines[0].strip() in ("---", "+++"):
        delimiter = lines[0].strip()
        for i, line in enumerate(lines[1:], 1):
            if line.strip() == delimiter:
                start = i + 1
                break

    result = []
    heading_stripped = False

    for line in lines[start:]:
        stripped = line.strip()

        # Skip lines that are only tags (e.g. "#prose " or "#poem #anthology")
        if stripped and re.match(r"^(#[A-Za-z][\w-]*\s*)+$", stripped):
            continue

        # Skip lines that are only wiki-links
        if stripped and re.match(r"^(\[\[[^\]]+\]\]\s*)+$", stripped):
            continue

        # Skip the first H1 heading (prose-file title convention)
        if not heading_stripped and re.match(r"^#\s", stripped):
            heading_stripped = True
            continue

        # Replace wiki-link syntax inline with a marker the JS can make clickable
        # Format: {{LINK:raw_target:display_text}}
        line = re.sub(
            r"\[\[([^\]|]+?)\|([^\]]*?)\]\]",
            r"{{LINK:\1:\2}}", line
        )
        line = re.sub(
            r"\[\[([^\]]+?)\]\]",
            r"{{LINK:\1:\1}}", line
        )

        result.append(line)

    # Strip leading and trailing blank lines
    while result and not result[0].strip():
        result.pop(0)
    while result and not result[-1].strip():
        result.pop()

    return "\n".join(result)


# ── File scanning ─────────────────────────────────────────────────────────────

def scan_markdown_files(scan_path: str) -> dict:
    """Walk scan_path recursively, extract data from all .md files.

    Returns dict with keys:
        file_data:     {relpath: {label, tags, body}}
        tag_edges:     [(relpath, tag), ...]
        file_edges:    [(src_relpath, tgt_relpath), ...]
        virtual_nodes: {display_label: [backlink_relpaths...]}
        virtual_edges: [(relpath, display_label), ...]
    """
    file_data = {}
    raw_links = []  # (source_relpath, raw_target, display_text)
    basename_lookup = {}  # basename (no ext) -> relpath
    relpath_lookup = {}   # relpath without .md -> relpath

    # First pass: collect all files and their data
    for root, _dirs, files in os.walk(scan_path):
        for fname in sorted(files):
            if not fname.endswith(".md"):
                continue
            full_path = os.path.join(root, fname)
            rel = os.path.relpath(full_path, scan_path)

            # Build lookups for link resolution
            base = os.path.splitext(fname)[0]
            basename_lookup[base] = rel
            basename_lookup[fname] = rel
            rel_no_ext = os.path.splitext(rel)[0]
            relpath_lookup[rel_no_ext] = rel
            relpath_lookup[rel] = rel

            try:
                with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
            except OSError:
                continue

            tags = extract_inline_tags(content) | extract_frontmatter_tags(content)
            normalized_tags = sorted({normalize_tag(t) for t in tags} - {""})
            body = extract_body(content)

            # Extract wiki links from body (which has stripped standalone
            # link-only lines like [[Poetry]]) via the {{LINK:target:display}} markers
            wiki_links = re.findall(r"\{\{LINK:([^:}]+):([^}]+)\}\}", body)

            file_data[rel] = {
                "label": base,
                "tags": normalized_tags,
                "body": body,
            }

            for raw_target, display in wiki_links:
                raw_links.append((rel, raw_target, display))

    # Second pass: resolve wiki-links
    tag_edges = []
    file_edges = []
    virtual_nodes = {}  # display_label -> set of backlink relpaths
    virtual_edges = []

    # Build tag edges
    tag_degree = {}
    for rel, info in file_data.items():
        for tag in info["tags"]:
            tag_edges.append((rel, tag))
            tag_degree[tag] = tag_degree.get(tag, 0) + 1

    # Resolve wiki-links
    for source_rel, raw_target, display in raw_links:
        source_base = os.path.splitext(os.path.basename(source_rel))[0]

        # Skip self-references
        target_base = os.path.splitext(os.path.basename(raw_target))[0]
        if target_base == source_base:
            continue

        # Try to resolve to an existing file
        target_rel = None
        # Try basename lookup (handles "Poetry" -> "Poetry.md", "eyes" -> "eyes.md")
        if raw_target in basename_lookup:
            target_rel = basename_lookup[raw_target]
        elif target_base in basename_lookup:
            target_rel = basename_lookup[target_base]
        # Try relative path lookup (handles "Index/Prose" -> "Index/Prose.md")
        elif raw_target in relpath_lookup:
            target_rel = relpath_lookup[raw_target]
        elif os.path.splitext(raw_target)[0] in relpath_lookup:
            target_rel = relpath_lookup[os.path.splitext(raw_target)[0]]

        if target_rel and target_rel in file_data and target_rel != source_rel:
            # Resolved file-to-file link
            file_edges.append((source_rel, target_rel))
        else:
            # Unresolved -> virtual node using display text
            if display not in virtual_nodes:
                virtual_nodes[display] = []
            if source_rel not in virtual_nodes[display]:
                virtual_nodes[display].append(source_rel)
            virtual_edges.append((source_rel, display))

    return {
        "file_data": dict(sorted(file_data.items())),
        "tag_degree": tag_degree,
        "tag_edges": tag_edges,
        "file_edges": file_edges,
        "virtual_nodes": virtual_nodes,
        "virtual_edges": virtual_edges,
    }


# ── HTML template ─────────────────────────────────────────────────────────────

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>/*PAGE_TITLE*/ — Prose Graph</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      background: #f0f2f7;
      color: #1a1c28;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      overflow: hidden;
    }

    #cy {
      width: 100vw;
      height: 100vh;
    }

    /* -- Shared panel style ----------------------------------------- */
    .panel {
      position: fixed;
      z-index: 20;
      background: rgba(255, 255, 255, 0.94);
      backdrop-filter: blur(10px);
      border: 1px solid rgba(0, 0, 0, 0.08);
      border-radius: 10px;
      box-shadow: 0 2px 12px rgba(0,0,0,0.08);
    }

    .panel h3 {
      font-size: 11px;
      font-weight: 700;
      color: #8890a8;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      margin-bottom: 10px;
    }

    /* -- Controls panel (top-left) ---------------------------------- */
    #controls {
      top: 12px;
      left: 12px;
      padding: 14px;
      width: 230px;
    }

    #search {
      width: 100%;
      background: #f4f5f9;
      border: 1px solid #dde0ea;
      color: #1a1c28;
      padding: 7px 10px;
      border-radius: 6px;
      font-size: 13px;
      outline: none;
      transition: border-color 0.2s;
    }

    #search:focus { border-color: #2563eb; }
    #search::placeholder { color: #aab0c0; }

    #match-count {
      font-size: 11px;
      color: #9098b0;
      margin-top: 6px;
      min-height: 15px;
    }

    .section-label {
      font-size: 10px;
      font-weight: 600;
      color: #9098b0;
      letter-spacing: 0.05em;
      text-transform: uppercase;
      margin: 10px 0 5px;
    }

    .btn-row { display: flex; gap: 5px; margin-top: 5px; }

    button {
      background: #f0f2f7;
      border: 1px solid #dde0ea;
      color: #3a4060;
      padding: 5px 8px;
      border-radius: 6px;
      font-size: 11px;
      cursor: pointer;
      flex: 1;
      transition: background 0.15s, border-color 0.15s;
      white-space: nowrap;
    }

    button:hover {
      background: #e2e6f0;
      border-color: #bcc4d8;
    }

    button.active {
      background: #2563eb;
      border-color: #2563eb;
      color: #fff;
      font-weight: 600;
    }

    #layout-btns {
      display: grid;
      grid-template-columns: 1fr 1fr 1fr;
      gap: 4px;
      margin-top: 5px;
    }

    #layout-btns button { flex: unset; }

    /* -- Legend (top-right) ----------------------------------------- */
    #legend {
      top: 12px;
      right: 12px;
      padding: 12px 14px;
      font-size: 12px;
      line-height: 1.9;
    }

    .legend-row { display: flex; align-items: center; gap: 8px; color: #3a4060; }

    .dot {
      display: inline-block;
      width: 12px; height: 12px;
      border-radius: 50%;
      flex-shrink: 0;
    }

    .tag-shape {
      display: inline-block;
      width: 13px; height: 10px;
      border-radius: 3px;
      flex-shrink: 0;
    }

    .diamond-shape {
      display: inline-block;
      width: 12px; height: 12px;
      background: rgba(139, 92, 246, 0.3);
      border: 2px dashed #8b5cf6;
      transform: rotate(45deg);
      flex-shrink: 0;
    }

    /* -- Modal overlay ---------------------------------------------- */
    #modal-overlay {
      display: none;
      position: fixed;
      top: 0; left: 0; right: 0; bottom: 0;
      background: rgba(0, 0, 0, 0.4);
      backdrop-filter: blur(3px);
      z-index: 100;
      justify-content: center;
      align-items: center;
    }

    #modal {
      background: #fff;
      border-radius: 14px;
      box-shadow: 0 8px 40px rgba(0,0,0,0.18);
      width: 90%;
      max-width: 600px;
      max-height: 80vh;
      overflow-y: auto;
      padding: 28px 32px;
      position: relative;
    }

    #modal-close {
      position: absolute;
      top: 12px;
      right: 16px;
      background: none;
      border: none;
      font-size: 22px;
      color: #9098b0;
      cursor: pointer;
      flex: unset;
      padding: 4px 8px;
      line-height: 1;
    }

    #modal-close:hover { color: #1a1c28; background: none; }

    #modal-type {
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      margin-bottom: 4px;
    }

    #modal-title {
      font-size: 18px;
      font-weight: 600;
      color: #1a1c28;
      margin-bottom: 16px;
      line-height: 1.4;
      word-break: break-word;
    }

    #modal-body {
      font-size: 15px;
      color: #3a4060;
      line-height: 1.8;
      word-break: break-word;
    }

    #modal-body .md-para { white-space: pre-wrap; margin-bottom: 12px; }
    #modal-body .md-h1, #modal-body .md-h2, #modal-body .md-h3,
    #modal-body .md-h4, #modal-body .md-h5, #modal-body .md-h6 {
      color: #2a4a80;
      margin: 18px 0 10px;
      font-weight: 600;
      line-height: 1.35;
    }
    #modal-body .md-h1 { font-size: 22px; }
    #modal-body .md-h2 { font-size: 19px; }
    #modal-body .md-h3 { font-size: 17px; }
    #modal-body .md-h4, #modal-body .md-h5, #modal-body .md-h6 { font-size: 15px; }
    #modal-body .md-list { margin: 8px 0 12px 22px; padding: 0; }
    #modal-body .md-list li { margin: 4px 0; }
    #modal-body .md-url {
      color: #2563eb;
      text-decoration: underline;
      text-decoration-style: dotted;
      text-underline-offset: 2px;
    }
    #modal-body .md-url:hover { color: #1e40af; text-decoration-style: solid; }

    #modal-body .backlink-list {
      white-space: normal;
    }

    .backlink-item {
      display: inline-block;
      margin: 3px 0;
      padding: 4px 10px;
      background: rgba(37, 99, 235, 0.08);
      border: 1px solid rgba(37, 99, 235, 0.2);
      border-radius: 6px;
      color: #2563eb;
      cursor: pointer;
      font-size: 13px;
      transition: background 0.15s;
    }

    .backlink-item:hover {
      background: rgba(37, 99, 235, 0.16);
    }

    .backlink-item.inline-link {
      display: inline;
      margin: 0;
      padding: 0 1px;
      background: none;
      border: none;
      border-bottom: 1px dashed #2563eb;
      border-radius: 0;
      color: #2563eb;
      font-size: inherit;
    }

    .backlink-item.inline-link:hover {
      background: rgba(37, 99, 235, 0.08);
      border-bottom-style: solid;
    }

    .backlink-item.tag-link {
      background: rgba(224, 123, 26, 0.08);
      border-color: rgba(224, 123, 26, 0.2);
      color: #e07b1a;
    }

    .backlink-item.tag-link:hover {
      background: rgba(224, 123, 26, 0.16);
    }

    .backlink-item.virtual-link {
      background: rgba(139, 92, 246, 0.08);
      border-color: rgba(139, 92, 246, 0.2);
      color: #7c3aed;
    }

    .backlink-item.virtual-link:hover {
      background: rgba(139, 92, 246, 0.16);
    }

    /* -- Stats (bottom-right) --------------------------------------- */
    #stats {
      position: fixed;
      bottom: 12px;
      right: 12px;
      z-index: 20;
      background: rgba(255,255,255,0.80);
      border: 1px solid rgba(0,0,0,0.07);
      border-radius: 8px;
      box-shadow: 0 1px 6px rgba(0,0,0,0.06);
      padding: 7px 12px;
      font-size: 11px;
      color: #8890a8;
    }
  </style>
</head>
<body>

  <!-- Controls -->
  <div id="controls" class="panel">
    <h3>/*PAGE_TITLE*/</h3>
    <input type="text" id="search" placeholder="Search files or tags..." autocomplete="off">
    <div id="match-count"></div>

    <div class="section-label">View</div>
    <div class="btn-row">
      <button id="btn-fit">Fit All</button>
      <button id="btn-reset">Reset</button>
    </div>

    <div class="section-label">Layout</div>
    <div id="layout-btns">
      <button class="layout-btn active" data-layout="cose">Force</button>
      <button class="layout-btn" data-layout="concentric">Concentric</button>
      <button class="layout-btn" data-layout="breadthfirst">Tree</button>
      <button class="layout-btn" data-layout="circle">Circle</button>
      <button class="layout-btn" data-layout="grid">Grid</button>
      <button class="layout-btn" data-layout="random">Random</button>
    </div>
  </div>

  <!-- Legend -->
  <div id="legend" class="panel">
    <h3>Legend</h3>
    <div class="legend-row"><span class="dot" style="background:#2563eb"></span> File</div>
    <div class="legend-row"><span class="tag-shape" style="background:#e07b1a"></span> Tag</div>
    <div class="legend-row"><span class="diamond-shape"></span> Virtual (unresolved link)</div>
    <div class="legend-row"><span style="display:inline-block;width:14px;height:2px;border-top:2px dashed #16a34a;flex-shrink:0"></span> Wiki-link</div>
    <div class="legend-row"><span style="display:inline-block;width:14px;height:1px;border-top:1px solid #c4c8da;flex-shrink:0"></span> Tag connection</div>
    <div class="legend-row" style="margin-top:3px;color:#9098b0;font-size:11px">Node size = connections</div>
  </div>

  <!-- Modal -->
  <div id="modal-overlay">
    <div id="modal">
      <button id="modal-close">&times;</button>
      <div id="modal-type"></div>
      <div id="modal-title"></div>
      <div id="modal-body"></div>
    </div>
  </div>

  <!-- Stats -->
  <div id="stats"></div>

  <div id="cy"></div>

  <script src="https://cdnjs.cloudflare.com/ajax/libs/cytoscape/3.29.2/cytoscape.min.js"></script>

  <script>
  // -- Data ----------------------------------------------------------------
  const fileData     = /*FILE_DATA*/;
  const tagEdges     = /*TAG_EDGES*/;
  const fileEdges    = /*FILE_EDGES*/;
  const virtualNodes = /*VIRTUAL_NODES*/;
  const virtualEdges = /*VIRTUAL_EDGES*/;

  // -- Build elements ------------------------------------------------------
  const elements = [];

  // Tag degree counts
  const tagDegree = {};
  for (const [, tag] of tagEdges) {
    tagDegree[tag] = (tagDegree[tag] || 0) + 1;
  }

  // File nodes
  for (const [relpath, info] of Object.entries(fileData)) {
    elements.push({ data: {
      id: relpath,
      label: info.label,
      type: "file",
      degree: info.tags.length,
      body: info.body
    }});
  }

  // Tag nodes
  for (const [tag, deg] of Object.entries(tagDegree)) {
    elements.push({ data: {
      id: "tag:" + tag,
      label: tag,
      type: "tag",
      degree: deg
    }});
  }

  // Virtual nodes
  for (const [label, backlinks] of Object.entries(virtualNodes)) {
    elements.push({ data: {
      id: "virtual:" + label,
      label: label,
      type: "virtual",
      degree: backlinks.length,
      backlinks: backlinks
    }});
  }

  // Tag edges
  for (const [src, tag] of tagEdges) {
    elements.push({ data: {
      id: src + "__tag:" + tag,
      source: src,
      target: "tag:" + tag
    }});
  }

  // File-to-file wiki-link edges
  for (const [src, tgt] of fileEdges) {
    elements.push({ data: {
      id: "link:" + src + "->" + tgt,
      source: src,
      target: tgt,
      type: "wiki-link"
    }});
  }

  // Virtual edges
  for (const [src, vlabel] of virtualEdges) {
    elements.push({ data: {
      id: "vlink:" + src + "->" + vlabel,
      source: src,
      target: "virtual:" + vlabel,
      type: "wiki-link"
    }});
  }

  // -- Cytoscape init ------------------------------------------------------
  const cy = cytoscape({
    container: document.getElementById("cy"),
    elements,
    style: [
      {
        selector: 'node[type="file"]',
        style: {
          "background-color": "#2563eb",
          "label": "data(label)",
          "font-size": "9px",
          "color": "#1a1c28",
          "text-valign": "bottom",
          "text-halign": "center",
          "text-margin-y": "5px",
          "text-outline-width": 2,
          "text-outline-color": "#f0f2f7",
          "width": "mapData(degree, 1, 10, 20, 50)",
          "height": "mapData(degree, 1, 10, 20, 50)",
          "border-width": 0,
          "cursor": "pointer"
        }
      },
      {
        selector: 'node[type="tag"]',
        style: {
          "background-color": "#e07b1a",
          "label": "data(label)",
          "font-size": "8px",
          "color": "#1a1c28",
          "text-valign": "bottom",
          "text-halign": "center",
          "text-margin-y": "4px",
          "text-outline-width": 2,
          "text-outline-color": "#f0f2f7",
          "width": "mapData(degree, 1, 15, 14, 46)",
          "height": "mapData(degree, 1, 15, 10, 34)",
          "shape": "round-rectangle",
          "border-width": 0,
          "cursor": "pointer"
        }
      },
      {
        selector: 'node[type="virtual"]',
        style: {
          "background-color": "rgba(139, 92, 246, 0.3)",
          "label": "data(label)",
          "font-size": "9px",
          "font-style": "italic",
          "color": "#6d28d9",
          "text-valign": "bottom",
          "text-halign": "center",
          "text-margin-y": "5px",
          "text-outline-width": 2,
          "text-outline-color": "#f0f2f7",
          "width": "mapData(degree, 1, 10, 16, 40)",
          "height": "mapData(degree, 1, 10, 16, 40)",
          "border-width": 2,
          "border-style": "dashed",
          "border-color": "#8b5cf6",
          "shape": "diamond",
          "cursor": "pointer"
        }
      },
      {
        selector: "edge",
        style: {
          "width": 1,
          "line-color": "#c4c8da",
          "opacity": 0.6,
          "curve-style": "haystack"
        }
      },
      {
        selector: 'edge[type="wiki-link"]',
        style: {
          "width": 2,
          "line-color": "#16a34a",
          "line-style": "dashed",
          "line-dash-pattern": [6, 3],
          "opacity": 0.8,
          "curve-style": "bezier",
          "target-arrow-shape": "triangle",
          "target-arrow-color": "#16a34a",
          "arrow-scale": 0.8
        }
      },
      {
        selector: "node.highlighted",
        style: {
          "border-width": 2.5,
          "border-color": "#1a1c28",
          "opacity": 1
        }
      },
      {
        selector: "node.faded",
        style: { "opacity": 0.12 }
      },
      {
        selector: "edge.highlighted",
        style: {
          "line-color": "#2563eb",
          "opacity": 0.7,
          "width": 1.5
        }
      },
      {
        selector: 'edge[type="wiki-link"].highlighted',
        style: {
          "line-color": "#16a34a",
          "opacity": 0.9,
          "width": 2.5
        }
      },
      {
        selector: "edge.faded",
        style: { "opacity": 0.05 }
      },
      {
        selector: "node.search-match",
        style: {
          "border-width": 3,
          "border-color": "#d97706",
          "opacity": 1
        }
      }
    ],
    layout: layoutConfig("cose")
  });

  // -- Layout configs ------------------------------------------------------
  function layoutConfig(name) {
    const base = { animate: true, animationDuration: 700, fit: true, padding: 40 };
    switch (name) {
      case "cose":
        return {
          ...base,
          name: "cose",
          randomize: true,
          nodeRepulsion: () => 500000,
          nodeOverlap: 12,
          idealEdgeLength: () => 80,
          edgeElasticity: () => 80,
          nestingFactor: 1.2,
          gravity: 0.3,
          numIter: 1000,
          initialTemp: 200,
          coolingFactor: 0.95,
          minTemp: 1
        };
      case "concentric":
        return {
          ...base,
          name: "concentric",
          concentric: n => n.connectedEdges().length,
          levelWidth: () => 4,
          minNodeSpacing: 20
        };
      case "breadthfirst":
        return {
          ...base,
          name: "breadthfirst",
          directed: false,
          spacingFactor: 1.4,
          maximal: true
        };
      case "circle":
        return { ...base, name: "circle", spacingFactor: 1.2 };
      case "grid":
        return { ...base, name: "grid", spacingFactor: 1.3, avoidOverlap: true };
      case "random":
        return { ...base, name: "random", animate: false };
      default:
        return { ...base, name };
    }
  }

  // -- Stats ---------------------------------------------------------------
  const numFiles   = Object.keys(fileData).length;
  const numTags    = Object.keys(tagDegree).length;
  const numVirtual = Object.keys(virtualNodes).length;
  const numTagEdges  = tagEdges.length;
  const numWikiLinks = fileEdges.length + virtualEdges.length;
  document.getElementById("stats").innerHTML =
    `${numFiles} files &middot; ${numTags} tags &middot; ${numVirtual} virtual` +
    ` &middot; ${numTagEdges} tag edges &middot; ${numWikiLinks} wiki-links`;

  // -- Modal ---------------------------------------------------------------
  const modalOverlay = document.getElementById("modal-overlay");
  const modalType    = document.getElementById("modal-type");
  const modalTitle   = document.getElementById("modal-title");
  const modalBody    = document.getElementById("modal-body");

  function resolveWikiTarget(rawTarget, display) {
    const baseName = rawTarget.replace(/\.md$/, "");
    for (const [rp, fi] of Object.entries(fileData)) {
      if (fi.label === baseName || fi.label === rawTarget) return rp;
    }
    if (virtualNodes[display]) return "virtual:" + display;
    if (virtualNodes[baseName]) return "virtual:" + baseName;
    return null;
  }

  function renderInline(parent, text) {
    const pattern = /(\{\{LINK:[^:}]+:[^}]+\}\})|\[([^\]]+)\]\(([^)]+)\)|\*\*([^*]+)\*\*/g;
    let last = 0;
    let m;
    while ((m = pattern.exec(text)) !== null) {
      if (m.index > last) {
        parent.appendChild(document.createTextNode(text.slice(last, m.index)));
      }
      if (m[1]) {
        const wm = m[1].match(/^\{\{LINK:([^:}]+):([^}]+)\}\}$/);
        const rawTarget = wm[1].trim();
        const display = wm[2].trim();
        const nodeId = resolveWikiTarget(rawTarget, display);
        if (nodeId) {
          const span = document.createElement("span");
          span.className = "backlink-item inline-link";
          span.dataset.nodeId = nodeId;
          span.textContent = display;
          parent.appendChild(span);
        } else {
          parent.appendChild(document.createTextNode(display));
        }
      } else if (m[2]) {
        const a = document.createElement("a");
        a.href = m[3];
        a.target = "_blank";
        a.rel = "noopener noreferrer";
        a.className = "md-url";
        a.textContent = m[2];
        parent.appendChild(a);
      } else {
        const b = document.createElement("strong");
        b.textContent = m[4];
        parent.appendChild(b);
      }
      last = pattern.lastIndex;
    }
    if (last < text.length) {
      parent.appendChild(document.createTextNode(text.slice(last)));
    }
  }

  function renderMarkdown(container, body) {
    const lines = body.split("\n");
    let list = null;
    let para = null;
    for (const line of lines) {
      const trimmed = line.trim();
      const heading = trimmed.match(/^(#{1,6})\s+(.+)$/);
      if (heading) {
        list = null; para = null;
        const level = heading[1].length;
        const h = document.createElement("h" + level);
        h.className = "md-h" + level;
        renderInline(h, heading[2]);
        container.appendChild(h);
        continue;
      }
      const bullet = trimmed.match(/^[-*]\s+(.+)$/);
      if (bullet) {
        para = null;
        if (!list) {
          list = document.createElement("ul");
          list.className = "md-list";
          container.appendChild(list);
        }
        const li = document.createElement("li");
        renderInline(li, bullet[1]);
        list.appendChild(li);
        continue;
      }
      if (!trimmed) { list = null; para = null; continue; }
      list = null;
      if (!para) {
        para = document.createElement("div");
        para.className = "md-para";
        container.appendChild(para);
      } else {
        para.appendChild(document.createTextNode("\n"));
      }
      renderInline(para, line);
    }
  }

  function showModal(node) {
    const type = node.data("type");
    modalOverlay.style.display = "flex";

    if (type === "file") {
      modalType.style.color = "#2563eb";
      modalType.textContent = "FILE";
      modalTitle.textContent = node.data("label");
      const relpath = node.id();
      const info = fileData[relpath];
      modalBody.innerHTML = "";
      renderMarkdown(modalBody, node.data("body") || "(empty)");
      if (info && info.tags && info.tags.length > 0) {
        const tagWrap = document.createElement("div");
        tagWrap.className = "backlink-list";
        tagWrap.style.cssText = "margin-top:16px;padding-top:12px;border-top:1px solid #eee";
        info.tags.forEach((tag, i) => {
          if (i > 0) tagWrap.appendChild(document.createTextNode(" "));
          const span = document.createElement("span");
          span.className = "backlink-item tag-link";
          span.dataset.nodeId = "tag:" + tag;
          span.textContent = "#" + tag;
          tagWrap.appendChild(span);
        });
        modalBody.appendChild(tagWrap);
      }
    }
    else if (type === "tag") {
      modalType.style.color = "#e07b1a";
      modalType.textContent = "TAG";
      modalTitle.textContent = "#" + node.data("label");
      const files = node.connectedEdges().map(e => {
        const other = e.source().id() === node.id() ? e.target() : e.source();
        return other;
      }).filter(n => n.data("type") === "file");
      modalBody.innerHTML =
        `<div class="backlink-list"><b style="color:#9098b0">Used in ${files.length} file${files.length !== 1 ? "s" : ""}:</b><br><br>` +
        files.map(f =>
          `<span class="backlink-item" data-node-id="${f.id()}">${f.data("label")}</span>`
        ).join(" ") + "</div>";
    }
    else if (type === "virtual") {
      modalType.style.color = "#8b5cf6";
      modalType.textContent = "VIRTUAL";
      modalTitle.textContent = node.data("label");
      const backlinks = node.data("backlinks") || [];
      modalBody.innerHTML =
        `<div class="backlink-list"><b style="color:#9098b0">Referenced by ${backlinks.length} file${backlinks.length !== 1 ? "s" : ""}:</b><br><br>` +
        backlinks.map(relpath => {
          const label = fileData[relpath] ? fileData[relpath].label : relpath;
          return `<span class="backlink-item" data-node-id="${relpath}">${label}</span>`;
        }).join(" ") + "</div>";
    }
  }

  function highlightNode(node) {
    cy.elements().removeClass("highlighted faded");
    cy.elements().addClass("faded");
    const neighbourhood = node.closedNeighborhood();
    neighbourhood.removeClass("faded").addClass("highlighted");
    neighbourhood.connectedEdges().removeClass("faded").addClass("highlighted");
  }

  // -- Backlink navigation -------------------------------------------------
  document.getElementById("modal-body").addEventListener("click", function(evt) {
    const item = evt.target.closest(".backlink-item");
    if (!item) return;
    const nodeId = item.dataset.nodeId;
    const targetNode = cy.getElementById(nodeId);
    if (targetNode.length) {
      modalOverlay.style.display = "none";
      cy.animate({ center: { eles: targetNode }, zoom: 2, duration: 400 });
      highlightNode(targetNode);
      setTimeout(() => showModal(targetNode), 450);
    }
  });

  // -- Node interactions ---------------------------------------------------
  cy.on("tap", "node", function(evt) {
    const node = evt.target;
    highlightNode(node);
    showModal(node);
  });

  cy.on("tap", function(evt) {
    if (evt.target === cy) {
      cy.elements().removeClass("highlighted faded");
      modalOverlay.style.display = "none";
    }
  });

  // Close modal on overlay click (but not on modal itself)
  modalOverlay.addEventListener("click", function(evt) {
    if (evt.target === modalOverlay) {
      modalOverlay.style.display = "none";
    }
  });

  document.getElementById("modal-close").addEventListener("click", function() {
    modalOverlay.style.display = "none";
  });

  // Close modal on Escape key
  document.addEventListener("keydown", function(evt) {
    if (evt.key === "Escape") {
      modalOverlay.style.display = "none";
    }
  });

  // -- Search --------------------------------------------------------------
  const searchInput = document.getElementById("search");
  const matchCount  = document.getElementById("match-count");

  searchInput.addEventListener("input", function() {
    const query = this.value.trim().toLowerCase();
    cy.nodes().removeClass("search-match");
    if (!query) { matchCount.textContent = ""; return; }

    const matches = cy.nodes().filter(n =>
      n.data("label").toLowerCase().includes(query)
    );
    matches.addClass("search-match");
    matchCount.textContent = matches.length
      ? `${matches.length} match${matches.length !== 1 ? "es" : ""}`
      : "No matches";
    if (matches.length > 0) {
      cy.animate({ fit: { eles: matches, padding: 80 }, duration: 400 });
    }
  });

  // -- View buttons --------------------------------------------------------
  document.getElementById("btn-fit").addEventListener("click", () => {
    cy.fit(undefined, 40);
  });

  document.getElementById("btn-reset").addEventListener("click", () => {
    searchInput.value = "";
    matchCount.textContent = "";
    cy.nodes().removeClass("search-match highlighted faded");
    cy.edges().removeClass("highlighted faded");
    modalOverlay.style.display = "none";
    cy.fit(undefined, 40);
  });

  // -- Layout switcher -----------------------------------------------------
  document.querySelectorAll(".layout-btn").forEach(btn => {
    btn.addEventListener("click", function() {
      document.querySelectorAll(".layout-btn").forEach(b => b.classList.remove("active"));
      this.classList.add("active");
      cy.layout(layoutConfig(this.dataset.layout)).run();
    });
  });
  </script>
</body>
</html>"""


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Generate an interactive Cytoscape.js prose graph from markdown files."
    )
    parser.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="Directory to scan (default: current directory)",
    )
    parser.add_argument(
        "-o", "--output",
        default=None,
        help="Output HTML file path (default: ./prose-graph.html)",
    )
    parser.add_argument(
        "--virtual",
        action="store_true",
        default=False,
        help="Create virtual nodes for unresolved wiki links (disabled by default)",
    )
    args = parser.parse_args()

    scan_path = os.path.abspath(args.directory)
    if not os.path.isdir(scan_path):
        print(f"Error: not a directory: {scan_path}", file=sys.stderr)
        sys.exit(1)

    output_path = args.output or os.path.join(os.getcwd(), "prose-graph.html")

    # Scan
    print(f"Scanning: {scan_path}")
    data = scan_markdown_files(scan_path)

    file_data = data["file_data"]
    tag_degree = data["tag_degree"]

    # Page title from the scan directory name
    page_title = os.path.basename(scan_path)

    # Prepare JSON-safe file data (label, tags, body for each file)
    file_data_json = {}
    for rel, info in file_data.items():
        file_data_json[rel] = {
            "label": info["label"],
            "tags": info["tags"],
            "body": info["body"],
        }

    # Generate HTML
    html = HTML_TEMPLATE
    html = html.replace("/*FILE_DATA*/", json.dumps(file_data_json, indent=2, ensure_ascii=False))
    tag_edges = data["tag_edges"] if args.virtual else []
    virtual_nodes = data["virtual_nodes"] if args.virtual else {}
    virtual_edges = data["virtual_edges"] if args.virtual else []
    html = html.replace("/*TAG_EDGES*/", json.dumps(tag_edges, ensure_ascii=False))
    html = html.replace("/*FILE_EDGES*/", json.dumps(data["file_edges"], ensure_ascii=False))
    html = html.replace("/*VIRTUAL_NODES*/", json.dumps(virtual_nodes, ensure_ascii=False))
    html = html.replace("/*VIRTUAL_EDGES*/", json.dumps(virtual_edges, ensure_ascii=False))
    html = html.replace("/*PAGE_TITLE*/", page_title)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    # Summary
    num_files = len(file_data)
    num_tags = len(tag_degree)
    num_virtual = len(virtual_nodes)
    num_tag_edges = len(tag_edges)
    num_wiki_links = len(data["file_edges"]) + len(virtual_edges)

    print(f"Generated: {output_path}")
    print(f"  {num_files} files, {num_tags} tags, {num_virtual} virtual nodes")
    print(f"  {num_tag_edges} tag edges, {num_wiki_links} wiki-links")


if __name__ == "__main__":
    main()
