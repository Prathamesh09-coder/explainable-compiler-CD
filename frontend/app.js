/* ============================= API base auto-detection =============================
   If this page is served BY the backend (uvicorn backend.main:app), relative fetches
   just work. If you instead serve this frontend folder separately (e.g. a plain static
   server on another port), we fall back to http://localhost:8000. Override by setting
   window.EXPLAINABLE_COMPILER_API before this script runs, if your backend runs elsewhere. */
let API_BASE = window.EXPLAINABLE_COMPILER_API || '';
async function detectApiBase(){
  const candidates = [API_BASE, 'http://localhost:8000', 'http://127.0.0.1:8000'];
  for(const base of candidates){
    try{
      const r = await fetch(base + '/api/health');
      if(r.ok){ API_BASE = base; document.getElementById('apiStatus').textContent = 'backend connected'; return; }
    }catch(e){ /* try next */ }
  }
  document.getElementById('apiStatus').textContent = 'backend not reachable — start it (see README)';
}

/* ============================= language config (UI-side only; analysis is server-side) ============================= */
const LANGS = {
  c:   {name:'C', sample:`#include <stdio.h>\n\nint main() {\n    int a = 10;\n    int b = 20;\n    int sum = a + b;\n    printf("%d", sum);\n    return 0;\n}`,
        pipeline:['preprocess','lexical','syntax','expressions','semantic','symtab','ir','optimize','target','execute','summary']},
  cpp: {name:'C++', sample:`#include <iostream>\nusing namespace std;\n\nint main() {\n    int a = 10;\n    int b = 20;\n    int sum = a + b;\n    cout << sum;\n    return 0;\n}`,
        pipeline:['preprocess','lexical','syntax','expressions','semantic','symtab','ir','optimize','target','execute','summary']},
  java:{name:'Java', sample:`public class Main {\n    public static void main(String[] args) {\n        int a = 10;\n        int b = 20;\n        int sum = a + b;\n        System.out.println(sum);\n    }\n}`,
        pipeline:['lexical','syntax','expressions','semantic','symtab','ir','optimize','target','execute','summary']},
  python:{name:'Python', sample:`a = 10\nb = 20\nsum = a + b\nprint(sum)`,
        pipeline:['lexical','syntax','expressions','semantic','symtab','ir','optimize','target','execute','summary']}
};
const EXAMPLES = {
  c:[['Hello / sum (default)',LANGS.c.sample],
     ['If-else',`#include <stdio.h>\nint main() {\n    int a = 10;\n    int b = 20;\n    if (a < b) {\n        printf("b is bigger");\n    } else {\n        printf("a is bigger");\n    }\n    return 0;\n}`],
     ['While loop',`#include <stdio.h>\nint main() {\n    int i = 0;\n    int total = 0;\n    while (i < 5) {\n        total = total + i;\n        i = i + 1;\n    }\n    printf("%d", total);\n    return 0;\n}`],
     ['Syntax error demo',`#include <stdio.h>\nint main() {\n    int a = ;\n    return 0;\n}`],
     ['Type error demo',`#include <stdio.h>\nint main() {\n    int a;\n    a = "hello";\n    return 0;\n}`]],
  cpp:[['Hello / sum (default)',LANGS.cpp.sample],
     ['If-else',`#include <iostream>\nusing namespace std;\nint main() {\n    int a = 10;\n    int b = 20;\n    if (a < b) { cout << 1; } else { cout << 0; }\n    return 0;\n}`]],
  java:[['Hello / sum (default)',LANGS.java.sample],
     ['If-else',`public class Main {\n    public static void main(String[] args) {\n        int a = 10;\n        int b = 20;\n        if (a < b) { System.out.println(1); } else { System.out.println(0); }\n    }\n}`]],
  python:[['Hello / sum (default)',LANGS.python.sample],
     ['If-else',`a = 10\nb = 20\nif a < b:\n    print(1)\nelse:\n    print(0)`],
     ['While loop',`i = 0\ntotal = 0\nwhile i < 5:\n    total = total + i\n    i = i + 1\nprint(total)`],
     ['Type note (dynamic typing)',`a = 5\na = "hello"\nprint(a)`]]
};
const PHASE_META = {
  preprocess:{label:'Preprocessing'}, lexical:{label:'Lexical Analysis'}, syntax:{label:'Syntax Analysis'},
  expressions:{label:'Expression Trees & Postfix'},
  semantic:{label:'Semantic Analysis'}, symtab:{label:'Symbol Table'}, ir:{label:'Intermediate Code'},
  optimize:{label:'Optimization'}, target:{label:'Target Code'}, execute:{label:'Execution'}, summary:{label:'Summary'}
};

/* ============================= AST -> SVG TREE (client-side rendering of a tree the server computed) ============================= */
function exprLabel(e){
  if(e.type==='Num') return String(e.value);
  if(e.type==='Str') return e.value;
  if(e.type==='Id') return e.name;
  if(e.type==='Input') return 'input()';
  if(e.type==='BinOp') return e.op;
  if(e.type==='Compare') return e.op;
  return '?';
}
function buildLayout(e){
  let leafX=0; const NODEW=64, LEVELH=64;
  function layout(n, depth){
    if(!n.left && !n.right){ const x=leafX*NODEW; leafX++; return {n, x, y:depth*LEVELH, kids:[]}; }
    const l = n.left? layout(n.left, depth+1): null;
    const r = n.right? layout(n.right, depth+1): null;
    const xs=[l,r].filter(Boolean).map(k=>k.x);
    const x = xs.length? (xs.reduce((a,b)=>a+b,0)/xs.length) : (leafX++)*NODEW;
    return {n, x, y:depth*LEVELH, kids:[l,r].filter(Boolean)};
  }
  return layout(e,0);
}
function renderTree(root){
  let maxX=0,maxY=0; const nodes=[];
  (function collect(k){ maxX=Math.max(maxX,k.x); maxY=Math.max(maxY,k.y); nodes.push(k); k.kids.forEach(collect); })(root);
  const W=maxX+120, H=maxY+70;
  let svg=`<svg viewBox="0 0 ${W} ${H}" width="${Math.min(W+40,760)}" height="${H+40}">`;
  function edges(k){ k.kids.forEach(c=>{ svg+=`<line x1="${k.x+60}" y1="${k.y+30}" x2="${c.x+60}" y2="${c.y+30}" stroke="#556074" stroke-width="1.5"/>`; edges(c); }); }
  edges(root);
  nodes.forEach((k,i)=>{
    const label = exprLabel(k.n);
    const isOp = k.n.type==='BinOp'||k.n.type==='Compare';
    svg+=`<g class="astnode" data-idx="${i}" style="cursor:pointer">
      <circle cx="${k.x+60}" cy="${k.y+30}" r="20" fill="${isOp?'#2c4a63':'#2c4a37'}" stroke="#7fb3e0" stroke-width="1.2"/>
      <text x="${k.x+60}" y="${k.y+35}" text-anchor="middle" font-family="JetBrains Mono, monospace" font-size="13" fill="#e9e7de">${label}</text>
    </g>`;
  });
  svg+='</svg>';
  return {svg, nodes};
}
/* mountTree: generic — pass container/info element ids so multiple trees can
   be mounted on one page (one per expression found in the program). */
