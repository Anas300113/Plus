"""Full dashboard pages: Home, Learn, Mock Exams, Progress, Parent.
Served by the API with no build step; all data from approved-only
and deterministic aggregation endpoints.
"""
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
<script>async function load(){
const t=document.getElementById('t').value;
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
const r=await (await fetch('/api/exams/'+e.exam_id+'/assemble',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({count:document.getElementById('c').value})})).json();
document.getElementById('out').innerHTML='<p>Build done: '+e.exam_id+' ('+r.attempts+' attempts, practice +'+(r.missed||0)+') ready.</p>';}
</script>""")

PROGRESS = _page("Progress", """<h1>Progress</h1>
<div class="card"><label>View progress for <input id="stu" style="width:180px" value="s1"></label>
<button onclick="load()">Load</button></div><div id="out"></div>
<script>async function load(){
const stu=document.getElementById('stu').value;
const p=await (await fetch('/api/progress/'+encodeURIComponent(stu))).json();
document.getElementById('out').innerHTML='<p>Total questions: '+p.total+' . Correct: '+p.correct+' . Accuracy: '+p.accuracy+'%</p>';
const tc=p.top.map?p.top.join(''):'';document.getElementById('out').innerHTML+=('<p>Top topics: '+tc+'</p>');}
load();</script>""")

PARENT = _page("Parent", """<h1>Parent dashboard</h1>
<div class="card"><label>Student <input id="stu" style="width:180px" value="s1"></label>
<button onclick="load()">Load</button></div><div id="out"></div>
<script>async function load(){
const stu=document.getElementById('stu').value;
const perf=await (await fetch('/api/progress/'+encodeURIComponent(stu))).json();
document.getElementById('out').innerHTML='<p>Progress for '+stu+': correct '+perf.correct+' / '+perf.total+' ('+perf.accuracy+'%)</p>';
const sb=await (await fetch('/api/sessions?parent=true')).json();
document.getElementById('out').innerHTML+='<h3>Sessions</h3><ul id="list">'+sb.map(s=>'<li>'+s.session_id.slice(0,8)+' - '+(s.current_sector||0)+' sectors done</li>').join('')||'<li class="muted">None.</li>'+(s=>'</ul>')()+'</ul>';
load();</script>""")

REVIEW = _page("Review", """<h1>Question review</h1>
<div id=errors style="display:none;color:#a00;"></div>
<p class="muted">Server-side token required for changes. Set <code>PLUS_REVIEWER_TOKEN</code>
and paste it below. Approval is blocked until every requirement is met.</p>
<label>Reviewer token <input id="tok" type="password" placeholder="token"></label>
<button onclick="loadQueue()">Load queue</button>
<div id="queue"></div><div id="detail"></div>
<script>
function esc(s){return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');}
const api=async(u,o)=>{const h={'Content-Type':'application/json'};
const t=document.getElementById('tok').value;if(t)h['X-Reviewer-Token']=t;
const r=await fetch(u,{method:o?'POST':'GET',headers:h,body:o?JSON.stringify(o):undefined});
return {ok:r.ok,status:r.status,data:await r.json().catch(()=>({}))};};
let errorMsg='';
function showError(msg){errorMsg=msg||'';
  const el=document.getElementById('errors');if(el){el.textContent=errorMsg;el.style.display=errorMsg?'':none;}}
async function loadQueue(){
  const r=await api('/api/review-queue?limit=50');
  showError('');
  const box=document.getElementById('queue');
  if(!r.ok){showError(r.status+': '+(await r.json().catch(()=>({})).detail||r.statusText));return;}
  box.innerHTML=r.data.length?
    '<table><tr><th>Subject/topic</th><th>Status</th><th></th></tr>'+
    r.data.map(function(q){return '<tr><td>'+esc(q.subject)+'/'+esc(q.topic)+'</td><td>'+esc(q.status)+'</td><td><button onclick="loadDetail('+JSON.stringify(q.id)+')">Open</button></td></tr>';}).join('')+'</table>'
   :'<p class="muted">No candidates awaiting review.</p>';}
async function loadDetail(id){
  const r=await api('/api/review/'+id);
  showError('');
  const d=r.data||{};
  const blockers=(d.approval_blockers||[]).map(function(b){return '<li>'+esc(b)+'</li>';}).join('');
  const opts=(d.options||[]).map(function(o){return '<li>'+esc(o.letter||o.label||'')+'. '+(o.text?esc(o.text):'')+'</li>';}).join('');
  const prov=(d.provenance||[]).map(function(p){return esc(p.filename)+' p.'+esc(p.page_number)+' #'+esc(p.question_number);}).join('; ');
  document.getElementById('detail').innerHTML=
    '<div class="card"><b>'+esc(d.question_text||'')+'</b>'+
    '<p class="muted">Type: '+esc(d.question_type||'')+' | Review: '+esc(d.review_status||'')+
    ' | Answer: '+esc(d.answer_status||'')+' | Explanation: '+esc(d.explanation_status||'')+'</p>'+
    '<p class="muted">Source: '+(prov||'none')+'</p><ul>'+opts+'</ul>'+
    '<p><b>Answer:</b> '+esc(d.correct_answer||'')+' <b>Explanation:</b> '+esc(d.explanation||'---')+'</p>'+
    (blockers?'<p style="color:#a00;"><b>Blocked:</b><ul>'+blockers+'</ul></p>'
     :'<p style="color:#080;"><b>Eligible to approve.</b></p>')+
    '<div class="card"><label>Question text <textarea id="qt" rows="3">'+esc(d.question_text||'')+'</textarea></label></div>'+
    '<div class="card">Answer <input id="ca" size="40" value="'+esc(d.correct_answer||'')+'"></div>'+
    '<div class="card">Options <textarea id="opts" rows="5">'+esc(JSON.stringify(d.options||[]))+'</textarea></div>'+
    '<div class="card"><label>Explanation <textarea id="ex" rows="3"></textarea></label></div><div class="card"><label>Answer evidence (source ref) <input id="ev" size="40" value="'+esc(d.answer_evidence||'')+'"></label></div>'+
    '<div class="card"><button onclick="verifyA('+JSON.stringify(id)+')">Verify answer</button> '+
    '<button onclick="verifyE('+JSON.stringify(id)+')">Verify explanation</button></div>'+
    '<div class="card"><button onclick="editQ('+JSON.stringify(id)+')">Save edit</button></div>'+
    '<div class="card"><button onclick="decide('+JSON.stringify(id)+',&quot;approved&quot;)">Approved</button> '+
    '<button onclick="decide('+JSON.stringify(id)+',&quot;rejected&quot;)">Rejected</button></div></div>';}
async function mustOk(r,what){if(!r.ok){showError(what+' failed ('+r.status+'): '+JSON.stringify(r.data));return false;}return true;}
async function verifyA(id){const r=await api('/api/review/'+id+'/verify-answer',
{evidence:document.getElementById('ev').value});if(mustOk(r,'Verify answer'))loadDetail(id);}
async function verifyE(id){const r=await api('/api/review/'+id+'/verify-explanation',
{evidence:document.getElementById('ev').value});if(mustOk(r,'Verify explanation'))loadDetail(id);}
async function editQ(id){await api('/api/review/'+id+'/edit',
{question_text:document.getElementById('qt').value,
correct_answer:document.getElementById('ca').value,explanation:document.getElementById('ex').value,
options_json:JSON.parse(document.getElementById('opts').value)});
loadDetail(id);}
async function decide(id,action){const r=await api('/api/review/'+id,{status:action});if(mustOk(r,'Decision'))loadDetail(id);}"""
)