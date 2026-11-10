import {REPO, PROTOCOL, REPORT_EMAIL, MP3_EVALUATION, safeURL, validStudentID, validateSubmission, validateMP3Score, makeIssueURL, createPeerReviewReport, peerReviewEmailURL, bestRows, submissionPhase, encryptArtifactLinks} from './arena.1b5f9fa2d0c3.mjs';

const $=id=>document.getElementById(id);
const STATUS={'self-reported':'Self-reported',verified:'Verified',review:'Review required',invalid:'Invalidated',withdrawn:'Withdrawn',late:'Late submission',superseded:'Superseded','links-missing':'Links missing'};
let snapshot={submissions:[]}, refreshing=false, hasSnapshot=false, scoreReport=null, scoreHash=null, loadedScoreFile=null, formVersion=0, challengeTarget=null;
function element(tag,text,className) {
  const node=document.createElement(tag);
  if(text!==undefined) node.textContent=text;
  if(className) node.className=className;
  return node;
}
function issueLink(row) {
  const link=element('a',`#${row.number}`);
  const url=safeURL(row.url);
  if(url) link.href=url;
  link.target='_blank'; link.rel='noopener noreferrer';
  return link;
}
function artifactLink(label,url) {
  const link=element('a',label), safe=safeURL(url);
  if(safe) link.href=safe;
  link.target='_blank'; link.rel='noopener noreferrer';
  return link;
}
function prepared(target,url,kind) {
  const ready=element('div',`${kind} prepared, not submitted. Create the GitHub issue to save it.`,'prepared');
  const link=element('a','Submit on GitHub ↗');
  link.href=url; link.target='_blank'; link.rel='noopener noreferrer';
  ready.append(element('br'),link); target.replaceChildren(ready);
}
function empty(body,columns,text) {
  const row=element('tr'), cell=element('td',text,'empty');
  cell.colSpan=columns; row.append(cell); body.append(row);
}
function submissionsOpen() {
  return submissionPhase('mp3',snapshot.publication)==='scores';
}
function configureForm() {
  const phase=submissionPhase('mp3',snapshot.publication), open=phase==='scores';
  $('submit').hidden=!open;
  $('workspace').classList.toggle('mp2-workspace',open);
  $('prepare-submit').disabled=!open;
  $('phase-badge').textContent={scores:'Score submissions open',review:'7-day peer review',complete:'Review closed',closed:'Submissions closed'}[phase];
  $('phase-note').textContent=open
    ? 'Submit your final score, source and optional LoRA adapter by 30 November, 23:59 (UTC+8). Artifact links are sealed until the instructor releases them for peer review.'
    : phase==='review' ? 'Scores are frozen. Reproduce released submissions and submit a Peer Review Report by 7 December, 23:59 (UTC+8).'
    : 'Submissions and peer review are closed. Results remain subject to instructor verification.';
}
function render() {
  const history=$('history').checked, rows=bestRows(snapshot.submissions,'mp3',history);
  const phase=submissionPhase('mp3',snapshot.publication), released=['review','complete'].includes(phase);
  $('board-body').replaceChildren();
  if(!rows.length) empty($('board-body'),6,'No eligible results yet. Evaluate locally and submit your test-score JSON.');
  let rank=0, previous=null;
  for(const [index,row] of rows.entries()) {
    if(row.score!==previous) rank=index+1;
    previous=row.score;
    const tr=element('tr'), materials=element('td'), accuracy=element('td',`${row.score.toFixed(2)}%`);
    accuracy.append(element('br'),element('span',`${row.correct} / ${row.n}`,'caption'));
    const links=element('div',undefined,'artifact-links');
    for(const [label,url,kind] of [['Source',row.code_url,'code'],['LoRA',row.checkpoint_url,'checkpoint']]) {
      if(!released || !url) continue;
      const item=element('span',undefined,'artifact-item'), link=artifactLink(label,url);
      link.title=label==='Source'?row.source_sha256||'Submitted source export':row.model?.adapter_sha256||'Submitted LoRA adapter';
      item.append(link);
      const access=row.artifact_access?.[kind];
      if(access?.status==='unavailable') {
        const warning=element('span','Unable to open','artifact-unavailable');
        warning.title=access.reason || 'Unavailable at the last check.';
        item.append(warning);
      }
      links.append(item);
    }
    if(!links.childElementCount) links.append(element('span',released
      ? 'Awaiting artifact release' : row.artifact_status==='received'?'Links received':'Links pending','caption'));
    materials.append(links,issueLink(row));
    const status=element('td');
    status.append(element('span',STATUS[row.status]||row.status,`badge ${row.status}`));
    const review=element('td'), button=element('button','Peer Review Report','text-button');
    button.type='button'; button.disabled=phase!=='review' || !row.code_url;
    button.addEventListener('click',()=>openChallenge(row)); review.append(button);
    tr.append(element('td',history?'—':String(rank)),element('td',row.student_id),accuracy,materials,status,review);
    $('board-body').append(tr);
  }
}
async function refresh() {
  if(refreshing) return;
  refreshing=true; $('refresh').disabled=true; $('sync-status').textContent='Refreshing…';
  const raw=`https://raw.githubusercontent.com/${REPO}/main/courses/dase7506/data/leaderboard.json?v=${Date.now()}`;
  const api=`https://api.github.com/repos/${REPO}/contents/courses/dase7506/data/leaderboard.json?ref=main`;
  const fetchSnapshot=async(url,headers={})=>{
    const response=await fetch(url,{headers,cache:'no-cache',signal:AbortSignal.timeout(6000)});
    if(!response.ok) throw new Error(`HTTP ${response.status}`);
    const data=await response.json();
    if(data.schema!=='dase7506/board-v1' || data.snapshot_version!==2 || data.protocol!==PROTOCOL
      || !Array.isArray(data.submissions)) throw new Error('The leaderboard snapshot is invalid.');
    return data;
  };
  try {
    const responses=await Promise.allSettled([fetchSnapshot(raw),fetchSnapshot('../data/leaderboard.json')]);
    const candidates=responses.filter(result=>result.status==='fulfilled').map(result=>result.value)
      .sort((a,b)=>Date.parse(b.generated_at)-Date.parse(a.generated_at));
    let result=candidates[0];
    if(!result) result=await fetchSnapshot(api,{Accept:'application/vnd.github.raw+json'});
    if(hasSnapshot && Date.parse(result.generated_at)<Date.parse(snapshot.generated_at)) result=snapshot;
    snapshot=result; hasSnapshot=true; render();
    $('sync-status').textContent=`Updated: ${new Date(result.generated_at).toLocaleString('en-GB')}. Auto-refresh every 30 seconds. Reported scores remain subject to instructor checks.`;
  } catch(error) {
    $('sync-status').textContent=hasSnapshot?'Refresh failed; showing the last loaded results. Retrying automatically.'
      :`Results unavailable: ${error.message} Your score submission is saved only after you create its GitHub issue.`;
    if(!hasSnapshot) {
      $('board-body').replaceChildren();
      empty($('board-body'),6,'Leaderboard unavailable. Your GitHub issue is the submission receipt.');
    }
  } finally {refreshing=false; $('refresh').disabled=false; configureForm();}
}
$('history').addEventListener('change',render);
$('refresh').addEventListener('click',refresh);
$('submission-form').addEventListener('input',()=>{
  formVersion++; $('submission-status').replaceChildren();
});
$('submission-form').addEventListener('submit',async event=>{
  event.preventDefault(); $('prepare-submit').disabled=true; $('submission-status').replaceChildren();
  try {
    const version=formVersion;
    if(!submissionsOpen()) throw new Error('Score submissions are closed.');
    if(!$('consent').checked) throw new Error('Confirm the project rules and privacy notice.');
    if(!scoreReport || loadedScoreFile!==$('score-file').files[0]) throw new Error('Load a valid full test-score JSON first.');
    const student_id=$('student-id').value.trim(), code=safeURL($('code-url').value.trim());
    if(!validStudentID(student_id)) throw new Error('Enter a student ID of 1–64 visible characters.');
    if(!code) throw new Error('Provide an HTTPS source ZIP link without credentials.');
    const rawAdapter=$('adapter-url').value.trim();
    const adapter=rawAdapter?safeURL(rawAdapter):null;
    if(rawAdapter && !adapter) throw new Error('Provide an HTTPS adapter ZIP link without credentials.');
    const model={kind:'report',has_adapter:adapter!==null};
    const data={schema:'dase7506/submission-v1',protocol:PROTOCOL,project:'mp3',student_id,
      score:scoreReport.accuracy,correct:scoreReport.correct,n:scoreReport.n,score_sha256:scoreHash,
      predictions_sha256:scoreReport.predictions_sha256,
      benchmark:{...MP3_EVALUATION},model};
    data.artifacts=await encryptArtifactLinks(code,adapter,'mp3');
    if(version!==formVersion) throw new Error('The form changed while preparing. Check your fields and prepare again.');
    if(!submissionsOpen()) throw new Error('Score submissions closed while preparing. The GitHub issue must be created before the deadline.');
    if(!validateSubmission(data)) throw new Error('Check the official test-score JSON and submission details. Describe your method and model, if any, in the report.');
    prepared($('submission-status'),makeIssueURL(data),'Score submission');
    $('code-url').value=''; $('adapter-url').value='';
  } catch(error) {$('submission-status').append(element('p',error.message,'error'));}
  finally {configureForm();}
});
function openChallenge(row) {
  challengeTarget=row;
  $('challenge-form').reset(); $('challenge-status').replaceChildren();
  $('email-report').href=`mailto:${REPORT_EMAIL}`;
  $('challenge-target').textContent=`MP3 · ${row.student_id} · #${row.number} · reported ${row.score.toFixed(2)}%`;
  $('challenge-dialog').showModal();
}
function peerReportData() {
  const score=$('reproduced-score').value.trim();
  return createPeerReviewReport(challengeTarget,snapshot.publication,{
    reproduced_score:score?Number(score):null,
    reason:$('review-reason').value,evidence_url:$('evidence-url').value,
  });
}
$('close-dialog').addEventListener('click',()=>$('challenge-dialog').close());
$('challenge-form').addEventListener('submit',event=>{
  event.preventDefault(); $('challenge-status').replaceChildren();
  try {prepared($('challenge-status'),makeIssueURL(peerReportData()),'Peer Review Report');}
  catch(error) {$('challenge-status').append(element('p',error.message,'error'));}
});
$('email-report').addEventListener('click',event=>{
  $('challenge-status').replaceChildren();
  if(!$('challenge-form').reportValidity()){event.preventDefault();return;}
  try {$('email-report').href=peerReviewEmailURL(peerReportData());}
  catch(error) {event.preventDefault();$('challenge-status').append(element('p',error.message,'error'));}
});
$('score-file').addEventListener('change',async()=>{
  scoreReport=null; scoreHash=null; loadedScoreFile=null; $('score').value='';
  const file=$('score-file').files[0];
  if(!file) {$('score-status').textContent='Select the complete outputs/test-score.json.';return;}
  $('score-status').textContent='Checking the local score file…';
  try {
    if(file.size>4*1024*1024) throw new Error('The score JSON must be at most 4 MiB.');
    const bytes=await file.arrayBuffer(), data=JSON.parse(new TextDecoder().decode(bytes));
    if(!validateMP3Score(data)) throw new Error('Use an unchanged, full 240-task test-score JSON from this starter package and scorer, not validation results or one-instance checks.');
    const hash=await crypto.subtle.digest('SHA-256',bytes);
    if($('score-file').files[0]!==file) return;
    scoreReport=data; loadedScoreFile=file;
    scoreHash=Array.from(new Uint8Array(hash),byte=>byte.toString(16).padStart(2,'0')).join('');
    $('score').value=`${data.correct} / ${data.n} = ${data.accuracy.toFixed(2)}%`;
    $('score-status').textContent='Full public test score loaded. This checks format and identity, not independent reproduction.';
  } catch(error) {
    if($('score-file').files[0]===file) $('score-status').textContent=`Score file rejected: ${error.message}`;
  }
});
configureForm();
refresh();
function refreshVisiblePage() {
  if(document.hidden) return;
  configureForm(); render(); refresh();
}
setInterval(refreshVisiblePage,30000);
document.addEventListener('visibilitychange',refreshVisiblePage);
window.addEventListener('focus',refreshVisiblePage);
window.addEventListener('online',refreshVisiblePage);

