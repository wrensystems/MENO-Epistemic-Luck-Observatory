"""Loopback-only, read-oriented projection of authoritative campaign archives."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs

from .meno2_campaign import inspect_campaign, _read_frozen, _stage_path, _stage_records


def model_projection(report):
    """Deliberately separate payload; hidden world/role/oracle fields never reach this view."""
    return {'perspective': 'model', 'rows': [
        {'id': r['id'], 'model': r['model'], 'condition': r['condition'],
         'repetition': r['repetition'], 'evidence': [
             {'id': e['id'], 'text': e.get('text', '')} for e in r['evidence']],
         'request': r.get('invocation', {}).get('intent', {}).get('request', {}).get('prompt'),
         'response': r.get('invocation', {}).get('response', {}).get('text') if r.get('invocation', {}).get('response') else None}
        for r in report['rows']]}


HTML = r'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>MENO: Epistemic Luck Observatory</title><style>
:root{color-scheme:light;--ink:#182b34;--muted:#50646c;--line:#cbd6d7;--paper:#f4f6f3;--accent:#176459}*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.55 system-ui,sans-serif}header{padding:28px 4vw 18px;background:#173a3d;color:white}header small{letter-spacing:.15em;color:#b8d3ce}h1{font:600 30px/1.2 Georgia,serif;margin:8px 0}header p{margin:6px 0;color:#d1e0dd}nav{display:flex;gap:8px;padding:14px 4vw;background:white;border-bottom:1px solid var(--line);flex-wrap:wrap}button,select,input{font:inherit;border:1px solid var(--line);border-radius:5px;padding:8px 12px;background:white;color:var(--ink)}button{cursor:pointer}button.active{background:var(--accent);color:white}button:focus-visible,select:focus-visible{outline:3px solid #c48e32;outline-offset:2px}main{padding:24px 4vw;max-width:1800px;margin:auto}h2{font:600 25px Georgia,serif}h3{margin:0 0 12px}p.note{color:var(--muted)}.toolbar{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin:0 0 20px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px}.card{background:white;border:1px solid var(--line);border-radius:8px;padding:20px;min-width:0;margin-bottom:16px}.metric{font-size:30px;font-weight:650}.label{color:var(--muted);font-size:13px}.badge{background:#e3eee9;padding:4px 10px;border-radius:4px;display:inline-block}.warning{background:#fff2d4;border-left:4px solid #ae7c22;padding:12px 16px;margin-bottom:18px}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:12px/1.6 ui-monospace,Consolas,monospace;background:#f5f7f6;padding:12px;max-height:440px;overflow:auto}table{border-collapse:collapse;width:100%;font-size:13px}td,th{text-align:left;padding:10px;border-bottom:1px solid var(--line);vertical-align:top}.scroll{overflow:auto}.responses{display:grid;grid-template-columns:repeat(auto-fit,minmax(265px,1fr));gap:14px}.bar{height:8px;background:#e1e9e7;border-radius:6px;margin:8px 0}.fill{height:100%;background:var(--accent);border-radius:6px}details{margin:10px 0}summary{cursor:pointer;font-weight:600}.error{color:#9c2c25}footer{padding:20px 4vw;color:var(--muted);font-size:12px}@media(max-width:600px){h1{font-size:24px}main{padding:16px}.card{padding:14px}}
</style><header><small>MENO / RESEARCH INSTRUMENT</small><h1>Epistemic Luck Observatory</h1><p>Inspect truth, available evidence, source integrity and decisions independently.</p></header>
<nav aria-label="Research views"><button data-view="overview" class="active">Campaign overview</button><button data-view="microscope">Case microscope</button><button data-view="compare">Comparison explorer</button><button data-view="lineage">Incidents &amp; lineage</button></nav>
<main id="app" aria-live="polite">Loading verified campaign…</main><footer>Local archive projection · Read only · Synthetic fixtures establish software behavior only. Structural counterfactual publication exposure is not observed counterfactual model behavior.</footer>
<script>
let report=null,view='overview',perspective='investigator',chosenBlock='',chosenCase='',chosenModel='',chosenRep='0';
const app=document.getElementById('app');
function el(tag,text,cls){let n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n}
function pre(value){return el('pre',typeof value==='string'?value:JSON.stringify(value,null,2))}
function card(title,value){let n=el('section',undefined,'card');n.append(el('h3',title));if(value!==undefined)n.append(pre(value));return n}
function metric(label,value){let n=el('div',undefined,'card');n.append(el('div',label,'label'),el('div',String(value),'metric'));return n}
function select(label,values,current,change){let box=el('label',label+' '),s=el('select');for(let [value,text] of values){let o=el('option',text);o.value=value;s.append(o)}s.value=current;s.onchange=()=>change(s.value);box.append(s);return box}
function table(headers,rows){let wrap=el('div',undefined,'scroll'),t=el('table'),head=el('tr');for(let h of headers)head.append(el('th',h));t.append(head);for(let row of rows){let tr=el('tr');for(let value of row)tr.append(el('td',value===null?'—':String(value)));t.append(tr)}wrap.append(t);return wrap}
function rounded(n){return n===null||n===undefined?'—':Number(n).toFixed(4)}
function details(title,value){let d=el('details');d.append(el('summary',title),pre(value));return d}
function base(){app.replaceChildren();if(report.status.scoring_provenance.read_only_rescore)app.append(el('div','Read-only rescoring: frozen '+report.status.scoring_provenance.frozen_scoring_version+'; applied '+report.status.scoring_provenance.applied_scoring_version+'. Original evidence and exports are unchanged.','warning'));app.append(el('h2',{'overview':'Campaign overview','microscope':'Case microscope','compare':'Comparison explorer','lineage':'Incidents & lineage'}[view]));if(report.status.evidence_kind==='synthetic')app.append(el('div','SYNTHETIC SOFTWARE EVIDENCE — these are scripted mock responses, not measured model performance.','warning'))}
async function draw(){base();if(view==='overview'){let s=report.status,g=el('div',undefined,'grid');g.append(metric('Matched blocks complete / planned',s.completed_blocks+' / '+s.planned_blocks),metric('Trials completed / planned',s.completed_trials+' / '+s.planned_trials),metric('Schema-valid / invalid outputs',s.valid_responses+' / '+s.invalid_responses),metric('Contradictory publications',s.contradictory_publications),metric('Missing trials',s.missing_trials),metric('Reserved / observed USD',s.reserved_usd+' / '+s.observed_cost_usd));app.append(g);let c=card('Frozen protocol');c.append(table(['Setting','Value'],[['Campaign',s.campaign],['Regime',s.regime],['Mode',s.mode],['Analysis',report.protocol.analysis_status],['Models',s.models.join(', ')],['Primary eligible blocks',s.eligible_blocks],['Scoring frozen / applied',s.scoring_provenance.frozen_scoring_version+' / '+s.scoring_provenance.applied_scoring_version],['Source matches',s.source_matches],['Status',s.status]]),details('Hypothesis, stopping rules and model settings',report.protocol));app.append(c);return}
if(view==='microscope'){let bar=el('div',undefined,'toolbar');bar.append(select('Perspective',[['investigator','Investigator: hidden world + oracle'],['model','Model: exact visible request only']],perspective,v=>{perspective=v;draw()}));app.append(bar);
if(perspective==='model'){let data=await fetch('/api/report?perspective=model').then(r=>r.json());app.append(el('p','This server projection excludes world states, roles, oracle labels and scores. Select a trial to inspect exactly what was sent.','note'));let ids=data.rows.map(r=>[r.id,r.model+' · '+r.condition+' · '+r.id.slice(-8)]);let selected=data.rows.find(r=>r.id===chosenCase)||data.rows[0];app.append(select('Trial',ids,selected.id,v=>{chosenCase=v;draw()}),card('Exact provider prompt',selected.request||'Not sent'),card('Model response',selected.response||'No completed response'));return}
let block=report.blocks.find(b=>b.id===chosenBlock)||report.blocks[0];chosenBlock=block.id;let c=block.cases.find(c=>c.id===chosenCase)||block.cases[0];chosenCase=c.id;chosenModel=chosenModel||report.status.models[0];bar.append(select('Block',report.blocks.map(b=>[b.id,b.mechanism+' · '+b.id.slice(-8)]),block.id,v=>{chosenBlock=v;chosenCase='';draw()}),select('Case',block.cases.map(c=>[c.id,c.role+' · '+c.id.slice(-8)]),c.id,v=>{chosenCase=v;draw()}),select('Model',report.status.models.map(m=>[m,m]),chosenModel,v=>{chosenModel=v;draw()}),select('Repetition',Array.from({length:report.protocol.repetitions},(_,i)=>[String(i),String(i)]),chosenRep,v=>{chosenRep=v;draw()}));app.append(el('p',block.case_class+' · '+block.regime+' · '+block.cohort+' · Primary eligible: '+block.eligible,'badge'));let grid=el('div',undefined,'grid');grid.append(card('Formal world & realized hidden state',c.world),card('Exact initial evidence records',c.initial_evidence),card('World-structure labels',c.structure_labels));app.append(grid,details('Seeded generation settings',block.generation));let rows=report.rows.filter(r=>r.block_id===block.id&&r.case_id===c.id&&r.model===chosenModel&&r.repetition===Number(chosenRep));let responses=el('div',undefined,'responses');for(let r of rows){let section=card(r.condition);section.append(el('span','Transport: '+r.operational_status,'badge'));if(r.score.contradictory_publication)section.append(el('p','Contradictory publication: '+r.score.decision_errors.join(', '),'error'));let parsed=r.score.response;if(parsed){section.append(el('p','p(true): '+rounded(parsed.p_true)+' · '+parsed.action));let b=el('div',undefined,'bar'),fill=el('div',undefined,'fill');fill.style.width=(parsed.p_true*100)+'%';b.append(fill);section.append(b,pre(parsed))}else section.append(pre(r.score.errors));section.append(details('Available evidence',r.evidence),details('Current oracle & structural witnesses',r.score.oracle),details('Initial-information oracle for cited basis',r.score.initial_oracle),details('Deterministic scores (structural exposure, not counterfactual behavior)',r.score),details('Exact request and response',r.invocation));responses.append(section)}app.append(responses);return}
if(view==='compare'){app.append(el('p','The primary analysis using the displayed scoring version is shown below. Structural counterfactual publication exposure is an oracle possibility combined with a reported publication action; no counterfactual model response was observed. Mechanism filters are exploratory and never rewrite the confirmatory denominator. Models and regimes remain separate.','note'));let choices=[['all','All mechanisms (frozen analysis)'],...Object.keys(report.analysis.exploratory_mechanism_strata).map(k=>[k,k])];let region=el('div');function show(value){region.replaceChildren();let groups=value==='all'?report.analysis.groups:report.analysis.exploratory_mechanism_strata[value];for(let [name,g] of Object.entries(groups)){let n=card(name+(value==='all'?'':' · exploratory'));n.append(table(['Condition','Valid / planned','Balanced decision','Coherent supported publication','Contradictions','Structural CF exposure','Brier','Missing'],Object.entries(g.conditions).map(([k,v])=>[k,v.valid+' / '+v.planned_trials,rounded(v.balanced_decision),rounded(v.supported_publication_coverage),v.contradictory_publications,rounded(v.structural_counterfactual_publication_exposure_rate),rounded(v.truth_brier),v.operational_missing])));n.append(table(['Paired comparison','Blocks','Effect','95% block bootstrap'],Object.entries(g.comparisons).map(([k,v])=>[k,v.n_matched_blocks,rounded(v.delta),v.bootstrap_95_ci? v.bootstrap_95_ci.map(rounded).join(' to '):'Unavailable'])));n.append(details('Secondary outcomes and block scores',g));region.append(n)}}app.append(select('Mechanism',choices,'all',show),region,details('Statistical interpretation',report.analysis.notes));show('all');let strata=card('Block-level comparison dimensions');for(let [key,g] of Object.entries(report.analysis.groups)){strata.append(el('h3',key),table(['Mechanism','Reliability','Complexity','Observability','Exact facts B','Audit B'],report.blocks.map(b=>[b.mechanism,b.generation.reliability,b.generation.source_complexity,b.case_class,rounded((g.block_scores.exact_facts||{})[b.id]),rounded((g.block_scores.structured_audit||{})[b.id])])))}app.append(strata);return}
let incidents=report.rows.filter(r=>r.operational_status!=='success'||!r.score.valid||r.score.contradictory_publication);app.append(el('p',incidents.length+' trial(s) with missing, failed, uncertain, invalid or contradictory output. Campaign hash: '+report.campaign_sha256,'note'));app.append(card('Durable run summaries',report.runs));let picker=el('div',undefined,'toolbar'),target=el('div');let selected=report.rows[0];function trace(id){let r=report.rows.find(r=>r.id===id);target.replaceChildren(card('Trial identity and frozen parent',{id:r.id,block:r.block_id,case:r.case_id,parent:r.parent_id,parent_response_hash:r.parent_response_hash,attempt:r.attempt,scoring_version:r.score.scoring_version}),card('Request intent, response and outcome',r.invocation),card('Validation and scoring',r.score))}picker.append(select('Trace trial',report.rows.map(r=>[r.id,r.condition+' · '+r.incident_kind+' · '+r.id.slice(-8)]),selected.id,trace));app.append(picker,target);trace(selected.id)}
document.querySelectorAll('nav button').forEach(b=>b.onclick=()=>{view=b.dataset.view;document.querySelectorAll('nav button').forEach(n=>n.classList.toggle('active',n===b));draw().catch(error)});
function error(e){app.replaceChildren(el('h2','Archive inspection failed'),el('p',String(e),'error'))}
fetch('/api/report').then(r=>{if(!r.ok)throw Error('Campaign verification failed');return r.json()}).then(r=>{report=r;draw().catch(error)}).catch(error);
</script></html>'''


def make_server(root, port=8792):
    inspect_campaign(root)  # Validate before binding.
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            route = urlsplit(self.path)
            try:
                if route.path == '/':
                    content, kind = HTML.encode(), 'text/html; charset=utf-8'
                elif route.path == '/api/report':
                    report = inspect_campaign(root)
                    if parse_qs(route.query).get('perspective') == ['model']:
                        report = model_projection(report)
                    content, kind = json.dumps(report, allow_nan=False).encode(), 'application/json'
                else:
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header('Content-Type', kind)
                self.send_header('Cache-Control', 'no-store')
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'")
                self.send_header('Content-Length', str(len(content)))
                self.end_headers()
                self.wfile.write(content)
            except (ValueError, OSError, KeyError, TypeError):
                self.send_error(409, 'Archive verification failed')

        def log_message(self, format, *args):
            pass
    return ThreadingHTTPServer(('127.0.0.1', port), Handler)


def serve(root, port=8792):
    server = make_server(root, port)
    print(f'MENO Observatory: http://127.0.0.1:{server.server_port}', flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()
