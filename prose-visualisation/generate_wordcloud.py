#!/usr/bin/env python3
"""
Generate an interactive word cloud HTML page from markdown files.

Words are sized by frequency. Words matching a markdown filename are
clickable and open a modal showing the prose content with navigable
wiki-links.

Usage:
    python3 generate_wordcloud.py randomProse/
    python3 generate_wordcloud.py randomProse/ -o my-cloud.html
    python3 generate_wordcloud.py randomProse/ -r
"""

import argparse
import collections
import json
import os
import re
import sys


# ── Stop words ───────────────────────────────────────────────────────────────

STOP_WORDS = frozenset("""
a about above after again all also am an and any are aren't as at be because
been before being below between both but by can cannot could couldn't did
didn't do does doesn't doing don't down during each even every few for from
further get got had hadn't has hasn't have haven't having he he'd he'll he's
her here here's hers herself him himself his how how's however i i'd i'll i'm
i've if in into is isn't it it's its itself just let's like may me might more
most must my myself no nor not now of off on once one only or other ought our
ours ourselves out over own per same shall she she'd she'll she's should
shouldn't so some still such than that that's the their theirs them
themselves then there there's therefore these they they'd they'll they're
they've this those though through to too under until up upon us very was
wasn't we we'd we'll we're we've were weren't what what's when when's where
where's whether which while who who's whom whose why why's will with won't
would wouldn't yet you you'd you'll you're you've your yours yourself
yourselves
""".split())


# ── Frontmatter tag extraction ───────────────────────────────────────────────

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


# ── Body extraction (from generate_prose_graph.py) ───────────────────────────

