"""Hierarchical tree viewer for a strict-mode exam graph.

Renders a self-contained HTML page with:
  • collapsible tree on the left  (Chapter ▸ Theme ▸ Task)
  • detail panel on the right     (selected node info + linked concepts/tasks)
  • header with stats             (chapters/themes/tasks/concepts/links)

This is intentionally simpler — and far more readable for our 13/68/2102/553
schema — than the k2-18 force-directed Cytoscape soup. The k2-18 viewer is
still vendored under ``vendor/k2-18/`` for reference but no longer rendered.
"""

from __future__ import annotations

import html
import json
from pathlib import Path

from app.core.logging import get_logger
from app.exams.graph_service import StrictGraph
from app.exams.registry import Exam, load_bank

logger = get_logger(__name__)


def _strip_prefix(s: str, *prefixes: str) -> str:
    for p in prefixes:
        if s.startswith(p):
            return s[len(p):]
    return s


def _build_tree_data(graph: StrictGraph, bank: dict) -> dict:
    """Convert the strict graph + bank into a render-ready tree blob."""
    chapters_meta = {int(c["id"]): c for c in (bank.get("chapters") or [])}
    themes_meta = {str(t["code"]): t for t in (bank.get("themes") or [])}
    tasks_meta = {int(t["id"]): t for t in (bank.get("tasks") or [])}

    # ---- collect concept info + prereq adjacency ----
    concepts: dict[str, dict] = {}
    for cid, info in graph.concept_info.items():
        concepts[cid] = {
            "id": cid,
            "term": info.get("term") or cid,
            "definition": (info.get("definition") or "").strip(),
            "prereqs": list(graph.prereqs_of.get(cid, [])),
            "dependants": list(graph.dependants_of.get(cid, [])),
        }

    # ---- task -> concepts links (top-3, ordered by score) ----
    task_skills: dict[int, list[dict]] = {}
    for tid, skills in graph.skills_by_task.items():
        task_skills[int(tid)] = [
            {
                "concept_id": s.concept_id,
                "term": s.concept_term,
                "score": round(s.score, 3),
            }
            for s in skills[:5]
        ]

    # ---- build hierarchy ----
    chapters_idx: dict[int, dict] = {}
    for chap_id, chap in chapters_meta.items():
        chapters_idx[chap_id] = {
            "id": chap_id,
            "num": chap.get("num"),
            "name": chap.get("name"),
            "themes": [],
            "n_themes": 0,
            "n_tasks": 0,
            "n_concepts": 0,
        }
    # group themes by chapter
    themes_by_chapter: dict[int, list[str]] = {}
    for tcode, t in themes_meta.items():
        chid = int(t.get("chapter_id") or 0)
        themes_by_chapter.setdefault(chid, []).append(tcode)

    # group tasks by theme
    tasks_by_theme: dict[str, list[int]] = {}
    for tid, t in tasks_meta.items():
        tasks_by_theme.setdefault(str(t.get("theme_code")), []).append(int(tid))

    for chid, chap in chapters_idx.items():
        theme_codes = sorted(themes_by_chapter.get(chid, []), key=lambda c: c)
        ch_concept_ids: set[str] = set()
        for tc in theme_codes:
            tasks = sorted(tasks_by_theme.get(tc, []))
            t_concept_ids: set[str] = set()
            task_blobs: list[dict] = []
            for tid in tasks:
                links = task_skills.get(tid, [])
                for l in links:
                    t_concept_ids.add(l["concept_id"])
                task_blobs.append(
                    {
                        "id": tid,
                        "number": tasks_meta.get(tid, {}).get("task_number") or str(tid),
                        "text": (tasks_meta.get(tid, {}).get("task_text") or "").strip(),
                        "difficulty": tasks_meta.get(tid, {}).get("difficulty"),
                        "concepts": links,
                    }
                )
            ch_concept_ids |= t_concept_ids
            chap["themes"].append(
                {
                    "code": tc,
                    "name": themes_meta.get(tc, {}).get("name") or tc,
                    "tasks": task_blobs,
                    "n_tasks": len(task_blobs),
                    "n_concepts": len(t_concept_ids),
                    "concept_ids": sorted(t_concept_ids),
                }
            )
        chap["n_themes"] = len(chap["themes"])
        chap["n_tasks"] = sum(t["n_tasks"] for t in chap["themes"])
        chap["n_concepts"] = len(ch_concept_ids)

    tree = {
        "chapters": [chapters_idx[k] for k in sorted(chapters_idx.keys())],
        "concepts": concepts,
        "meta": (graph.meta or {}).get("stats", {}),
    }
    return tree