function mountTree(exprNode, svgElId, infoElId){
  const layout = buildLayout(exprNode);
  const {svg, nodes} = renderTree(layout);
  const el = document.getElementById(svgElId); if(!el) return;
  el.innerHTML = svg;
  el.querySelectorAll('.astnode').forEach(g=>{
    g.addEventListener('click', ()=>{
      const idx=+g.dataset.idx; const n = nodes[idx].n;
      const info = document.getElementById(infoElId); if(!info) return;
      let meaning='';
      if(n.type==='BinOp'){ meaning = `Compute the value of the left side, the value of the right side, then apply '${n.op}' to combine them.`; }
      else if(n.type==='Compare'){ meaning = `Compare the left and right sides using '${n.op}', producing true or false.`; }
      else if(n.type==='Id'){ meaning = `Look up the current value of variable '${n.name}'.`; }
      else if(n.type==='Num'){ meaning = `A literal numeric value.`; }
      else if(n.type==='Input'){ meaning = `Read a value from program input at run time.`; }
      info.innerHTML = `<b>Node:</b> ${exprLabel(n)}<br><b>Children:</b> ${[n.left,n.right].filter(Boolean).map(exprLabel).join(', ')||'none (leaf)'}<br><b>Compiler meaning:</b> ${meaning}`;
    });
  });
}

/* ============================= postfix evaluation stack visualization ============================= */
function postfixStackHTML(postfix){
  const tokens = postfix.split(' ');
  const OPS = new Set(['+','-','*','/','==','!=','<','>','<=','>=']);
  let stack = [];
  const frames = [];
  tokens.forEach(tok=>{
    if(OPS.has(tok)){
      const b = stack.pop(), a = stack.pop();
      const combined = `(${a} ${tok} ${b})`;
      stack = [...stack, combined];
      frames.push({tok, action:`pop '${b}' and '${a}', push '${combined}'`, stack:[...stack]});
    } else {
      stack = [...stack, tok];
      frames.push({tok, action:`push '${tok}'`, stack:[...stack]});
    }
  });
  return `<div class="stackViz">` + frames.map((f,i)=>`
    <div class="stackStep">
      <div class="stackStepHead"><span class="badge">${i+1}</span> read <code>${esc(f.tok)}</code> → ${esc(f.action)}</div>
      <div class="stackRow">${f.stack.map(s=>`<div class="stackCell">${esc(s)}</div>`).join('')}</div>
    </div>`).join('') + `</div>`;
}

/* ============================= simple inline bar-chart (before/after) ============================= */
function barChartHTML(items){
  const max = Math.max(1, ...items.map(i=>i.value));
  return `<div class="barChart">` + items.map(i=>`
    <div class="barRow">
      <div class="barLabel">${esc(i.label)}</div>
      <div class="barTrack"><div class="barFill" style="width:${Math.max(4,(i.value/max)*100)}%">${i.value}</div></div>
    </div>`).join('') + `</div>`;
}

