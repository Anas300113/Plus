"""Full dashboard pages: Home, Learn, Mock Exams, Progress, Parent.
Served by the API with no build step; all data from approved-only
and deterministic aggregation endpoints."""
from __future__ import annotations

def _page(title: str, body: str) -> str:
    return ("<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
            "<title>" + title + " - 11+ Platform</title>"
            "<style>body{font-family:system-ui,sans-serif;max-width:720px;margin:0 auto;padding:0 1rem 3rem}"
            "nav{display:flex;gap:.5rem;flex-wrap:wrap;margin:1rem 0}"
            "nav a{padding:.4rem .8rem;border:1px solid #ccc;border-radius:6px;text-decoration:none;color:#111}"
            ".card{border:1px solid #ddd;border-radius:8px;padding:1rem;margin:.75rem 0}"
            "button{padding:.5rem 1rem;margin:.25rem;cursor:pointer}"
            "table{border-collapse:collapse;width:100%}td,th{border:1px solid #ddd;padding:.4rem;text-align:left}"
            ".muted{color:#555}</style></head><body>"
            "<nav><a href=\"/\">Home</a><a href=\"/learn\">Learn</a><a href=\"/practice\">Practice</a>"
            "<a href=\"/mocks\">Mock Exams</a><a href=\"/progress\">Progress</a><a href=\"/parent\">Parent</a></nav>"
            + body + "</body></html>")


HOME = _page("Home", """<h1>11+ Preparation Platform</h1>
<p class="muted">Learn a topic, try a worked example, practise, review mistakes, re-test.</p>
<div class="card"><b>Learn</b><p>Lessons, strategies, worked examples and common mistakes per topic.</p><a href="/learn">Open Learn</a></div>
<div class="card"><b>Practice</b><p>Approved questions only. <a href="/practice">Open Practice</a></p></div>
<div class="card"><b>Mock Exams</b><p>Authentic source-paper mode or generated papers. <a href="/mocks">Open Mocks</a></p></div>
<div class="card"><b>Progress + Parent</b><p><a href="/progress">Progress</a> - <a href="/parent">Parent dashboard</a></p></div>""")

LEARN = _page("Learn", """<h1>Learn</h1>
<div><label>Topic id <input id="t" value="maths-fractions" size="24"></label>
<button onclick="load()">Load</button></div><div id="out"></div>
<script>async function load(){const t=document.getElementById('t').value;
const c=await (await fetch('/api/curriculum/'+encodeURIComponent(t))).json();
const sec=(h,items,k)=>'<h3>'+h+'</h3>'+(items.map(i=>'<div class=card><b>'+i.title+'</b><pre style=white-space:pre-wrap>'+(i.content||i.explanation||'')+'</pre></div>').join('')||'<p class=muted>None yet.</p>');
document.getElementById('out').innerHTML=sec('Lessons',c.lessons)+sec('Strategies',c.strategies)+sec('Worked examples',c.worked_examples)+'<h3>Common mistakes</h3>'+(c.common_mistakes.map(m=>'<div class=card><b>'+m.mistake+'</b><pre style=white-space:pre-wrap>'+m.explanation+'</pre></div>').join('')||'<p class=muted>None yet.</p>');}
load();</script>""")

MOCKS = _page("Mock Exams", """<h1>Mock Exams</h1>
<div class="card"><h3>Build a generated paper (approved questions only)</h3>
<label>Name <input id="n" value="Practice paper"></label><br>
<label>Subject <input id="s" value="maths"></label>
<label>Count <input id="c" value="10" size="4"></label>
<label>Minutes <input id="m" value="30" size="4"></label><br>
<button onclick="build()">Assemble</button><div id="out"></div></div>
<script>async function build(){
const e=await (await fetch('/api/exams',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:document.getElementById('n').value})})).json();
const r=await (await fetch('/api/exams/'+e.exam_id+'/assemble',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({mode:'generated',sections:[{subject:document.getElementById('s').value,count:+document.getElementById('c').value,time_minutes:+document.getElementById('m').value,name:'Section 1'}]})})).json();
document.getElementById('out').innerHTML='<p>Assembled '+r.questions.length+' questions.</p><ol>'+r.questions.map(q=>'<li>'+q+'</li>').join('')+'</ol><p>Answer them in <a href="/practice">Practice</a>.</p>';}</script>""")

PROGRESS = _page("Progress", """<h1>Progress</h1>
<div><label>Student id <input id="sid" value="demo"></label>
<button onclick="load()">Load</button></div><div id="out"></div>
<script>async function load(){const sid=document.getElementById('sid').value;
const p=await (await fetch('/api/progress/'+encodeURIComponent(sid))).json();
const rows=p.weak_topics.map(w=>'<tr><td>'+w.topic+'</td><td>'+Math.round(w.accuracy*100)+'%</td><td>'+w.practiced+'</td></tr>').join('');
document.getElementById('out').innerHTML='<h3>Weak topics</h3><table><tr><th>Topic</th><th>Accuracy</th><th>Practised</th></tr>'+(rows||'<tr><td colspan=3 class=muted>No weak topics recorded.</td></tr>')+'</table>';}
load();</script>""")

PARENT = _page("Parent", """<h1>Parent dashboard</h1>
<div><label>Student id <input id="sid" value="demo"></label>
<button onclick="load()">Load</button></div><div id="out"></div>
<script>async function load(){const sid=document.getElementById('sid').value;
const d=await (await fetch('/api/parent/'+encodeURIComponent(sid))).json();
const subj=Object.entries(d.subject_performance).map(([k,v])=>'<tr><td>'+k+'</td><td>'+v.correct+'/'+v.attempted+'</td></tr>').join('');
document.getElementById('out').innerHTML='<div class=card><b>Practice completed:</b> '+d.practice_completed+'</div>'
+'<h3>Subject performance</h3><table><tr><th>Subject</th><th>Correct/Attempted</th></tr>'+(subj||'<tr><td colspan=2 class=muted>No attempts yet.</td></tr>')+'</table>'
+'<h3>Weak areas</h3><ul>'+(d.weak_areas.map(w=>'<li>'+w.topic+' - '+Math.round(w.accuracy*100)+'%</li>').join('')||'<li class=muted>None.</li>')+'</ul>'
+'<h3>Recommended next steps</h3><ul>'+(d.recommended_next_steps.map(s=>'<li>'+s+'</li>').join('')||'<li class=muted>Keep practising.</li>')+'</ul>'
+'<h3>Recent activity</h3><ul>'+(d.recent_activity.map(a=>'<li>'+a.question_id.slice(0,8)+' - '+(a.correct?'correct':'incorrect')+'</li>').join('')||'<li class=muted>None.</li>')+'</ul>';}
load();</script>""")
