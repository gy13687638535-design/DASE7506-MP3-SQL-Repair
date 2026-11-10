// MP1 is archived; MP3 accepts public-benchmark self-reports.
export const PROTOCOL = '7506-submissions-v1';
export const MP3_EVALUATION = Object.freeze({
  protocol:'dase7506-sql-repair-v1',
  benchmark:'spider-sql-repair-public-evaluation-v3',
  manifest_sha256:'bf7a517249ebe31b9cad8cbf5d6598fde98316d89f9aa1172cae3ad83289a6bc',
  bank_sha256:'598b1a072a47cdcf7308dc5646ae2bffd356390ab8df533510b69f2c884d712c',
  references_sha256:'8be5f2746ee324d6b4b880dd84a2f8de56fa540af08e93842c0476adec581506',
  scorer_sha256:'87870af26173fbe6d8994e4de179fb272ef1fadf7dcaafc2e7b4c814c61ec95b',
  executor_sha256:'4ecc3839728d68bd83f0d2a52cdd8392fd76dbaec3e54a19422118dee587b471',
});
export const MP3_LORA_BASE = Object.freeze({
  repository:'Qwen/Qwen3-0.6B',
  revision:'c1899de289a04d12100db370d81485cdf75e47ca',
  parameters:596049920,
});
export const PROJECTS = {
  mp1: {name:'Small Language Model Challenge', unit:'BPB', lower:true, open:true, min:0, max:null, review_threshold:null, review_request_flag_above:3, reward:0, penalty:0, score_deadline:'2026-10-01T00:00:00+08:00', review_days:7},
  mp2: {name:'Selecting Reliable LLM Reasoning', unit:'%', lower:false, open:true, min:0, max:100, review_threshold:null, review_request_flag_above:3, reward:0, penalty:0, score_deadline:'2026-11-01T00:00:00+08:00', review_days:7},
  mp3: {name:'SQL Repair Agent', unit:'%', lower:false, open:true, min:0, max:100, review_threshold:null, review_request_flag_above:3, reward:0, penalty:0, score_deadline:'2026-12-01T00:00:00+08:00', review_days:7, review_deadline:'2026-12-08T00:00:00+08:00'},
};

