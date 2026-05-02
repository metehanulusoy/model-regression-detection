"""Embedded Jinja2 template for the HTML diff report.

Kept as a Python string so the package ships standalone (no MANIFEST.in tricks)
and so unit tests can render snapshots without a tmp dir."""

from __future__ import annotations

HTML_TEMPLATE: str = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Regression Report — {{ report.candidate.run_id }}</title>
<style>
  :root {
    --bg: #0f172a; --panel: #1e293b; --text: #e2e8f0; --muted: #94a3b8;
    --ok: #22c55e; --warn: #f59e0b; --crit: #ef4444; --imp: #38bdf8;
    --border: #334155;
  }
  * { box-sizing: border-box; }
  body { margin: 0; font: 14px/1.5 -apple-system, BlinkMacSystemFont, sans-serif;
         background: var(--bg); color: var(--text); }
  header { padding: 24px 32px; background: var(--panel); border-bottom: 1px solid var(--border); }
  h1 { margin: 0 0 4px; font-size: 22px; }
  .meta { color: var(--muted); font-size: 13px; }
  .pill { display: inline-block; padding: 2px 10px; border-radius: 12px;
          font-weight: 600; font-size: 12px; text-transform: uppercase;
          letter-spacing: 0.5px; }
  .pill.ok { background: rgba(34,197,94,0.15); color: var(--ok); }
  .pill.warning { background: rgba(245,158,11,0.15); color: var(--warn); }
  .pill.critical { background: rgba(239,68,68,0.15); color: var(--crit); }
  main { padding: 24px 32px; max-width: 1200px; }
  .summary { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
             gap: 12px; margin-bottom: 24px; }
  .card { background: var(--panel); border: 1px solid var(--border); border-radius: 8px;
          padding: 12px 16px; }
  .card h3 { margin: 0 0 4px; font-size: 12px; color: var(--muted); text-transform: uppercase; }
  .card .v { font-size: 22px; font-weight: 600; }
  table { width: 100%; border-collapse: collapse; background: var(--panel);
          border: 1px solid var(--border); border-radius: 8px; overflow: hidden; }
  th, td { padding: 10px 12px; text-align: left; border-bottom: 1px solid var(--border);
           vertical-align: top; font-family: inherit; }
  th { font-size: 12px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.5px; }
  tr:last-child td { border-bottom: none; }
  .verdict { font-size: 11px; font-weight: 600; text-transform: uppercase; padding: 2px 8px;
             border-radius: 6px; display: inline-block; }
  .verdict.regression { background: rgba(239,68,68,0.15); color: var(--crit); }
  .verdict.improvement { background: rgba(56,189,248,0.15); color: var(--imp); }
  .verdict.unchanged { background: rgba(148,163,184,0.15); color: var(--muted); }
  .verdict.new, .verdict.removed { background: rgba(245,158,11,0.15); color: var(--warn); }
  .delta { font-variant-numeric: tabular-nums; }
  .delta.neg { color: var(--crit); }
  .delta.pos { color: var(--imp); }
  pre { background: #0b1220; color: #e2e8f0; padding: 8px; border-radius: 4px;
        white-space: pre-wrap; word-wrap: break-word; font-size: 12px; max-width: 380px;
        max-height: 200px; overflow: auto; margin: 0; }
  code { background: #0b1220; color: var(--imp); padding: 1px 4px; border-radius: 3px; }
  footer { padding: 16px 32px; color: var(--muted); font-size: 12px; }
</style>
</head>
<body>
  <header>
    <h1>
      Regression Report
      <span class="pill {{ report.severity.value }}">{{ report.severity.value }}</span>
    </h1>
    <div class="meta">
      <strong>Prompt:</strong> {{ report.candidate.prompt_name }}@{{ report.candidate.prompt_version }}
      <span style="margin: 0 8px;">|</span>
      <strong>Model:</strong> <code>{{ report.candidate.model }}</code>
      <span style="margin: 0 8px;">|</span>
      Baseline <code>{{ report.baseline.run_id }}</code> → Candidate <code>{{ report.candidate.run_id }}</code>
    </div>
  </header>
  <main>
    <section class="summary">
      <div class="card"><h3>Composite Δ</h3><div class="v delta {{ 'neg' if report.avg_composite_delta_pct < 0 else 'pos' }}">{{ '%+.2f' % report.avg_composite_delta_pct }}pp</div></div>
      <div class="card"><h3>Regressions</h3><div class="v">{{ report.n_regressions }}</div></div>
      <div class="card"><h3>Improvements</h3><div class="v">{{ report.n_improvements }}</div></div>
      <div class="card"><h3>Unchanged</h3><div class="v">{{ report.n_unchanged }}</div></div>
    </section>
    <table>
      <thead>
        <tr><th>Case</th><th>Verdict</th><th>Δ</th><th>Baseline output</th><th>Candidate output</th></tr>
      </thead>
      <tbody>
        {% for d in report.diffs %}
        <tr>
          <td><code>{{ d.case_id }}</code></td>
          <td><span class="verdict {{ d.verdict.value }}">{{ d.verdict.value }}</span></td>
          <td class="delta {{ 'neg' if d.composite_delta < 0 else 'pos' }}">{{ '%+.3f' % d.composite_delta }}</td>
          <td>{% if d.baseline %}<pre>{{ d.baseline.output }}</pre><div class="meta">composite {{ '%.3f' % d.baseline.scores.composite }}</div>{% else %}<em>—</em>{% endif %}</td>
          <td>{% if d.candidate %}<pre>{{ d.candidate.output }}</pre><div class="meta">composite {{ '%.3f' % d.candidate.scores.composite }}</div>{% else %}<em>—</em>{% endif %}</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </main>
  <footer>
    Generated by <a style="color:#38bdf8" href="https://github.com/metehanulusoy/model-regression-detection">model-regression-detection</a>.
  </footer>
</body>
</html>
"""
