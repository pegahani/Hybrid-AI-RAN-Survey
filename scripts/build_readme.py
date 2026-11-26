#!/usr/bin/env python3
"""Generate README.md for the Hybrid-AI-RAN-Survey paper list.

Reads the capability-mapping tables and the evaluation-resources table
directly from the paper's LaTeX sources and pulls titles, venues, years and
links from references.bib, so the list stays in sync with the paper.

Usage:
    python3 scripts/build_readme.py /path/to/paper/repo > README.md
"""
import re
import sys
from pathlib import Path

PAPER = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
APPS = PAPER / "sections" / "multi-time scale applications"
BENCH = PAPER / "sections" / "benchmarks_datasets" / "main2.tex"
BIB = PAPER / "references.bib"

# Order of the application tables in the paper: (file, section heading)
APP_FILES = [
    ("slow-time-scale.tex", "Slow-Timescale Control (minutes to hours)"),
    ("medium-time-scale.tex", "Medium-Timescale Control (10 ms to 1 s, Near-RT RIC)"),
    ("fast-time-scale.tex", "Fast-Timescale Control (below 10 ms)"),
    ("multi-time-scale.tex", "Cross-Timescale and Multi-Capability Systems"),
]
CAPS = ["R&R", "P&S", "AC", "DS"]


# --------------------------------------------------------------------- bib
def parse_bib(text):
    entries = {}
    for m in re.finditer(r"@(\w+)\s*\{\s*([^,\s]+)\s*,", text):
        start, depth, i = m.end(), 1, m.end()
        while i < len(text) and depth:
            depth += {"{": 1, "}": -1}.get(text[i], 0)
            i += 1
        body = text[start:i - 1]
        fields = {}
        for f in re.finditer(r"(\w+)\s*=\s*", body):
            j = f.end()
            if j < len(body) and body[j] == "{":
                d, k = 1, j + 1
                while k < len(body) and d:
                    d += {"{": 1, "}": -1}.get(body[k], 0)
                    k += 1
                val = body[j + 1:k - 1]
            elif j < len(body) and body[j] == '"':
                k = body.index('"', j + 1)
                val = body[j + 1:k]
            else:
                val = re.match(r"[^,\n]*", body[j:]).group(0)
            fields.setdefault(f.group(1).lower(), val.strip())
        entries[m.group(2)] = fields
    return entries


ACCENTS = {r'\"u': "ü", r'\"o': "ö", r'\"a': "ä", r"\'e": "é", r"\`e": "è",
           r"\'a": "á", r"\'i": "í", r"\'o": "ó", r"\c c": "ç", r"\~n": "ñ"}


def clean(s):
    s = s or ""
    for k, v in ACCENTS.items():
        s = s.replace("{" + k + "}", v).replace(k, v)
    s = s.replace(r"\&", "&").replace("$>$", ">").replace("$<$", "<").replace("---", "—").replace("--", "–").replace("~", " ")
    s = re.sub(r"\\[a-zA-Z]+\s*", "", s)
    s = s.replace("{", "").replace("}", "")
    return re.sub(r"\s+", " ", s).strip()


def venue(e):
    v = clean(e.get("journal") or e.get("booktitle") or e.get("howpublished")
              or e.get("publisher") or e.get("institution") or "")
    if re.match(r"arxiv", v, re.I):
        return "arXiv"
    return v


def link(e):
    if e.get("doi"):
        doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", e["doi"].strip())
        return "https://doi.org/" + doi
    if e.get("url"):
        return e["url"].strip()
    ax = re.search(r"(\d{4}\.\d{4,5})", (e.get("eprint", "") + " " +
                                         e.get("journal", "")))
    return f"https://arxiv.org/abs/{ax.group(1)}" if ax else ""


def cite_md(keys, bib, label=None):
    """Return a markdown bullet for one or more cite keys."""
    parts = []
    for k in keys:
        e = bib.get(k)
        if not e:
            parts.append(f"`{k}` (missing from bib)")
            continue
        title = clean(e.get("title", k))
        url = link(e)
        t = f"[{title}]({url})" if url else title
        meta = ", ".join(x for x in (venue(e), clean(e.get("year", ""))) if x)
        parts.append(f"{t}{' — *' + meta + '*' if meta else ''}")
    return (f"**{label}**: " if label else "") + " · ".join(parts)


# ------------------------------------------------------------------ tables
def strip_comments(tex):
    return re.sub(r"(?<!\\)%.*", "", tex)


def iter_tables(tex):
    for m in re.finditer(r"\\begin\{table\*?\}(.*?)\\end\{table\*?\}", tex, re.S):
        yield m.group(1)


def caption(tab):
    m = re.search(r"\\caption\{", tab)
    i, d = m.end(), 1
    j = i
    while d:
        d += {"{": 1, "}": -1}.get(tab[j], 0)
        j += 1
    return clean(tab[i:j - 1])


def rows(tab):
    body = tab.split(r"\midrule", 1)[-1].split(r"\bottomrule", 1)[0]
    for r in body.split(r"\\"):
        r = r.strip()
        if "\\cite" in r and "&" in r:
            yield [c.strip() for c in re.split(r"(?<!\\)&", r)]


