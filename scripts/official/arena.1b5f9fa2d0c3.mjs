// Shared validation for the browser and the trusted snapshot builder. No dependencies.
export const REPO = 'xudongwu-0/xudongwu-0.github.io';
import {PROTOCOL, PROJECTS, MP3_EVALUATION, MP3_LORA_BASE} from './projects.96a85432df3c.mjs';
export {PROTOCOL, PROJECTS, MP3_EVALUATION, MP3_LORA_BASE};
export const KEY_ID = '7506-2026-v1';
export const REPORT_EMAIL = 'wu.xudong@connect.hku.hk';
export function validStudentID(value) {
  return typeof value==='string' && value.length>=1 && value.length<=64 && value===value.trim()
    && !/[\u0000-\u001f\u007f-\u009f\u202a-\u202e\u2066-\u2069]/u.test(value);
}
export function reviewStartTime(project, release) {
  return Date.parse(PROJECTS[project]?.review_deadline ? PROJECTS[project].score_deadline : release?.published_at);
}
export function reviewEndTime(project, release) {
  const start=reviewStartTime(project,release);
  if (!Number.isFinite(start)) return NaN;
  const deadline=PROJECTS[project]?.review_deadline ?? release?.review_ends_at;
  if (deadline != null) {
    const end=Date.parse(deadline);
    if (!Number.isFinite(end) || end<=start) throw new Error('Invalid instructor review deadline.');
    return end;
  }
  return start+(PROJECTS[project]?.review_days||7)*86400000;
}
export function submissionPhase(project, publication={}, now=Date.now()) {
  const config=PROJECTS[project], release=publication.projects?.[project];
  if (!config?.open) return 'closed';
  if (!config.score_deadline || +new Date(now)<Date.parse(config.score_deadline)) return 'scores';
  if (config.review_deadline) return +new Date(now)<reviewEndTime(project,release) ? 'review' : 'complete';
  if (!release || Date.parse(release.published_at)>+new Date(now)) return 'artifacts';
  return +new Date(now)<reviewEndTime(project,release) ? 'review' : 'complete';
}
export function validSealedArtifacts(d) {
  return d && d.algorithm==='RSA-OAEP-256+AES-256-GCM' && d.key_id===KEY_ID
    && typeof d.wrapped_key==='string' && /^[A-Za-z0-9+/]{512}$/.test(d.wrapped_key)
    && typeof d.iv==='string' && /^[A-Za-z0-9+/]{16}$/.test(d.iv)
    && typeof d.ciphertext==='string' && d.ciphertext.length>=24 && d.ciphertext.length<=4096
    && /^[A-Za-z0-9+/]+={0,2}$/.test(d.ciphertext);
}
let artifactPublicKeyPromise;
export async function encryptArtifactLinks(code, checkpoint, project, submission=null) {
  if(!globalThis.isSecureContext || !crypto.subtle) throw new Error('Open this page over HTTPS to encrypt your submission.');
  if(!artifactPublicKeyPromise) artifactPublicKeyPromise=(async()=>{
    const response=await fetch('../data/student-id-public.pem',{cache:'no-cache'});
    if(!response.ok) throw new Error('The encryption key could not be loaded. Please try again.');
    const pem=await response.text(), binary=atob(pem.replace(/-----[^-]+-----|\s/g,''));
    return crypto.subtle.importKey('spki',Uint8Array.from(binary,c=>c.charCodeAt(0)),{name:'RSA-OAEP',hash:'SHA-256'},false,['encrypt']);
  })().catch(error=>{artifactPublicKeyPromise=null;throw error;});
  const key=await crypto.subtle.generateKey({name:'AES-GCM',length:256},true,['encrypt']);
  const iv=crypto.getRandomValues(new Uint8Array(12));
  const text=JSON.stringify({schema:'dase7506/artifact-links-v1',project,submission,code_url:code,checkpoint_url:checkpoint});
  const ciphertext=await crypto.subtle.encrypt({name:'AES-GCM',iv},key,new TextEncoder().encode(text));
  const wrapped=await crypto.subtle.encrypt({name:'RSA-OAEP'},await artifactPublicKeyPromise,await crypto.subtle.exportKey('raw',key));
  const base64=bytes=>btoa(String.fromCharCode(...new Uint8Array(bytes)));
  return {algorithm:'RSA-OAEP-256+AES-256-GCM',key_id:KEY_ID,wrapped_key:base64(wrapped),iv:base64(iv),ciphertext:base64(ciphertext)};
}
export function validateArtifacts(d) {
  return d && d.schema==='dase7506/artifacts-v1' && d.protocol===PROTOCOL
    && Object.hasOwn(PROJECTS,d.project) && PROJECTS[d.project].open
    && Number.isSafeInteger(d.submission) && d.submission>0 && validSealedArtifacts(d.artifacts);
}
export function safeURL(value) {
  if (typeof value !== 'string' || value.length > 500 || /[\s<>`]/.test(value)) return null;
  try {
    const u = new URL(value);
    return u.protocol === 'https:' && !u.username && !u.password && u.hostname.includes('.') ? u.href : null;
  } catch { return null; }
}
export function validScore(project, score) {
  return Object.hasOwn(PROJECTS, project) && typeof score === 'number' && Number.isFinite(score)
    && (PROJECTS[project].min === null || score >= PROJECTS[project].min)
    && (PROJECTS[project].max === null || score <= PROJECTS[project].max);
}
export function validateSubmission(d) {
  return d && d.schema === 'dase7506/submission-v1' && d.protocol === PROTOCOL
    && validScore(d.project, d.score) && PROJECTS[d.project].open
    && (d.project!=='mp3' || validateMP3Details(d))
    && (d.code_url == null || d.code_url === '' || !!safeURL(d.code_url))
    && (d.checkpoint_url == null || d.checkpoint_url === '' || !!safeURL(d.checkpoint_url))
    && (d.artifacts == null || validSealedArtifacts(d.artifacts))
    && (validStudentID(d.student_id) || (d.student_id?.key_id === KEY_ID && d.student_id?.algorithm === 'RSA-OAEP-256'
    && typeof d.student_id?.ciphertext === 'string' && /^[A-Za-z0-9+/]{512}$/.test(d.student_id.ciphertext)));
}
export function validSHA256(value) {
  return typeof value==='string' && /^[a-f0-9]{64}$/.test(value);
}
export function hasMP3Adapter(model) {
  return model?.has_adapter===true || model?.kind==='lora' || !!model?.adapter_sha256;
}
function validMP3Counts(d) {
  return d.n===240 && Number.isSafeInteger(d.correct) && d.correct>=0 && d.correct<=240
    && typeof d.accuracy==='number' && Math.abs(d.accuracy-100*d.correct/d.n)<1e-10;
}
export function validateMP3Score(d) {
  if(!d || d.split!=='test' || !validMP3Counts(d)
    || !Object.entries(MP3_EVALUATION).every(([key,value])=>d[key]===value)
    || !validSHA256(d.predictions_sha256) || !Array.isArray(d.per_question)
    || d.per_question.length!==240 || new Set(d.per_question.map(row=>row?.id)).size!==240) return false;
  return d.per_question.every(row=>row && typeof row.id==='string' && row.id.length>0
    && Number.isSafeInteger(row.tool_calls) && row.tool_calls>=0 && row.tool_calls<=8
    && Array.isArray(row.cases) && row.cases.length===3
    && row.cases.every(item=>item && typeof item.passed==='boolean')
    && row.passed===row.cases.every(item=>item.passed))
    && d.per_question.filter(row=>row.passed).length===d.correct;
}
function validateMP3Details(d) {
  if(!validStudentID(d.student_id) || !validMP3Counts({...d,accuracy:d.score})
    || !validSHA256(d.score_sha256)
    || !validSHA256(d.predictions_sha256) || !validSealedArtifacts(d.artifacts)) return false;
  const fields=['schema','protocol','project','student_id','score','correct','n',
    'score_sha256','predictions_sha256','benchmark','model','artifacts'];
  if(Object.hasOwn(d,'source_sha256')) {
    if(!validSHA256(d.source_sha256)) return false;
    fields.push('source_sha256');
  }
  if(Object.keys(d).length!==fields.length || !fields.every(key=>Object.hasOwn(d,key))) return false;
  if(!d.benchmark || Object.keys(d.benchmark).length!==Object.keys(MP3_EVALUATION).length
    || !Object.entries(MP3_EVALUATION).every(([key,value])=>d.benchmark[key]===value)) return false;
  const model=d.model;
  if(model?.kind==='report') {
    if(Object.keys(model).length!==2) return false;
    return Object.hasOwn(model,'has_adapter') ? typeof model.has_adapter==='boolean'
      : Object.hasOwn(model,'adapter_sha256') && (model.adapter_sha256===null || validSHA256(model.adapter_sha256));
  }
  if(!model || !['none','public','lora'].includes(model.kind)) return false;
  if(model.kind==='none') return Object.keys(model).length===1;
  if(typeof model.repository!=='string' || !/^\w(?:[\w.-]*\w)?\/\w(?:[\w.-]*\w)?$/.test(model.repository)
    || /--|\.\./.test(model.repository) || model.repository.split('/').some(part=>part.length>96)
    || typeof model.revision!=='string' || !/^[a-f0-9]{40}$/.test(model.revision)
    || !Number.isSafeInteger(model.parameters) || model.parameters<1 || model.parameters>1000000000) return false;
  if(model.kind==='public') return Object.keys(model).length===4;
  return Object.keys(model).length===5 && model.repository===MP3_LORA_BASE.repository
    && model.revision===MP3_LORA_BASE.revision && model.parameters>MP3_LORA_BASE.parameters
    && validSHA256(model.adapter_sha256);
}
export function validateChallenge(d) {
  if(validatePeerReviewReport(d)) return true;
  return d && d.schema === 'dase7506/challenge-v1' && d.protocol === PROTOCOL
    && Number.isSafeInteger(d.submission) && d.submission > 0
    && validScore(d.project, d.reproduced_score) && PROJECTS[d.project].open && !!safeURL(d.evidence_url);
}
export function validatePeerReviewReport(d) {
  return d && d.schema==='dase7506/peer-review-v1' && d.protocol===PROTOCOL
    && Number.isSafeInteger(d.submission) && d.submission>0
    && validScore(d.project,d.reproduced_score) && PROJECTS[d.project].open
    && (d.reason==null || (typeof d.reason==='string' && d.reason.length<=2000))
    && (d.evidence_url==null || d.evidence_url==='' || !!safeURL(d.evidence_url));
}
export function createPeerReviewReport(target, publication, input, now=Date.now()) {
  if(!target || submissionPhase(target.project,publication,now)!=='review') throw new Error('Peer review reports are closed.');
  if(!validScore(target.project,input.reproduced_score)) throw new Error('Enter your reproduced score.');
  const reason=(input.reason??'').trim(), rawEvidence=(input.evidence_url??'').trim();
  const evidence=rawEvidence?safeURL(rawEvidence):null;
  if(reason.length>2000) throw new Error('Keep the optional report within 2,000 characters.');
  if(rawEvidence && !evidence) throw new Error('Check the optional HTTPS evidence link.');
  const threshold=PROJECTS[target.project].review_threshold;
  if(typeof threshold==='number' && Math.abs(input.reproduced_score-target.score)<=threshold) {
    throw new Error(`The difference does not exceed the review threshold of ${threshold} ${PROJECTS[target.project].unit}. Discuss general questions on the original submission.`);
  }
  const data={schema:'dase7506/peer-review-v1',protocol:PROTOCOL,project:target.project,
    submission:target.number,reason,reproduced_score:input.reproduced_score,evidence_url:evidence};
  if(!validatePeerReviewReport(data)) throw new Error('Enter a valid peer review report.');
  return data;
}
export function peerReviewEmailURL(data) {
  if(!validatePeerReviewReport(data)) throw new Error('Enter a valid reproduced score.');
  const subject=`[DASE7506] Peer Review Report · ${data.project.toUpperCase()} #${data.submission}`;
  const body=[`Submission: https://github.com/${REPO}/issues/${data.submission}`,
    `Project: ${data.project.toUpperCase()}`,`Reproduced score: ${data.reproduced_score} ${PROJECTS[data.project].unit}`,
    ...(data.evidence_url?[`Evidence: ${data.evidence_url}`]:[]),...(data.reason?['',data.reason]:[])].join('\n');
  return `mailto:${REPORT_EMAIL}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
}
export function validateReviewRequest(d) {
  return d && d.schema==='dase7506/review-request-v1' && d.protocol===PROTOCOL
    && Object.hasOwn(PROJECTS,d.project) && PROJECTS[d.project].open
    && Number.isSafeInteger(d.submission) && d.submission>0
    && typeof d.reason==='string' && d.reason.trim().length>=10 && d.reason.length<=2000
    && (d.evidence_url==null || !!safeURL(d.evidence_url))
    && (d.reproduced_score==null || validScore(d.project,d.reproduced_score));
}
export function parseIssue(issue) {
  if (issue.pull_request || issue.user?.type !== 'User' || !Number.isSafeInteger(issue.number)) return null;
  const body = issue.body || '';
  if (body.length > 12000) return null;
  const blocks = [...body.matchAll(/```json\s*\n([\s\S]*?)\n```/g)];
  if (blocks.length !== 1) return null;
  try {
    const d = JSON.parse(blocks[0][1]);
    if (!validateSubmission(d) && !validateChallenge(d) && !validateArtifacts(d) && !validateReviewRequest(d)) return null;
    return {data: d, number: issue.number, author: issue.user.login,
      url: `https://github.com/${REPO}/issues/${issue.number}`,
      created_at: issue.created_at, updated_at: issue.updated_at,
      labels: (issue.labels || []).map(l => typeof l === 'string' ? l : l.name),
      closed: issue.state === 'closed'};
  } catch { return null; }
}
export function makeIssueURL(data) {
  const submission = validateSubmission(data);
  const artifacts=validateArtifacts(data);
  const review=validateReviewRequest(data)||validatePeerReviewReport(data);
  if (!submission && !validateChallenge(data) && !artifacts && !review) throw new Error('Invalid submission data.');
  const title = submission
    ? `[DASE7506] ${data.project.toUpperCase()} · ${data.score} ${PROJECTS[data.project].unit}`
    : artifacts ? `[DASE7506 artifacts] #${data.submission}` : `[DASE7506 Peer Review Report] #${data.submission}`;
  const intro = submission
    ? (data.project==='mp3'
      ? 'Self-reported public test result, subject to instructor reproduction and compliance checks. Student IDs, scores and evaluation metadata are public. Artifact URLs are sealed until the instructor publishes them for peer review. GitHub retains the submitting account.\n\nKeep the JSON unchanged. Submit improvements as new issues before the score deadline.'
      : 'Self-reported score. The leaderboard displays student IDs and scores. Artifact links are sealed for the instructor until release. GitHub records retain the submitting account.\n\nKeep the JSON unchanged. Submit improvements as new issues before the score deadline.')
    : artifacts ? 'Sealed code and checkpoint links for an existing score submission. The instructor will publish links together for a seven-day review. Keep the JSON unchanged.'
    : 'Peer review report, pending instructor review. Your GitHub account and report are public. Use the same checkpoint and evaluator. Reports alone do not affect grades.';
  const body = `${intro}\n\n\`\`\`json\n${JSON.stringify(data, null, 2)}\n\`\`\``;
  const url = new URL(`https://github.com/${REPO}/issues/new`);
  url.searchParams.set('title', title);
  url.searchParams.set('body', body);
  return url.href;
}
function buildBaseSnapshot(issues, previous = {}, now = new Date().toISOString()) {
  const parsed = issues.map(parseIssue).filter(Boolean);
  const old = new Map((previous.submissions || []).map(s => [s.number, s]));
  const submissions = parsed.filter(p => validateSubmission(p.data)).map(p => {
    const d = p.data;
    // Bind reviewed status to the exact submitted payload. Edits need another review.
    const parts=[d.project, d.score, d.code_url, d.checkpoint_url, d.student_id, d.artifacts || null];
    if(d.project==='mp3') parts.push({correct:d.correct,n:d.n,source_sha256:d.source_sha256,
      score_sha256:d.score_sha256,predictions_sha256:d.predictions_sha256,benchmark:d.benchmark,model:d.model});
    const signature = JSON.stringify(parts);
    const prior = old.get(p.number);
    // An author cannot erase an adjudicated submission by editing its body.
    if (prior?.status === 'invalid' && p.labels.includes('7506:invalid')) return prior;
    const priorParts=prior?.signature ? JSON.parse(prior.signature) : null;
    if(priorParts?.length===5) priorParts.push(null);
    const changed = !!prior && JSON.stringify(priorParts) !== signature;
    const reviewChanged = prior && JSON.stringify(prior.review_labels) !== JSON.stringify(p.labels.filter(l => l.startsWith('7506:')).sort());
    const editedAfterReview = changed || (!!prior?.edited_after_review && !reviewChanged);
    const status = p.labels.includes('7506:invalid') ? 'invalid'
      : p.labels.includes('7506:review') || editedAfterReview ? 'review'
      : p.closed ? 'withdrawn' : p.labels.includes('7506:verified') ? 'verified' : 'self-reported';
    return {number: p.number, author: p.author, student_id:validStudentID(d.student_id)?d.student_id:null, url: p.url, project: d.project,
      score: d.score, code_url: d.code_url, checkpoint_url: d.checkpoint_url,
      ...(d.project==='mp3'?{correct:d.correct,n:d.n,model_kind:d.model.kind,
        source_sha256:d.source_sha256,score_sha256:d.score_sha256,
        predictions_sha256:d.predictions_sha256,benchmark:d.benchmark,model:d.model,
        code_url:null,checkpoint_url:null,artifact_status:'received'}:{}),
      status, created_at: p.created_at, signature, edited_after_review: editedAfterReview,
      review_labels: p.labels.filter(l => l.startsWith('7506:')).sort()};
  });
  for (const prior of old.values()) {
    if (prior.status === 'invalid' && !submissions.some(s => s.number === prior.number)
      && issues.some(i => i.number === prior.number && (i.labels || []).some(l => (l.name || l) === '7506:invalid'))) submissions.push(prior);
  }
  const byNumber = new Map(submissions.map(s => [s.number, s]));
  const priorChallenges = new Map((previous.challenges || []).map(c => [c.number, c]));
  const challenges = parsed.filter(p => validateChallenge(p.data)).map(p => {
    const prior = priorChallenges.get(p.number);
    if (prior?.status === 'upheld' && p.labels.includes('7506:upheld') && byNumber.get(prior.submission)?.status === 'invalid') return prior;
    const d = p.data, target = byNumber.get(d.submission);
    if (!target || target.project !== d.project || target.author.toLowerCase() === p.author.toLowerCase()) return null;
    const difference = Math.abs(target.score - d.reproduced_score);
    const threshold = PROJECTS[d.project].review_threshold;
    // Labels can only be applied by repository maintainers. Both decisions are needed.
    const upheld = p.labels.includes('7506:upheld') && target.status === 'invalid'
      && (typeof threshold !== 'number' || difference > threshold);
    return {number: p.number, author: p.author, url: p.url, submission: d.submission,
      project: d.project, reproduced_score: d.reproduced_score, evidence_url: d.evidence_url,
      created_at: p.created_at, status: upheld ? 'upheld' : p.labels.includes('7506:rejected') ? 'rejected' : 'pending'};
  }).filter(Boolean);
  for (const prior of priorChallenges.values()) {
    if (prior.status === 'upheld' && !challenges.some(c => c.number === prior.number)
      && byNumber.get(prior.submission)?.status === 'invalid'
      && issues.some(i => i.number === prior.number && (i.labels || []).some(l => (l.name || l) === '7506:upheld'))) challenges.push(prior);
  }
  challenges.sort((a,b) => a.number - b.number);
  const adjustments = new Map(), awarded = new Set();
  for (const c of challenges.filter(c => c.status === 'upheld')) {
    if (awarded.has(c.submission)) continue;
    awarded.add(c.submission);
    const target = byNumber.get(c.submission);
    for (const [author, kind] of [[target.author, 'penalty'], [c.author, 'reward']]) {
      const key = `${c.project}/${author}`;
      const a = adjustments.get(key) || {project: c.project, author, reward: 0, penalty: 0};
      a[kind] = PROJECTS[c.project][kind];
      adjustments.set(key, a);
    }
  }
  return {schema: 'dase7506/board-v1', protocol: PROTOCOL, generated_at: now,
    submissions: submissions.sort((a,b) => a.number - b.number), challenges,
    adjustments: [...adjustments.values()]};
}
export function bestRows(submissions, project, history = false) {
  let rows = submissions.filter(s => s.project === project);
  if (!history) {
    rows = rows.filter(s => ['self-reported','verified'].includes(s.status));
    const best = new Map();
    for (const s of rows) {
      // A teacher account can publish several named baselines. Only repeated
      // results for the same Student ID and account compete for one entry.
      // Legacy encrypted IDs keep their account grouping until resolved.
      const key = JSON.stringify([validStudentID(s.student_id) ? s.student_id : null, s.author.toLowerCase()]);
      const old = best.get(key);
      const better=!old || (PROJECTS[project].lower ? s.score < old.score : s.score > old.score);
      const available=row=>Number(!!row.code_url)+Number(!!row.checkpoint_url);
      if (better || (old && s.score===old.score && available(s)>available(old))) best.set(key, s);
    }
    rows = [...best.values()];
  }
  return rows.sort((a,b) => (PROJECTS[project].lower ? a.score - b.score : b.score - a.score) || a.number - b.number);
}

