#!/usr/bin/env python3
"""
Generate an interactive 3D force-directed tag graph from Obsidian markdown files.

Uses 3d-force-graph (https://github.com/vasturiano/3d-force-graph) to produce
a self-contained HTML visualization. Files appear as coloured spheres, tags as
orange spheres, and wiki-links as directed edges with particle flow.

Mirrors the modes and Obsidian-URI integration of generate_tag_graph.py:
    article mode: status-tag colouring (published / blog-idea / ideas / draft)
    link mode:    Cool Tek Technology Links variant

Usage:
    python3 generate_tag_graph_3d.py
    python3 generate_tag_graph_3d.py --scan-dir "Ideas and Concepts"
    python3 generate_tag_graph_3d.py --mode link
    python3 generate_tag_graph_3d.py --scan-dir "NM_Book" --vault-name "Obsidian"
"""

import argparse
import json
import os
import re
import sys


# ── Tag extraction ────────────────────────────────────────────────────────────

def parse_frontmatter_tags(content: str) -> set[str]:
    """Extract tags from YAML frontmatter."""
    if not content.startswith("---"):
        return set()

    end = content.find("\n---", 3)
    if end == -1:
        return set()

    frontmatter = content[3:end]

    try:
        import yaml
        data = yaml.safe_load(frontmatter)
        if isinstance(data, dict) and "tags" in data:
            tags = data["tags"]
            if isinstance(tags, list):
                return {str(t) for t in tags}
            elif isinstance(tags, str):
                return {tags}
        return set()
    except ImportError:
        pass

    tags = set()
    in_tags = False
    for line in frontmatter.split("\n"):
        stripped = line.strip()
        if stripped == "tags:" or stripped.startswith("tags:"):
            rest = stripped[5:].strip()
            if rest.startswith("["):
                items = rest.strip("[]").split(",")
                tags.update(i.strip().strip("'\"") for i in items if i.strip())
                return tags
            in_tags = True
            continue
        if in_tags:
            if stripped.startswith("- "):
                tags.add(stripped[2:].strip().strip("'\""))
            elif stripped and not stripped.startswith("-"):
                in_tags = False
    return tags


def extract_inline_tags(content: str) -> set[str]:
    """Extract inline hashtags from markdown content, skipping headings and code blocks."""
    tags = set()
    in_code_block = False

    lines = content.split("\n")
    start = 0
    if lines and lines[0].strip() == "---":
        for i, line in enumerate(lines[1:], 1):
            if line.strip() == "---":
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


def extract_wiki_links(content: str) -> set[str]:
    """Extract Obsidian [[wiki-links]] from markdown content."""
    links = set()
    in_code_block = False
    for line in content.split("\n"):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue
        for m in re.finditer(r"\[\[([^\]|]+?)(?:\|[^\]]*?)?\]\]", line):
            target = m.group(1).strip()
            if target:
                links.add(target)
    return links


# ── File scanning ─────────────────────────────────────────────────────────────

def scan_markdown_files(scan_path: str) -> tuple[dict[str, list[str]], list[tuple[str, str]]]:
    """Walk scan_path, extract tags and wiki-links from all .md files."""
    result = {}
    raw_links = []
    all_filenames = {}

    for root, _dirs, files in os.walk(scan_path):
        for fname in sorted(files):
            if not fname.endswith(".md"):
                continue
            full_path = os.path.join(root, fname)
            rel = os.path.relpath(full_path, scan_path)

            base = os.path.splitext(fname)[0]
            all_filenames[base] = rel
            all_filenames[fname] = rel

            try:
                with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
            except OSError:
                continue

            tags = parse_frontmatter_tags(content) | extract_inline_tags(content)
            normalized = {normalize_tag(t) for t in tags}
            normalized.discard("")
            if normalized:
                result[rel] = sorted(normalized)

            for link_target in extract_wiki_links(content):
                raw_links.append((rel, link_target))

    file_links = []
    for source, raw_target in raw_links:
        target_rel = all_filenames.get(raw_target)
        if not target_rel:
            target_no_ext = os.path.splitext(raw_target)[0]
            target_rel = all_filenames.get(target_no_ext)
        if target_rel and target_rel != source and target_rel in result:
            file_links.append((source, target_rel))

    return dict(sorted(result.items())), file_links


