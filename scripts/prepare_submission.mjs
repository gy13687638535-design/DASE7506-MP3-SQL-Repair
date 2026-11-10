#!/usr/bin/env node
/** Prepare the exact official MP3 GitHub handoff offline; never publishes anything. */
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { resolve, dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash, webcrypto } from 'node:crypto';
import {
  PROTOCOL, MP3_EVALUATION, safeURL, validStudentID, validateMP3Score,
  validateSubmission, encryptArtifactLinks, makeIssueURL,
} from './official/arena.1b5f9fa2d0c3.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const allowed = new Set(['score', 'code-url', 'student-id', 'output-dir']);
const args = {};
for (let i = 2; i < process.argv.length; i += 2) {
  const key = process.argv[i].replace(/^--/, '');
  if (!process.argv[i].startsWith('--') || !allowed.has(key) || !process.argv[i + 1]) {
    throw new Error('Usage: node scripts/prepare_submission.mjs --score outputs/test-score.json --code-url HTTPS_IMMUTABLE_ZIP --student-id STUDENT_ID --output-dir submission-handoff');
  }
  args[key] = process.argv[i + 1];
}
if (!args.score || !args['code-url'] || !args['student-id'] || !args['output-dir']) {
  throw new Error('All four arguments --score, --code-url, --student-id, --output-dir are required.');
}
const bytes = await readFile(resolve(args.score));
if (bytes.length > 4 * 1024 * 1024) throw new Error('Official score exceeds 4 MiB.');
const score = JSON.parse(bytes.toString('utf8'));
if (!validateMP3Score(score)) throw new Error('The official validator rejected this full test score. Do not alter the scorer output.');
if (!validStudentID(args['student-id'])) throw new Error('Invalid student ID.');
const code = safeURL(args['code-url']);
if (!code) throw new Error('Expected an HTTPS source ZIP URL without credentials.');
const pem = await readFile(join(here, 'official', 'student-id-public.pem'), 'utf8');

// Supply only the already downloaded official public key. The official encryption
// implementation otherwise runs unchanged and no network requests are made.
Object.defineProperty(globalThis, 'isSecureContext', {value: true, configurable: true});
Object.defineProperty(globalThis, 'crypto', {value: webcrypto, configurable: true});
globalThis.fetch = async (url) => {
  if (url !== '../data/student-id-public.pem') throw new Error('Unexpected network request.');
  return new Response(pem, {status: 200});
};
const data = {
  schema: 'dase7506/submission-v1', protocol: PROTOCOL, project: 'mp3',
  student_id: args['student-id'], score: score.accuracy, correct: score.correct, n: score.n,
  score_sha256: createHash('sha256').update(bytes).digest('hex'),
  predictions_sha256: score.predictions_sha256,
  benchmark: {...MP3_EVALUATION}, model: {kind: 'report', has_adapter: false},
  artifacts: await encryptArtifactLinks(code, null, 'mp3'),
};
if (!validateSubmission(data)) throw new Error('Official submission payload validation failed.');
const issueURL = new URL(makeIssueURL(data));
const output = resolve(args['output-dir']);
await mkdir(output, {recursive: true});
await writeFile(join(output, 'payload.json'), JSON.stringify(data, null, 2) + '\n', 'utf8');
await writeFile(join(output, 'issue-body.md'), issueURL.searchParams.get('body') + '\n', 'utf8');
await writeFile(join(output, 'issue-title.txt'), issueURL.searchParams.get('title') + '\n', 'utf8');
await writeFile(join(output, 'issue-url.txt'), issueURL.href + '\n', 'utf8');
console.log(JSON.stringify({prepared: true, submitted: false, correct: score.correct, n: score.n,
  accuracy: score.accuracy, output_directory: output,
  target_repository: 'xudongwu-0/xudongwu-0.github.io'}, null, 2));