/* ============================= token highlighting helpers ============================= */
function tokCategory(t){
  if(t.error) return 'lexerr';
  if(t.cat==='Keyword') return 'KEYWORD';
  if(t.cat==='Identifier') return 'IDENTIFIER';
  if(t.cat==='Operator') return 'OPERATOR';
  if(t.cat==='Literal') return 'LITERAL';
  if(t.cat==='String') return 'STRING';
  if(t.cat==='Comment') return 'COMMENT';
  return 'SEPARATOR';
}
function esc(s){ return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

/* ============================= tiny Markdown renderer (headers, bold, inline/block code, lists) ============================= */
function mdToHtml(md){
  const blocks = esc(md).split(/```([\s\S]*?)```/g);
  let out = '';
  blocks.forEach((chunk, i)=>{
    if(i % 2 === 1){ out += `<pre><code>${chunk}</code></pre>`; return; }
    let html = chunk
      .replace(/^### (.*)$/gm, '<h4>$1</h4>')
      .replace(/^## (.*)$/gm, '<h3>$1</h3>')
      .replace(/^# (.*)$/gm, '<h2>$1</h2>')
      .replace(/\*\*(.+?)\*\*/g, '<b>$1</b>')
      .replace(/`([^`]+)`/g, '<code>$1</code>');
    const lines = html.split('\n'); let buf=''; let inList=false;
    lines.forEach(line=>{
      const m = line.match(/^\s*[-*]\s+(.*)$/);
      if(m){ if(!inList){ buf+='<ul>'; inList=true; } buf+=`<li>${m[1]}</li>`; }
      else { if(inList){ buf+='</ul>'; inList=false; } buf += line.trim()===''?'':`<p>${line}</p>`; }
    });
    if(inList) buf+='</ul>';
    out += buf;
  });
  return out;
}
function highlightedSource(src, tokens){
  const lines = src.split('\n'); const byLine={};
  tokens.forEach(t=>{ (byLine[t.line]=byLine[t.line]||[]).push(t); });
  return lines.map((line,i)=>{
    const lt=byLine[i+1]; if(!lt) return esc(line)||' ';
    let out=''; let cursor=0; let search=line;
    lt.forEach(t=>{
      const val=t.v; const pos=search.indexOf(val, cursor);
      if(pos===-1) return;
      out+=esc(search.slice(cursor,pos));
      const cls = t.error?'hl-ILLEGAL': ('hl-'+tokCategory(t));
      out+=`<span class="${cls}">${esc(val)}</span>`;
      cursor=pos+val.length;
    });
    out+=esc(search.slice(cursor));
    return out;
  }).join('\n');
}

/* ============================= APP STATE ============================= */
let state = { lang:'c', activePhase:null, result:null };
function pipelineForLang(lang){ return LANGS[lang].pipeline; }
function statusIcon(s){ return s==='ok'?'✓':s==='err'?'✗':s==='na'?'○':'…'; }
function statusClass(s){ return s==='ok'?'ok':s==='err'?'err':'na'; }

async function runAnalysis(){
  const lang = state.lang;
  const src = document.getElementById('code').value;
  const stdin = document.getElementById('stdin').value;
  const btn = document.getElementById('analyzeBtn'); btn.disabled=true; btn.textContent='Analyzing…';
  try{
    const resp = await fetch(API_BASE + '/api/analyze', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({language:lang, code:src, input:stdin})
    });
    if(!resp.ok){
      const errBody = await resp.json().catch(()=>({detail:resp.statusText}));
      alert('Backend error: ' + (errBody.detail || resp.statusText));
      return;
    }
    const res = await resp.json();
    renderAll(res);
  }catch(e){
    alert('Could not reach the backend at ' + API_BASE + '. Is it running? See README for setup steps.\n\n' + e.message);
  }finally{
    btn.disabled=false; btn.textContent='▶ Analyze';
  }
}

function renderNav(res){
  const nav=document.getElementById('pipelineNav');
  nav.innerHTML = pipelineForLang(state.lang).map(p=>{
    const st = res? (res.status[p]||'na') : 'na';
    const active = state.activePhase===p ? 'active':'';
    return `<div class="step ${active}" data-phase="${p}"><span class="dot ${statusClass(st)}">${statusIcon(st)}</span> ${PHASE_META[p].label}</div>`;
  }).join('') + `<div style="margin-top:14px;padding:8px 10px;font-size:11px;color:var(--textDim);border-top:1px solid var(--line)">Click Analyze, then step through the pipeline.</div>`;
  nav.querySelectorAll('.step').forEach(el=>el.addEventListener('click',()=>{ state.activePhase=el.dataset.phase; renderNav(res); renderPhase(res); }));
  const banner = document.getElementById('errorBanner');
  if(res && res.error){
    const label = PHASE_META[res.error.phase]?PHASE_META[res.error.phase].label:res.error.phase;
    banner.className = 'errorBanner';
    banner.innerHTML = `⚠ Error in <b>${esc(label)}</b>${res.error.line?` (line ${res.error.line})`:''}`;
    banner.onclick = ()=>{ state.activePhase = res.error.phase; renderNav(res); renderPhase(res); };
  } else {
    banner.className = 'errorBanner hidden';
    banner.innerHTML = ''; banner.onclick = null;
  }
}

function explain(text){ return `<div class="explain">${text}</div>`; }
function codeSnippetHTML(src, line, col){
  if(!src || !line) return '';
  const lines = src.split('\n');
  const from = Math.max(1, line-2), to = Math.min(lines.length, line+2);
  let out = '<div class="codeSnippet">';
  for(let n=from; n<=to; n++){
    const isErr = n===line;
    out += `<div class="snipLine${isErr?' snipLineErr':''}"><span class="snipNo">${n}</span><span class="snipTxt">${esc(lines[n-1] ?? '')}</span></div>`;
    if(isErr && col){
      out += `<div class="snipLine snipCaretRow"><span class="snipNo"></span><span class="snipTxt">${' '.repeat(Math.max(0,col-1))}^ here</span></div>`;
    }
  }
  out += '</div>';
  return out;
}
function errorExplorer(err, src){
  return `<div class="card errCard">
    <h3 style="color:var(--danger)">⚠ Error Explorer — exactly what's wrong, and where</h3>
    <div class="kv">
      <b>Phase</b><span>${PHASE_META[err.phase]?PHASE_META[err.phase].label:err.phase}</span>
      ${err.line?`<b>Line</b><span>${err.line}${err.col?`, column ${err.col}`:''}</span>`:''}
      ${err.kind?`<b>Type</b><span>${err.kind}</span>`:''}
      ${err.expected?`<b>Expected</b><span>${esc(err.expected)}</span>`:''}
      ${err.received?`<b>Found</b><span>${esc(err.received)}</span>`:''}
    </div>
    ${codeSnippetHTML(src, err.line, err.col)}
    <p style="margin-top:8px"><b>Explanation:</b> ${esc(err.message)}</p>
    <p>Go back to the code editor above, fix line ${err.line||'?'}, and click Analyze again.</p>
    <button class="ghost" id="aiExplainErrBtn">🧠 Ask AI to explain this error</button>
  </div>`;
}
function wireErrorExplorer(res){
  const btn = document.getElementById('aiExplainErrBtn'); if(!btn) return;
  btn.onclick = ()=>{
    const err = res.error;
    const q = `I got this error during "${PHASE_META[err.phase]?PHASE_META[err.phase].label:err.phase}"` +
      `${err.line?` at line ${err.line}`:''}: "${err.message}". Explain in plain terms exactly why this ` +
      `happens and how to fix it in my code.`;
    document.getElementById('aiPanel').classList.remove('hidden');
    document.getElementById('aiInput').value = q;
    aiSendQuestion();
  };
}

function renderPhase(res){
  const c=document.getElementById('content');
  if(!res){ c.innerHTML = editorHTML(); wireEditor(); return; }
  const p = state.activePhase || pipelineForLang(state.lang)[0];
  let html = `<div class="card"><h2>${PHASE_META[p]?PHASE_META[p].label:''}</h2>`;
  if(res.status[p]==='na'){ html+=`<p>This phase was not reached because an earlier phase reported an error. Fix that first, then re-run Analyze.</p></div>`; c.innerHTML=editorControlsHTML()+html; wireEditor(); return; }
  if(res.status[p]==='err' && !res.phases[p]){
    // This phase itself is where analysis stopped, and it has no successful output to show
    // (e.g. the parser threw before building an AST) — show the full error explanation instead
    // of trying to render data that doesn't exist.
    html += explain(`This is the phase where analysis stopped — see exactly what went wrong below.`);
    html += errorExplorer(res.error, res.src);
    html += `</div>`;
    c.innerHTML = editorControlsHTML()+html; wireEditor(); wireErrorExplorer(res); return;
  }

  if(p==='preprocess'){
    const pre = res.phases.preprocess;
    html += explain(`The preprocessor runs before the compiler proper. It handles directives that start with '#' — textual instructions, not program statements — such as including header files or expanding macros.`);
    if(pre.note){ html+=`<p><b>${esc(pre.note)}</b></p></div>`; c.innerHTML=editorControlsHTML()+html; wireEditor(); return; }
    html += `<div class="flow"><div class="b">SOURCE</div>→<div class="b">PREPROCESSOR</div>→<div class="b">PREPROCESSED SOURCE</div></div>`;
    html += `<h3>Directives found</h3>`;
    if(pre.directives.length===0) html+=`<p>No preprocessor directives found.</p>`;
    else html += `<table><tr><th>Directive</th><th>Meaning</th></tr>` + pre.directives.map(d=>`<tr><td>${esc(d.text)}</td><td>${esc(d.explain)}</td></tr>`).join('') + `</table>`;
    html += `<h3>Source passed to the compiler after stripping directives</h3><pre>${esc(pre.body.trim())}</pre>`;
  }

  else if(p==='lexical'){
    const tokens = res.phases.lexical.tokens.filter(t=>t.t!=='COMMENT');
    html += explain(`The lexical analyzer (scanner) reads the source one character at a time and groups characters into the smallest meaningful units, called <b>tokens</b> — keywords, identifiers, literals, operators and separators. This removes whitespace/comments and hands a clean token stream to the parser.`);
    html += `<div class="legend">
      <span><i style="background:#2c4a63"></i>Keyword</span><span><i style="background:#2c4a37"></i>Identifier</span>
      <span><i style="background:#4a3a2c"></i>Operator</span><span><i style="background:#4a2c46"></i>Literal</span>
      <span><i style="background:#4a2c2c"></i>String</span><span><i style="background:#3a3a3a"></i>Separator</span></div>`;
    html += `<h3>Source (highlighted)</h3><pre><code class="src">${highlightedSource(res.phases.preprocess.body, tokens)}</code></pre>`;
    html += `<h3>Token Table</h3><table><tr><th>Line</th><th>Lexeme</th><th>Token</th><th>Category</th></tr>` +
      tokens.filter(t=>t.t!=='PREPROC').map(t=>`<tr><td>${t.line}</td><td>${esc(t.v)}</td><td>${t.error?'ILLEGAL':t.t}</td><td>${t.cat}</td></tr>`).join('') + `</table>`;
  }

  else if(p==='syntax'){
    const ast = res.phases.syntax.ast;
    html += explain(`The syntax analyzer (parser) checks whether the token stream follows the language's grammar — the rules describing valid sentence structure — and builds a tree describing that structure. Example rule used for expressions: <code>E → E + T | T</code>, <code>T → T * F | F</code>.`);
    if(res.phases.wrapperNote) html += `<p><i>${esc(res.phases.wrapperNote)}</i></p>`;
    html += `<h3>Statements (as parsed)</h3><table><tr><th>#</th><th>Statement type</th><th>Line</th></tr>` +
      ast.map((s,i)=>`<tr><td>${i+1}</td><td>${s.type}</td><td>${s.line}</td></tr>`).join('') + `</table>`;
    html += `<h3>Why an AST instead of a full parse tree?</h3><p>A full parse tree keeps every grammar rule used (including parentheses and intermediate non-terminals). The <b>Abstract Syntax Tree (AST)</b> keeps only what matters for meaning — operators and operands — discarding grammar 'scaffolding' that doesn't affect what the program does.</p>`;
    html += `<p>Every compound expression in this program gets its own syntax tree and postfix form on the <b>${PHASE_META.expressions.label}</b> tab.</p>`;
  }

  else if(p==='expressions'){
    const list = res.phases.expressions.list;
    html += explain(`Each compound expression in the program is really a small tree: operators are internal nodes, operands are leaves. Walking that tree in <b>post-order</b> (left, right, operator) produces the expression's <b>postfix (Reverse Polish) form</b> — a representation with no parentheses and no precedence rules needed, which is exactly why stack-based evaluators and some intermediate representations use it.`);
    if(list.length===0){
      html += `<p>This program has no compound expressions (nothing beyond a single literal/identifier) to visualize — try the arithmetic or if-else example.</p>`;
    } else {
      list.forEach((e,i)=>{
        const svgId = `astsvg_${i}`, infoId = `astinfo_${i}`;
        html += `<div class="card" style="background:var(--ink2)">
          <h3>Expression ${i+1} — ${esc(e.context)} <span class="badge">line ${e.line}</span></h3>
          <div class="grid2">
            <div>
              <p><b>Infix:</b> <code>${esc(e.infix)}</code></p>
              <p><b>Postfix:</b> <code>${esc(e.postfix)}</code></p>
              <p>Click a node in the tree to see what it computes.</p>
              <div class="svgTree" id="${svgId}"></div>
              <div class="node-info" id="${infoId}">Select a node above.</div>
            </div>
            <div>
              <h3 style="margin-top:0">Postfix evaluation, step by step</h3>
              <p>A postfix expression is evaluated with a stack: push operands; whenever an operator is read, pop its operands, apply the operator, and push the result back.</p>
              ${postfixStackHTML(e.postfix)}
            </div>
          </div>
        </div>`;
      });
      setTimeout(()=>{ list.forEach((e,i)=>mountTree(e.tree, `astsvg_${i}`, `astinfo_${i}`)); }, 0);
    }
  }

  else if(p==='semantic'){
    const sem = res.phases.semantic;
    html += explain(`Semantic analysis checks whether a syntactically valid program actually <b>makes sense</b>: are variables declared before use, do types match, is scope respected? This is where a compiler catches errors like assigning text to a number.`);
    if(sem.dynamicTyping) html += `<p><b>Note:</b> Python does not enforce static types at compile time — a name can be rebound to a value of a different type. So classic 'type mismatch' checks are relaxed here; type errors would typically surface at run time instead.</p>`;
    if(sem.errors.length===0) html += `<p>✓ No semantic errors found — declarations, types and usage are consistent.</p>`;
    else html += sem.errors.map(e=>`<div class="errCard"><b>${e.kind}</b> — line ${e.line}<br>${esc(e.message)}</div>`).join('');
  }

  else if(p==='symtab'){
    const rows = res.phases.symtab.symtab;
    html += explain(`The <b>symbol table</b> is the compiler's internal record of every declared name: its type, kind, scope and declaration line. Later phases (semantic checking, code generation) consult it whenever a name is used.`);
    html += `<table><tr><th>Name</th><th>Type</th><th>Kind</th><th>Scope</th><th>Line</th><th>Value (at end of run)</th></tr>` +
      rows.map(r=>`<tr><td>${esc(r.name)}</td><td>${r.type}</td><td>${r.kind}</td><td>${r.scope}</td><td>${r.line}</td><td>${r.value!==null&&r.value!==undefined?esc(String(r.value)):'—'}</td></tr>`).join('') + `</table>`;
    html += `<h3>Memory view (final values)</h3><div class="memBoxes">` +
      rows.map(r=>`<div class="memBox"><div class="memName">${esc(r.name)}</div><div class="memVal">${r.value!==null&&r.value!==undefined?esc(String(r.value)):'?'}</div></div>`).join('') +
      `</div>`;
  }

  else if(p==='ir'){
    const {tac, quadruples, triples, indirectTriples, llvm} = res.phases.ir;
    html += explain(`Intermediate code is a representation that's lower-level than source code but not tied to any specific machine — this makes optimization and portability vastly easier. We show both classic textbook representations (<b>Three-Address Code</b>, <b>Quadruples</b>, <b>Triples</b>, and <b>Indirect Triples</b>) and the modern industry standard: <b>LLVM IR</b>.`);
    html += `<div class="flow"><div class="b">Source</div>→<div class="b">AST</div>→<div class="b">TAC / Quadruples / Triples</div>→<div class="b">LLVM IR (SSA Form)</div></div>`;

    html += `<h3>1. Three-Address Code (TAC)</h3><pre>${tac.map((l,i)=>fmtTAC(l,i)).join('\n')}</pre>`;
    html += `<p>Temporaries like <code>t1, t2, …</code> hold intermediate values so that each instruction performs only one operation — this uniformity is what makes later optimization passes easy to write.</p>`;

    html += `<h3>2. Quadruples</h3><p>One row per instruction, with an explicit <b>result</b> column — the most direct, table-shaped view of TAC.</p>`;
    html += `<table><tr><th>#</th><th>Operator</th><th>Arg1</th><th>Arg2</th><th>Result</th></tr>` +
      quadruples.map(q=>`<tr><td>${q.index+1}</td><td>${esc(String(q.op))}</td><td>${q.arg1??'—'}</td><td>${q.arg2??'—'}</td><td>${q.result??'—'}</td></tr>`).join('') + `</table>`;

    html += `<h3>3. Triples</h3><p>No result column. When an operand is the result of an earlier triple, it's written as <code>(i)</code> — "the value produced by statement i" — instead of a temp name. This saves the temp-naming machinery, at the cost of triples being harder to move around (since positions matter).</p>`;
    html += `<table><tr><th>#</th><th>Operator</th><th>Arg1</th><th>Arg2</th></tr>` +
      triples.map(t=>`<tr><td>${t.index}</td><td>${esc(String(t.op))}</td><td>${fmtTriple(t.arg1)}</td><td>${fmtTriple(t.arg2)}</td></tr>`).join('') + `</table>`;

    html += `<h3>4. Indirect Triples</h3><p>The <b>triple table above is left untouched</b>. A separate list of statement pointers determines execution order — currently pointer <code>i</code> targets triple <code>i</code>, since no reordering optimization ran, but this indirection is exactly what lets an optimizer perform code motion (e.g. hoisting a loop-invariant computation) by editing only the pointer list.</p>`;
    html += `<table><tr><th>Statement</th><th>→ Triple #</th></tr>` +
      indirectTriples.map(p=>`<tr><td>${p.stmt}</td><td>(${p.ptr})</td></tr>`).join('') + `</table>`;

    if(llvm && llvm.raw){
      html += `<div style="margin-top:28px;padding-top:16px;border-top:1px solid var(--line)">`;
      html += `<h3>5. LLVM IR (Industry Standard SSA Form)</h3>`;
      html += `<p>Modern compilers (like <b>Clang</b> for C/C++, <b>rustc</b> for Rust, and <b>swiftc</b> for Swift) do not stop at textbook TAC. They lower code into <b>LLVM IR</b> — a strongly-typed, infinite-register intermediate representation in Static Single Assignment (SSA) form.</p>`;
      html += `<div class="card" style="background:var(--ink2);margin-bottom:14px">`;
      html += `<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">`;
      html += `<b>Generated LLVM IR (<code>.ll</code> module)</b>`;
      html += `<button class="ghost" id="copyLlvmBtn" style="font-size:12px;padding:4px 10px;cursor:pointer">📋 Copy LLVM IR</button>`;
      html += `</div>`;
      html += `<pre style="max-height:400px;overflow-y:auto;background:var(--bg);border:1px solid var(--line);padding:10px 12px;border-radius:6px"><code class="src">${esc(llvm.raw)}</code></pre>`;
      html += `</div>`;

      if(llvm.concepts && llvm.concepts.length){
        html += `<h4>Key LLVM IR Concepts in this Program:</h4>`;
        html += `<div class="grid2">` + llvm.concepts.map(c => `
          <div class="card" style="padding:10px 14px;background:var(--ink2);border:1px solid var(--line)">
            <b style="color:var(--accent)">${esc(c.title)}</b>
            <p style="margin:4px 0 0;font-size:13px;line-height:1.45;color:var(--text)">${esc(c.desc)}</p>
          </div>
        `).join('') + `</div>`;
      }
      html += `</div>`;

      setTimeout(()=>{
        const cpBtn = document.getElementById('copyLlvmBtn');
        if(cpBtn && llvm && llvm.raw){
          cpBtn.onclick = ()=>{
            navigator.clipboard.writeText(llvm.raw).then(()=>{
              cpBtn.textContent = '✓ Copied!';
              setTimeout(()=>{ cpBtn.textContent = '📋 Copy LLVM IR'; }, 1800);
            }).catch(()=>{});
          };
        }
      }, 0);
    }
  }

  else if(p==='optimize'){
    const {code, notes} = res.phases.optimize;
    const before = res.phases.ir.tac.length, after = code.length;
    html += explain(`Optimization rewrites intermediate code to be more efficient <b>without changing what the program computes</b>. Every transformation below is applied only when it is provably safe.`);
    html += `<div class="flow"><div class="b">BEFORE</div>→<div class="b">OPTIMIZER</div>→<div class="b">AFTER</div></div>`;
    html += `<h3>Instruction count: before vs. after</h3>`;
    html += barChartHTML([{label:'Before optimization', value:before}, {label:'After optimization', value:after}]);
    const byRule = {};
    notes.forEach(n=>{ byRule[n.rule] = (byRule[n.rule]||0)+1; });
    if(Object.keys(byRule).length){
      html += `<h3>Optimizations applied, by rule</h3>` + barChartHTML(Object.entries(byRule).map(([label,value])=>({label,value})));
    }
    if(notes.length===0) html += `<p>No safe optimization opportunities were found in this program.</p>`;
    else html += notes.map(n=>`<div class="card" style="margin-bottom:8px"><span class="badge">${n.rule}</span><p style="margin-top:8px"><code>${esc(n.before)}</code></p><p>${esc(n.detail)}</p></div>`).join('');
    html += `<h3>Optimized Three-Address Code</h3><pre>${code.map((l,i)=>fmtTAC(l,i)).join('\n')}</pre>`;
  }

  else if(p==='target'){
    const lines = res.phases.target.lines;
    html += explain(`Target code generation maps intermediate code onto instructions for a machine model — here, simple LOAD/STORE/arithmetic instructions on numbered registers, chosen for clarity rather than matching the real output of gcc/g++/javac/CPython.`);
    html += `<span class="badge warn">Simplified instruction set — not real machine code</span>`;
    html += `<div class="flow" style="margin-top:10px"><div class="b">Intermediate Code</div>→<div class="b">Instruction Selection</div>→<div class="b">Register Mapping</div>→<div class="b">Target Instructions</div></div>`;
    html += `<pre>${lines.join('\n')}</pre>`;
    const langNote = {c:'A real C compiler would continue toward native machine code for a specific CPU (e.g. via an intermediate form like LLVM IR).',
      cpp:'A real C++ compiler follows a similar path to native machine code, plus name mangling, templates and class layout.',
      java:'A real Java compiler (javac) instead emits JVM bytecode into a .class file, which the JVM interprets or JIT-compiles.',
      python:'A real Python implementation (CPython) instead compiles to Python bytecode, run by the Python Virtual Machine.'}[state.lang];
    html += `<p>${langNote}</p>`;
  }

  else if(p==='execute'){
    const ex = res.phases.execute;
    html += explain(`The program is now run. The backend executes your parsed program with a small tree-walking interpreter (not by invoking gcc/javac/python as an OS subprocess), so no server-side sandboxing of an external process is needed for this subset.`);
    html += `<div class="grid2"><div><h3>Program Input</h3><pre>${esc(document.getElementById('stdin').value)||'(none)'}</pre></div>
      <div><h3>Program Output</h3><pre>${ex.error? '(no output — see error below)' : esc(ex.output||'(no output)')}</pre></div></div>`;
    html += `<h3>Execution Status</h3>`;
    html += ex.error? `<div class="errCard"><b>Runtime Error</b><br>${esc(ex.error)}</div>` : `<p>✓ Program executed successfully.</p>`;
  }

  else if(p==='summary'){
    html += `<p>Compilation journey for <b>${LANGS[state.lang].name}</b>:</p>`;
    html += `<table><tr><th>Phase</th><th>Status</th></tr>` + pipelineForLang(state.lang).filter(x=>x!=='summary').map(ph=>`<tr><td>${PHASE_META[ph].label}</td><td>${statusIcon(res.status[ph])}</td></tr>`).join('') + `</table>`;
    if(res.phases.execute) html += `<h3>Execution Result</h3><pre>${esc(res.phases.execute.output||'(no output)')}</pre>`;
    html += `<p>Use the pipeline on the left to revisit any phase in detail.</p>`;
    html += `<div class="card" style="background:var(--ink2)">
      <h3 style="margin-top:0">🧠 AI Compilation Report</h3>
      <p>Generates a single narrated, phase-by-phase explanation of exactly what happened when <i>this</i> program was compiled — written by the AI assistant, grounded in your actual tokens, tree, IR, optimizations and output.</p>
      <div style="display:flex;gap:8px;flex-wrap:wrap">
        <button class="primary" id="genReportBtn">Generate AI Report</button>
        <button class="ghost" id="downloadReportBtn" style="display:none">⇩ Download report (.md)</button>
      </div>
      <div id="reportStatus" style="font-size:12px;color:var(--textDim);margin-top:6px"></div>
      <div id="reportOutput" class="mdReport"></div>
    </div>`;
    html += `<div class="card" style="background:var(--ink2)">
      <h3 style="margin-top:0">📄 Full PDF Report</h3>
      <p>Builds one PDF covering every phase of this run — source, tokens, AST, expression trees &amp; postfix, symbol table, TAC/quadruples/triples/indirect-triples, optimizations, target code, and execution — plus the exact error (with line/column and a highlighted code snippet) if the pipeline stopped early. If you've already generated the AI report above, it's appended as a final section.</p>
      <div style="display:flex;gap:8px;flex-wrap:wrap">
        <button class="primary" id="genPdfBtn">Generate PDF</button>
        <button class="ghost hidden" id="viewPdfBtn">👁 View PDF</button>
        <button class="ghost hidden" id="downloadPdfBtn">⇩ Download PDF</button>
      </div>
      <div id="pdfStatus" style="font-size:12px;color:var(--textDim);margin-top:6px"></div>
    </div>`;
  }

  html += `</div>`;
  if(res.error && res.error.phase===p) html += errorExplorer(res.error, res.src);
  c.innerHTML = editorControlsHTML() + html;
  wireEditor();
  wireSummaryExtras(res);
  wireErrorExplorer(res);
}

let lastReportText = '';
function wireSummaryExtras(res){
  const genBtn = document.getElementById('genReportBtn'); if(!genBtn) return;
  const dlBtn = document.getElementById('downloadReportBtn');
  const statusEl = document.getElementById('reportStatus');
  const outEl = document.getElementById('reportOutput');
  genBtn.onclick = async ()=>{
    genBtn.disabled = true; genBtn.textContent = 'Generating…'; statusEl.textContent = 'Asking the AI assistant to write your report — this can take a few seconds.'; outEl.innerHTML='';
    try{
      const resp = await fetch(API_BASE + '/api/report', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({language: state.lang, code: document.getElementById('code').value, phases: res.phases})
      });
      const body = await resp.json().catch(()=>({}));
      if(!resp.ok){ statusEl.textContent = body.detail || 'Could not generate the report.'; return; }
      lastReportText = body.report;
      outEl.innerHTML = mdToHtml(body.report);
      statusEl.textContent = '';
      dlBtn.style.display = '';
    }catch(e){
      statusEl.textContent = 'Could not reach the backend: ' + e.message;
    }finally{
      genBtn.disabled = false; genBtn.textContent = 'Generate AI Report';
    }
  };
  if(dlBtn) dlBtn.onclick = ()=>{
    const blob = new Blob([lastReportText], {type:'text/markdown'});
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob); a.download = `compilation-report-${state.lang}.md`; a.click();
    URL.revokeObjectURL(a.href);
  };

  const genPdfBtn = document.getElementById('genPdfBtn');
  const viewPdfBtn = document.getElementById('viewPdfBtn');
  const downloadPdfBtn = document.getElementById('downloadPdfBtn');
  const pdfStatusEl = document.getElementById('pdfStatus');
  if(genPdfBtn) genPdfBtn.onclick = async ()=>{
    genPdfBtn.disabled = true; genPdfBtn.textContent = 'Generating…';
    pdfStatusEl.textContent = 'Building the PDF — laying out every phase, this can take a moment for larger programs.';
    try{
      const resp = await fetch(API_BASE + '/api/pdf-report', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({
          language: state.lang, code: document.getElementById('code').value,
          phases: res.phases, status: res.status, error: res.error || null,
          aiReport: lastReportText || null
        })
      });
      if(!resp.ok){
        const body = await resp.json().catch(()=>({}));
        pdfStatusEl.textContent = body.detail || 'Could not generate the PDF.';
        return;
      }
      const blob = await resp.blob();
      if(lastPdfUrl) URL.revokeObjectURL(lastPdfUrl);
      lastPdfUrl = URL.createObjectURL(blob);
      pdfStatusEl.textContent = 'PDF ready.';
      viewPdfBtn.classList.remove('hidden');
      downloadPdfBtn.classList.remove('hidden');
    }catch(e){
      pdfStatusEl.textContent = 'Could not reach the backend: ' + e.message;
    }finally{
      genPdfBtn.disabled = false; genPdfBtn.textContent = 'Generate PDF';
    }
  };
  if(viewPdfBtn) viewPdfBtn.onclick = ()=>{ if(lastPdfUrl) openPdfModal(lastPdfUrl); };
  if(downloadPdfBtn) downloadPdfBtn.onclick = ()=>{
    if(!lastPdfUrl) return;
    const a = document.createElement('a');
    a.href = lastPdfUrl; a.download = `compilation-report-${state.lang}.pdf`; a.click();
  };
}

let lastPdfUrl = null;
function openPdfModal(url){
  let overlay = document.getElementById('pdfModalOverlay');
  if(!overlay){
    overlay = document.createElement('div');
    overlay.id = 'pdfModalOverlay';
    overlay.className = 'pdfModalOverlay';
    overlay.innerHTML = `<div class="pdfModalBox">
      <div class="pdfModalHead"><span>📄 Compilation Report PDF</span><button class="ghost" id="pdfModalClose">✕ Close</button></div>
      <iframe id="pdfModalFrame"></iframe>
    </div>`;
    document.body.appendChild(overlay);
    overlay.addEventListener('click', (e)=>{ if(e.target===overlay) closePdfModal(); });
    document.getElementById('pdfModalClose').addEventListener('click', closePdfModal);
  }
  document.getElementById('pdfModalFrame').src = url;
  overlay.classList.remove('hidden');
}
function closePdfModal(){
  const overlay = document.getElementById('pdfModalOverlay');
  if(overlay) overlay.classList.add('hidden');
}

function fmtTriple(v){ return (v===null||v===undefined)?'—':v; }
function fmtTAC(line, idx){
  const n=idx!==undefined?(idx+1)+'. ':'';
  if(line.op==='=') return `${n}${line.res} = ${line.a1}`;
  if(line.op==='PRINT') return `${n}PRINT ${line.a1}`;
  if(line.op==='LABEL') return `${n}${line.res}:`;
  if(line.op==='GOTO') return `${n}goto ${line.res}`;
  if(line.op==='IFFALSE') return `${n}ifFalse ${line.a1} goto ${line.res}`;
  if(line.op==='READ') return `${n}${line.res} = read()`;
  return `${n}${line.res} = ${line.a1} ${line.op} ${line.a2}`;
}

function editorControlsHTML(){
  const curCode = document.getElementById('code')?document.getElementById('code').value:LANGS[state.lang].sample;
  const curStdin = document.getElementById('stdin')?document.getElementById('stdin').value:'';
  return `<div class="card"><div class="editorWrap">
    <h2>Source Code — ${LANGS[state.lang].name}</h2>
    <p>Supported constructs: variable declarations/assignment, arithmetic (+ - * /), comparisons, print, if/else, while. Programs outside this range may not parse — that's shown honestly as a syntax error, not silently guessed at.</p>
    <textarea id="code" spellcheck="false">${esc(curCode)}</textarea>
    <label style="font-size:12px;color:var(--textDim)">Program Input (stdin) — whitespace-separated values consumed by input()/scanf</label>
    <textarea id="stdin">${esc(curStdin)}</textarea>
    <div style="display:flex;gap:8px;flex-wrap:wrap">
      <button class="primary" id="analyzeBtn">▶ Analyze</button>
      <button id="stepBtn">Explain Step-by-Step</button>
      <button class="ghost" id="uploadBtn">⇧ Upload Code File</button>
      <input type="file" id="codeFile" accept=".c,.cc,.cpp,.cxx,.h,.hpp,.java,.py,.txt" style="display:none">
      <button class="ghost" id="resetBtn">Reset Example</button>
    </div>
    <div id="uploadNote" style="font-size:12px;color:var(--textDim)"></div>
    <div id="stepPanel"></div>
  </div></div>`;
}
function editorHTML(){ return editorControlsHTML() + `<div class="card"><p>Click <b>Analyze</b> to run the program through every compiler phase (handled by the FastAPI backend). Use the left-hand pipeline to open each phase once results are ready.</p></div>`; }

const EXT_TO_LANG = {c:'c', h:'c', cc:'cpp', cpp:'cpp', cxx:'cpp', hpp:'cpp', java:'java', py:'python', txt:null};
const STEP_TEMPLATES = ['Read keyword int','Recognize identifier','Recognize assignment operator =','Recognize expression on the right-hand side','Build the AST node for this statement','Perform semantic checks (declared? type OK?)','Generate three-address code, quadruples, triples & indirect triples','Apply safe optimizations','Generate target instructions','Execute and observe output'];
function wireEditor(){
  const codeEl=document.getElementById('code'); if(!codeEl) return;
  document.getElementById('analyzeBtn').onclick = runAnalysis;
  document.getElementById('resetBtn').onclick = ()=>{ codeEl.value = LANGS[state.lang].sample; document.getElementById('stdin').value=''; };
  document.getElementById('uploadBtn').onclick = ()=>document.getElementById('codeFile').click();
  document.getElementById('codeFile').onchange = (ev)=>{
    const file = ev.target.files[0]; if(!file) return;
    const ext = file.name.split('.').pop().toLowerCase();
    const detected = EXT_TO_LANG[ext];
    const reader = new FileReader();
    reader.onload = ()=>{
      const text = reader.result;
      if(detected && detected !== state.lang){
        state.lang = detected; state.result=null; state.activePhase=null;
        document.getElementById('langSel').value = detected;
        loadExamples();
        document.getElementById('content').innerHTML = editorHTML();
        document.getElementById('code').value = text;
        wireEditor();
        renderNav(null);
        document.getElementById('uploadNote').textContent = `Loaded "${file.name}" — language auto-detected as ${LANGS[detected].name}.`;
      } else {
        document.getElementById('code').value = text;
        document.getElementById('uploadNote').textContent = `Loaded "${file.name}".${detected?'':' Could not auto-detect language from its extension — check the language dropdown.'}`;
      }
    };
    reader.onerror = ()=>{ document.getElementById('uploadNote').textContent = `Could not read "${file.name}".`; };
    reader.readAsText(file);
    ev.target.value = '';
  };
  document.getElementById('stepBtn').onclick = ()=>{
    const panel=document.getElementById('stepPanel'); let i=0;
    function draw(){ panel.innerHTML = `<div class="explain"><b>Step ${i+1}/${STEP_TEMPLATES.length}:</b> ${STEP_TEMPLATES[i]}</div>
      <div class="stepbar"><button id="prevS">◀ Previous</button><button id="nextS">Next ▶</button><button id="restartS">Restart</button></div>`;
      document.getElementById('prevS').onclick=()=>{ i=Math.max(0,i-1); draw(); };
      document.getElementById('nextS').onclick=()=>{ i=Math.min(STEP_TEMPLATES.length-1,i+1); draw(); };
      document.getElementById('restartS').onclick=()=>{ i=0; draw(); };
    }
    draw();
  };
}

function renderAll(res){
  state.result=res;
  if(res.error && res.error.phase){
    // Always take the user straight to the phase where things went wrong —
    // don't make them hunt for it across tabs.
    state.activePhase = res.error.phase;
  } else if(!state.activePhase || !pipelineForLang(state.lang).includes(state.activePhase)){
    state.activePhase = pipelineForLang(state.lang)[0];
  }
  renderNav(res); renderPhase(res);
}
function loadExamples(){ const sel=document.getElementById('exampleSel'); sel.innerHTML = EXAMPLES[state.lang].map((e,i)=>`<option value="${i}">${e[0]}</option>`).join(''); }

document.getElementById('langSel').addEventListener('change', e=>{
  state.lang = e.target.value; state.result=null; state.activePhase=null;
  loadExamples();
  document.getElementById('content').innerHTML = editorHTML();
  document.getElementById('code').value = LANGS[state.lang].sample;
  wireEditor();
  renderNav(null);
});
document.getElementById('exampleSel').addEventListener('change', e=>{
  document.getElementById('code').value = EXAMPLES[state.lang][+e.target.value][1];
});
document.getElementById('themeBtn').addEventListener('click', ()=>{
  const root=document.documentElement; const dark = root.getAttribute('data-theme')!=='light';
  root.setAttribute('data-theme', dark?'light':'dark');
});

/* ============================= AI chat assistant (floating panel) ============================= */
function aiPushMessage(role, text){
  const box = document.getElementById('aiMessages');
  const div = document.createElement('div');
  div.className = 'aiMsg ' + (role==='user' ? 'aiMsgUser' : 'aiMsgBot');
  div.innerHTML = role==='user' ? esc(text) : mdToHtml(text);
  box.appendChild(div);
  box.scrollTop = box.scrollHeight;
}
async function aiSendQuestion(){
  const input = document.getElementById('aiInput');
  const question = input.value.trim(); if(!question) return;
  aiPushMessage('user', question);
  input.value=''; input.disabled=true;
  const sendBtn = document.getElementById('aiSend'); sendBtn.disabled=true; sendBtn.textContent='…';
  const thinking = document.createElement('div');
  thinking.className='aiMsg aiMsgBot'; thinking.id='aiThinking'; thinking.textContent='Thinking…';
  document.getElementById('aiMessages').appendChild(thinking);
  try{
    const codeEl = document.getElementById('code');
    const body = {
      question,
      language: state.lang,
      code: codeEl ? codeEl.value : '',
      activePhase: state.activePhase || '',
      phases: state.result ? state.result.phases : {}
    };
    const resp = await fetch(API_BASE + '/api/ask', {
      method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)
    });
    const data = await resp.json().catch(()=>({}));
    thinking.remove();
    if(!resp.ok){ aiPushMessage('bot', '⚠️ ' + (data.detail || 'The assistant could not answer that.')); }
    else aiPushMessage('bot', data.answer);
  }catch(e){
    thinking.remove();
    aiPushMessage('bot', '⚠️ Could not reach the backend: ' + e.message);
  }finally{
    input.disabled=false; sendBtn.disabled=false; sendBtn.textContent='Send'; input.focus();
  }
}
function initAiPanel(){
  const toggle = document.getElementById('aiToggle'), panel = document.getElementById('aiPanel'), close = document.getElementById('aiClose');
  toggle.addEventListener('click', ()=>panel.classList.toggle('hidden'));
  close.addEventListener('click', ()=>panel.classList.add('hidden'));
  document.getElementById('aiSend').addEventListener('click', aiSendQuestion);
  document.getElementById('aiInput').addEventListener('keydown', e=>{
    if(e.key==='Enter' && !e.shiftKey){ e.preventDefault(); aiSendQuestion(); }
  });
  fetch(API_BASE + '/api/ai-status').then(r=>r.json()).then(d=>{
    const note = document.getElementById('aiNote');
    if(!note) return;
    if(!d.configured) {
      note.textContent = '⚠️ No API key set — set NVIDIA_API_KEY or ANTHROPIC_API_KEY to enable AI.';
    } else {
      note.textContent = '🟢 AI active: ' + (d.provider || 'Ready');
    }
  }).catch(()=>{});
}

/* init */
loadExamples();
renderNav(null);
renderPhase(null);
initAiPanel();
detectApiBase().then(()=>{
  fetch(API_BASE + '/api/ai-status').then(r=>r.json()).then(d=>{
    const note = document.getElementById('aiNote');
    if(!note) return;
    if(!d.configured) {
      note.textContent = '⚠️ No API key set — set NVIDIA_API_KEY or ANTHROPIC_API_KEY to enable AI.';
    } else {
      note.textContent = '🟢 AI active: ' + (d.provider || 'Ready');
    }
  }).catch(()=>{});
});
