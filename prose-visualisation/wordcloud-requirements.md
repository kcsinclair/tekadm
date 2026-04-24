can you write a script which creates a HTML page which contains a word cloud from all the markdown files in a directory, the meta data including tags should be ignored.  

the size of the words should be proportional to the number of times it appears in the documents.  

if there is a markdown file for a word, make a link which when clicked will display a modal of the word and the contents of the document.

when displaying the modal, if a word has links to another document, you can click the work to open the modal for that word.

# Plan: generate_wordcloud.py

## Context
The user wants a word cloud visualization from their prose/poetry markdown files. Words sized by frequency, with clickable words that have matching .md files (opening a modal with the prose content). Modal wiki-links should be clickable to navigate between documents.

## Output
A single Python script: Writing/generate_wordcloud.py producing a self-contained HTML file.

## CLI Interface
python3 generate_wordcloud.py [directory] [-o output.html] [-r]
directory defaults to .
-o defaults to ./wordcloud.html
-r enables recursive directory scanning (off by default)
Reusable Code from generate_prose_graph.py
Copy these functions (they're small and self-contained, no shared module exists):

extract_body() — strips frontmatter, tags, headings, standalone wiki-link lines; preserves inline wiki-links as {{LINK:target:display}} markers
extract_inline_tags() — needed to identify tag-only lines (used internally by body extraction logic, but extract_body handles this inline)
Actually, extract_body() already handles tag stripping internally. We just need extract_body() and a simplified file scanner.

##  Key files
generate_prose_graph.py — source of extract_body() function (lines 88-143)
generate_prose_graph.py — scan_markdown_files() pattern (lines 148+), adapt for word counting

## Data Pipeline
Step 1: Scan files
Walk directory (optionally recursive with -r)
For each .md file: extract body text, store {filename_base: body_text}
Build basename lookup for link resolution (same as prose graph)
Step 2: Count words
From each body, strip {{LINK:...}} markers back to plain display text
Tokenize: split on whitespace/punctuation, lowercase, keep only [a-z'] words (min length 2)
Filter stop words (hardcoded English stop word list ~150 words)
Count frequency across all files with collections.Counter
Step 3: Build word cloud data
Take top N words (e.g., top 200) to avoid clutter
For each word, check if it matches a filename basename (case-insensitive) — if so, mark it as "has_file" with the body content and resolved links
Serialize as JSON: [{word, count, has_file, body?, links?}]
Step 4: Generate HTML
Inject JSON data into HTML template via token replacement (/*WORD_DATA*/, /*FILE_DATA*/)
HTML/JS Design
Word Cloud Layout
Use a simple CSS-based word cloud (no external library needed)
Words displayed as inline-block <span> elements with:
font-size scaled proportionally: min_size + (count - min_count) / (max_count - min_count) * (max_size - min_size)
Range: 14px to 72px
Random subtle color variation (blues/greys palette to match existing tools' dark theme)
Words with matching files get cursor: pointer and a subtle underline on hover
Container centered, text-align: center, words wrap naturally with varied sizes
Dark background (#0a0a1a) consistent with the 3D graph
Modal (reuse pattern from prose graph)
Centered overlay modal, dark themed
white-space: pre-wrap for prose body
{{LINK:target:display}} markers rendered as clickable <span> elements
Clicking a linked word in the modal:
Closes current modal
Opens modal for the target file (if it exists)
Close on clicking backdrop or pressing Escape
Title bar shows the word/filename
Interactivity
Hover on word: subtle scale/glow effect
Click word with matching file: open modal
Click word without file: no action (or brief tooltip showing count)
Search box at top to highlight/filter words
Stop Words
Hardcoded list covering common English stop words: a, an, the, and, or, but, is, are, was, were, be, been, being, have, has, had, do, does, did, will, would, could, should, may, might, shall, can, not, no, nor, so, if, then, than, that, this, these, those, it, its, he, she, they, we, you, i, me, my, his, her, our, your, their, him, them, us, who, what, which, when, where, how, why, all, each, every, both, few, more, most, some, any, such, only, own, same, too, very, just, about, above, after, again, also, am, at, by, for, from, here, in, into, of, on, once, out, over, per, to, under, until, up, with, etc.

Verification
Run: cd Writing && python3 generate_wordcloud.py randomProse/
Open wordcloud.html in browser
Check: words displayed with varying sizes
Check: common stop words (the, a, is) are absent
Click a word that matches a filename (e.g., "life", "soul") -> modal shows prose
In modal, click a wiki-linked word -> navigates to that document's modal
Check: words without matching files are not clickable
Test: python3 generate_wordcloud.py randomProse/ -o custom.html outputs to custom path
Test: python3 generate_wordcloud.py -r scans recursively