# ---------- HTML template (vanilla JS, no build step) ----------


_PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<title>Граф · {title}</title>
<style>
:root {{
  --bg:#f6f7fb; --bg-2:#fff; --bg-3:#eef1f6;
  --fg:#0f172a; --fg-2:#475569; --fg-3:#94a3b8;
  --border:#e2e8f0; --border-strong:#cbd5e1;
  --accent:#4f46e5; --accent-strong:#4338ca; --accent-soft:#eef2ff;
  --ok:#16a34a; --warn:#d97706; --err:#dc2626;
  font-family:'Inter',ui-sans-serif,system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;
}}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--fg); font-size:14px; line-height:1.5; }}
header {{
  display:flex; align-items:center; justify-content:space-between;
  padding:14px 22px; background:#fff; border-bottom:1px solid var(--border);
  position:sticky; top:0; z-index:10;
}}
header h1 {{ font-size:18px; margin:0; }}
header .stats {{ color:var(--fg-2); font-size:12px; margin-top:2px; }}
header a {{ color:var(--accent); font-size:13px; text-decoration:none; padding:6px 12px; border-radius:8px; }}
header a:hover {{ background:var(--accent-soft); }}
#shell {{ display:grid; grid-template-columns:420px 1fr; gap:0; min-height:calc(100vh - 64px); }}
#left {{ background:#fff; border-right:1px solid var(--border); overflow:auto; max-height:calc(100vh - 64px); position:sticky; top:64px; }}
#right {{ padding:22px 26px; max-width:900px; }}
.search-box {{ position:sticky; top:0; padding:12px; background:#fff; border-bottom:1px solid var(--border); z-index:5; }}
.search-box input {{
  width:100%; padding:10px 12px; border:1px solid var(--border-strong);
  border-radius:8px; font-size:13px; font-family:inherit;
}}
.search-box input:focus {{ outline:3px solid var(--accent-soft); border-color:var(--accent); }}
.search-meta {{ font-size:11px; color:var(--fg-3); margin-top:6px; }}
.tree {{ padding:6px; }}
.chapter, .theme, .task {{
  border-radius:8px; transition:background 0.1s ease;
  user-select:none;
}}
.chapter {{ margin:2px 0; }}
.row {{
  display:flex; align-items:center; gap:8px; padding:8px 10px; cursor:pointer;
  border-radius:8px;
}}
.row:hover {{ background:var(--bg-3); }}
.row.selected {{ background:var(--accent-soft); color:var(--accent-strong); }}
.row .chev {{ width:14px; color:var(--fg-3); font-size:11px; transition:transform 0.15s ease; flex-shrink:0; }}
.row.open > .chev {{ transform:rotate(90deg); }}
.row .leaf-dot {{ width:14px; flex-shrink:0; text-align:center; color:var(--fg-3); }}
.title-cell {{ flex:1; min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
.title-cell .name {{ font-weight:500; }}
.chapter > .row > .title-cell .name {{ font-weight:700; }}
.title-cell .meta {{ font-size:11px; color:var(--fg-3); }}
.row .badge {{
  font-size:10px; font-weight:600; padding:2px 7px; border-radius:999px;
  background:var(--bg-3); color:var(--fg-2); white-space:nowrap;
}}
.row .badge.diff-1 {{ background:#dcfce7; color:var(--ok); }}
.row .badge.diff-2 {{ background:#fef3c7; color:var(--warn); }}
.themes, .tasks {{ display:none; padding-left:18px; border-left:1px dashed var(--border); margin-left:18px; }}
.row.open + .themes, .row.open + .tasks {{ display:block; }}
.row.matched-deep {{ }}
.row.dimmed {{ opacity:0.35; }}

/* Right panel */
.detail-header {{ margin-bottom:14px; }}
.detail-eyebrow {{ font-size:12px; color:var(--fg-3); text-transform:uppercase; letter-spacing:0.4px; }}
.detail-title {{ font-size:24px; font-weight:700; margin:4px 0 6px; }}
.detail-subtitle {{ color:var(--fg-2); font-size:14px; }}
.stat-row {{
  display:flex; gap:8px; flex-wrap:wrap; margin:14px 0 22px;
}}
.stat-pill {{
  background:#fff; border:1px solid var(--border); border-radius:10px;
  padding:8px 14px; font-size:13px; color:var(--fg-2);
}}
.stat-pill strong {{ color:var(--fg); font-size:15px; margin-right:4px; }}
.section {{ margin-top:24px; }}
.section h3 {{
  font-size:13px; font-weight:600; color:var(--fg-2); text-transform:uppercase;
  letter-spacing:0.5px; margin:0 0 10px;
}}
.task-card {{
  background:#fff; border:1px solid var(--border); border-radius:10px;
  padding:14px 16px; margin-bottom:8px;
}}
.task-card .task-head {{ display:flex; align-items:center; gap:8px; flex-wrap:wrap; margin-bottom:6px; }}
.task-card .task-id {{ font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:11px; color:var(--fg-3); }}
.task-card .task-text {{ font-size:13px; line-height:1.5; color:var(--fg); }}
.task-card .task-concepts {{ display:flex; flex-wrap:wrap; gap:4px; margin-top:8px; }}
.concept-chip {{
  background:var(--accent-soft); color:var(--accent-strong);
  font-size:11px; padding:2px 8px; border-radius:999px; cursor:pointer;
}}
.concept-chip:hover {{ background:#ddd6fe; }}
.concept-chip .score {{ color:var(--fg-3); margin-left:4px; }}
.concept-card {{
  background:#fff; border:1px solid var(--border); border-radius:10px;
  padding:12px 14px; margin-bottom:8px;
}}
.concept-card .term {{ font-weight:600; font-size:14px; margin-bottom:4px; }}
.concept-card .definition {{ font-size:12px; color:var(--fg-2); line-height:1.5; }}
.concept-edges {{ margin-top:6px; font-size:11px; }}
.edge-label {{ color:var(--fg-3); margin-right:4px; text-transform:uppercase; letter-spacing:0.3px; }}
.stat-action {{ cursor:pointer; border:1px solid var(--accent-soft); color:var(--accent-strong); background:var(--accent-soft); font-family:inherit; }}
.stat-action:hover {{ background:#ddd6fe; }}
.theory-section {{ background:#fff; border:1px solid var(--border); border-radius:10px; padding:12px 14px; margin-bottom:8px; }}
.theory-path {{ font-size:11px; color:var(--fg-3); text-transform:uppercase; letter-spacing:0.4px; margin-bottom:6px; }}
.theory-snippet {{ font-size:12.5px; line-height:1.6; white-space:pre-wrap; color:var(--fg); }}
.placeholder {{ color:var(--fg-3); padding:40px 20px; text-align:center; }}
.placeholder h3 {{ margin:0 0 6px; color:var(--fg-2); }}
.muted {{ color:var(--fg-3); }}
@media (max-width: 980px) {{
  #shell {{ grid-template-columns: 320px 1fr; }}
}}
</style>
</head>
<body>
<header>
  <div>
    <h1>{title}</h1>
    <div class="stats">{stats_line}</div>
  </div>
  <div>
    <a href="?layout=cytoscape">старый k2-18 viewer →</a>
  </div>
</header>
<div id="shell">
  <aside id="left">
    <div class="search-box">
      <input id="search" type="text" placeholder="Поиск по главам / темам / задачам / концептам…" />
      <div class="search-meta" id="search-meta"></div>
    </div>
    <div class="tree" id="tree"></div>
  </aside>
  <main id="right">
    <div class="placeholder" id="placeholder">
      <h3>Выберите узел в дереве слева</h3>
      <p>Главы открываются по клику. Поиск ищет по всем уровням сразу и подсвечивает совпадения.</p>
    </div>
    <div id="detail" style="display:none"></div>
  </main>
</div>
<script>
const TREE = {tree_json};
const CONCEPTS = TREE.concepts;
const STATS = TREE.meta;

// ---------- render tree ----------
function el(tag, opts) {{
  const e = document.createElement(tag);
  if (opts) {{
    if (opts.cls) e.className = opts.cls;
    if (opts.text) e.textContent = opts.text;
    if (opts.html) e.innerHTML = opts.html;
    if (opts.attr) for (const k in opts.attr) e.setAttribute(k, opts.attr[k]);
    if (opts.on) for (const k in opts.on) e.addEventListener(k, opts.on[k]);
  }}
  return e;
}}

let selected = null;
const treeRoot = document.getElementById('tree');

function makeRow(opts) {{
  // opts: hasChildren, label, meta, badge, onClick
  const row = el('div', {{ cls:'row' }});
  if (opts.hasChildren) {{
    const chev = el('span', {{ cls:'chev', html:'▶' }});
    row.appendChild(chev);
  }} else {{
    row.appendChild(el('span', {{ cls:'leaf-dot', text:'·' }}));
  }}
  const tc = el('div', {{ cls:'title-cell' }});
  tc.appendChild(el('div', {{ cls:'name', text: opts.label }}));
  if (opts.meta) tc.appendChild(el('div', {{ cls:'meta', text: opts.meta }}));
  row.appendChild(tc);
  if (opts.badge) row.appendChild(el('span', {{ cls:'badge ' + (opts.badgeCls||''), text: opts.badge }}));
  if (opts.onClick) row.addEventListener('click', opts.onClick);
  return row;
}}

function renderChapter(chap) {{
  const wrap = el('div', {{ cls:'chapter' }});
  const row = makeRow({{
    hasChildren: chap.themes.length > 0,
    label: 'Глава ' + chap.num + '. ' + chap.name,
    meta: chap.n_themes + ' тем · ' + chap.n_tasks + ' задач · ' + chap.n_concepts + ' концептов',
    onClick: (e) => {{
      e.stopPropagation();
      const open = row.classList.toggle('open');
      themes.style.display = open ? 'block' : 'none';
      selectRow(row, () => renderDetailChapter(chap));
    }}
  }});
  const themes = el('div', {{ cls:'themes' }});
  for (const th of chap.themes) themes.appendChild(renderTheme(th, chap));
  wrap.appendChild(row);
  wrap.appendChild(themes);
  return wrap;
}}

function renderTheme(theme, chap) {{
  const wrap = el('div', {{ cls:'theme' }});
  const row = makeRow({{
    hasChildren: theme.tasks.length > 0,
    label: theme.code + '. ' + theme.name,
    meta: theme.n_tasks + ' задач · ' + theme.n_concepts + ' концептов',
    onClick: (e) => {{
      e.stopPropagation();
      const open = row.classList.toggle('open');
      tasks.style.display = open ? 'block' : 'none';
      selectRow(row, () => renderDetailTheme(theme, chap));
    }}
  }});
  const tasks = el('div', {{ cls:'tasks' }});
  for (const t of theme.tasks) tasks.appendChild(renderTask(t, theme, chap));
  wrap.appendChild(row);
  wrap.appendChild(tasks);
  return wrap;
}}

function renderTask(task, theme, chap) {{
  const wrap = el('div', {{ cls:'task' }});
  const row = makeRow({{
    hasChildren: false,
    label: task.number + ' · ' + truncate(task.text, 64),
    badge: task.difficulty != null ? ('сл. ' + task.difficulty) : null,
    badgeCls: task.difficulty != null ? ('diff-' + task.difficulty) : '',
    onClick: (e) => {{
      e.stopPropagation();
      selectRow(row, () => renderDetailTask(task, theme, chap));
    }}
  }});
  wrap.appendChild(row);
  return wrap;
}}

function selectRow(row, render) {{
  if (selected) selected.classList.remove('selected');
  row.classList.add('selected');
  selected = row;
  document.getElementById('placeholder').style.display = 'none';
  const det = document.getElementById('detail');
  det.style.display = 'block';
  det.innerHTML = '';
  render();
}}

function truncate(s, n) {{ return s.length > n ? s.slice(0, n) + '…' : s; }}
function esc(s) {{ return String(s||'').replace(/[&<>"']/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c])); }}

// ---------- detail renderers ----------

function renderDetailChapter(chap) {{
  const det = document.getElementById('detail');
  det.innerHTML = `
    <div class="detail-header">
      <div class="detail-eyebrow">Глава ${{chap.num}}</div>
      <div class="detail-title">${{esc(chap.name)}}</div>
    </div>
    <div class="stat-row">
      <div class="stat-pill"><strong>${{chap.n_themes}}</strong> тем</div>
      <div class="stat-pill"><strong>${{chap.n_tasks}}</strong> задач</div>
      <div class="stat-pill"><strong>${{chap.n_concepts}}</strong> концептов</div>
    </div>
    <div class="section">
      <h3>Темы главы</h3>
      ${{chap.themes.map(t => `
        <div class="task-card">
          <div class="task-head">
            <span class="task-id">${{t.code}}</span>
            <strong>${{esc(t.name)}}</strong>
          </div>
          <div class="task-text muted">${{t.n_tasks}} задач · ${{t.n_concepts}} концептов</div>
        </div>
      `).join('')}}
    </div>
  `;
}}

function renderConceptCard(c) {{
  const prereqs = (c.prereqs || []).map(pid => CONCEPTS[pid]).filter(Boolean);
  const dependants = (c.dependants || []).map(pid => CONCEPTS[pid]).filter(Boolean);
  let edges = '';
  if (prereqs.length) {{
    edges += `<div class="concept-edges"><span class="edge-label">prereq:</span> ${{prereqs.map(p => `<span class="concept-chip">${{esc(p.term)}}</span>`).join(' ')}}</div>`;
  }}
  if (dependants.length) {{
    edges += `<div class="concept-edges"><span class="edge-label">unlocks:</span> ${{dependants.map(p => `<span class="concept-chip">${{esc(p.term)}}</span>`).join(' ')}}</div>`;
  }}
  return `
    <div class="concept-card">
      <div class="term">${{esc(c.term)}}</div>
      <div class="definition">${{esc(c.definition)}}</div>
      ${{edges}}
    </div>
  `;
}}

async function loadAndRenderTheory(themeCode) {{
  const box = document.getElementById('theory-box-' + themeCode);
  if (!box) return;
  box.innerHTML = '<div class="muted">Грузим секции учебника…</div>';
  try {{
    const r = await fetch(`/api/v1/exams/{exam_slug}/theme/${{encodeURIComponent(themeCode)}}`);
    if (!r.ok) {{
      box.innerHTML = `<div class="muted">Нет привязки к теории (${{r.status}}). Запусти <code>python -m app.pipeline.link_theory --exam {exam_slug}</code>.</div>`;
      return;
    }}
    const data = await r.json();
    if (!data.sections || data.sections.length === 0) {{
      box.innerHTML = '<div class="muted">Секции не найдены.</div>';
      return;
    }}
    box.innerHTML = data.sections.map(s => `
      <div class="theory-section">
        <div class="theory-path">${{esc(s.section_path)}} <span class="muted">· score ${{s.score}}</span></div>
        <div class="theory-snippet">${{esc((s.excerpt || s.snippet || '').slice(0, 1200))}}${{(s.excerpt || s.snippet || '').length > 1200 ? '…' : ''}}</div>
      </div>
    `).join('');
  }} catch (e) {{
    box.innerHTML = '<div class="muted">Ошибка загрузки: ' + esc(e.message) + '</div>';
  }}
}}

function renderDetailTheme(theme, chap) {{
  const det = document.getElementById('detail');
  const concepts = theme.concept_ids.map(id => CONCEPTS[id]).filter(Boolean);
  det.innerHTML = `
    <div class="detail-header">
      <div class="detail-eyebrow">${{chap ? ('Глава ' + chap.num + ' · ') : ''}}Тема ${{theme.code}}</div>
      <div class="detail-title">${{esc(theme.name)}}</div>
    </div>
    <div class="stat-row">
      <div class="stat-pill"><strong>${{theme.n_tasks}}</strong> задач</div>
      <div class="stat-pill"><strong>${{theme.n_concepts}}</strong> концептов</div>
      <button class="stat-pill stat-action" onclick="loadAndRenderTheory('${{theme.code}}')">📖 показать теорию темы</button>
    </div>
    <div class="section" id="theory-wrap">
      <div id="theory-box-${{theme.code}}"></div>
    </div>
    <div class="section">
      <h3>Концепты темы</h3>
      ${{concepts.length === 0 ? '<div class="muted">Концепты не размечены.</div>' : concepts.map(renderConceptCard).join('')}}
    </div>
    <div class="section">
      <h3>Задачи темы</h3>
      ${{theme.tasks.map(t => `
        <div class="task-card">
          <div class="task-head">
            <span class="task-id">#${{t.id}}</span>
            <span class="task-id">${{t.number}}</span>
            ${{t.difficulty != null ? `<span class="badge diff-${{t.difficulty}}">сл. ${{t.difficulty}}</span>` : ''}}
          </div>
          <div class="task-text">${{esc(truncate(t.text, 240))}}</div>
        </div>
      `).join('')}}
    </div>
  `;
}}

function renderDetailTask(task, theme, chap) {{
  const det = document.getElementById('detail');
  det.innerHTML = `
    <div class="detail-header">
      <div class="detail-eyebrow">${{chap ? ('Глава ' + chap.num + ' · ') : ''}}${{theme ? ('Тема ' + theme.code + ' · ') : ''}}Задача #${{task.id}}</div>
      <div class="detail-title">${{task.number}}</div>
    </div>
    <div class="stat-row">
      ${{task.difficulty != null ? `<div class="stat-pill"><strong>${{task.difficulty}}</strong> сложность</div>` : ''}}
      <div class="stat-pill"><strong>${{task.concepts.length}}</strong> связанных концептов</div>
    </div>
    <div class="section">
      <h3>Текст задачи</h3>
      <div class="task-card"><div class="task-text">${{esc(task.text)}}</div></div>
    </div>
    <div class="section">
      <h3>Связанные концепты <span class="muted">(TESTS_CONCEPT)</span></h3>
      ${{task.concepts.length === 0 ? '<div class="muted">Концепты не размечены.</div>' : task.concepts.map(c => {{
        const info = CONCEPTS[c.concept_id] || {{}};
        return `
          <div class="concept-card">
            <div class="term">${{esc(c.term)}} <span class="muted">· score ${{c.score}}</span></div>
            <div class="definition">${{esc(info.definition || '')}}</div>
          </div>
        `;
      }}).join('')}}
    </div>
  `;
}}

// ---------- search ----------

const searchInput = document.getElementById('search');
const searchMeta = document.getElementById('search-meta');
searchInput.addEventListener('input', () => {{
  const q = searchInput.value.trim().toLowerCase();
  if (!q) {{
    // collapse + clear dim
    document.querySelectorAll('.row.open').forEach(r => r.classList.remove('open'));
    document.querySelectorAll('.themes, .tasks').forEach(el => el.style.display = 'none');
    document.querySelectorAll('.dimmed').forEach(r => r.classList.remove('dimmed'));
    searchMeta.textContent = '';
    return;
  }}
  let hits = 0;
  for (const chap of TREE.chapters) {{
    let chapHit = matches(chap.name, q) || matches('глава ' + chap.num, q);
    for (const th of chap.themes) {{
      let thHit = matches(th.name, q) || matches(th.code, q);
      for (const tk of th.tasks) {{
        const tkHit = matches(tk.text, q) || matches(tk.number, q);
        tk._hit = tkHit;
        if (tkHit) {{ thHit = true; hits++; }}
      }}
      th._hit = thHit;
      if (thHit) chapHit = true;
    }}
    chap._hit = chapHit;
  }}
  // re-render with highlight + auto-expand
  treeRoot.innerHTML = '';
  for (const c of TREE.chapters) treeRoot.appendChild(renderChapter(c));
  // apply state
  applyFilter();
  searchMeta.textContent = hits + ' совпадений';
}});

function matches(s, q) {{ return String(s||'').toLowerCase().includes(q); }}

function applyFilter() {{
  // walk rendered tree and use _hit flags from data
  const chapNodes = treeRoot.querySelectorAll(':scope > .chapter');
  chapNodes.forEach((wrap, ci) => {{
    const chap = TREE.chapters[ci];
    const row = wrap.querySelector(':scope > .row');
    if (!chap._hit) row.classList.add('dimmed');
    else {{
      row.classList.add('open');
      wrap.querySelector(':scope > .themes').style.display = 'block';
    }}
    const themeWraps = wrap.querySelectorAll(':scope > .themes > .theme');
    themeWraps.forEach((tw, ti) => {{
      const th = chap.themes[ti];
      const tr = tw.querySelector(':scope > .row');
      if (!th._hit) tr.classList.add('dimmed');
      else {{
        tr.classList.add('open');
        tw.querySelector(':scope > .tasks').style.display = 'block';
      }}
      const taskWraps = tw.querySelectorAll(':scope > .tasks > .task');
      taskWraps.forEach((tkw, ki) => {{
        const tk = th.tasks[ki];
        const trk = tkw.querySelector(':scope > .row');
        if (!tk._hit) trk.classList.add('dimmed');
      }});
    }});
  }});
}}

// ---------- initial render ----------
for (const c of TREE.chapters) treeRoot.appendChild(renderChapter(c));
</script>
</body>
</html>
"""


# ---------- k2-18 cytoscape fallback (vendored, kept for ?layout=cytoscape) ----------


VENDOR_ROOT = Path(__file__).resolve().parent.parent.parent / "vendor" / "k2-18"
VIZ_ROOT = VENDOR_ROOT / "viz"
LEGACY_TPL_DIR = VIZ_ROOT / "templates" / "viewer"
LEGACY_STATIC_DIR = VIZ_ROOT / "static" / "viewer"
LEGACY_VENDOR_DIR = VIZ_ROOT / "vendor"


def _render_legacy_k218(exam: Exam, graph: StrictGraph) -> str:
    """Render the vendored k2-18 tabular viewer for users who want it."""
    from functools import lru_cache as _lru
    from jinja2 import Environment, FileSystemLoader

    # Adapt schema (Task → Assessment etc.) — kept compact, see prior version.
    nodes: list[dict] = []
    concepts_dict: list[dict] = []
    for n in graph.nodes:
        ntype = n.get("type")
        nid = n.get("id", "")
        if ntype == "Chapter":
            label = f"Глава {n.get('num')}. {n.get('name', '')}".strip()
            nodes.append({"id": nid, "type": "Chunk", "text": label, "definition": label})
        elif ntype == "Theme":
            label = f"Тема {n.get('code')}. {n.get('name', '')}".strip()
            nodes.append({"id": nid, "type": "Chunk", "text": label, "definition": label})
        elif ntype == "Task":
            text = (n.get("task_text") or "").strip()
            nodes.append({"id": nid, "type": "Assessment", "text": text, "definition": text[:300]})
        elif ntype == "Concept":
            term = (n.get("term") or "").strip()
            definition = (n.get("definition") or "").strip()
            nodes.append({"id": nid, "type": "Concept", "text": term, "definition": definition})
            concepts_dict.append({"concept_id": _strip_prefix(nid, "co:"), "term": {"primary": term, "aliases": n.get("aliases") or []}, "definition": definition})
        else:
            nodes.append(n)
    edges = []
    for e in graph.edges:
        et = e.get("type")
        if et == "TESTS_CONCEPT":
            et = "TESTS"
        elif et in {"HAS_THEME", "HAS_TASK", "BELONGS_TO_THEME"}:
            et = "MENTIONS"
        edges.append({"source": e.get("source"), "target": e.get("target"), "type": et, "weight": e.get("weight", 1.0)})
    g = {"_meta": {"version": "strict"}, "nodes": nodes, "edges": edges}
    cd = {"_meta": {"source": "strict-pipeline"}, "concepts": concepts_dict}

    env = Environment(loader=FileSystemLoader(str(LEGACY_TPL_DIR)), autoescape=False)
    template = env.get_template("index.html")
    css = (LEGACY_TPL_DIR / "viewer_styles.css").read_text(encoding="utf-8")
    modules_files = {
        "viewer_core_content": "viewer_core.js",
        "search_filter_content": "search_filter.js",
        "node_explorer_content": "node_explorer.js",
        "edge_inspector_content": "edge_inspector.js",
        "navigation_history_content": "navigation_history.js",
        "formatters_content": "formatters.js",
    }
    modules = {k: (LEGACY_STATIC_DIR / f).read_text(encoding="utf-8") for k, f in modules_files.items()}
    vendor_js = "\n\n".join(
        f"/* {f} */\n{(LEGACY_VENDOR_DIR / f).read_text(encoding='utf-8')}"
        for f in ("marked.min.js", "highlight.min.js", "mathjax-tex-mml-chtml.js")
        if (LEGACY_VENDOR_DIR / f).exists()
    )
    vendor_css = "\n\n".join(
        f"/* {f} */\n{(LEGACY_VENDOR_DIR / f).read_text(encoding='utf-8')}"
        for f in ("github-dark.min.css",)
        if (LEGACY_VENDOR_DIR / f).exists()
    )
    return template.render(
        title=exam.title,
        node_count=len(nodes), edge_count=len(edges),
        styles_content=css,
        vendor_css_content=vendor_css,
        link_tags="",
        graph_data_json=json.dumps(g, ensure_ascii=False, separators=(",", ":")),
        concepts_data_json=json.dumps(cd, ensure_ascii=False, separators=(",", ":")),
        text_formatting={"enabled": True, "markdown": True},
        vendor_js_content=vendor_js,
        script_tags="",
        embed_libraries=True,
        **modules,
    )


# ---------- public entrypoint ----------


def render_viewer_html(exam: Exam, graph: StrictGraph, *, layout: str = "tree") -> str:
    """Render the viewer.

    layout="tree" (default): our hierarchical Chapter → Theme → Task viewer.
    layout="cytoscape": the vendored k2-18 tabular viewer (legacy).
    """
    if layout == "cytoscape":
        return _render_legacy_k218(exam, graph)

    bank = load_bank(exam)
    tree = _build_tree_data(graph, bank)
    stats = tree.get("meta", {})
    by_node = stats.get("by_node_type", {})
    by_edge = stats.get("by_edge_type", {})
    stats_line = (
        f"{by_node.get('Chapter', 0)} глав · "
        f"{by_node.get('Theme', 0)} тем · "
        f"{by_node.get('Task', 0)} задач · "
        f"{by_node.get('Concept', 0)} концептов · "
        f"{by_edge.get('TESTS_CONCEPT', 0)} task↔concept связей"
    )
    return _PAGE_TEMPLATE.format(
        title=html.escape(exam.title),
        stats_line=html.escape(stats_line),
        tree_json=json.dumps(tree, ensure_ascii=False),
        exam_slug=exam.slug,
    )