// Instructor entries follow the latest result, retaining reports on every earlier
// result. This is a derived view: raw submissions and student ranking stay intact.
export function instructorRows(snapshot) {
  const groups=new Map(), accountsByID=new Map(), groupBySubmission=new Map();
  for(const row of snapshot.submissions||[]) {
    const account=row.author.toLowerCase(), knownID=validStudentID(row.student_id);
    // Unresolved legacy IDs are separate records, never a shared "ID pending" ID.
    const key=JSON.stringify([row.project,knownID?row.student_id:null,account,knownID?null:row.number]);
    if(!groups.has(key)) groups.set(key,{history:[],requests:[]});
    groups.get(key).history.push(row);
    groupBySubmission.set(row.number,groups.get(key));
    if(knownID) {
      if(!accountsByID.has(row.student_id)) accountsByID.set(row.student_id,new Set());
      accountsByID.get(row.student_id).add(account);
    }
  }
  for(const request of snapshot.review_requests||[]) {
    const group=groupBySubmission.get(request.submission);
    if(group && group.history[0].project===request.project) group.requests.push(request);
  }
  return [...groups].map(([key,{history,requests}])=>{
    const dated=history.every(row=>Number.isFinite(Date.parse(row.created_at)));
    history.sort((a,b)=>(dated?Date.parse(b.created_at)-Date.parse(a.created_at):0)||b.number-a.number);
    const latest=history[0];
    const accounts=[...(accountsByID.get(latest.student_id)||[])].sort();
    const active=new Set(requests.filter(r=>['pending','upheld'].includes(r.status)).map(r=>r.author.toLowerCase()));
    const threshold=PROJECTS[latest.project]?.review_request_flag_above??3;
    const reasons=[];
    if(accounts.length>1) reasons.push('Student ID used by multiple GitHub accounts');
    if(active.size>threshold) reasons.push(`More than ${threshold} active reporters`);
    return {...latest,review_group_key:key,submission_history:history,
      submission_numbers:history.map(r=>r.number),review_requests:requests,
      review_request_total:requests.length,review_request_count:active.size,
      review_accounts:accounts,review_flag_reasons:reasons,review_flag:reasons.length>0};
  }).sort((a,b)=>Number(b.review_flag)-Number(a.review_flag)||a.number-b.number);
}

