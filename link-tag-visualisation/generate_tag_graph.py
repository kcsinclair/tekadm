#!/usr/bin/env python3
"""
Generate an interactive Cytoscape.js tag graph from Obsidian markdown files.

Scans markdown files for tags (YAML frontmatter and inline hashtags),
normalizes them, and produces a self-contained HTML visualization.

Usage:
    python3 generate_tag_graph.py
    python3 generate_tag_graph.py --scan-dir "Ideas and Concepts"
    python3 generate_tag_graph.py --mode link
    python3 generate_tag_graph.py --scan-dir "NM_Book" --vault-name "Obsidian"
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

    # Try PyYAML first
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

    # Fallback: regex-based parsing
    tags = set()
    in_tags = False
    for line in frontmatter.split("\n"):
        stripped = line.strip()
        if stripped == "tags:" or stripped.startswith("tags:"):
            # Check for inline list: tags: [a, b, c]
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

    # Skip frontmatter
    lines = content.split("\n")
    start = 0
    if lines and lines[0].strip() == "---":
        for i, line in enumerate(lines[1:], 1):
            if line.strip() == "---":
                start = i + 1
                break

    for line in lines[start:]:
        stripped = line.strip()

        # Toggle code blocks
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue

        # Skip markdown headings
        if re.match(r"^#{1,6}\s", stripped):
            continue

        # Find hashtags: # followed by a letter, then word chars or hyphens
        for m in re.finditer(r"(?<![\\&/\w])#([A-Za-z][\w-]*)", line):
            tags.add(m.group(1))

    return tags


def normalize_tag(tag: str) -> str:
    """Normalize a tag to lowercase-hyphenated form.

    Examples:
        NetworkManagement -> network-management
        ITOperations -> it-operations
        GettingThingsDone -> getting-things-done
        blog-idea -> blog-idea
        AI -> ai
    """
    # Insert hyphen between uppercase sequences and following capitalized word
    tag = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1-\2", tag)
    # Insert hyphen between lowercase/digit and uppercase
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


def extract_tags(filepath: str) -> list[str]:
    """Extract and normalize all tags from a markdown file."""
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except OSError:
        return []

    tags = parse_frontmatter_tags(content) | extract_inline_tags(content)
    normalized = {normalize_tag(t) for t in tags}
    # Remove empty strings
    normalized.discard("")
    return sorted(normalized)


# ── File scanning ─────────────────────────────────────────────────────────────

def scan_markdown_files(scan_path: str) -> tuple[dict[str, list[str]], list[tuple[str, str]]]:
    """Walk scan_path, extract tags and wiki-links from all .md files.
    Returns:
        file_data: dict mapping relative path to sorted tag list (skips files with no tags)
        file_links: list of (source_file, target_file) tuples for [[wiki-links]]
    """
    result = {}
    raw_links = []  # (source_rel, raw_target)
    all_filenames = {}  # basename (no ext) -> relative path

    for root, _dirs, files in os.walk(scan_path):
        for fname in sorted(files):
            if not fname.endswith(".md"):
                continue
            full_path = os.path.join(root, fname)
            rel = os.path.relpath(full_path, scan_path)

            # Index by basename for link resolution
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

    # Resolve wiki-links to actual files in the scanned directory
    file_links = []
    for source, raw_target in raw_links:
        # Try exact match, then without .md extension
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
  <title>/*PAGE_TITLE*/ — Tag Graph</title>
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

    /* -- Section label ---------------------------------------------- */
    .section-label {
      font-size: 10px;
      font-weight: 600;
      color: #9098b0;
      letter-spacing: 0.05em;
      text-transform: uppercase;
      margin: 10px 0 5px;
    }

    /* -- Button rows ------------------------------------------------ */
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

    /* -- Layout buttons grid ---------------------------------------- */
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

    /* -- Info panel (bottom-left) ----------------------------------- */
    #info-panel {
      bottom: 12px;
      left: 12px;
      padding: 14px;
      width: 270px;
      display: none;
      max-height: 300px;
      overflow-y: auto;
    }

    #info-type {
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      margin-bottom: 4px;
    }

    #info-title {
      font-size: 14px;
      font-weight: 600;
      color: #1a1c28;
      margin-bottom: 8px;
      line-height: 1.4;
      word-break: break-word;
    }

    #info-links {
      font-size: 12px;
      color: #6a7090;
      line-height: 1.7;
    }

    #info-open {
      margin-top: 10px;
      width: 100%;
      background: rgba(37, 99, 235, 0.1);
      border-color: rgba(37, 99, 235, 0.3);
      color: #2563eb;
      font-size: 12px;
    }

    #info-open:hover {
      background: rgba(37, 99, 235, 0.18);
      border-color: rgba(37, 99, 235, 0.5);
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
    /*LEGEND_HTML*/
  </div>

  <!-- Info panel -->
  <div id="info-panel" class="panel">
    <div id="info-type"></div>
    <div id="info-title"></div>
    <div id="info-links"></div>
    <button id="info-open" style="display:none">Open in Obsidian &#8599;</button>
  </div>

  <!-- Stats -->
  <div id="stats"></div>

  <div id="cy"></div>

  <script src="https://cdnjs.cloudflare.com/ajax/libs/cytoscape/3.29.2/cytoscape.min.js"></script>

  <script>
  // -- Data ----------------------------------------------------------------
  const VAULT = "/*VAULT_NAME*/";
  const PATH_PREFIX = "/*PATH_PREFIX*/";

  const fileData = /*FILE_DATA*/;
  const fileLinks = /*FILE_LINKS*/;

  // -- Build elements ------------------------------------------------------
  const elements = [];

  const MODE = "/*MODE*/";
  const STATUS_TAGS = new Set(/*STATUS_TAGS_JSON*/);

  const minTagDegree = MODE === "link" ? 2 : 1;

  const tagDegree = {};
  for (const tags of Object.values(fileData)) {
    for (const t of tags) {
      if (STATUS_TAGS.has(t)) continue;
      tagDegree[t] = (tagDegree[t] || 0) + 1;
    }
  }

  for (const [fname, tags] of Object.entries(fileData)) {
    const visibleTags = tags.filter(t => !STATUS_TAGS.has(t) && (tagDegree[t] || 0) >= minTagDegree);
    const nodeData = {
      id: fname,
      label: fname.replace(/\.md$/, ""),
      type: "file",
      degree: visibleTags.length,
      path: PATH_PREFIX + fname
    };
    if (MODE === "article") {
      nodeData.published = tags.includes("published") ? "yes" : "no";
      nodeData.status = tags.includes("published") ? "published"
            : tags.includes("blog-idea") ? "blog-idea"
            : tags.includes("ideas") ? "ideas"
            : "draft";
    }
    elements.push({ data: nodeData });
  }

  for (const [tag, deg] of Object.entries(tagDegree)) {
    if (deg < minTagDegree) continue;
    elements.push({
      data: { id: "tag:" + tag, label: tag, type: "tag", degree: deg }
    });
  }

  for (const [fname, tags] of Object.entries(fileData)) {
    for (const tag of tags) {
      if (STATUS_TAGS.has(tag)) continue;
      if ((tagDegree[tag] || 0) < minTagDegree) continue;
      elements.push({
        data: { id: fname + "__" + tag, source: fname, target: "tag:" + tag }
      });
    }
  }

  // File-to-file wiki-links
  for (const [src, tgt] of fileLinks) {
    elements.push({
      data: { id: "link:" + src + "->" + tgt, source: src, target: tgt, type: "wiki-link" }
    });
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
      /*NODE_STATUS_STYLES*/
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
          concentric: n => n.data("type") === "tag" ? n.connectedEdges().length * 2 : n.connectedEdges().length,
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
  const numFiles = Object.keys(fileData).length;
  const numTags  = Object.keys(tagDegree).length;
  const numEdges = cy.edges().filter(e => e.data("type") !== "wiki-link").length;
  const numLinks = fileLinks.length;
  document.getElementById("stats").innerHTML =
    `${numFiles} files &nbsp;&middot;&nbsp; ${numTags} tags &nbsp;&middot;&nbsp; ${numEdges} tag connections` +
    (numLinks > 0 ? ` &nbsp;&middot;&nbsp; ${numLinks} wiki-links` : "");

  // -- Info panel ----------------------------------------------------------
  const infoPanel = document.getElementById("info-panel");
  const infoType  = document.getElementById("info-type");
  const infoTitle = document.getElementById("info-title");
  const infoLinks = document.getElementById("info-links");
  const infoOpen  = document.getElementById("info-open");

  function showInfo(node) {
    infoPanel.style.display = "block";
    const type = node.data("type");

    if (type === "file") {
      infoType.style.color = "#2563eb";
      infoType.textContent = "File";
      infoTitle.textContent = node.data("label");
      const tagEdges = node.connectedEdges().filter(e => e.data("type") !== "wiki-link");
      const tags = tagEdges.map(e => {
        const other = e.source().id() === node.id() ? e.target() : e.source();
        return other.data("label");
      });
      const wikiEdges = node.connectedEdges().filter(e => e.data("type") === "wiki-link");
      const linkedFiles = wikiEdges.map(e => {
        const other = e.source().id() === node.id() ? e.target() : e.source();
        return other.data("label");
      });
      let html = "<b style='color:#9098b0'>Tags:</b><br>" +
        tags.map(t => `<span style='color:#e07b1a'>#${t}</span>`).join("  ");
      if (linkedFiles.length > 0) {
        html += "<br><br><b style='color:#9098b0'>Linked files:</b><br>" +
          linkedFiles.map(f => `<span style='color:#16a34a'>${f}</span>`).join("<br>");
      }
      infoLinks.innerHTML = html;
      infoOpen.style.display = "block";
      infoOpen.onclick = () => {
        window.location.href = "obsidian://open?vault=" +
          encodeURIComponent(VAULT) + "&file=" +
          encodeURIComponent(node.data("path"));
      };
    } else {
      infoType.style.color = "#e07b1a";
      infoType.textContent = "Tag";
      infoTitle.textContent = "#" + node.data("label");
      const files = node.connectedEdges().map(e => {
        const other = e.source().id() === node.id() ? e.target() : e.source();
        return other.data("label");
      }).sort();
      infoLinks.innerHTML =
        `<b style='color:#9098b0'>Used in ${files.length} file${files.length !== 1 ? "s" : ""}:</b><br>` +
        files.map(f => `<span style='color:#2563eb'>${f}</span>`).join("<br>");
      infoOpen.style.display = "none";
    }
  }

  // -- Node interactions ---------------------------------------------------
  cy.on("tap", "node", function(evt) {
    const node = evt.target;
    cy.elements().removeClass("highlighted faded");
    cy.elements().addClass("faded");
    const neighbourhood = node.closedNeighborhood();
    neighbourhood.removeClass("faded").addClass("highlighted");
    neighbourhood.connectedEdges().removeClass("faded").addClass("highlighted");
    showInfo(node);
  });

  cy.on("tap", function(evt) {
    if (evt.target === cy) {
      cy.elements().removeClass("highlighted faded");
      infoPanel.style.display = "none";
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
    infoPanel.style.display = "none";
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

# Symlink at ~/Obsidian -> ~/Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian
# All vault paths use the symlink so Obsidian URI relpath calculations stay consistent.
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
    <div class="legend-row"><span class="dot" style="background:#16a34a"></span> Published</div>
    <div class="legend-row"><span class="dot" style="background:#2563eb"></span> Draft — click to open</div>
    <div class="legend-row"><span class="dot" style="background:#eab308"></span> Blog idea</div>
    <div class="legend-row"><span class="dot" style="background:#dc2626"></span> Idea</div>
    <div class="legend-row"><span class="tag-shape" style="background:#e07b1a"></span> Tag — click to focus</div>
    <div class="legend-row"><span style="display:inline-block;width:14px;height:2px;border-top:2px dashed #16a34a;flex-shrink:0"></span> Wiki-link between files</div>
    <div class="legend-row" style="margin-top:3px;color:#9098b0;font-size:11px">Node size = connections</div>"""

