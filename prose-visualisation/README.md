# Prose Visualisation Tools

Four Python scripts for visualising and maintaining an Obsidian-style collection
of markdown prose/notes:

| Script | Output | Purpose |
|--------|--------|---------|
| `generate_prose_graph.py`    | `prose-graph.html`    | 2D Cytoscape.js graph |
| `generate_prose_graph_3d.py` | `prose-graph-3d.html` | 3D force-directed graph |
| `generate_wordcloud.py`      | `wordcloud.html`      | Word cloud with clickable words |
| `add_wiki_links.py`          | edits files in place  | Auto-link first occurrences of matching filenames |

All outputs are self-contained HTML files (data embedded as JSON, JS libraries
loaded from CDN).

---

## Python dependencies

**None** — all four scripts use only the Python 3 standard library:
`argparse`, `collections`, `json`, `os`, `re`, `sys`.

Tested on Python 3.9+. No `pip install` required.

## Browser dependencies (CDN, loaded by the generated HTML)

| Script                 | Libraries |
|------------------------|-----------|
| `prose-graph.html`     | Cytoscape.js |
| `prose-graph-3d.html`  | Three.js 0.160.0 (UMD), 3d-force-graph 1.76.0 |
| `wordcloud.html`       | *(none — pure HTML/CSS/JS)* |

Pinned versions are used to avoid breakage; see note on Three.js ≥1.0 below.

---

## 1. `generate_prose_graph.py` — 2D graph

### Requirements implemented
- Interactive Cytoscape.js graph of all `.md` files in a directory
- File nodes, tag nodes (from inline `#hashtags` **and** YAML/TOML frontmatter
  `tags:` lists), and virtual nodes for unresolved `[[wiki-links]]`
- Wiki-link edges between files; self-references ignored
- Clicking a file node opens a modal with the prose body
- Clicking an inline `[[wiki-link]]` inside a modal navigates to the target's
  modal (or virtual node modal)
- Tag/virtual modals list backlinks, clickable to navigate
- Tag and virtual nodes are **off by default**; enable with `--virtual`
- Modal markdown rendering: `##` headings, `- bullet lists`,
  `[text](url)` external links, `**bold**`, and inline `[[wiki-links]]`

### Usage

```
python3 generate_prose_graph.py [directory] [-o output.html] [--virtual]
```

---

## 2. `generate_prose_graph_3d.py` — 3D graph

### Requirements implemented (beyond the 2D tool)
- Same data pipeline as the 2D version (file/tag/virtual nodes, wiki-links)
- 3D force-directed layout using `3d-force-graph`
- Node size scales with degree (`sqrt`-based)
- Nodes colour-coded:
  - Blue — bidirectional file
  - Yellow — inbound-only (sink)
  - Purple — outbound-only (source)
  - Orange — tag
  - Diamond purple — virtual (unresolved link)
- Wiki-link edges: light blue, with directional particles (on by default)
- Tag edges: orange, width 1.6
- Custom canvas text sprites for node labels (no `three-spritetext` dependency)
- Search with red highlight on matches
- Modal rendering identical to the 2D tool (same markdown subset)
- Controls panel:
  - Reset Camera
  - Refresh Layout (reheats the force simulation)
  - Labels on/off
  - Particles on/off
  - Singleton tags shown/hidden (hidden by default)
- Legend panel (hidden by default, enable with `--legend`)
- Page title: `<folder> — 3D Graph`

### CLI flags unique to this script
- `--virtual` — include tag and virtual nodes
- `--legend` — show the legend panel
- `--no-singletons` — exclude tags that are used by only one file from the graph
  entirely (hides the Singleton-tags toggle button since it's no longer relevant)

### Usage

```
python3 generate_prose_graph_3d.py [directory] [-o output.html]
    [--virtual] [--legend] [--no-singletons]
```

### Note on Three.js version
`3d-force-graph` 1.76.0 requires Three.js `>=0.179 <1`. Three.js 1.x ships a
breaking change to timers; we pin to `0.160.0` (UMD build) to avoid
`TypeError: undefined is not a constructor (evaluating 'new Ak.Timer')`.

---

## 3. `generate_wordcloud.py` — word cloud

### Requirements implemented
- Word cloud built from all `.md` files (body text only — frontmatter stripped
  by default)
- Word size proportional to frequency (14–72px range, top 200 words)
- Common English stop words filtered (~150 words)
- Words that match a markdown filename are clickable and open a modal with the
  document's content
- Wiki-links inside modals are clickable and navigate to the target word's modal
- YAML/TOML frontmatter `tags:` values added as words too, styled distinctly
  (orange italic) to match the tag-node colour in the graphs
- Search box highlights matches in red and dims non-matches
- Modal markdown rendering identical to the graph tools

### Usage

```
python3 generate_wordcloud.py [directory] [-o output.html] [-r]
```

- `-r` enables recursive directory scanning (off by default)
- Defaults to current directory and `./wordcloud.html`

---

## 4. `add_wiki_links.py` — auto-linker

### Requirements implemented
- Scans a directory for `.md` files, finds words matching **other** filenames,
  and adds `[[wiki-links]]` for the **first occurrence** in each file
- Preserves original case: `Life` → `[[life|Life]]`, `soul` → `[[soul]]`
- Skips:
  - Self-references (filename matching its own file)
  - Targets already wiki-linked in the file
  - Frontmatter, tag-only lines, heading lines, standalone wiki-link lines

### Usage

```
python3 add_wiki_links.py [directory]
```

Modifies files in place. Print-only summary shows counts per file.

---

## Shared parsing behaviour

All three generator scripts share the same extraction logic:

- **Frontmatter**: both YAML (`---`) and TOML (`+++`) delimiters supported;
  stripped from body output.
- **Inline hashtags**: `#foo` anywhere in the body, normalised to
  lowercase-hyphenated form.
- **Frontmatter tags**: YAML block-list, YAML inline array, YAML scalar, and
  TOML array (`tags = ["..."]`).
- **Body extraction**: strips frontmatter, tag-only lines, standalone wiki-link
  lines, and the first H1 heading (the prose-file title convention). H2+
  headings are preserved so RFC-style content renders correctly.
- **Wiki-links**: `[[Target]]` and `[[Path/Target|Display Text]]`; resolved
  against basenames and relative paths of scanned files.

## File organisation

```
Writing/
├── README.md                      ← this file
├── generate_prose_graph.py
├── generate_prose_graph_3d.py
├── generate_wordcloud.py
├── add_wiki_links.py
├── randomProse/                   ← source markdown files
├── prose-graph.html               ← generated
├── prose-graph-3d.html            ← generated
└── wordcloud.html                 ← generated
```
