# Obsidian Tag Graph Generators

Two Python scripts that scan an Obsidian vault folder and produce self-contained
HTML visualisations of files, tags and wiki-links between them.

| Script | Renderer | Output | Use it for |
|---|---|---|---|
| [`generate_tag_graph.py`](generate_tag_graph.py) | Cytoscape.js (2D) | `tag-graph.html` | Fast, structured 2D layouts (Force, Tree, Concentric, Circle, Grid, Random). Best for inspecting tag clusters and switching layouts on demand. |
| [`generate_tag_graph_3d.py`](generate_tag_graph_3d.py) | 3d-force-graph + Three.js | `tag-graph-3d.html` | Spatial 3D exploration with orbit/pan/zoom, particle flow on wiki-links, and animated camera focus. Best for visually walking the network. |

Both scripts are intentionally aligned: same scanning logic, same modes, same
Obsidian-URI integration, same default scan locations — only the renderer
differs.

---

## Requirements understood

The scripts were built to satisfy the following requirements:

1. **Scan a directory of Markdown files** recursively for `.md` content.
2. **Extract tags** from two sources:
    - YAML frontmatter (`tags:` as a list, inline list, or single string).
    - Inline `#hashtags` in body text — *skipping* code blocks, headings, and frontmatter.
3. **Normalise tags** to `lowercase-hyphenated` form (`NetworkManagement` → `network-management`, `AI` → `ai`).
4. **Extract Obsidian wiki-links** (`[[Target]]` / `[[Target|Display]]`) and resolve them to actual files in the scanned set.
5. **Two modes of operation:**
    - `article` — for blog/idea folders. Files coloured by status tag (`published`, `blog-idea`, `ideas`, otherwise draft). Status tags themselves are *hidden* from the graph (they only colour the file node).
    - `link` — for the "Cool Tek Technology Links" folder. Single-use tags hidden (`minTagDegree = 2`) to keep the graph readable.
6. **Open files directly in Obsidian** via `obsidian://open?vault=…&file=…` URIs, computed from a configurable vault root.
7. **Self-contained HTML output** — no build step, no external assets bundled, only CDN scripts at runtime. A user can double-click the HTML and explore.
8. **Search, focus, reset** controls; **legend** matching the active mode; on-screen **stats** (file count, tag count, edge counts).

---

## What was implemented

### Shared logic (both scripts)

- **`parse_frontmatter_tags`** — uses PyYAML if installed, otherwise falls back to a regex-based parser that handles list, inline-list, and string forms.
- **`extract_inline_tags`** — strips frontmatter, code blocks, and headings before matching `#tag` patterns. Avoids false matches inside paths and entities (`(?<![\\&/\w])`).
- **`normalize_tag`** — splits CamelCase into hyphens before lower-casing.
- **`extract_wiki_links`** — collects unique `[[wiki-link]]` targets, ignoring code blocks.
- **`scan_markdown_files`** — walks the directory, builds a basename lookup, then resolves each raw link target to a real file by basename or basename-without-extension. Self-references are dropped.
- **Status-tag filtering** — in `article` mode, `published` / `blog-idea` / `ideas` are excluded from the tag graph (they drive node colouring instead).

### `generate_tag_graph.py` (2D — Cytoscape.js)

- Cytoscape.js 3.29.2 from cdnjs.
- Six selectable layouts (Force `cose`, Concentric, Tree `breadthfirst`, Circle, Grid, Random) with shared animation defaults.
- File nodes (blue spheres / status colours), Tag nodes (orange round-rectangles), Wiki-link edges (dashed green with arrows), Tag edges (faint grey haystack).
- Click a node → fade rest, highlight neighbourhood, populate bottom-left **info panel** with tags + linked files + "Open in Obsidian" button (file nodes only).
- Top-left search bar with live match-count and auto-fit-to-matches.
- Mode-specific legend (`ARTICLE_LEGEND` / `LINK_LEGEND`) and status-colour styles (`ARTICLE_STATUS_STYLES` / `LINK_STATUS_STYLES`) injected at template fill time.

### `generate_tag_graph_3d.py` (3D — 3d-force-graph)