LINK_LEGEND = """\
    <div class="legend-row"><span class="dot" style="background:#2563eb"></span> Website Link — click to open</div>
    <div class="legend-row"><span class="tag-shape" style="background:#e07b1a"></span> Tag — click to focus</div>
    <div class="legend-row"><span style="display:inline-block;width:14px;height:2px;border-top:2px dashed #16a34a;flex-shrink:0"></span> Wiki-link between files</div>
    <div class="legend-row" style="margin-top:3px;color:#9098b0;font-size:11px">Node size = connections</div>"""

ARTICLE_STATUS_STYLES = """\
      {
        selector: 'node[type="file"][status="published"]',
        style: { "background-color": "#16a34a" }
      },
      {
        selector: 'node[type="file"][status="blog-idea"]',
        style: { "background-color": "#eab308" }
      },
      {
        selector: 'node[type="file"][status="ideas"]',
        style: { "background-color": "#dc2626" }
      },"""

LINK_STATUS_STYLES = ""


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))

    parser = argparse.ArgumentParser(
        description="Generate a Cytoscape.js tag graph from Obsidian markdown files."
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
        help='Directory to scan (default depends on mode)',
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output HTML file path (default: <scan-dir>/tag-graph.html)",
    )
    parser.add_argument(
        "--vault-name",
        default=None,
        help='Obsidian vault name for URI links (default depends on mode)',
    )
    parser.add_argument(
        "--vault-root",
        default=None,
        help='Vault root path for computing Obsidian URI paths (default depends on mode)',
    )
    args = parser.parse_args()

    # Apply mode-specific defaults
    if args.mode == "link":
        scan_dir = args.scan_dir or LINK_MODE_DEFAULTS["scan_dir"]
        vault_name = args.vault_name or LINK_MODE_DEFAULTS["vault_name"]
        vault_root = args.vault_root or LINK_MODE_DEFAULTS["vault_root"]
        status_tags = []
        legend_html = LINK_LEGEND
        node_status_styles = LINK_STATUS_STYLES
    else:
        scan_dir = args.scan_dir or ARTICLE_MODE_DEFAULTS["scan_dir"]
        vault_name = args.vault_name or ARTICLE_MODE_DEFAULTS["vault_name"]
        vault_root = args.vault_root or ARTICLE_MODE_DEFAULTS["vault_root"]
        status_tags = ["published", "blog-idea", "ideas"]
        legend_html = ARTICLE_LEGEND
        node_status_styles = ARTICLE_STATUS_STYLES

    # Resolve scan path (absolute paths used by default; relative paths resolved from script dir)
    if os.path.isabs(scan_dir):
        scan_path = scan_dir
    else:
        scan_path = os.path.join(script_dir, scan_dir)

    if not os.path.isdir(scan_path):
        print(f"Error: scan directory not found: {scan_path}", file=sys.stderr)
        sys.exit(1)

    output_path = args.output or os.path.join(scan_path, "tag-graph.html")

    # Scan and extract
    print(f"Scanning: {scan_path} (mode: {args.mode})")
    file_data, file_links = scan_markdown_files(scan_path)

    # Count unique tags
    all_tags = set()
    for tags in file_data.values():
        all_tags.update(tags)

    # Build the path prefix for Obsidian URIs (relative to vault root)
    path_prefix = os.path.relpath(scan_path, vault_root).replace(os.sep, "/") + "/"

    # Page title from the scan directory name
    page_title = "Website Link - Tag Graph" if args.mode == "link" else os.path.basename(scan_path)

    # Generate HTML
    html = HTML_TEMPLATE
    html = html.replace("/*FILE_DATA*/", json.dumps(file_data, indent=4, ensure_ascii=False))
    html = html.replace("/*FILE_LINKS*/", json.dumps(file_links, ensure_ascii=False))
    html = html.replace("/*VAULT_NAME*/", vault_name)
    html = html.replace("/*PATH_PREFIX*/", path_prefix)
    html = html.replace("/*PAGE_TITLE*/", page_title)
    html = html.replace("/*MODE*/", args.mode)
    html = html.replace("/*STATUS_TAGS_JSON*/", json.dumps(status_tags))
    html = html.replace("/*LEGEND_HTML*/", legend_html)
    html = html.replace("/*NODE_STATUS_STYLES*/", node_status_styles)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Generated: {output_path}")
    print(f"  {len(file_data)} files, {len(all_tags)} unique tags, "
          f"{sum(len(t) for t in file_data.values())} tag connections, "
          f"{len(file_links)} wiki-links")


if __name__ == "__main__":
    main()