def name_and_keys(cell):
    keys = [k.strip() for g in re.findall(r"\\cite\{([^}]*)\}", cell)
            for k in g.split(",")]
    name = clean(re.sub(r"\\cite\{[^}]*\}", "", cell))
    return name, keys


def mark(c):
    return "✅" if "cmark" in c else ("—" if "xmark" in c else clean(c))


def app_caption_to_heading(cap):
    cap = re.sub(r"^Instantiation of the four functional capabilities in ", "", cap)
    cap = re.sub(r"\.$", "", cap)
    return cap[:1].upper() + cap[1:]


# ------------------------------------------------------------------ output
def main():
    bib = parse_bib(BIB.read_text(encoding="utf-8"))
    out = []
    w = out.append
    toc = []

    app_sections = []
    total = set()
    for fname, heading in APP_FILES:
        tex = strip_comments((APPS / fname).read_text(encoding="utf-8"))
        subs = []
        for tab in iter_tables(tex):
            cap = caption(tab)
            entries = []
            for cells in rows(tab):
                name, keys = name_and_keys(cells[0])
                total.update(keys)
                entries.append((name, keys, [mark(c) for c in cells[1:]]))
            subs.append((cap, entries))
        app_sections.append((heading, subs))

    bench_tex = strip_comments(BENCH.read_text(encoding="utf-8"))
    bench_levels = []
    for tab in iter_tables(bench_tex):
        body = tab.split(r"\midrule", 1)[1].split(r"\bottomrule", 1)[0]
        current = None
        for r in body.split(r"\\"):
            lvl = re.search(r"\\textbf\{(Level [^}]*)\}\s*(?:---\s*([^}]*))?\}", r)
            if lvl:
                current = (clean(lvl.group(1)), clean(lvl.group(2) or ""), [])
                bench_levels.append(current)
                continue
            if "\\cite" in r and current:
                cells = [c.strip() for c in re.split(r"(?<!\\)&", r.replace(r"\midrule", ""))]
                name, keys = name_and_keys(cells[0])
                total.update(keys)
                current[2].append((name, keys, [clean(c) for c in cells[1:]]))

    # ---------------------------------------------------------- header
    w("# Awesome Hybrid AI for AI-Native RAN Control")
    w("")
    w("[![arXiv](https://img.shields.io/badge/arXiv-2611.33035-b31b1b.svg)](https://arxiv.org/abs/2611.33035)")
    w("[![Awesome](https://awesome.re/badge.svg)](https://awesome.re)")
    w("![Papers](https://img.shields.io/badge/works-%d-blue)" % len(total))
    w("[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](#contributing)")
    w("")
    w("A curated collection of works on **hybrid AI for radio access network (RAN) "
      "control**: how foundation models, world models, reinforcement learning, and "
      "optimization are combined to make RAN decisions across protocol layers and "
      "control timescales. It accompanies our survey and is organized with the "
      "survey's **functional taxonomy**. This list will be continuously updated.")
    w("")
    w("> 📄 **Hybrid AI for AI-Native RAN Control: A Functional Perspective**  ")
    w("> Sabrine Aroua, Osama Arouk, Pegah Alizadeh  ")
    w("> *Under review at IEEE Communications Surveys & Tutorials.* "
      "Preprint: [arXiv:2611.33035](https://arxiv.org/abs/2611.33035)")
    w("")

    w('<p align="center">')
    w('  <img src="figures/ran_decision_system.png" width="85%" '
      'alt="AI-native RAN control as a distributed decision-making system">')
    w('</p>')
    w('<p align="center"><em>AI-native RAN control as a distributed decision-making '
      'system: entities across protocol layers and timescales interact through coupled '
      'control loops, which calls for four complementary capabilities.</em></p>')
    w("")

    # ---------------------------------------------------------- taxonomy
    w("## The Functional Taxonomy")
    w("")
    w("Instead of grouping works by AI technique, the survey asks **which decision-"
      "making capability** a component provides. The taxonomy is technique-agnostic: "
      "the same capability can be realized by an LLM, a digital twin, an RL agent, "
      "or a classical optimizer.")
    w("")
    w("| Block | Capability | Role in the decision process |")
    w("|---|---|---|")
    w("| **R&R** | Representation & Reasoning | Interpret intents, specifications and "
      "network state; build the decision context |")
    w("| **P&S** | Prediction & Simulation | Forecast network evolution and evaluate "
      "candidate actions (what-if analysis, digital twins, world models) |")
    w("| **AC** | Adaptive Control | Adjust control actions online from feedback "
      "(RL, adaptive optimization, rule-based adaptation) |")
    w("| **DS** | Decision Synthesis | Reconcile objectives, constraints and candidate "
      "decisions into a final, executable decision |")
    w("")
    w('<p align="center">')
    w('  <img src="figures/building_blocks_loop.png" width="95%" '
      'alt="Interplay of the four functional building blocks">')
    w('</p>')
    w('<p align="center"><em>How the four blocks exchange information through a shared '
      'decision context within one control loop (left), and how such loops nest across '
      'slow, medium and fast timescales (right).</em></p>')
    w("")
    w("Works below are grouped by **application class** and **control timescale**. "
      "For each work, ✅ marks the capabilities it explicitly realizes.")
    w("")

    # ---------------------------------------------------------- TOC
    w("## Contents")
    w("")
    for heading, subs in app_sections:
        a = re.sub(r"[^a-z0-9 -]", "", heading.lower()).replace(" ", "-")
        w(f"- [{heading}](#{a})")
        if len(subs) > 1:
            for cap, _ in subs:
                h = app_caption_to_heading(cap)
                a2 = re.sub(r"[^a-z0-9 -]", "", h.lower()).replace(" ", "-")
                w(f"  - [{h}](#{a2})")
    w("- [Survey Roadmap](#survey-roadmap)")
    w("- [Benchmarks, Datasets, and Evaluation Environments]"
      "(#benchmarks-datasets-and-evaluation-environments)")
    w("- [Citation](#citation)")
    w("- [Contributing](#contributing)")
    w("")

    # ---------------------------------------------------------- applications
    for heading, subs in app_sections:
        w(f"## {heading}")
        w("")
        for cap, entries in subs:
            if len(subs) > 1:
                w(f"### {app_caption_to_heading(cap)}")
                w("")
            extra = len(entries[0][2]) > 4 if entries else False
            w("| Work | R&R | P&S | AC | DS |" + (" Timescales |" if extra else ""))
            w("|---|:-:|:-:|:-:|:-:|" + ("---|" if extra else ""))
            for name, keys, marks in entries:
                e = bib.get(keys[0], {}) if keys else {}
                title = clean(e.get("title", name))
                url = link(e)
                t = f"[{title}]({url})" if url else title
                meta = ", ".join(x for x in (venue(e), clean(e.get("year", ""))) if x)
                cell = f"{t}<br>*{name}{' — ' + meta if meta else ''}*"
                w(f"| {cell} | " + " | ".join(marks) + " |")
            w("")

    # ---------------------------------------------------------- benchmarks
    w("## Benchmarks, Datasets, and Evaluation Environments")
    w("")
    w("Resources are ordered by **decision-making depth**, from passive data to full "
      "closed-loop interaction. *Block* is the capability a resource mainly supports; "
      "*Time* is the decision horizon of its target application class.")
    w("")
    for lvl, desc, entries in bench_levels:
        w(f"### {lvl}" + (f" — {desc}" if desc else ""))
        w("")
        w("| Resource | Block(s) | Time | Access / Notes |")
        w("|---|---|---|---|")
        for name, keys, cells in entries:
            links = []
            for k in keys:
                e = bib.get(k, {})
                url = link(e)
                title = clean(e.get("title", k))
                links.append(f"[{title}]({url})" if url else title)
            block, time, notes = (cells + ["", "", "", ""])[1:4]
            w(f"| **{name}**<br>{' · '.join(links)} | {block} | {time} | {notes} |")
        w("")
    w("> **Gap identified by the survey:** no public resource yet combines closed-loop "
      "RAN control with standardized tasks, common metrics, reference baselines, and a "
      "fixed seed protocol, i.e. a reproducible closed-loop RAN benchmark.")
    w("")

    # ---------------------------------------------------------- roadmap
    w("## Survey Roadmap")
    w("")
    w("The survey goes from decision-making techniques, to the requirements of AI-native "
      "RAN control, to the four functional capabilities, their use in applications, the "
      "evaluation ecosystem, and open research directions.")
    w("")
    w('<p align="center">')
    w('  <img src="figures/survey_roadmap.png" width="85%" alt="Survey roadmap">')
    w('</p>')
    w("")

    # ---------------------------------------------------------- footer
    w("## Citation")
    w("")
    w("If you find this list or the survey useful, please cite:")
    w("")
    w("```bibtex")
    w("@article{aroua2026hybrid,")
    w("  title   = {Hybrid {AI} for {AI-Native} {RAN} Control: A Functional Perspective},")
    w("  author  = {Aroua, Sabrine and Arouk, Osama and Alizadeh, Pegah},")
    w("  journal = {arXiv preprint arXiv:2611.33035},")
    w("  year    = {2026},")
    w("  eprint  = {2611.33035},")
    w("  archivePrefix = {arXiv},")
    w("  primaryClass  = {cs.AI},")
    w("  url     = {https://arxiv.org/abs/2611.33035}")
    w("}")
    w("```")
    w("")
    w("## Contributing")
    w("")
    w("Missing a work, or think one is classified wrongly? Open an issue or a pull "
      "request with the paper link, its application class, and the capabilities "
      "(R&R, P&S, AC, DS) it realizes.")
    w("")
    w("This README is generated from the paper sources with "
      "[`scripts/build_readme.py`](scripts/build_readme.py).")
    print("\n".join(out))


if __name__ == "__main__":
    main()