def extract_body(content: str) -> str:
    """Extract display-ready prose body from markdown content.

    Strips: frontmatter, tag-only lines, wiki-link-only lines,
    first heading, and replaces wiki-link syntax with {{LINK:target:display}} markers.
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

        # Skip lines that are only tags
        if stripped and re.match(r"^(#[A-Za-z][\w-]*\s*)+$", stripped):
            continue

        # Skip lines that are only wiki-links
        if stripped and re.match(r"^(\[\[[^\]]+\]\]\s*)+$", stripped):
            continue

        # Skip the first H1 heading (prose-file title convention)
        if not heading_stripped and re.match(r"^#\s", stripped):
            heading_stripped = True
            continue

        # Replace wiki-link syntax inline with markers
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


# ── File scanning and word counting ──────────────────────────────────────────

def scan_files(scan_path: str, recursive: bool) -> dict:
    """Scan markdown files and return file data + word counts.

    Returns dict with:
        file_data:  {basename_lower: {label, body}}
        word_counts: Counter of all words across files
    """
    file_data = {}       # basename_lower -> {label, body}
    word_counts = collections.Counter()
    tag_words = set()    # lowercase values that came from frontmatter tags

    if recursive:
        walker = os.walk(scan_path)
    else:
        # Single directory: yield just the top level
        entries = os.listdir(scan_path)
        files = [f for f in entries if os.path.isfile(os.path.join(scan_path, f))]
        walker = [(scan_path, [], files)]

    for root, _dirs, files in walker:
        for fname in sorted(files):
            if not fname.endswith(".md"):
                continue
            full_path = os.path.join(root, fname)
            base = os.path.splitext(fname)[0]

            try:
                with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
            except OSError:
                continue

            body = extract_body(content)

            file_data[base.lower()] = {
                "label": base,
                "body": body,
            }

            # Strip LINK markers to plain text for word counting
            plain = re.sub(r"\{\{LINK:[^:}]+:([^}]+)\}\}", r"\1", body)

            # Tokenize
            words = re.findall(r"[a-zA-Z']+", plain)
            for w in words:
                w_lower = w.lower().strip("'")
                if len(w_lower) >= 2 and w_lower not in STOP_WORDS:
                    word_counts[w_lower] += 1

            # Frontmatter tags: counted once per file, preserving hyphenated form
            for tag in extract_frontmatter_tags(content):
                tag_lower = tag.lower()
                word_counts[tag_lower] += 1
                tag_words.add(tag_lower)

    return {"file_data": file_data, "word_counts": word_counts, "tag_words": tag_words}


# ── HTML template ────────────────────────────────────────────────────────────

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Word Cloud</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  background: #0a0a1a;
  color: #e0e0e0;
  font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  align-items: center;
}

/* ── Header ── */
.header {
  width: 100%;
  padding: 16px 24px;
  display: flex;
  align-items: center;
  gap: 16px;
  background: rgba(255,255,255,0.03);
  border-bottom: 1px solid rgba(255,255,255,0.06);
}
.header h1 {
  font-size: 18px;
  font-weight: 600;
  color: #8ba4d0;
  white-space: nowrap;
}
.search-box {
  flex: 0 1 280px;
  padding: 6px 12px;
  border-radius: 6px;
  border: 1px solid rgba(255,255,255,0.12);
  background: rgba(255,255,255,0.05);
  color: #e0e0e0;
  font-size: 14px;
  outline: none;
}
.search-box:focus {
  border-color: #5b8af5;
}
.stats {
  margin-left: auto;
  font-size: 13px;
  color: #888;
  white-space: nowrap;
}

/* ── Word cloud container ── */
.cloud {
  max-width: 1100px;
  width: 100%;
  padding: 48px 32px;
  text-align: center;
  line-height: 1.6;
}
.cloud .word {
  display: inline-block;
  margin: 4px 8px;
  transition: transform 0.15s, text-shadow 0.15s, opacity 0.2s;
  cursor: default;
  opacity: 1;
}
.cloud .word.clickable {
  cursor: pointer;
  text-decoration-style: dotted;
  text-decoration-line: underline;
  text-decoration-color: rgba(255,255,255,0.2);
  text-underline-offset: 3px;
}
.cloud .word.clickable:hover {
  transform: scale(1.12);
  text-shadow: 0 0 18px rgba(91,138,245,0.5);
  text-decoration-color: rgba(91,138,245,0.6);
}
.cloud .word.dimmed {
  opacity: 0.15;
}
.cloud .word.tag {
  color: #e07b1a;
  font-style: italic;
}
.cloud .word.highlighted {
  text-shadow: 0 0 12px rgba(239,68,68,0.7);
  color: #ef4444 !important;
}

/* ── Modal ── */
.modal-overlay {
  display: none;
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.7);
  z-index: 1000;
  justify-content: center;
  align-items: center;
}
.modal-overlay.active {
  display: flex;
}
.modal {
  background: #141428;
  border: 1px solid rgba(255,255,255,0.1);
  border-radius: 12px;
  padding: 0;
  max-width: 640px;
  width: 90%;
  max-height: 80vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 24px 80px rgba(0,0,0,0.6);
}
.modal-header {
  padding: 16px 20px;
  border-bottom: 1px solid rgba(255,255,255,0.06);
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.modal-title {
  font-size: 18px;
  font-weight: 600;
  color: #8ba4d0;
}
.modal-close {
  background: none;
  border: none;
  color: #888;
  font-size: 22px;
  cursor: pointer;
  padding: 2px 8px;
  border-radius: 4px;
}
.modal-close:hover {
  background: rgba(255,255,255,0.08);
  color: #e0e0e0;
}
.modal-body {
  padding: 20px;
  overflow-y: auto;
  font-size: 15px;
  line-height: 1.7;
  color: #ccc;
}
.modal-body .md-para {
  white-space: pre-wrap;
  margin-bottom: 12px;
}
.modal-body .md-h1,
.modal-body .md-h2,
.modal-body .md-h3,
.modal-body .md-h4,
.modal-body .md-h5,
.modal-body .md-h6 {
  color: #8ba4d0;
  margin: 18px 0 10px;
  font-weight: 600;
}
.modal-body .md-h1 { font-size: 22px; }
.modal-body .md-h2 { font-size: 19px; }
.modal-body .md-h3 { font-size: 17px; }
.modal-body .md-h4,
.modal-body .md-h5,
.modal-body .md-h6 { font-size: 15px; }
.modal-body .md-list {
  margin: 8px 0 12px 22px;
  padding: 0;
}
.modal-body .md-list li {
  margin: 4px 0;
}
.modal-body .link {
  color: #5b8af5;
  cursor: pointer;
  text-decoration: underline;
  text-decoration-style: dotted;
  text-underline-offset: 2px;
}
.modal-body .link:hover {
  color: #7da8ff;
  text-decoration-style: solid;
}
.modal-body .md-url {
  color: #7db4f0;
  text-decoration: underline;
  text-decoration-style: dotted;
  text-underline-offset: 2px;
}
.modal-body .md-url:hover {
  color: #a3cbff;
  text-decoration-style: solid;
}
</style>
</head>
<body>

<div class="header">
  <h1>Word Cloud</h1>
  <input type="text" class="search-box" placeholder="Search words…" id="search">
  <div class="stats" id="stats"></div>
</div>

<div class="cloud" id="cloud"></div>

<div class="modal-overlay" id="modal-overlay">
  <div class="modal">
    <div class="modal-header">
      <span class="modal-title" id="modal-title"></span>
      <button class="modal-close" id="modal-close">&times;</button>
    </div>
    <div class="modal-body" id="modal-body"></div>
  </div>
</div>

<script>
const wordData = /*WORD_DATA*/;
const fileData = /*FILE_DATA*/;

// ── Colour palette (subtle blues/purples/teals) ──
const palette = [
  "#7da4c7", "#8ba4d0", "#6d9bc4", "#9ab3d6", "#7ec8c8",
  "#a0b8d8", "#6fa8dc", "#88b5cf", "#7ab5a0", "#9cafc4",
  "#b0c4de", "#8cc5b9", "#a3bfdb", "#7eb8c9", "#9dc3d5",
];

// ── Build the cloud ──
const cloud = document.getElementById("cloud");
const counts = wordData.map(w => w.count);
const minCount = Math.min(...counts);
const maxCount = Math.max(...counts);
const minSize = 14;
const maxSize = 72;
const range = maxCount - minCount || 1;

const wordEls = [];

wordData.forEach((w, i) => {
  const span = document.createElement("span");
  span.className = "word"
    + (w.has_file ? " clickable" : "")
    + (w.is_tag ? " tag" : "");
  span.textContent = w.word;

  const size = minSize + ((w.count - minCount) / range) * (maxSize - minSize);
  span.style.fontSize = size + "px";
  if (!w.is_tag) {
    span.style.color = palette[i % palette.length];
  }
  span.dataset.word = w.word;

  if (w.has_file) {
    span.addEventListener("click", () => openModal(w.word));
  }

  cloud.appendChild(span);
  wordEls.push(span);
});

// Stats
const fileCount = Object.keys(fileData).length;
const totalWords = wordData.reduce((s, w) => s + w.count, 0);
document.getElementById("stats").textContent =
  `${wordData.length} unique words \u00b7 ${totalWords} total \u00b7 ${fileCount} files`;

// ── Search ──
const searchBox = document.getElementById("search");
searchBox.addEventListener("input", () => {
  const q = searchBox.value.trim().toLowerCase();
  wordEls.forEach(el => {
    const word = el.dataset.word;
    if (!q) {
      el.classList.remove("dimmed", "highlighted");
    } else if (word.includes(q)) {
      el.classList.remove("dimmed");
      el.classList.add("highlighted");
    } else {
      el.classList.add("dimmed");
      el.classList.remove("highlighted");
    }
  });
});

// ── Modal ──
const overlay = document.getElementById("modal-overlay");
const modalTitle = document.getElementById("modal-title");
const modalBody = document.getElementById("modal-body");

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
      const target = wm[1].trim().toLowerCase();
      const display = wm[2].trim();
      if (fileData[target]) {
        const link = document.createElement("span");
        link.className = "link";
        link.textContent = display;
        link.addEventListener("click", () => openModal(target));
        parent.appendChild(link);
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
  container.innerHTML = "";
  const lines = body.split("\n");
  let list = null;
  let para = null;

  for (const line of lines) {
    const trimmed = line.trim();

    const heading = trimmed.match(/^(#{1,6})\s+(.+)$/);
    if (heading) {
      list = null;
      para = null;
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

    if (!trimmed) {
      list = null;
      para = null;
      continue;
    }

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

function openModal(fileKey) {
  const data = fileData[fileKey];
  if (!data) return;

  modalTitle.textContent = data.label;
  renderMarkdown(modalBody, data.body);

  overlay.classList.add("active");
}

function closeModal() {
  overlay.classList.remove("active");
}

document.getElementById("modal-close").addEventListener("click", closeModal);
overlay.addEventListener("click", (e) => {
  if (e.target === overlay) closeModal();
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") closeModal();
});
</script>
</body>
</html>
"""


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Generate a word cloud HTML page from markdown files."
    )
    parser.add_argument(
        "directory", nargs="?", default=".",
        help="Directory to scan (default: current directory)",
    )
    parser.add_argument(
        "-o", "--output", default="wordcloud.html",
        help="Output HTML file (default: wordcloud.html)",
    )
    parser.add_argument(
        "-r", "--recursive", action="store_true",
        help="Scan subdirectories recursively",
    )
    args = parser.parse_args()

    scan_path = os.path.abspath(args.directory)
    if not os.path.isdir(scan_path):
        print(f"Error: not a directory: {scan_path}")
        sys.exit(1)

    data = scan_files(scan_path, args.recursive)
    file_data = data["file_data"]
    word_counts = data["word_counts"]
    tag_words = data["tag_words"]

    # Take top 200 words
    top_words = word_counts.most_common(200)

    # Build word data list
    word_data = []
    for word, count in top_words:
        entry = {
            "word": word,
            "count": count,
            "has_file": word in file_data,
            "is_tag": word in tag_words,
        }
        word_data.append(entry)

    # Build file data dict (only files that match a top word, for the modal)
    # Also include any file reachable via wiki-links from those files
    relevant_files = set()
    for w in word_data:
        if w["has_file"]:
            relevant_files.add(w["word"])

    # Add files reachable via links from relevant files
    for key in list(relevant_files):
        body = file_data[key]["body"]
        for m in re.finditer(r"\{\{LINK:([^:}]+):", body):
            target = m.group(1).strip().lower()
            if target in file_data:
                relevant_files.add(target)

    file_data_json = {}
    for key in relevant_files:
        if key in file_data:
            file_data_json[key] = file_data[key]

    # Generate HTML
    html = HTML_TEMPLATE
    html = html.replace("/*WORD_DATA*/", json.dumps(word_data))
    html = html.replace("/*FILE_DATA*/", json.dumps(file_data_json))

    output_path = os.path.abspath(args.output)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Word cloud: {output_path}")
    print(f"  {len(file_data)} files scanned")
    print(f"  {len(word_counts)} unique words (after filtering)")
    print(f"  {len(top_words)} words in cloud")
    print(f"  {sum(1 for w in word_data if w['has_file'])} words linked to files")


if __name__ == "__main__":
    main()