- Three.js 0.160.0 + 3d-force-graph 1.76.0 from unpkg.
- Dark theme; force-directed layout (`d3Force` `charge: -120`, link distance 40 for wiki-links / 60 for tag edges).
- Sprite-based labels rendered above each node, sized in proportion to `√degree`.
- Particle flow animated along wiki-link edges.
- Click a node → camera orbits + zooms onto it, highlights node + neighbours in white, opens a modal with clickable tag chips and linked-file chips. File modals include the same "Open in Obsidian" button.
- Toggle buttons: **Labels On/Off**, **Particles On/Off**, **Tag Edges On/Off** (the last lets you strip tag connections to view only the wiki-link backbone).
- Search field highlights matches in amber across the full 3D scene.
- Modal supports backlink navigation — clicking a chip closes the modal and re-focuses the graph on the target.

---

## Usage

Both scripts live in `Blogs and Articles/` and accept the same flags.

### Defaults

```bash
# Article mode → scans Obsidian/Blogs and Articles/Ideas and Concepts
python3 generate_tag_graph.py
python3 generate_tag_graph_3d.py

# Link mode → scans Obsidian/Main/Cool Tek Technology Links
python3 generate_tag_graph.py    --mode link
python3 generate_tag_graph_3d.py --mode link
```

Output is written to `<scan-dir>/tag-graph.html` (2D) or
`<scan-dir>/tag-graph-3d.html` (3D) by default.

### Custom scan directory

```bash
python3 generate_tag_graph.py    --scan-dir "NM_Book"
python3 generate_tag_graph_3d.py --scan-dir "/Users/keith/Obsidian/Main/Notes"
```

Relative paths are resolved against the script's own directory; absolute paths
are used as-is.

### Custom output path

```bash
python3 generate_tag_graph_3d.py --output ~/Desktop/my-graph.html
```

### Custom vault for the "Open in Obsidian" link

```bash
python3 generate_tag_graph.py \
    --vault-name "MyVault" \
    --vault-root "/Users/me/MyVault" \
    --scan-dir   "/Users/me/MyVault/Notes"
```

### CLI reference

```
--mode {article,link}     Mode preset (default: article)
--scan-dir PATH           Directory to scan (default depends on mode)
--output PATH             Output HTML file path
--vault-name NAME         Obsidian vault name for URI links
--vault-root PATH         Vault root for computing relative paths in URIs
```

---

## Dependencies

### Runtime

- **Python ≥ 3.9** — uses PEP 585 generics (`dict[str, list[str]]`, `set[str]`).
- **PyYAML** *(optional)* — used by `parse_frontmatter_tags` if present; otherwise a regex fallback handles common YAML tag formats.
    ```bash
    pip3 install pyyaml
    ```

### Browser-side (loaded from CDN at runtime, nothing to install)

| Library | Version | Used by | Source |
|---|---|---|---|
| Cytoscape.js | 3.29.2 | 2D | `cdnjs.cloudflare.com/ajax/libs/cytoscape/3.29.2/` |
| Three.js | 0.160.0 | 3D | `unpkg.com/three@0.160.0/` |
| 3d-force-graph | 1.76.0 | 3D | `unpkg.com/3d-force-graph@1.76.0/` |

The generated HTML files require an internet connection on first load to fetch
those scripts. Once loaded, they are typically cached by the browser.

### Obsidian integration

The "Open in Obsidian" button uses the `obsidian://open` URI scheme. It
requires:

- Obsidian installed locally.
- The `--vault-name` flag matching a vault registered in Obsidian.
- The `--vault-root` flag pointing at that vault's filesystem root, so the
  script can compute the correct relative path for the URI.

The default vault root is `/Users/keith/Obsidian` (a symlink to the iCloud
Obsidian folder). Override `--vault-root` and `--vault-name` for any other
setup.

---

## File layout

```
Blogs and Articles/
├── generate_tag_graph.py       # 2D (Cytoscape.js)
├── generate_tag_graph_3d.py    # 3D (3d-force-graph)
├── README-tag-graph.md         # this file
└── …
```

## Output files (after running)

```
<scan-dir>/tag-graph.html       # produced by the 2D script
<scan-dir>/tag-graph-3d.html    # produced by the 3D script
```

Each is a single self-contained HTML document — share it, host it, or open it
locally with a double-click.
