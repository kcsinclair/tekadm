#!/usr/bin/env python3
"""
Generate an interactive 3D force-directed prose graph from markdown files.

Uses 3d-force-graph (https://github.com/vasturiano/3d-force-graph) to produce
a self-contained HTML visualization where clicking a node opens a modal
displaying the prose content.

Usage:
    python3 generate_prose_graph_3d.py
    python3 generate_prose_graph_3d.py randomProse/
    python3 generate_prose_graph_3d.py randomProse/ -o my-graph-3d.html
    python3 generate_prose_graph_3d.py randomProse/ --virtual
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
        for line in fm:
            m = re.match(r"^\s*tags\s*=\s*\[(.*)\]\s*$", line)
            if m:
                for item in m.group(1).split(","):
                    item = item.strip().strip("\"'")
                    if item:
                        tags.add(item)
        return tags

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
    """Extract display-ready prose body from markdown content."""
    lines = content.split("\n")
    start = 0

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

        if stripped and re.match(r"^(#[A-Za-z][\w-]*\s*)+$", stripped):
            continue
        if stripped and re.match(r"^(\[\[[^\]]+\]\]\s*)+$", stripped):
            continue
        if not heading_stripped and re.match(r"^#\s", stripped):
            heading_stripped = True
            continue

        line = re.sub(r"\[\[([^\]|]+?)\|([^\]]*?)\]\]", r"{{LINK:\1:\2}}", line)
        line = re.sub(r"\[\[([^\]]+?)\]\]", r"{{LINK:\1:\1}}", line)

        result.append(line)

    while result and not result[0].strip():
        result.pop(0)
    while result and not result[-1].strip():
        result.pop()

    return "\n".join(result)


# ── File scanning ─────────────────────────────────────────────────────────────

def scan_markdown_files(scan_path: str) -> dict:
    """Walk scan_path recursively, extract data from all .md files."""
    file_data = {}
    raw_links = []
    basename_lookup = {}
    relpath_lookup = {}

    for root, _dirs, files in os.walk(scan_path):
        for fname in sorted(files):
            if not fname.endswith(".md"):
                continue
            full_path = os.path.join(root, fname)
            rel = os.path.relpath(full_path, scan_path)

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
            wiki_links = re.findall(r"\{\{LINK:([^:}]+):([^}]+)\}\}", body)

            file_data[rel] = {
                "label": base,
                "tags": normalized_tags,
                "body": body,
            }

            for raw_target, display in wiki_links:
                raw_links.append((rel, raw_target, display))

    tag_edges = []
    file_edges = []
    virtual_nodes = {}
    virtual_edges = []

    tag_degree = {}
    for rel, info in file_data.items():
        for tag in info["tags"]:
            tag_edges.append((rel, tag))
            tag_degree[tag] = tag_degree.get(tag, 0) + 1

    for source_rel, raw_target, display in raw_links:
        source_base = os.path.splitext(os.path.basename(source_rel))[0]
        target_base = os.path.splitext(os.path.basename(raw_target))[0]
        if target_base == source_base:
            continue

        target_rel = None
        if raw_target in basename_lookup:
            target_rel = basename_lookup[raw_target]
        elif target_base in basename_lookup:
            target_rel = basename_lookup[target_base]
        elif raw_target in relpath_lookup:
            target_rel = relpath_lookup[raw_target]
        elif os.path.splitext(raw_target)[0] in relpath_lookup:
            target_rel = relpath_lookup[os.path.splitext(raw_target)[0]]

        if target_rel and target_rel in file_data and target_rel != source_rel:
            file_edges.append((source_rel, target_rel))
        else:
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
  <title>/*PAGE_TITLE*/ — 3D Graph</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      background: #0a0a1a;
      color: #e0e0f0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      overflow: hidden;
    }

    #graph { width: 100vw; height: 100vh; }

    /* -- Controls panel (top-left) ---------------------------------- */
    .panel {
      position: fixed;
      z-index: 20;
      background: rgba(20, 20, 40, 0.92);
      backdrop-filter: blur(10px);
      border: 1px solid rgba(255, 255, 255, 0.08);
      border-radius: 10px;
      box-shadow: 0 2px 16px rgba(0,0,0,0.4);
    }

    .panel h3 {
      font-size: 11px;
      font-weight: 700;
      color: #7880a8;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      margin-bottom: 10px;
    }

    #controls {
      top: 12px;
      left: 12px;
      padding: 14px;
      width: 220px;
    }

    #search {
      width: 100%;
      background: rgba(255,255,255,0.06);
      border: 1px solid rgba(255,255,255,0.12);
      color: #e0e0f0;
      padding: 7px 10px;
      border-radius: 6px;
      font-size: 13px;
      outline: none;
      transition: border-color 0.2s;
    }

    #search:focus { border-color: #5b8af5; }
    #search::placeholder { color: #556; }

    #match-count {
      font-size: 11px;
      color: #667;
      margin-top: 6px;
      min-height: 15px;
    }

    .section-label {
      font-size: 10px;
      font-weight: 600;
      color: #667;
      letter-spacing: 0.05em;
      text-transform: uppercase;
      margin: 10px 0 5px;
    }

    .btn-row { display: flex; gap: 5px; margin-top: 5px; }

    button {
      background: rgba(255,255,255,0.06);
      border: 1px solid rgba(255,255,255,0.1);
      color: #aab;
      padding: 5px 8px;
      border-radius: 6px;
      font-size: 11px;
      cursor: pointer;
      flex: 1;
      transition: background 0.15s, border-color 0.15s;
      white-space: nowrap;
    }

    button:hover {
      background: rgba(255,255,255,0.12);
      border-color: rgba(255,255,255,0.2);
    }

    /* -- Legend (top-right) ----------------------------------------- */
    #legend {
      top: 12px;
      right: 12px;
      padding: 12px 14px;
      font-size: 12px;
      line-height: 1.9;
    }

    .legend-row { display: flex; align-items: center; gap: 8px; color: #aab; }

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
      background: rgba(139, 92, 246, 0.4);
      border: 2px dashed #8b5cf6;
      transform: rotate(45deg);
      flex-shrink: 0;
    }

    /* -- Modal overlay ---------------------------------------------- */
    #modal-overlay {
      display: none;
      position: fixed;
      top: 0; left: 0; right: 0; bottom: 0;
      background: rgba(0, 0, 0, 0.6);
      backdrop-filter: blur(4px);
      z-index: 100;
      justify-content: center;
      align-items: center;
    }

    #modal {
      background: #1a1a2e;
      border: 1px solid rgba(255,255,255,0.08);
      border-radius: 14px;
      box-shadow: 0 8px 40px rgba(0,0,0,0.5);
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
      color: #667;
      cursor: pointer;
      flex: unset;
      padding: 4px 8px;
      line-height: 1;
    }

    #modal-close:hover { color: #e0e0f0; background: none; }

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
      color: #e0e0f0;
      margin-bottom: 16px;
      line-height: 1.4;
      word-break: break-word;
    }

    #modal-body {
      font-size: 15px;
      color: #aab0c8;
      line-height: 1.8;
      word-break: break-word;
    }

    #modal-body .md-para { white-space: pre-wrap; margin-bottom: 12px; }
    #modal-body .md-h1, #modal-body .md-h2, #modal-body .md-h3,
    #modal-body .md-h4, #modal-body .md-h5, #modal-body .md-h6 {
      color: #8ba4d0;
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
      color: #7db4f0;
      text-decoration: underline;
      text-decoration-style: dotted;
      text-underline-offset: 2px;
    }
    #modal-body .md-url:hover { color: #a3cbff; text-decoration-style: solid; }
    #modal-body .backlink-list { white-space: normal; }

    .backlink-item {
      display: inline-block;
      margin: 3px 0;
      padding: 4px 10px;
      background: rgba(91, 138, 245, 0.12);
      border: 1px solid rgba(91, 138, 245, 0.25);
      border-radius: 6px;
      color: #5b8af5;
      cursor: pointer;
      font-size: 13px;
      transition: background 0.15s;
    }

    .backlink-item:hover { background: rgba(91, 138, 245, 0.22); }

    .backlink-item.inline-link {
      display: inline;
      margin: 0;
      padding: 0 1px;
      background: none;
      border: none;
      border-bottom: 1px dashed #5b8af5;
      border-radius: 0;
      color: #5b8af5;
      font-size: inherit;
    }

    .backlink-item.inline-link:hover {
      background: rgba(91, 138, 245, 0.12);
      border-bottom-style: solid;
    }

    .backlink-item.tag-link {
      background: rgba(224, 123, 26, 0.12);
      border-color: rgba(224, 123, 26, 0.25);
      color: #e07b1a;
    }

    .backlink-item.tag-link:hover { background: rgba(224, 123, 26, 0.22); }

    .backlink-item.virtual-link {
      background: rgba(139, 92, 246, 0.12);
      border-color: rgba(139, 92, 246, 0.25);
      color: #a78bfa;
    }

    .backlink-item.virtual-link:hover { background: rgba(139, 92, 246, 0.22); }

    /* -- Stats (bottom-right) --------------------------------------- */
    #stats {
      position: fixed;
      bottom: 12px;
      right: 12px;
      z-index: 20;
      background: rgba(20,20,40,0.80);
      border: 1px solid rgba(255,255,255,0.06);
      border-radius: 8px;
      box-shadow: 0 1px 6px rgba(0,0,0,0.3);
      padding: 7px 12px;
      font-size: 11px;
      color: #667;
    }

    /* -- Node tooltip ----------------------------------------------- */
    .node-tooltip {
      background: rgba(20,20,40,0.95);
      border: 1px solid rgba(255,255,255,0.12);
      border-radius: 6px;
      padding: 6px 10px;
      font-size: 12px;
      color: #e0e0f0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
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
      <button id="btn-reset-cam">Reset Camera</button>
      <button id="btn-refresh-layout">Refresh Layout</button>
    </div>
    <div class="btn-row">
      <button id="btn-toggle-labels">Labels: On</button>
      <button id="btn-toggle-particles">Particles: On</button>
    </div>
    <div class="btn-row" style="/*SINGLETON_DISPLAY*/">
      <button id="btn-toggle-singletons">Singleton tags: Hidden</button>
    </div>
  </div>

  <!-- Legend -->
  <div id="legend" class="panel" style="/*LEGEND_DISPLAY*/">
    <h3>Legend</h3>
    <div class="legend-row"><span class="dot" style="background:#5b8af5"></span> File</div>
    <div class="legend-row"><span class="dot" style="background:#facc15"></span> Inbound only</div>
    <div class="legend-row"><span class="dot" style="background:#a855f7"></span> Outbound only</div>
    <div class="legend-row"><span class="tag-shape" style="background:#e07b1a"></span> Tag</div>
    <div class="legend-row"><span class="diamond-shape"></span> Virtual (unresolved link)</div>
    <div class="legend-row"><span style="display:inline-block;width:14px;height:2px;border-top:2px dashed #7db4f0;flex-shrink:0"></span> Wiki-link</div>
    <div class="legend-row"><span style="display:inline-block;width:14px;height:1px;border-top:1px solid #445;flex-shrink:0"></span> Tag connection</div>
    <div class="legend-row" style="margin-top:3px;color:#556;font-size:11px">Node size = connections</div>
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

  <div id="graph"></div>

  <script src="https://unpkg.com/three@0.160.0/build/three.min.js"></script>
  <script src="https://unpkg.com/3d-force-graph@1.76.0/dist/3d-force-graph.min.js"></script>

  <script>
  // -- Data ----------------------------------------------------------------
  const fileData     = /*FILE_DATA*/;
  const tagEdges     = /*TAG_EDGES*/;
  const fileEdges    = /*FILE_EDGES*/;
  const virtualNodes = /*VIRTUAL_NODES*/;
  const virtualEdges = /*VIRTUAL_EDGES*/;

  // -- Build graph data ----------------------------------------------------
  const nodes = [];
  const links = [];
  const nodeDegree = {};

  // Count degrees for sizing
  for (const [src, tgt] of fileEdges) {
    nodeDegree[src] = (nodeDegree[src] || 0) + 1;
    nodeDegree[tgt] = (nodeDegree[tgt] || 0) + 1;
  }
  for (const [src, tag] of tagEdges) {
    nodeDegree[src] = (nodeDegree[src] || 0) + 1;
    nodeDegree["tag:" + tag] = (nodeDegree["tag:" + tag] || 0) + 1;
  }
  for (const [src, vlabel] of virtualEdges) {
    nodeDegree[src] = (nodeDegree[src] || 0) + 1;
    nodeDegree["virtual:" + vlabel] = (nodeDegree["virtual:" + vlabel] || 0) + 1;
  }

  // Determine which file nodes have outbound wiki-links
  // Determine outbound and inbound wiki-links per file node
  const hasOutbound = new Set();
  const hasInbound = new Set();
  for (const [src, tgt] of fileEdges) { hasOutbound.add(src); hasInbound.add(tgt); }
  for (const [src,] of virtualEdges) { hasOutbound.add(src); }

  // File nodes
  for (const [relpath, info] of Object.entries(fileData)) {
    const inboundOnly = !hasOutbound.has(relpath) && hasInbound.has(relpath);
    const outboundOnly = hasOutbound.has(relpath) && !hasInbound.has(relpath);
    const nodeColor = inboundOnly ? "#facc15"
                    : outboundOnly ? "#a855f7"
                    : "#5b8af5";
    nodes.push({
      id: relpath,
      label: info.label,
      type: "file",
      body: info.body,
      tags: info.tags,
      degree: nodeDegree[relpath] || 1,
      color: nodeColor
    });
  }

  // Tag nodes
  const tagDegree = {};
  for (const [, tag] of tagEdges) {
    tagDegree[tag] = (tagDegree[tag] || 0) + 1;
  }
  for (const [tag, deg] of Object.entries(tagDegree)) {
    nodes.push({
      id: "tag:" + tag,
      label: tag,
      type: "tag",
      degree: nodeDegree["tag:" + tag] || 1,
      color: "#e07b1a"
    });
  }

  // Virtual nodes
  for (const [label, backlinks] of Object.entries(virtualNodes)) {
    nodes.push({
      id: "virtual:" + label,
      label: label,
      type: "virtual",
      backlinks: backlinks,
      degree: nodeDegree["virtual:" + label] || 1,
      color: "#8b5cf6"
    });
  }

  // Tag edges
  for (const [src, tag] of tagEdges) {
    links.push({
      source: src,
      target: "tag:" + tag,
      type: "tag"
    });
  }

  // File-to-file wiki-link edges
  for (const [src, tgt] of fileEdges) {
    links.push({
      source: src,
      target: tgt,
      type: "wiki-link"
    });
  }

  // Virtual edges
  for (const [src, vlabel] of virtualEdges) {
    links.push({
      source: src,
      target: "virtual:" + vlabel,
      type: "wiki-link"
    });
  }

  // -- Node lookup ---------------------------------------------------------
  const nodeMap = {};
  for (const n of nodes) { nodeMap[n.id] = n; }

  // -- 3D Graph init -------------------------------------------------------
  let showLabels = true;
  let showParticles = true;
  let showSingletonTags = false;

  function isSingletonTag(n) {
    return n.type === "tag" && (n.degree || 0) <= 1;
  }
  function nodeVisible(n) {
    return showSingletonTags || !isSingletonTag(n);
  }
  function linkVisible(l) {
    const src = typeof l.source === "object" ? l.source : nodeMap[l.source];
    const tgt = typeof l.target === "object" ? l.target : nodeMap[l.target];
    return nodeVisible(src) && nodeVisible(tgt);
  }

  function makeLabelSprite(n) {
    if (!showLabels) return false;
    const THREE = window.THREE;
    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d");
    const text = n.label;
    const fontSize = 48;
    ctx.font = `${fontSize}px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`;
    const textWidth = ctx.measureText(text).width;
    canvas.width = textWidth + 16;
    canvas.height = fontSize + 16;
    ctx.font = `${fontSize}px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`;
    ctx.fillStyle = n.type === "file" ? "#8899cc"
                  : n.type === "tag" ? "#cc8833"
                  : "#9977cc";
    ctx.textBaseline = "middle";
    ctx.fillText(text, 8, canvas.height / 2);
    const texture = new THREE.CanvasTexture(canvas);
    texture.minFilter = THREE.LinearFilter;
    const spriteMaterial = new THREE.SpriteMaterial({ map: texture, transparent: true });
    const sprite = new THREE.Sprite(spriteMaterial);
    const scaleFactor = 0.07;
    sprite.scale.set(canvas.width * scaleFactor, canvas.height * scaleFactor, 1);
    sprite.position.y = Math.max(2, Math.sqrt(n.degree) * 1.5) + 3;
    return sprite;
  }

  const Graph = new ForceGraph3D(document.getElementById("graph"))
    .graphData({ nodes, links })
    .backgroundColor("#0a0a1a")
    .nodeVal(n => Math.max(1, Math.sqrt(n.degree) * 1.5))
    .nodeColor(n => {
      if (n.__highlighted) return "#fff";
      if (n.__searchMatch) return "#ef4444";
      return n.color;
    })
    .nodeOpacity(0.9)
    .nodeVisibility(nodeVisible)
    .linkVisibility(linkVisible)
    .nodeLabel(n => `<div class="node-tooltip"><b>${n.label}</b>${n.type !== "file" ? " (" + n.type + ")" : ""}</div>`)
    .linkWidth(l => l.type === "wiki-link" ? 1.5 : 1.6)
    .linkColor(l => l.type === "wiki-link" ? "rgba(125,180,240,0.6)" : "rgba(224,123,26,0.75)")
    .linkDirectionalArrowLength(l => l.type === "wiki-link" ? 4 : 0)
    .linkDirectionalArrowRelPos(1)
    .linkDirectionalArrowColor(l => "rgba(125,180,240,0.6)")
    .linkDirectionalParticles(l => showParticles && l.type === "wiki-link" ? 2 : 0)
    .linkDirectionalParticleWidth(1.5)
    .linkDirectionalParticleColor(l => "#7db4f0")
    .linkDirectionalParticleSpeed(0.005)
    .onNodeClick(handleNodeClick)
    .onBackgroundClick(handleBgClick)
    .nodeThreeObjectExtend(true)
    .nodeThreeObject(makeLabelSprite);

  // Adjust force parameters
  Graph.d3Force("charge").strength(-120);
  Graph.d3Force("link").distance(l => l.type === "wiki-link" ? 40 : 60);

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
    modalOverlay.style.display = "flex";

    if (node.type === "file") {
      modalType.style.color = "#5b8af5";
      modalType.textContent = "";
      modalTitle.textContent = node.label;
      modalBody.innerHTML = "";
      renderMarkdown(modalBody, node.body || "(empty)");
      const info = fileData[node.id];
      if (info && info.tags && info.tags.length > 0) {
        const tagWrap = document.createElement("div");
        tagWrap.className = "backlink-list";
        tagWrap.style.cssText = "margin-top:16px;padding-top:12px;border-top:1px solid rgba(255,255,255,0.08)";
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
    else if (node.type === "tag") {
      modalType.style.color = "#e07b1a";
      modalType.textContent = "";
      modalTitle.textContent = "#" + node.label;
      const connectedFiles = links
        .filter(l => {
          const src = typeof l.source === "object" ? l.source.id : l.source;
          const tgt = typeof l.target === "object" ? l.target.id : l.target;
          return src === node.id || tgt === node.id;
        })
        .map(l => {
          const src = typeof l.source === "object" ? l.source.id : l.source;
          const tgt = typeof l.target === "object" ? l.target.id : l.target;
          return src === node.id ? tgt : src;
        })
        .filter(id => nodeMap[id] && nodeMap[id].type === "file");
      modalBody.innerHTML =
        `<div class="backlink-list"><b style="color:#667">Used in ${connectedFiles.length} file${connectedFiles.length !== 1 ? "s" : ""}:</b><br><br>` +
        connectedFiles.map(id =>
          `<span class="backlink-item" data-node-id="${id}">${nodeMap[id].label}</span>`
        ).join(" ") + "</div>";
    }
    else if (node.type === "virtual") {
      modalType.style.color = "#a78bfa";
      modalType.textContent = "";
      modalTitle.textContent = node.label;
      const backlinks = node.backlinks || [];
      modalBody.innerHTML =
        `<div class="backlink-list"><b style="color:#667">Referenced by ${backlinks.length} file${backlinks.length !== 1 ? "s" : ""}:</b><br><br>` +
        backlinks.map(relpath => {
          const label = fileData[relpath] ? fileData[relpath].label : relpath;
          return `<span class="backlink-item" data-node-id="${relpath}">${label}</span>`;
        }).join(" ") + "</div>";
    }
  }

  function focusNode(node) {
    const distance = 80;
    const distRatio = 1 + distance / Math.hypot(node.x, node.y, node.z);
    Graph.cameraPosition(
      { x: node.x * distRatio, y: node.y * distRatio, z: node.z * distRatio },
      node,
      1000
    );
  }

  function handleNodeClick(node) {
    // Clear previous highlights
    nodes.forEach(n => { n.__highlighted = false; });
    // Highlight this node and neighbours
    node.__highlighted = true;
    const connectedIds = new Set();
    links.forEach(l => {
      const src = typeof l.source === "object" ? l.source.id : l.source;
      const tgt = typeof l.target === "object" ? l.target.id : l.target;
      if (src === node.id) connectedIds.add(tgt);
      if (tgt === node.id) connectedIds.add(src);
    });
    connectedIds.forEach(id => {
      if (nodeMap[id]) nodeMap[id].__highlighted = true;
    });
    Graph.nodeColor(Graph.nodeColor()); // refresh
    focusNode(node);
    showModal(node);
  }

  function handleBgClick() {
    nodes.forEach(n => { n.__highlighted = false; });
    Graph.nodeColor(Graph.nodeColor());
    modalOverlay.style.display = "none";
  }

  // -- Backlink navigation -------------------------------------------------
  document.getElementById("modal-body").addEventListener("click", function(evt) {
    const item = evt.target.closest(".backlink-item");
    if (!item) return;
    const nodeId = item.dataset.nodeId;
    const targetNode = nodeMap[nodeId];
    if (targetNode) {
      modalOverlay.style.display = "none";
      setTimeout(() => {
        handleNodeClick(targetNode);
      }, 100);
    }
  });

  // Close modal
  modalOverlay.addEventListener("click", function(evt) {
    if (evt.target === modalOverlay) modalOverlay.style.display = "none";
  });
  document.getElementById("modal-close").addEventListener("click", function() {
    modalOverlay.style.display = "none";
  });
  document.addEventListener("keydown", function(evt) {
    if (evt.key === "Escape") modalOverlay.style.display = "none";
  });

  // -- Search --------------------------------------------------------------
  const searchInput = document.getElementById("search");
  const matchCount  = document.getElementById("match-count");

  searchInput.addEventListener("input", function() {
    const query = this.value.trim().toLowerCase();
    nodes.forEach(n => { n.__searchMatch = false; });

    if (!query) {
      matchCount.textContent = "";
      Graph.nodeColor(Graph.nodeColor());
      return;
    }

    let count = 0;
    nodes.forEach(n => {
      if (n.label.toLowerCase().includes(query)) {
        n.__searchMatch = true;
        count++;
      }
    });
    matchCount.textContent = count
      ? `${count} match${count !== 1 ? "es" : ""}`
      : "No matches";
    Graph.nodeColor(Graph.nodeColor());
  });

  // -- Button controls -----------------------------------------------------
  document.getElementById("btn-reset-cam").addEventListener("click", () => {
    nodes.forEach(n => { n.__highlighted = false; n.__searchMatch = false; });
    searchInput.value = "";
    matchCount.textContent = "";
    Graph.nodeColor(Graph.nodeColor());
    Graph.cameraPosition({ x: 0, y: 0, z: 300 }, { x: 0, y: 0, z: 0 }, 1000);
    modalOverlay.style.display = "none";
  });

  const labelBtn = document.getElementById("btn-toggle-labels");
  labelBtn.addEventListener("click", () => {
    showLabels = !showLabels;
    labelBtn.textContent = "Labels: " + (showLabels ? "On" : "Off");
    Graph.nodeThreeObject(makeLabelSprite); // re-assign to trigger refresh
  });

  const particleBtn = document.getElementById("btn-toggle-particles");
  particleBtn.addEventListener("click", () => {
    showParticles = !showParticles;
    particleBtn.textContent = "Particles: " + (showParticles ? "On" : "Off");
    Graph.linkDirectionalParticles(Graph.linkDirectionalParticles()); // refresh
  });

  const singletonBtn = document.getElementById("btn-toggle-singletons");
  singletonBtn.addEventListener("click", () => {
    showSingletonTags = !showSingletonTags;
    singletonBtn.textContent = "Singleton tags: " + (showSingletonTags ? "Shown" : "Hidden");
    Graph.nodeVisibility(nodeVisible);
    Graph.linkVisibility(linkVisible);
  });

  const refreshBtn = document.getElementById("btn-refresh-layout");
  refreshBtn.addEventListener("click", () => {
    Graph.d3ReheatSimulation();
  });
  </script>
</body>
</html>"""


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Generate an interactive 3D force-directed prose graph from markdown files."
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
        help="Output HTML file path (default: ./prose-graph-3d.html)",
    )
    parser.add_argument(
        "--virtual",
        action="store_true",
        default=False,
        help="Create tag and virtual nodes for unresolved wiki links (disabled by default)",
    )
    parser.add_argument(
        "--legend",
        action="store_true",
        default=False,
        help="Display the legend panel (disabled by default)",
    )
    parser.add_argument(
        "--no-singletons",
        action="store_true",
        default=False,
        help="Exclude singleton tag nodes (tags used in only one file) from the graph",
    )
    args = parser.parse_args()

    scan_path = os.path.abspath(args.directory)
    if not os.path.isdir(scan_path):
        print(f"Error: not a directory: {scan_path}", file=sys.stderr)
        sys.exit(1)

    output_path = args.output or os.path.join(os.getcwd(), "prose-graph-3d.html")

    print(f"Scanning: {scan_path}")
    data = scan_markdown_files(scan_path)

    file_data = data["file_data"]
    tag_degree = data["tag_degree"]

    page_title = os.path.basename(scan_path)

    file_data_json = {}
    for rel, info in file_data.items():
        file_data_json[rel] = {
            "label": info["label"],
            "tags": info["tags"],
            "body": info["body"],
        }

    tag_edges = data["tag_edges"] if args.virtual else []
    virtual_nodes = data["virtual_nodes"] if args.virtual else {}
    virtual_edges = data["virtual_edges"] if args.virtual else []

    if args.no_singletons and tag_edges:
        tag_edges = [(src, tag) for src, tag in tag_edges if tag_degree.get(tag, 0) > 1]
        # Drop tags that no longer appear on any edge from tag_degree for accurate stats
        remaining_tags = {tag for _, tag in tag_edges}
        tag_degree = {t: d for t, d in tag_degree.items() if t in remaining_tags}

    html = HTML_TEMPLATE
    html = html.replace("/*FILE_DATA*/", json.dumps(file_data_json, indent=2, ensure_ascii=False))
    html = html.replace("/*TAG_EDGES*/", json.dumps(tag_edges, ensure_ascii=False))
    html = html.replace("/*FILE_EDGES*/", json.dumps(data["file_edges"], ensure_ascii=False))
    html = html.replace("/*VIRTUAL_NODES*/", json.dumps(virtual_nodes, ensure_ascii=False))
    html = html.replace("/*VIRTUAL_EDGES*/", json.dumps(virtual_edges, ensure_ascii=False))
    html = html.replace("/*PAGE_TITLE*/", page_title)
    html = html.replace("/*LEGEND_DISPLAY*/", "" if args.legend else "display:none")
    html = html.replace("/*SINGLETON_DISPLAY*/", "display:none" if args.no_singletons else "")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

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