# ── HTML template ─────────────────────────────────────────────────────────────

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>/*PAGE_TITLE*/ — 3D Tag Graph</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      background: #0a0a1a;
      color: #e0e0f0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      overflow: hidden;
    }

    #graph { width: 100vw; height: 100vh; }

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
      width: 230px;
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
      font-size: 14px;
      color: #aab0c8;
      line-height: 1.7;
      word-break: break-word;
    }

    #modal-body .backlink-list { white-space: normal; }

    .backlink-item {
      display: inline-block;
      margin: 3px 2px;
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

    .backlink-item.tag-link {
      background: rgba(224, 123, 26, 0.12);
      border-color: rgba(224, 123, 26, 0.25);
      color: #e07b1a;
    }

    .backlink-item.tag-link:hover { background: rgba(224, 123, 26, 0.22); }

    .backlink-item.wiki-link {
      background: rgba(125, 180, 240, 0.12);
      border-color: rgba(125, 180, 240, 0.25);
      color: #7db4f0;
    }

    .backlink-item.wiki-link:hover { background: rgba(125, 180, 240, 0.22); }

    #modal-open {
      margin-top: 18px;
      width: 100%;
      background: rgba(91, 138, 245, 0.15);
      border-color: rgba(91, 138, 245, 0.35);
      color: #7db4f0;
      padding: 8px 12px;
      font-size: 12px;
      display: none;
    }

    #modal-open:hover {
      background: rgba(91, 138, 245, 0.25);
      border-color: rgba(91, 138, 245, 0.55);
    }

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
    </div>
    <div class="btn-row">
      <button id="btn-toggle-labels">Labels: On</button>
      <button id="btn-toggle-particles">Particles: On</button>
    </div>
    <div class="btn-row">
      <button id="btn-toggle-tags">Tag Edges: On</button>
    </div>
  </div>

  <!-- Legend -->
  <div id="legend" class="panel">
    <h3>Legend</h3>
    /*LEGEND_HTML*/
  </div>

  <!-- Modal -->
  <div id="modal-overlay">
    <div id="modal">
      <button id="modal-close">&times;</button>
      <div id="modal-type"></div>
      <div id="modal-title"></div>
      <div id="modal-body"></div>
      <button id="modal-open">Open in Obsidian &#8599;</button>
    </div>
  </div>

  <!-- Stats -->
  <div id="stats"></div>

  <div id="graph"></div>

  <script src="https://unpkg.com/three@0.160.0/build/three.min.js"></script>
  <script src="https://unpkg.com/3d-force-graph@1.76.0/dist/3d-force-graph.min.js"></script>

  <script>
  // -- Data ----------------------------------------------------------------
  const VAULT       = "/*VAULT_NAME*/";
  const PATH_PREFIX = "/*PATH_PREFIX*/";
  const MODE        = "/*MODE*/";
  const STATUS_TAGS = new Set(/*STATUS_TAGS_JSON*/);

  const fileData  = /*FILE_DATA*/;
  const fileLinks = /*FILE_LINKS*/;

  // -- Build graph data ----------------------------------------------------
  const minTagDegree = MODE === "link" ? 2 : 1;

  const tagDegree = {};
  for (const tags of Object.values(fileData)) {
    for (const t of tags) {
      if (STATUS_TAGS.has(t)) continue;
      tagDegree[t] = (tagDegree[t] || 0) + 1;
    }
  }

  // Connection counts (for sizing)
  const nodeDegree = {};
  for (const [src, tgt] of fileLinks) {
    nodeDegree[src] = (nodeDegree[src] || 0) + 1;
    nodeDegree[tgt] = (nodeDegree[tgt] || 0) + 1;
  }
  for (const [fname, tags] of Object.entries(fileData)) {
    for (const t of tags) {
      if (STATUS_TAGS.has(t)) continue;
      if ((tagDegree[t] || 0) < minTagDegree) continue;
      nodeDegree[fname] = (nodeDegree[fname] || 0) + 1;
      nodeDegree["tag:" + t] = (nodeDegree["tag:" + t] || 0) + 1;
    }
  }

  function fileColor(tags) {
    if (MODE !== "article") return "#5b8af5";
    if (tags.includes("published")) return "#22c55e";
    if (tags.includes("blog-idea")) return "#eab308";
    if (tags.includes("ideas"))     return "#ef4444";
    return "#5b8af5";
  }

  function fileStatus(tags) {
    if (MODE !== "article") return null;
    if (tags.includes("published")) return "published";
    if (tags.includes("blog-idea")) return "blog-idea";
    if (tags.includes("ideas"))     return "ideas";
    return "draft";
  }

  const nodes = [];
  const links = [];

  // File nodes
  for (const [fname, tags] of Object.entries(fileData)) {
    nodes.push({
      id: fname,
      label: fname.replace(/\.md$/, ""),
      type: "file",
      tags: tags,
      status: fileStatus(tags),
      path: PATH_PREFIX + fname,
      degree: nodeDegree[fname] || 1,
      color: fileColor(tags)
    });
  }

  // Tag nodes
  for (const [tag, deg] of Object.entries(tagDegree)) {
    if (deg < minTagDegree) continue;
    nodes.push({
      id: "tag:" + tag,
      label: tag,
      type: "tag",
      degree: nodeDegree["tag:" + tag] || 1,
      color: "#e07b1a"
    });
  }

  // Tag edges
  for (const [fname, tags] of Object.entries(fileData)) {
    for (const tag of tags) {
      if (STATUS_TAGS.has(tag)) continue;
      if ((tagDegree[tag] || 0) < minTagDegree) continue;
      links.push({ source: fname, target: "tag:" + tag, type: "tag" });
    }
  }

  // File-to-file wiki-link edges
  for (const [src, tgt] of fileLinks) {
    links.push({ source: src, target: tgt, type: "wiki-link" });
  }

  // -- Node lookup ---------------------------------------------------------
  const nodeMap = {};
  for (const n of nodes) { nodeMap[n.id] = n; }

  // -- 3D Graph init -------------------------------------------------------
  let showLabels    = true;
  let showParticles = true;
  let showTagEdges  = true;

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
    ctx.fillStyle = n.type === "tag" ? "#cc8833" : "#aab8d8";
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

  function visibleLinks() {
    return showTagEdges ? links : links.filter(l => l.type === "wiki-link");
  }

  const Graph = new ForceGraph3D(document.getElementById("graph"))
    .graphData({ nodes, links: visibleLinks() })
    .backgroundColor("#0a0a1a")
    .nodeVal(n => Math.max(1, Math.sqrt(n.degree) * 1.5))
    .nodeColor(n => {
      if (n.__highlighted) return "#fff";
      if (n.__searchMatch) return "#f59e0b";
      return n.color;
    })
    .nodeOpacity(0.92)
    .nodeLabel(n => {
      const suffix = n.type === "tag" ? " (tag)"
                   : (n.type === "file" && n.status && MODE === "article") ? ` (${n.status})`
                   : "";
      return `<div class="node-tooltip"><b>${n.label}</b>${suffix}</div>`;
    })
    .linkWidth(l => l.type === "wiki-link" ? 1.5 : 0.6)
    .linkColor(l => l.type === "wiki-link" ? "rgba(125,180,240,0.6)" : "rgba(224,123,26,0.35)")
    .linkDirectionalArrowLength(l => l.type === "wiki-link" ? 4 : 0)
    .linkDirectionalArrowRelPos(1)
    .linkDirectionalArrowColor(() => "rgba(125,180,240,0.6)")
    .linkDirectionalParticles(l => showParticles && l.type === "wiki-link" ? 2 : 0)
    .linkDirectionalParticleWidth(1.5)
    .linkDirectionalParticleColor(() => "#7db4f0")
    .linkDirectionalParticleSpeed(0.005)
    .onNodeClick(handleNodeClick)
    .onBackgroundClick(handleBgClick)
    .nodeThreeObjectExtend(true)
    .nodeThreeObject(makeLabelSprite);

  Graph.d3Force("charge").strength(-120);
  Graph.d3Force("link").distance(l => l.type === "wiki-link" ? 40 : 60);

  // -- Stats ---------------------------------------------------------------
  const numFiles    = Object.keys(fileData).length;
  const numTags     = Object.keys(tagDegree).filter(t => tagDegree[t] >= minTagDegree).length;
  const numTagEdges = links.filter(l => l.type === "tag").length;
  const numWiki     = fileLinks.length;
  document.getElementById("stats").innerHTML =
    `${numFiles} files &middot; ${numTags} tags &middot; ${numTagEdges} tag edges` +
    (numWiki > 0 ? ` &middot; ${numWiki} wiki-links` : "");

  // -- Modal ---------------------------------------------------------------
  const modalOverlay = document.getElementById("modal-overlay");
  const modalType    = document.getElementById("modal-type");
  const modalTitle   = document.getElementById("modal-title");
  const modalBody    = document.getElementById("modal-body");
  const modalOpen    = document.getElementById("modal-open");

  function showModal(node) {
    modalOverlay.style.display = "flex";

    if (node.type === "file") {
      modalType.style.color = node.color;
      modalType.textContent = node.status ? node.status.toUpperCase() : "FILE";
      modalTitle.textContent = node.label;

      const tags = (node.tags || []).filter(t => !STATUS_TAGS.has(t));
      const wikiLinkedFiles = links.filter(l => l.type === "wiki-link").map(l => {
        const src = typeof l.source === "object" ? l.source.id : l.source;
        const tgt = typeof l.target === "object" ? l.target.id : l.target;
        if (src === node.id) return tgt;
        if (tgt === node.id) return src;
        return null;
      }).filter(id => id && nodeMap[id]);

      let html = "";
      if (tags.length > 0) {
        html += `<div style="color:#667;font-size:11px;font-weight:700;letter-spacing:0.06em;text-transform:uppercase;margin-bottom:8px">Tags</div>` +
          `<div class="backlink-list">` +
          tags.map(t =>
            `<span class="backlink-item tag-link" data-node-id="tag:${t}">#${t}</span>`
          ).join(" ") + "</div>";
      }
      if (wikiLinkedFiles.length > 0) {
        html += `<div style="color:#667;font-size:11px;font-weight:700;letter-spacing:0.06em;text-transform:uppercase;margin:14px 0 8px">Linked Files</div>` +
          `<div class="backlink-list">` +
          wikiLinkedFiles.map(id =>
            `<span class="backlink-item wiki-link" data-node-id="${id}">${nodeMap[id].label}</span>`
          ).join(" ") + "</div>";
      }
      if (!html) html = `<div style="color:#667">No tags or wiki-links</div>`;
      modalBody.innerHTML = html;

      modalOpen.style.display = "block";
      modalOpen.onclick = () => {
        window.location.href = "obsidian://open?vault=" +
          encodeURIComponent(VAULT) + "&file=" +
          encodeURIComponent(node.path);
      };
    }
    else if (node.type === "tag") {
      modalType.style.color = "#e07b1a";
      modalType.textContent = "TAG";
      modalTitle.textContent = "#" + node.label;

      const connectedFiles = links
        .filter(l => l.type === "tag")
        .map(l => {
          const src = typeof l.source === "object" ? l.source.id : l.source;
          const tgt = typeof l.target === "object" ? l.target.id : l.target;
          if (src === node.id) return tgt;
          if (tgt === node.id) return src;
          return null;
        })
        .filter(id => id && nodeMap[id])
        .sort((a, b) => nodeMap[a].label.localeCompare(nodeMap[b].label));

      modalBody.innerHTML =
        `<div style="color:#667;font-size:11px;font-weight:700;letter-spacing:0.06em;text-transform:uppercase;margin-bottom:8px">` +
        `Used in ${connectedFiles.length} file${connectedFiles.length !== 1 ? "s" : ""}</div>` +
        `<div class="backlink-list">` +
        connectedFiles.map(id =>
          `<span class="backlink-item" data-node-id="${id}">${nodeMap[id].label}</span>`
        ).join(" ") + "</div>";
      modalOpen.style.display = "none";
    }
  }

  function focusNode(node) {
    const distance = 80;
    const distRatio = 1 + distance / Math.hypot(node.x || 1, node.y || 1, node.z || 1);
    Graph.cameraPosition(
      { x: (node.x || 0) * distRatio, y: (node.y || 0) * distRatio, z: (node.z || 0) * distRatio },
      node,
      1000
    );
  }

  function handleNodeClick(node) {
    nodes.forEach(n => { n.__highlighted = false; });
    node.__highlighted = true;
    const connectedIds = new Set();
    links.forEach(l => {
      const src = typeof l.source === "object" ? l.source.id : l.source;
      const tgt = typeof l.target === "object" ? l.target.id : l.target;
      if (src === node.id) connectedIds.add(tgt);
      if (tgt === node.id) connectedIds.add(src);
    });
    connectedIds.forEach(id => { if (nodeMap[id]) nodeMap[id].__highlighted = true; });
    Graph.nodeColor(Graph.nodeColor());
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
      setTimeout(() => handleNodeClick(targetNode), 100);
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
    Graph.cameraPosition({ x: 0, y: 0, z: 400 }, { x: 0, y: 0, z: 0 }, 1000);
    modalOverlay.style.display = "none";
  });

  const labelBtn = document.getElementById("btn-toggle-labels");
  labelBtn.addEventListener("click", () => {
    showLabels = !showLabels;
    labelBtn.textContent = "Labels: " + (showLabels ? "On" : "Off");
    Graph.nodeThreeObject(makeLabelSprite);
  });

  const particleBtn = document.getElementById("btn-toggle-particles");
  particleBtn.addEventListener("click", () => {
    showParticles = !showParticles;
    particleBtn.textContent = "Particles: " + (showParticles ? "On" : "Off");
    Graph.linkDirectionalParticles(Graph.linkDirectionalParticles());
  });

  const tagBtn = document.getElementById("btn-toggle-tags");
  tagBtn.addEventListener("click", () => {
    showTagEdges = !showTagEdges;
    tagBtn.textContent = "Tag Edges: " + (showTagEdges ? "On" : "Off");
    Graph.graphData({ nodes, links: visibleLinks() });
  });
  </script>
