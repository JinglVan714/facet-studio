"""Local Run Detail + dashboard pages for product-v1 observability.

Served by ``preview_server``:
- ``/runs``                 -> recent runs + aggregate stats
- ``/runs/<run_id>``        -> Live / Trace / Stats
- ``/runs/<run_id>/stream`` -> SSE updates while a run is in progress

No external observability service and no database: JSONL/JSON files remain the
source of truth.
"""

from __future__ import annotations

RUN_DETAIL_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Run · __RUN_ID__</title>
<style>
:root{--bg:#f3f0e8;--paper:#fffdf9;--ink:#1c1a17;--muted:#6e675e;--line:#ded6c9;
--accent:#b5502f;--ok:#2f7d4a;--bad:#b23a2e;--wait:#a07a2c}
*{box-sizing:border-box}
body{margin:0;background:radial-gradient(1100px 520px at 50% -12%,#fffdf9 0%,var(--bg) 58%);
color:var(--ink);font-family:system-ui,"Segoe UI","Microsoft YaHei","PingFang SC",sans-serif;
line-height:1.65;-webkit-font-smoothing:antialiased}
.page{max-width:1160px;margin:0 auto;padding:28px 20px 80px}
.top{display:flex;justify-content:space-between;gap:18px;align-items:flex-start;flex-wrap:wrap}
.kicker{font-size:11px;letter-spacing:.18em;text-transform:uppercase;color:var(--accent);font-weight:750}
h1{font-family:"Noto Serif SC","Source Han Serif SC","Songti SC",SimSun,Georgia,serif;
font-size:30px;line-height:1.25;margin:6px 0 4px;letter-spacing:-.01em}
.sub{font-size:13px;color:var(--muted);word-break:break-all}
.badges{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}
.badge{font-size:12px;border:1px solid var(--line);background:var(--paper);border-radius:999px;padding:4px 10px;color:var(--muted)}
.live{display:inline-flex;align-items:center;gap:7px;font-size:12px;color:var(--muted)}
.live i{width:7px;height:7px;border-radius:50%;background:var(--ok);animation:pulse 1.5s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:10px;margin:18px 0 16px}
.stat{background:var(--paper);border:1px solid var(--line);border-radius:14px;padding:12px 14px}
.stat .label{font-size:10px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted)}
.stat .value{font-size:21px;font-weight:750;margin-top:3px;font-variant-numeric:tabular-nums}
.tabs{display:flex;gap:8px;flex-wrap:wrap;margin:0 0 14px}
.tab{font:inherit;font-size:13px;border:1px solid var(--line);background:var(--paper);color:var(--muted);
border-radius:999px;padding:7px 14px;cursor:pointer}
.tab.active{background:var(--ink);color:#fff;border-color:var(--ink)}
.section{display:none}.section.active{display:block}
.card{background:var(--paper);border:1px solid var(--line);border-radius:18px;padding:20px 22px;margin:0 0 16px;
box-shadow:0 10px 30px rgba(66,50,32,.04)}
h2{font-size:16px;margin:0 0 12px}
h2 .hint{font-size:12px;font-weight:400;color:var(--muted);margin-left:8px}
.muted{color:var(--muted);font-size:12.5px}
.stepper{display:grid;grid-template-columns:repeat(6,1fr);gap:8px;margin:4px 0 8px}
.step{padding:12px 10px;border:1px solid var(--line);border-radius:12px;background:#fff}
.step .name{font-size:13px;font-weight:700}.step .en{font-size:10px;color:var(--muted);letter-spacing:.05em}
.step .meta{font-size:11px;color:var(--muted);margin-top:4px}
.step.done{border-color:#cfe4d5;background:#f6fbf7}
.step.current{border-color:var(--accent);background:#f6e7df;box-shadow:0 0 0 2px rgba(181,80,47,.12)}
.step.failed{border-color:#edc9c2;background:#fbeeeb}
.dot{display:inline-block;width:7px;height:7px;border-radius:50%;margin-right:5px}
.dot.ok{background:var(--ok)}.dot.bad{background:var(--bad)}.dot.wait{background:var(--wait)}
.events{margin-top:12px;border-top:1px solid var(--line);padding-top:10px}
.event{display:flex;gap:10px;font-size:12px;padding:5px 0;border-bottom:1px dashed #eee8de}
.event:last-child{border-bottom:0}
.event time{color:var(--muted);font-variant-numeric:tabular-nums;min-width:150px}
.event b{font-weight:650}
.story{display:grid;gap:0}
.story-step{display:grid;grid-template-columns:30px 1fr;gap:12px;padding:12px 0;border-bottom:1px dashed #eee8de}
.story-step:last-child{border-bottom:0}
.story-num{width:24px;height:24px;border-radius:50%;display:grid;place-items:center;font-size:11px;font-weight:700;background:#f1ede4;color:var(--muted)}
.story-step.ok .story-num{background:#eef6f0;color:var(--ok)}
.story-step.wait .story-num{background:#f7f0df;color:#9a6b1f}
.story-step.bad .story-num{background:#fbeeeb;color:var(--bad)}
.story-title{font-size:14px;font-weight:700;display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.story-detail{font-size:13px;color:var(--text);margin-top:2px;line-height:1.6}
.story-meta{font-size:11px;color:var(--muted);margin-top:3px;font-variant-numeric:tabular-nums}
.plan-grid{display:grid;grid-template-columns:110px 1fr;gap:8px 12px;font-size:13px;line-height:1.6}
.plan-grid b{color:var(--muted);font-weight:600}
.result-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px;margin:4px 0 12px}
.result-stat{background:#fff;border:1px solid var(--line);border-radius:12px;padding:10px 12px}
.result-stat .k{font-size:11px;color:var(--muted)}
.result-stat .v{font-size:18px;font-weight:750;margin-top:2px;font-variant-numeric:tabular-nums}
.actions{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}
.actions a{display:inline-flex;align-items:center;border:1px solid var(--line);border-radius:999px;padding:5px 12px;font-size:12px;color:var(--ink);text-decoration:none;background:#fff}
.actions a.primary{background:var(--accent);border-color:var(--accent);color:#fff}
.muted-note{font-size:12px;color:var(--muted);line-height:1.6}
.trace-grid{display:grid;grid-template-columns:minmax(0,1.05fr) minmax(0,.95fr);gap:14px}
.tree{border:1px solid var(--line);border-radius:14px;background:#fff;padding:8px;min-height:220px}
.tree-row{border-radius:10px;padding:8px 10px;cursor:pointer;display:flex;gap:9px;align-items:flex-start}
.tree-row:hover{background:#f8f5ee}.tree-row.selected{background:#f6e7df}
.tree-row .indent{color:#c9c1b5;font-family:ui-monospace,Consolas,monospace;font-size:11px;white-space:pre;padding-top:2px}
.tree-row .body{min-width:0;flex:1}
.tree-row .title{font-size:13px;font-weight:650;display:flex;gap:6px;align-items:center;flex-wrap:wrap}
.tree-row .sub{font-size:11px;color:var(--muted);margin-top:1px;word-break:break-word}
.tree-row .meta{font-size:10.5px;color:var(--muted);margin-top:2px}
.kind{font-size:10px;border:1px solid var(--line);border-radius:999px;padding:1px 6px;color:var(--muted)}
.inspector{border:1px solid var(--line);border-radius:14px;background:#fff;padding:14px;min-height:220px}
.inspector h3{font-size:14px;margin:0 0 4px}.inspector .ins-sub{font-size:11px;color:var(--muted);margin-bottom:10px}
.kv{display:grid;grid-template-columns:96px 1fr;gap:4px 10px;font-size:12px}
.kv b{color:var(--muted);font-weight:600}
.dev{margin-top:12px;border-top:1px solid var(--line);padding-top:8px}
.dev summary{font-size:12px;color:var(--muted);cursor:pointer}
.inspector pre{background:#211d19;color:#f4f1e8;padding:10px 12px;border-radius:8px;overflow-x:auto;
font-size:11.5px;line-height:1.55;margin:8px 0 0}
.table-wrap{overflow-x:auto;border:1px solid var(--line);border-radius:12px;background:#fff}
table.data{width:100%;border-collapse:collapse;font-size:12.5px}
table.data th,table.data td{border-bottom:1px solid var(--line);padding:8px 10px;text-align:left;vertical-align:top}
table.data th{font-size:11px;color:var(--muted);background:#f6f2ea;white-space:nowrap}
table.data tr:last-child td{border-bottom:0}
code{background:#f1ede4;border-radius:4px;padding:1px 5px;font-size:.92em}
.empty{color:var(--muted);font-size:13px;padding:10px 0}
.pill{display:inline-block;font-size:11px;border-radius:999px;padding:1px 8px;border:1px solid var(--line)}
.pill.ok{color:var(--ok);background:#eef6f0;border-color:#cfe4d5}
.pill.bad{color:var(--bad);background:#fbeeeb;border-color:#edc9c2}
.pill.wait{color:var(--muted);background:#f4f0e6;border-color:var(--line)}
@media(max-width:820px){.page{padding:20px 12px 60px}.stepper{grid-template-columns:1fr 1fr}
.trace-grid{grid-template-columns:1fr}.top{flex-direction:column}}
</style>
</head>
<body>
<div class="page">
  <div class="top">
    <div>
      <div class="kicker">Facet Studio · Run</div>
      <h1>运行数据</h1>
      <div class="sub" id="run-id">__RUN_ID__</div>
      <div class="sub" id="run-title" style="margin-top:4px;font-size:14px;color:var(--text)"></div>
      <div class="badges" id="badges"></div>
    </div>
    <div class="live" id="live"><span>连接中…</span></div>
  </div>

  <div class="stats" id="stats"></div>
  <div class="sub" style="margin-top:8px">GROUNDING 是候选标记，不是幻觉率；机器检查通过不等于写作质量通过。</div>

  <div class="tabs">
    <button class="tab active" data-tab="overview">概览</button>
    <button class="tab" data-tab="live">Live 实时</button>
    <button class="tab" data-tab="trace">Trace 详情</button>
    <button class="tab" data-tab="stats">Stats 统计</button>
  </div>
  <div class="sub" style="margin-top:10px">概览 / Live 面向产品用户；Trace / Stats 面向开发与面试，含内部调用、机器检查和 grounding 候选，不是写作质量分。</div>

  <div class="section active" id="tab-overview">
    <div class="card">
      <h2>这次 run 做了什么</h2>
      <div class="story" id="story"></div>
    </div>
    <div class="card">
      <h2>关键判断</h2>
      <div id="plan-summary"></div>
    </div>
    <div class="card">
      <h2>结果</h2>
      <div id="result-summary"></div>
    </div>
  </div>

  <div class="section" id="tab-live">
    <div class="card">
      <h2>运行进度 <span class="hint">SSE 实时更新</span></h2>
      <div class="stepper" id="stepper"></div>
      <div class="muted" id="now-text"></div>
      <div class="events" id="events"></div>
    </div>
  </div>

  <div class="section" id="tab-trace">
    <div class="card">
      <h2>Trace 树 <span class="hint">点一条，右侧看详情</span></h2>
      <div class="trace-grid">
        <div class="tree" id="tree"></div>
        <div class="inspector" id="inspector"><div class="empty">选择左边一条记录。</div></div>
      </div>
    </div>
  </div>

  <div class="section" id="tab-stats">
    <div class="card">
      <h2>阶段统计</h2>
      <div class="table-wrap"><table class="data"><thead><tr><th>阶段</th><th>状态</th><th>耗时</th><th>tokens</th><th>错误</th></tr></thead><tbody id="stage-stats"></tbody></table></div>
    </div>
    <div class="card">
      <h2>模型统计</h2>
      <div class="table-wrap"><table class="data"><thead><tr><th>stage</th><th>model</th><th>calls</th><th>prompt</th><th>completion</th><th>total</th><th>平均延迟</th></tr></thead><tbody id="call-stats"></tbody></table></div>
    </div>
    <div class="card">
      <h2>运行配置</h2>
      <div class="table-wrap"><table class="data"><tbody id="config"></tbody></table></div>
    </div>
    <div class="card">
      <h2>机器检查 <span class="hint">P4 contract/trajectory；不是写作质量分</span></h2>
      <div class="table-wrap"><table class="data"><thead><tr><th>结果</th><th>检查</th><th>详情</th></tr></thead><tbody id="checks"></tbody></table></div>
    </div>
    <div class="card">
      <h2>Grounding 候选 <span class="hint">候选 ≠ 错；不是幻觉率</span></h2>
      <div class="table-wrap"><table class="data"><thead><tr><th>类型</th><th>候选值</th><th>上下文</th></tr></thead><tbody id="grounding"></tbody></table></div>
    </div>
  </div>
</div>

<script>
const RUN_ID = "__RUN_ID__";
const FINAL = new Set(["approved","typeset","partial","rejected","changes_requested","failed"]);
const STAGE_LABEL = {intake:"接入",plan:"规划",approval:"计划确认",write:"写作",typeset:"排版",review:"验收"};
const CALL_TITLE = {bundle_plan:"规划文章",visual_audit:"视觉审计",typeset:"排版"};
const DECISION_IMPACT = {plan:"决定这次写什么形态、角度和读者；不写正文。",approval:"决定是否开始写作；自动通过表示没有人工确认。",review:"决定产物能不能发布；自动通过仍不是用户验收。"};
function safeJson(text){
 try{return JSON.parse(String(text||""));}catch(e){
  const a=String(text||"").indexOf("{"),b=String(text||"").lastIndexOf("}");
  if(a>=0&&b>a){try{return JSON.parse(String(text).slice(a,b+1));}catch(e2){return null;}}
  return null;
 }
}
function auditFacts(c){
 const key=String(c.key||"");const file=(key.split(":").pop()||"").split(/[\\/]/).pop();
 const raw=safeJson(c.raw_response)||{};const reasons=[];
 if(raw.has_watermark)reasons.push("水印/平台界面");
 if(raw.has_person)reasons.push("人物出镜");
 if(["ui","other"].includes(String(raw.scene_type||"")))reasons.push("屏幕/其他");
 if(String(raw.quality||"")&&String(raw.quality)!=="clear")reasons.push("画面质量");
 if(raw.info_value===false)reasons.push("信息价值低");
 return {file:file||"候选帧",passed:reasons.length===0,reasons};
}
function callTitle(c,i){
 const stage=String(c.stage||"");
 if(stage==="visual_audit"){return `视觉审计 · ${auditFacts(c).file}`;}
 if(stage.startsWith("write_"))return "写作";
 if(stage.includes("_svg_spec")||stage==="svg_spec")return "生成图表";
 return CALL_TITLE[stage]||`模型调用 #${i+1}`;
}
function callHelp(c){
 const stage=String(c.stage||"");
 if(stage==="visual_audit"){
  const f=auditFacts(c);
  return f.passed?`${f.file} 通过：可以当关键帧`:`${f.file} 未通过：${f.reasons.join("、")}`;
 }
 const help=(trace.help&&trace.help.call)||{};
 return help[c.stage]||"一次模型调用，用来完成当前阶段。";
}
function decisionTitle(d){
 const stage=String(d.stage||"");
 return stage?`${stageLabel(stage)}判断`:"判断";
}
const STATUS_TEXT = {awaiting_plan_approval:"等待计划确认",awaiting_review:"等待验收",planned:"已规划",written:"已写完",
typeset:"已排版",partial:"部分完成",approved:"已验收",rejected:"已拒绝",changes_requested:"待修改",failed:"失败"};
const STATUS_DISPLAY = {auto_approved:"自动通过（未人工确认）",auto_accepted:"自动通过（未验收）",succeeded:"成功",complete:"完成",running:"进行中",queued:"排队中"};
const REVIEW_DISPLAY = {approved:"已验收",draft:"未验收",stale:"待重新验收",changes_requested:"待修改",rejected:"已拒绝"};
const DECISION_DISPLAY = {approved:"已通过",changes_requested:"要求修改",rejected:"已拒绝",auto_approved:"自动通过（未人工确认）",auto_accepted:"自动通过（未验收）"};
const DECIDED_BY_DISPLAY = {auto_approve:"工作流自动",user:"用户"};
function statusText(s){const key=String(s||"").toLowerCase();return STATUS_DISPLAY[key]||STATUS_TEXT[s]||s||"—";}
let trace=null, tab="live", selected=null, source=null, pollTimer=null;

function esc(v){return String(v==null?"":v).replace(/[&<>"']/g,s=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[s]));}
function num(v){const n=Number(v||0);return Number.isFinite(n)?n.toLocaleString():String(v??"");}
function cls(s){s=String(s||"").toLowerCase();
 if(["succeeded","approved","typeset","auto_approved","auto_accepted","complete"].includes(s))return "ok";
 if(["failed","error","rejected","partial"].includes(s))return "bad";return "wait";}
function dot(s){return `<span class="dot ${cls(s)}"></span>`;}
function fmt(ms){return Number(ms||0)?`${num(ms)} ms`:"—";}
function usage(u){return u&&u.total_tokens?`${num(u.total_tokens)} tokens`:"";}
function stageLabel(n){return STAGE_LABEL[n]||n||"—";}

function renderBadges(){
 const c=trace.context||{}, r=trace.review||{};
 const items=[["视频",c.video_id||"—"],["形态",trace.form_label||trace.form||"—"],["run",statusText(trace.status)],["验收",REVIEW_DISPLAY[r.decision]||r.decision||"未验收"]];
 document.getElementById("badges").innerHTML=items.map(([k,v])=>`<span class="badge">${esc(k)} ${esc(v)}</span>`).join("");
 const title=document.getElementById("run-title");
 if(title)title.textContent=c.central_idea||"";
}
function renderStats(){
 const u=trace.usage||{}, checks=trace.checks_total?`${trace.checks_passed||0}/${trace.checks_total}`:"—";
 const items=[["调用",trace.calls_known===false?"—":trace.calls_total||0],["TOKENS",trace.tokens_known===false?"—":num(u.total_tokens||0)],["延迟",fmt(trace.latency_ms)],
 ["工具",trace.tools_total||0],["检查",checks],["GROUNDING",(trace.grounding&&trace.grounding.flags||[]).length]];
 document.getElementById("stats").innerHTML=items.map(([k,v])=>`<div class="stat"><div class="label">${esc(k)}</div><div class="value">${esc(v)}</div></div>`).join("");
}
function renderStepper(){
 const stages=trace.stages||[];
 const current=stages.findIndex(s=>!["succeeded","approved","typeset","auto_approved","auto_accepted","complete"].includes(String(s.status||"").toLowerCase()));
 const idx=current===-1?stages.length-1:current;
 document.getElementById("stepper").innerHTML=stages.map((s,i)=>{
  const done=i<idx||(i===idx&&current===-1), cur=i===idx&&current!==-1, bad=cls(s.status)==="bad";
  return `<div class="step ${bad?"failed":done?"done":cur?"current":""}">
   <div class="name">${esc(stageLabel(s.name))}</div><div class="en">${esc(s.name)}</div>
   <div class="meta">${esc(statusText(s.status))}${s.duration_ms?` · ${fmt(s.duration_ms)}`:""}${usage(s.usage)?` · ${esc(usage(s.usage))}`:""}</div></div>`;
 }).join("");
 document.getElementById("now-text").textContent=STATUS_TEXT[trace.status]||trace.status||"";
}
function renderEvents(){
 if(trace.final){document.getElementById("events").innerHTML="";return;}
 const events=(trace.events||[]).slice(-20).reverse();
 const heading='<div class="muted" style="margin:14px 0 6px">状态变更（最近 20 条）</div>';
 document.getElementById("events").innerHTML=events.length?heading+events.map(e=>{
  const t=e.at||e.created_at||""; const node=stageLabel(e.node)||e.type||"事件";
  const detail=e.type==="interrupt"?"等待人工确认":"状态更新";
  return `<div class="event"><time>${esc(t)}</time><b>${esc(node)}</b><span class="muted">${esc(detail)}</span></div>`;
 }).join(""):`<div class="empty">还没有事件。</div>`;
}
function renderStageStats(){
 const stages=trace.stages||[];
 document.getElementById("stage-stats").innerHTML=stages.length?stages.map(s=>
  `<tr><td>${esc(stageLabel(s.name))} <span class="muted">${esc(s.name)}</span></td><td>${esc(statusText(s.status))}</td><td>${fmt(s.duration_ms)}</td><td>${num((s.usage||{}).total_tokens||0)}</td><td>${esc(s.error||"—")}</td></tr>`
 ).join(""):`<tr><td colspan="5" class="empty">没有 stage。</td></tr>`;
}
function renderCallStats(){
 const calls=trace.llm_calls||[], groups={};
 calls.forEach(c=>{const k=`${c.stage||""}|${c.model||""}`;const g=groups[k]||(groups[k]={stage:c.stage,model:c.model,calls:0,prompt:0,completion:0,total:0,lat:0});
  g.calls++;g.prompt+=Number((c.usage||{}).prompt_tokens||0);g.completion+=Number((c.usage||{}).completion_tokens||0);
  g.total+=Number((c.usage||{}).total_tokens||0);g.lat+=Number(c.latency_ms||0);});
 const rows=Object.values(groups);
 document.getElementById("call-stats").innerHTML=rows.length?rows.map(g=>
  `<tr><td><code>${esc(g.stage)}</code></td><td>${esc(g.model)}</td><td>${g.calls}</td><td>${num(g.prompt)}</td><td>${num(g.completion)}</td><td>${num(g.total)}</td><td>${fmt(Math.round(g.lat/g.calls))}</td></tr>`
 ).join(""):`<tr><td colspan="7" class="empty">没有模型调用。</td></tr>`;
}
function renderConfig(){
 const c=trace.context||{};
 const src=[c.video_id,c.source_title].filter(Boolean); const source=src.length>1&&src[0]===src[1]?src[0]:(src.join(" · ")||"—");
 const rows=[["来源",source],["形态",trace.form_label||trace.form||"—"],["请求",c.request||"—"],["模型",c.model||"—"],
 ["temperature",c.temperature==null?"—":c.temperature],["max_tokens",c.max_tokens==null?"—":num(c.max_tokens)],
 ["skill 版本",[c.skill_id,c.skill_version].filter(Boolean).join(" ")||"—"],["内容稿",`${num(c.content_chars||0)} 字 · ${num(c.figure_count||0)} 图`],["关键帧",`${num(c.keyframes_referenced ?? c.figures_referenced ?? 0)} 图`],["SVG",`${num(c.svg_count||0)} 个`],
 ["视觉审计",(()=>{const va=c.visual_audit||{};if(va.error)return `出错：${va.error}`;return `${num(va.candidate_count||0)} 候选 / ${num(va.approved_count||0)} 通过`;})()],
 ["未通过原因",Object.entries((c.visual_audit||{}).reasons||{}).map(([k,v])=>`${k} ${v}`).join(" · ")||"—"],
 ["中心判断",c.central_idea||"—"]];
 document.getElementById("config").innerHTML=rows.map(([k,v])=>`<tr><th>${esc(k)}</th><td>${esc(v)}</td></tr>`).join("");
}
function callStageMatch(callStage,stageName){const s=String(callStage||"");
 if(stageName==="plan")return s==="bundle_plan"||s.startsWith("visual_audit");
 if(stageName==="write")return s.startsWith("write_")||s.includes("_svg_spec");
 if(stageName==="typeset")return s.startsWith("typeset");return false;}
function nodes(){
 const out=[],stages=trace.stages||[],calls=trace.llm_calls||[],decisions=trace.decisions||[];
 out.push({id:"run",kind:"run",title:"Run",sub:trace.run_id,status:trace.status,body:trace});
 stages.forEach(st=>{const sid=`stage:${st.name}`;
  out.push({id:sid,kind:"stage",title:stageLabel(st.name),sub:st.name,status:st.status,usage:st.usage,duration:st.duration_ms,body:st,parent:"run"});
  calls.forEach((c,i)=>{if(callStageMatch(c.stage,st.name))out.push({id:`llm:${i}`,kind:"llm",title:callTitle(c,i),sub:callHelp(c),status:c.status,usage:c.usage,duration:c.latency_ms,body:c,parent:sid});});
  decisions.forEach((d,i)=>{if(d.stage===st.name)out.push({id:`dec:${i}`,kind:"decision",title:decisionTitle(d),sub:d.question,status:d.selected,body:d,parent:sid});});
 });
 calls.forEach((c,i)=>{if(!stages.some(s=>callStageMatch(c.stage,s.name)))out.push({id:`llm:${i}`,kind:"llm",title:callTitle(c,i),sub:callHelp(c),status:c.status,usage:c.usage,duration:c.latency_ms,body:c,parent:"run"});});
 decisions.forEach((d,i)=>{if(!stages.some(s=>d.stage===s.name))out.push({id:`dec:${i}`,kind:"decision",title:decisionTitle(d),sub:d.question,status:d.selected,body:d,parent:"run"});});
 return out;
}
function renderTree(){
 const all=nodes(),byParent={}; all.forEach(n=>{(byParent[n.parent||"root"]=byParent[n.parent||"root"]||[]).push(n);});
 const order=[],seen=new Set();
 function walk(parent,depth){for(const n of byParent[parent]||[]){if(seen.has(n.id))continue;seen.add(n.id);order.push({n,depth});walk(n.id,depth+1);}}
 walk("root",0);walk("run",0);
 const runIdx=order.findIndex(x=>x.n.id==="run"); if(runIdx>0)order.unshift(order.splice(runIdx,1)[0]);
 const html=order.map(({n,depth})=>{
  const indent=depth?("│  ".repeat(Math.max(0,depth-1))+"├─ "):"";
  const kind={run:"run",stage:"阶段",llm:"模型调用",decision:"判断"}[n.kind]||n.kind;
  return `<div class="tree-row ${selected===n.id?"selected":""}" data-id="${esc(n.id)}">
   <div class="indent">${esc(indent)}</div><div class="body">
    <div class="title">${dot(n.status)}${esc(n.title)}<span class="kind">${esc(kind)}</span></div>
    <div class="sub">${esc(n.sub||"")}</div>
    <div class="meta">${esc(n.kind==="decision"?(DECISION_DISPLAY[n.status]||n.status||""):statusText(n.status))}${n.duration?` · ${fmt(n.duration)}`:""}${usage(n.usage)?` · ${esc(usage(n.usage))}`:""}</div>
   </div></div>`;
 }).join("");
 const tree=document.getElementById("tree"); tree.innerHTML=html||`<div class="empty">还没有 trace。</div>`;
 tree.querySelectorAll(".tree-row").forEach(row=>row.addEventListener("click",()=>{selected=row.dataset.id;renderTree();}));
 renderInspector(all);
}
function renderInspector(all){
 const node=(all||nodes()).find(n=>n.id===selected),box=document.getElementById("inspector");
 if(!node){box.innerHTML=`<div class="empty">选择左边一条记录。</div>`;return;}
 const b=node.body||{},k=node.kind;
 const stageHelp=(trace.help&&trace.help.stage)||{};
 let kv="";
 if(k==="run")kv=`<div class="kv"><b>总览</b><span>这次 run 的完整执行记录</span><b>状态</b><span>${esc(statusText(b.status))}</span><b>中心判断</b><span>${esc((trace.context||{}).central_idea||"—")}</span></div>`;
 else if(k==="stage")kv=`<div class="kv"><b>作用</b><span>${esc(stageHelp[b.name]||"这次 run 的一个执行阶段")}</span><b>状态</b><span>${esc(statusText(b.status))}</span><b>耗时</b><span>${fmt(b.duration_ms)}</span><b>tokens</b><span>${esc(usage(b.usage)||"—")}</span></div>`;
 else if(k==="llm")kv=`<div class="kv"><b>作用</b><span>${esc(callHelp(b))}</span><b>模型</b><span>${esc(b.model||"—")}</span><b>状态</b><span>${esc(statusText(b.status))}</span><b>tokens</b><span>${esc(usage(b.usage)||"—")}</span><b>延迟</b><span>${fmt(b.latency_ms)}</span><b>finish</b><span>${esc(b.finish_reason||"—")}</span></div>`;
 else if(k==="decision")kv=`<div class="kv"><b>问题</b><span>${esc(b.question||"")}</span><b>选择</b><span>${esc(DECISION_DISPLAY[b.selected]||b.selected||"")}</span><b>由谁</b><span>${esc(DECIDED_BY_DISPLAY[b.decided_by]||b.decided_by||"")}</span><b>影响</b><span>${esc(DECISION_IMPACT[b.stage]||"影响下一步执行。")}</span></div>`;
 const payload=JSON.stringify(b,null,2);
 box.innerHTML=`<h3>${esc(node.title)}</h3><div class="ins-sub">${esc(node.sub||"")}</div>${kv}
  <details class="dev"><summary>开发者详情（原始字段/ID）</summary><pre>${esc(payload.length>5000?payload.slice(0,5000)+"…":payload)}</pre></details>`;
}
function checkDisplay(c){
 const id=String(c.check_id||""),d=String(c.detail||"");
 if(id==="manual_acceptance"&&/review=(missing|draft|stale)/.test(d))return ["未验收","wait"];
 if(id==="trajectory_hitl"&&/auto_accepted/.test(d))return ["自动通过","wait"];
 return [c.passed?"通过":"未通过",c.passed?"ok":"bad"];
}
function renderChecks(){
 const checks=trace.checks||[];
 document.getElementById("checks").innerHTML=checks.length?checks.map(c=>{
  const [label,status]=checkDisplay(c);
  return `<tr><td><span class="pill ${status}">${label}</span></td><td><code>${esc(c.check_id)}</code></td><td>${esc(c.detail)}</td></tr>`;
 }).join(""):`<tr><td colspan="3" class="empty">还没有机器检查。</td></tr>`;
 const flags=(trace.grounding&&trace.grounding.flags)||[];
 document.getElementById("grounding").innerHTML=flags.length?flags.slice(0,50).map(f=>
  `<tr><td><code>${esc(f.kind)}</code></td><td>${esc(f.value)}</td><td>${esc(f.context)}</td></tr>`
 ).join(""):`<tr><td colspan="3" class="empty">没有 grounding 候选。</td></tr>`;
}
const STORY_STATUS={succeeded:"完成",typeset:"完成",auto_approved:"自动通过",auto_accepted:"自动通过",awaiting:"等待",awaiting_review:"等待验收",no_frames:"0 通过",passed:"通过",failed:"失败"};
function storyClass(s){s=String(s||"").toLowerCase();if(s==="failed")return "bad";if(["awaiting","awaiting_review","no_frames","auto_accepted","auto_approved"].includes(s))return "wait";return "ok";}
function renderStory(){
 const items=trace.story||[];
 const box=document.getElementById("story");
 box.innerHTML=items.length?items.map((item,i)=>{
  const cls=storyClass(item.status);
  const meta=[item.duration_ms?fmt(item.duration_ms):"",item.tokens?`${num(item.tokens)} tokens`:""].filter(Boolean).join(" · ");
  return `<div class="story-step ${cls}"><div class="story-num">${i+1}</div><div>
   <div class="story-title">${esc(item.step||"步骤")}<span class="pill ${cls}">${esc(STORY_STATUS[item.status]||item.status||"")}</span></div>
   <div class="story-detail">${esc(item.detail||"")}</div>
   ${meta?`<div class="story-meta">${esc(meta)}</div>`:""}
  </div></div>`;
 }).join(""):`<div class="empty">还在启动，暂无步骤。</div>`;
}
function renderPlanSummary(){
 const c=trace.context||{}, va=c.visual_audit||{};
 const rows=[
  ["中心判断",c.central_idea||"—"],
  ["角度",c.plan_angle||"—"],
  ["读者收获",c.plan_reader||"—"],
  ["用户要求",c.request||"—"],
  ["视觉审计",(()=>{if(va.error)return `出错：${va.error}`;if(!va.candidate_count)return "未发现候选关键帧";return `${num(va.candidate_count)} 候选 / ${num(va.approved_count||0)} 通过`;})()],
  ["未通过原因",Object.entries(va.reasons||{}).map(([k,v])=>`${k} ${v}`).join(" · ")||"—"],
 ];
 document.getElementById("plan-summary").innerHTML=`<div class="plan-grid">${rows.map(([k,v])=>`<b>${esc(k)}</b><span>${esc(v)}</span>`).join("")}</div>`;
}
function renderResultSummary(){
 const c=trace.context||{}, form=trace.form||c.form||"";
 const visual=form==="xiaohongshu_note"?["卡片",`${num(c.card_count||0)} 张`]:["关键帧",`${num(c.keyframes_referenced ?? c.figures_referenced ?? 0)} 图`];
 const stats=[
  ["正文",`${num(c.output_chars||0)} 字`],
  visual,
  ["SVG",`${num(c.svg_count||0)} 个`],
  ["状态",STATUS_TEXT[trace.status]||trace.status||"—"],
  ["验收",trace.review&&trace.review.decision?REVIEW_DISPLAY[trace.review.decision]||trace.review.decision:"未验收"],
 ];
 const links=[];
 const artifacts=trace.artifacts||{};
 const add=(label,path,primary)=>{if(!path)return;const href=/^https?:\\/\\//.test(String(path))?String(path):`/runs/${encodeURIComponent(trace.run_id)}/${String(path).replace(/^\\//,"")}`;links.push(`<a class="${primary?"primary":""}" href="${href}" target="_blank" rel="noopener">${label}</a>`);};
 if(artifacts.preview_url)add("阅读预览",artifacts.preview_url,true);
 if(artifacts.wechat_url)add("公众号预览",artifacts.wechat_url,false);
 if(form==="long_article")add("PDF",`${form}/article.pdf`,false);
 if(artifacts.trace_url)add("Trace 导出",artifacts.trace_url,false);
 document.getElementById("result-summary").innerHTML=`<div class="result-grid">${stats.map(([k,v])=>`<div class="result-stat"><div class="k">${esc(k)}</div><div class="v">${esc(v)}</div></div>`).join("")}</div>${links.length?`<div class="actions">${links.join("")}</div>`:""}<div class="muted-note" style="margin-top:10px">验收在聊天里回复“通过 / 要改 / 不要了”；这里只读，不会自动发布。</div>`;
}
function render(){
 if(!trace)return;
 renderBadges();renderStats();renderStepper();renderEvents();renderStageStats();renderCallStats();renderConfig();renderTree();renderChecks();renderStory();renderPlanSummary();renderResultSummary();
 document.querySelectorAll(".tab").forEach(b=>b.classList.toggle("active",b.dataset.tab===tab));
 document.querySelectorAll(".section").forEach(s=>s.classList.toggle("active",s.id===`tab-${tab}`));
 const done=trace.final||FINAL.has(String(trace.status||""));
 document.getElementById("live").innerHTML=done?`<span>已结束 · 只读</span>`:`<i></i><span>运行中 · SSE</span>`;
}
function applyTrace(t){trace=t;render();if(trace.final||FINAL.has(String(trace.status||""))){if(source){source.close();source=null;}if(pollTimer){clearTimeout(pollTimer);pollTimer=null;}}}
async function fetchTrace(){
 try{const r=await fetch(`/runs/${encodeURIComponent(RUN_ID)}/api/trace`,{cache:"no-store"});if(!r.ok)throw new Error(`HTTP ${r.status}`);applyTrace(await r.json());return true;}
 catch(e){document.getElementById("live").innerHTML=`<span style="color:var(--bad)">读取失败：${esc(e.message)}</span>`;return false;}
}
function startSSE(){
 if(!window.EventSource)return poll();
 source=new EventSource(`/runs/${encodeURIComponent(RUN_ID)}/stream`);
 source.onmessage=e=>{try{applyTrace(JSON.parse(e.data));}catch(_){}};
 source.onerror=()=>{if(source){source.close();source=null;}poll();};
}
function poll(){
 if(trace&&(trace.final||FINAL.has(String(trace.status||""))))return;
 fetchTrace().then(ok=>{if(ok&&!(trace.final||FINAL.has(String(trace.status||""))))pollTimer=setTimeout(poll,1500);});
}
document.querySelectorAll(".tab").forEach(b=>b.addEventListener("click",()=>{tab=b.dataset.tab;render();}));
fetchTrace().then(()=>{if(!(trace&&(trace.final||FINAL.has(String(trace.status||"")))))startSSE();});
</script>
</body></html>
"""


DASHBOARD_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Runs · Facet Studio</title>
<style>
:root{--bg:#f3f0e8;--paper:#fffdf9;--ink:#1c1a17;--muted:#6e675e;--line:#ded6c9;--accent:#b5502f;--ok:#2f7d4a;--bad:#b23a2e}
*{box-sizing:border-box}
body{margin:0;background:radial-gradient(1100px 500px at 50% -12%,#fffdf9 0%,var(--bg) 58%);
color:var(--ink);font-family:system-ui,"Segoe UI","Microsoft YaHei","PingFang SC",sans-serif;line-height:1.6}
.page{max-width:1160px;margin:0 auto;padding:30px 20px 80px}
.kicker{font-size:11px;letter-spacing:.18em;text-transform:uppercase;color:var(--accent);font-weight:750}
h1{font-family:"Noto Serif SC","Source Han Serif SC","Songti SC",SimSun,Georgia,serif;font-size:30px;margin:6px 0 4px}
.sub{font-size:13px;color:var(--muted)}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px;margin:18px 0}
.stat{background:var(--paper);border:1px solid var(--line);border-radius:14px;padding:12px 14px}
.stat .label{font-size:10px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted)}
.stat .value{font-size:21px;font-weight:750;margin-top:3px;font-variant-numeric:tabular-nums}
.card{background:var(--paper);border:1px solid var(--line);border-radius:18px;padding:18px 20px;margin:0 0 16px;
box-shadow:0 10px 30px rgba(66,50,32,.04)}
h2{font-size:16px;margin:0 0 12px}
.table-wrap{overflow-x:auto;border:1px solid var(--line);border-radius:12px;background:#fff}
table{width:100%;border-collapse:collapse;font-size:12.5px}
th,td{border-bottom:1px solid var(--line);padding:8px 10px;text-align:left;vertical-align:top}
th{font-size:11px;color:var(--muted);background:#f6f2ea;white-space:nowrap}
tr:last-child td{border-bottom:0}
tr:hover td{background:#faf8f3;cursor:pointer}
.title-cell{max-width:320px;white-space:normal;line-height:1.45}
code{background:#f1ede4;border-radius:4px;padding:1px 5px;font-size:.92em}
.ok{color:var(--ok)}.bad{color:var(--bad)}.muted{color:var(--muted)}
@media(max-width:760px){.page{padding:20px 12px 60px}}
</style>
</head>
<body>
<div class="page">
  <div class="kicker">Facet Studio · Runs</div>
  <h1>运行看板</h1>
  <div class="sub">开发/面试视图：最近 runs + 聚合统计；旧 run 缺 llm_calls.jsonl 时 calls 显示 —，不按 0 计；grounding 是候选计数，不是幻觉率。</div>
  <div class="stats" id="stats"></div>
  <div class="card">
    <h2>最近 runs</h2>
    <div class="table-wrap"><table><thead><tr><th>run</th><th>标题/任务</th><th>视频</th><th>形态</th><th>状态</th><th>验收</th><th>calls</th><th>tokens</th><th>延迟</th><th>检查</th><th>grounding</th></tr></thead><tbody id="rows"></tbody></table></div>
  </div>
</div>
<script>
function esc(v){return String(v==null?"":v).replace(/[&<>"']/g,s=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[s]));}
function num(v){const n=Number(v||0);return Number.isFinite(n)?n.toLocaleString():String(v??"");}
function fmt(ms){return Number(ms||0)?`${num(ms)} ms`:"—";}
const REVIEW_DISPLAY={approved:"已验收",draft:"未验收",stale:"待重新验收",changes_requested:"待修改",rejected:"已拒绝"};
const STATUS_DISPLAY={typeset:"已排版",approved:"已验收",partial:"部分完成",failed:"失败",planned:"已规划",written:"已写完",awaiting_plan_approval:"等待计划确认",awaiting_review:"等待验收"};
async function load(){
 try{
  const r=await fetch("/api/runs",{cache:"no-store"}); const data=await r.json(); const s=data.summary||{};
  const stats=[["runs",s.runs||0],["calls",s.calls_total||0],["tokens",num(s.tokens_total||0)],
   ["p50",fmt(s.latency_p50_ms)],["p95",fmt(s.latency_p95_ms)],["error",`${Math.round((s.error_rate||0)*100)}%`],
   ["checks",s.checks_total?`${s.checks_passed||0}/${s.checks_total}`:"—"],["grounding",s.grounding_flags||0]];
  document.getElementById("stats").innerHTML=stats.map(([k,v])=>`<div class="stat"><div class="label">${esc(k)}</div><div class="value">${esc(v)}</div></div>`).join("");
  document.getElementById("rows").innerHTML=(data.runs||[]).map(x=>{
   const cls=x.status==="approved"||x.status==="typeset"?"ok":x.status==="failed"||x.status==="partial"?"bad":"";
   return `<tr onclick="location.href='/runs/${encodeURIComponent(x.run_id)}'">
    <td><code>${esc(x.run_id)}</code></td><td class="title-cell">${esc(x.title||"")}</td><td>${esc(x.video_id||"")}</td><td>${esc(x.form_label||x.form||"")}</td>
    <td class="${cls}">${esc(STATUS_DISPLAY[x.status]||x.status||"")}</td><td>${esc(REVIEW_DISPLAY[x.review]||x.review||"未验收")}</td><td>${x.calls_known===false?"—":num(x.calls_total)}</td>
    <td>${x.tokens_known===false?"—":num(x.tokens)}</td><td>${fmt(x.latency_ms)}</td><td>${x.checks_total?`${x.checks_passed}/${x.checks_total}`:"—"}</td><td>${num(x.grounding_flags)}</td>
   </tr>`;
  }).join("")||`<tr><td colspan="11" class="muted">没有 runs。</td></tr>`;
 }catch(e){document.getElementById("rows").innerHTML=`<tr><td colspan="11" class="muted">读取失败：${esc(e.message)}</td></tr>`;}
}
load(); setInterval(load,5000);
</script>
</body></html>
"""