// Deadline and publication policy wraps the existing review/adjudication rules.
export function buildSnapshot(issues, previous={}, now=new Date().toISOString(), publication={projects:{}}, metadata={}) {
  const instant=+new Date(now), old=new Map((previous.submissions||[]).map(r=>[r.number,r]));
  const lateEdits=new Set(), uncertain=new Set();
  const effective=issues.map(original=>{
    let issue=original;
    const manual=Object.entries(publication.projects||{}).flatMap(([project,release])=>(release.entries||[]).map(entry=>({project,...entry})))
      .find(entry=>entry.instructor_recorded_score===true && entry.instructor_accepted===true && entry.submission===issue.number
        && entry.author.toLowerCase()===issue.user?.login?.toLowerCase() && validStudentID(entry.student_id)
        && validScore(entry.project,entry.score) && safeURL(entry.code_url) && safeURL(entry.checkpoint_url));
    if(manual) {
      const data={schema:'dase7506/submission-v1',protocol:PROTOCOL,project:manual.project,student_id:manual.student_id,
        score:manual.score,code_url:manual.code_url,checkpoint_url:manual.checkpoint_url};
      issue={...issue,body:'```json\n'+JSON.stringify(data)+'\n```'};
    }
    const prior=old.get(issue.number), parsed=parseIssue(issue);
    if (!prior || !PROJECTS[prior.project]?.score_deadline || instant<Date.parse(PROJECTS[prior.project].score_deadline)) return issue;
    if (!prior.signature) return issue;
    const [project,score,code_url,checkpoint_url,student_id,artifacts,details]=JSON.parse(prior.signature);
    if (parsed && validateSubmission(parsed.data) && parsed.data.score!==score) lateEdits.add(issue.number);
    const frozen={schema:'dase7506/submission-v1',protocol:PROTOCOL,project,score,student_id,
      ...(project==='mp3'?details:{code_url,checkpoint_url}),artifacts};
    return {...issue,body:'```json\n'+JSON.stringify(frozen)+'\n```'};
  }).filter(issue=>{
    const parsed=parseIssue(issue);
    if (!parsed || !validateChallenge(parsed.data) || !PROJECTS[parsed.data.project].score_deadline) return true;
    const release=publication.projects?.[parsed.data.project];
    const start=reviewStartTime(parsed.data.project,release), end=reviewEndTime(parsed.data.project,release);
    return Number.isFinite(start) && Date.parse(parsed.created_at)>=start && Date.parse(parsed.created_at)<end;
  });
  const result=buildBaseSnapshot(effective,previous,now);
  const raw=new Map(issues.map(i=>[i.number,i]));
  // Keep the score record even if its issue is removed after the deadline.
  for(const prior of old.values()) {
    if(PROJECTS[prior.project]?.score_deadline && instant>=Date.parse(PROJECTS[prior.project].score_deadline)
      && !result.submissions.some(r=>r.number===prior.number)) result.submissions.push({...prior,status:prior.status==='invalid'?'invalid':'withdrawn'});
  }
  const receipts=issues.map(parseIssue).filter(p=>p && validateArtifacts(p.data))
    .sort((a,b)=>a.number-b.number);
  for(const row of result.submissions) {
    const config=PROJECTS[row.project];
    const identity=JSON.parse(row.signature)[4], legacy=metadata.identities?.[row.number];
    if(!validStudentID(row.student_id) && validStudentID(legacy?.student_id) && legacy.source_ciphertext===identity?.ciphertext) row.student_id=legacy.student_id;
    if(!config.score_deadline) continue;
    const deadline=Date.parse(config.score_deadline), prior=old.get(row.number), issue=raw.get(row.number);
    const release=publication.projects?.[row.project];
    const accepted=release?.entries?.find(e=>e.instructor_accepted===true && e.submission===row.number
      && e.student_id===row.student_id && e.author.toLowerCase()===row.author.toLowerCase() && e.score===row.score);
    if(accepted) {
      row.instructor_entered=true;
      if(accepted.late_submission===true) row.late_submission=true;
    }
    if(publication.superseded_submissions?.[row.project]?.includes(row.number)
      && ['self-reported','verified'].includes(row.status)) row.status='superseded';
    if(Date.parse(row.created_at)>=deadline && !accepted) row.status='late';
    if(instant>=deadline && Date.parse(row.created_at)<deadline && !prior && issue && Date.parse(issue.updated_at)>deadline && !accepted) {
      row.status='review'; uncertain.add(row.number);
    }
    if(lateEdits.has(row.number)) row.late_score_edit_ignored=true;
    if(prior?.late_score_edit_ignored) row.late_score_edit_ignored=true;
    if(uncertain.has(row.number)) row.deadline_review_required=true;
    if(prior?.deadline_review_required && !accepted && !row.review_labels.includes('7506:verified')) {
      row.deadline_review_required=true;
      if(!['invalid','withdrawn','late'].includes(row.status)) row.status='review';
    }
    const phase=submissionPhase(row.project,publication,instant);
    const source=parseIssue(issue||{});
    const previousArtifact=raw.get(prior?.artifact_issue);
    row.artifact_issue=previousArtifact && previousArtifact.state!=='closed' ? prior.artifact_issue
      : (source?.data.artifacts || (source?.data.code_url && source?.data.checkpoint_url) ? row.number : null);
    for(const p of receipts) {
      if(p.data.submission!==row.number || p.data.project!==row.project || p.author.toLowerCase()!==row.author.toLowerCase() || p.closed) continue;
      if(release && Date.parse(p.created_at)>=Date.parse(release.published_at)) continue;
      row.artifact_issue=p.number;
    }
    row.artifact_status=row.artifact_issue ? 'received' : 'pending';
    const published=['review','complete'].includes(phase)
      ? release?.entries?.find(e=>e.submission===row.number && e.author.toLowerCase()===row.author.toLowerCase() && e.score===row.score) : null;
    row.code_url=published?.code_url || null;
    row.checkpoint_url=published?.checkpoint_url || null;
    row.artifact_access={code:publication.link_checks?.[row.code_url]||null,checkpoint:publication.link_checks?.[row.checkpoint_url]||null};
    const adapterRequired=row.project==='mp3' && hasMP3Adapter(row.model);
    if(published) row.artifact_status=row.code_url && (row.project==='mp3' ? !adapterRequired || row.checkpoint_url : row.checkpoint_url)
      ? 'published' : row.code_url || row.checkpoint_url ? 'partial' : 'missing';
    else if(['review','complete'].includes(phase) && release && Date.parse(release.published_at)<=instant
      && ['self-reported','verified'].includes(row.status)) row.status='links-missing';
  }
  // The release file is teacher-controlled. Unreleased links never enter new
  // score signatures: the browser seals them before creating a public issue.
  result.publication={schema:'dase7506/publication-v1',projects:{}};
  for(const [id,release] of Object.entries(publication.projects||{})) {
    if(Date.parse(release.published_at)<=instant) result.publication.projects[id]={
      published_at:release.published_at,
      review_ends_at:new Date(reviewEndTime(id,release)).toISOString()
    };
  }
  result.phases=Object.fromEntries(Object.keys(PROJECTS).map(id=>[id,submissionPhase(id,publication,instant)]));
  // Teacher overview only: keep counts and reporter identities off the student UI.
  // Source issues remain public GitHub records; these statistics are not secret.
  const acceptedChallenges=new Map(result.challenges.map(c=>[c.number,c]));
  result.review_requests=issues.map(parseIssue).filter(p=>p && (validateReviewRequest(p.data)||validatePeerReviewReport(p.data)||acceptedChallenges.has(p.number))).map(p=>{
    const challenge=acceptedChallenges.get(p.number), target=result.submissions.find(s=>s.number===(challenge?.submission??p.data.submission));
    if(!target || target.project!==(challenge?.project??p.data.project)) return null;
    const self=p.author.toLowerCase()===target.author.toLowerCase();
    const release=publication.projects?.[target.project];
    const fixedReview=!!PROJECTS[target.project].review_deadline;
    const start=fixedReview ? reviewStartTime(target.project,release) : -Infinity;
    const end=release || fixedReview ? reviewEndTime(target.project,release) : Infinity;
    const status=self?'self-request':Date.parse(p.created_at)<start?'early':Date.parse(p.created_at)>=end?'late':p.labels.includes('7506:rejected')?'rejected':p.closed?'closed':!validScore(target.project,challenge?.reproduced_score??p.data.reproduced_score)?'score-missing':challenge?.status||'pending';
    return {number:p.number,submission:target.number,project:target.project,author:p.author,url:p.url,
      reason:p.data.reason||'',evidence_url:challenge?.evidence_url||p.data.evidence_url||null,
      reproduced_score:challenge?.reproduced_score??p.data.reproduced_score??null,created_at:p.created_at,status};
  }).filter(Boolean).sort((a,b)=>a.number-b.number);
  for(const row of result.submissions) {
    const requests=result.review_requests.filter(r=>r.submission===row.number);
    row.review_request_total=requests.length;
    row.review_request_count=new Set(requests.filter(r=>['pending','upheld'].includes(r.status)).map(r=>r.author.toLowerCase())).size;
    row.review_flag=row.review_request_count>(PROJECTS[row.project].review_request_flag_above??3);
  }
  result.snapshot_version=2;
  return result;
}