</body>
</html>"""


# ── Mode defaults & assets ────────────────────────────────────────────────────

# Symlink at ~/Obsidian -> ~/Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian
OBSIDIAN_ROOT = "/Users/keith/Obsidian"

ARTICLE_MODE_DEFAULTS = {
    "scan_dir": f"{OBSIDIAN_ROOT}/Blogs and Articles/Ideas and Concepts",
    "vault_name": "Obsidian",
    "vault_root": OBSIDIAN_ROOT,
}

LINK_MODE_DEFAULTS = {
    "scan_dir": f"{OBSIDIAN_ROOT}/Main/Cool Tek Technology Links",
    "vault_name": "Obsidian",
    "vault_root": OBSIDIAN_ROOT,
}

ARTICLE_LEGEND = """\
    <div class="legend-row"><span class="dot" style="background:#22c55e"></span> Published</div>
    <div class="legend-row"><span class="dot" style="background:#5b8af5"></span> Draft</div>
    <div class="legend-row"><span class="dot" style="background:#eab308"></span> Blog idea</div>
    <div class="legend-row"><span class="dot" style="background:#ef4444"></span> Idea</div>
    <div class="legend-row"><span class="dot" style="background:#e07b1a"></span> Tag</div>
    <div class="legend-row"><span style="display:inline-block;width:14px;height:2px;border-top:2px dashed #7db4f0;flex-shrink:0"></span> Wiki-link</div>
    <div class="legend-row"><span style="display:inline-block;width:14px;height:1px;border-top:1px solid #445;flex-shrink:0"></span> Tag connection</div>
    <div class="legend-row" style="margin-top:3px;color:#556;font-size:11px">Node size = connections</div>"""

LINK_LEGEND = """\
    <div class="legend-row"><span class="dot" style="background:#5b8af5"></span> Website Link</div>
    <div class="legend-row"><span class="dot" style="background:#e07b1a"></span> Tag</div>
    <div class="legend-row"><span style="display:inline-block;width:14px;height:2px;border-top:2px dashed #7db4f0;flex-shrink:0"></span> Wiki-link</div>
    <div class="legend-row"><span style="display:inline-block;width:14px;height:1px;border-top:1px solid #445;flex-shrink:0"></span> Tag connection</div>
    <div class="legend-row" style="margin-top:3px;color:#556;font-size:11px">Node size = connections</div>"""


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))

    parser = argparse.ArgumentParser(
        description="Generate an interactive 3D force-directed tag graph from Obsidian markdown files."
    )
    parser.add_argument(
        "--mode",
        choices=["article", "link"],
        default="article",
        help='Mode: "article" (default) or "link" for Cool Tek Technology Links',
    )
    parser.add_argument(
        "--scan-dir",
        default=None,
        help="Directory to scan (default depends on mode)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output HTML file path (default: <scan-dir>/tag-graph-3d.html)",
    )
    parser.add_argument(
        "--vault-name",
        default=None,
        help="Obsidian vault name for URI links (default depends on mode)",
    )
    parser.add_argument(
        "--vault-root",
        default=None,
        help="Vault root path for computing Obsidian URI paths (default depends on mode)",
    )
    args = parser.parse_args()

    if args.mode == "link":
        scan_dir = args.scan_dir or LINK_MODE_DEFAULTS["scan_dir"]
        vault_name = args.vault_name or LINK_MODE_DEFAULTS["vault_name"]
        vault_root = args.vault_root or LINK_MODE_DEFAULTS["vault_root"]
        status_tags = []
        legend_html = LINK_LEGEND
    else:
        scan_dir = args.scan_dir or ARTICLE_MODE_DEFAULTS["scan_dir"]
        vault_name = args.vault_name or ARTICLE_MODE_DEFAULTS["vault_name"]
        vault_root = args.vault_root or ARTICLE_MODE_DEFAULTS["vault_root"]
        status_tags = ["published", "blog-idea", "ideas"]
        legend_html = ARTICLE_LEGEND

    if os.path.isabs(scan_dir):
        scan_path = scan_dir
    else:
        scan_path = os.path.join(script_dir, scan_dir)

    if not os.path.isdir(scan_path):
        print(f"Error: scan directory not found: {scan_path}", file=sys.stderr)
        sys.exit(1)

    output_path = args.output or os.path.join(scan_path, "tag-graph-3d.html")

    print(f"Scanning: {scan_path} (mode: {args.mode})")
    file_data, file_links = scan_markdown_files(scan_path)

    all_tags = set()
    for tags in file_data.values():
        all_tags.update(tags)

    path_prefix = os.path.relpath(scan_path, vault_root).replace(os.sep, "/") + "/"

    page_title = "Website Link" if args.mode == "link" else os.path.basename(scan_path)

    html = HTML_TEMPLATE
    html = html.replace("/*FILE_DATA*/", json.dumps(file_data, indent=2, ensure_ascii=False))
    html = html.replace("/*FILE_LINKS*/", json.dumps(file_links, ensure_ascii=False))
    html = html.replace("/*VAULT_NAME*/", vault_name)
    html = html.replace("/*PATH_PREFIX*/", path_prefix)
    html = html.replace("/*PAGE_TITLE*/", page_title)
    html = html.replace("/*MODE*/", args.mode)
    html = html.replace("/*STATUS_TAGS_JSON*/", json.dumps(status_tags))
    html = html.replace("/*LEGEND_HTML*/", legend_html)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Generated: {output_path}")
    print(f"  {len(file_data)} files, {len(all_tags)} unique tags, "
          f"{sum(len(t) for t in file_data.values())} tag connections, "
          f"{len(file_links)} wiki-links")


if __name__ == "__main__":
    main()
