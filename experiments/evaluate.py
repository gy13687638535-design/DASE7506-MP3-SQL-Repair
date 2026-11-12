"""Isolated experiments using unchanged official predictor/scorer commands."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--package', type=Path, required=True)
    p.add_argument('--configs', nargs='+', required=True)
    p.add_argument('--split', choices=['validation','test'], default='validation')
    args = p.parse_args()
    env = os.environ.copy()
    env['PYTHONUTF8'] = '1'
    env['PYTHONPATH'] = os.pathsep.join([str(ROOT/'v2'), str(ROOT.parent/'.deps'), env.get('PYTHONPATH','')])
    output = ROOT/'results'
    output.mkdir(exist_ok=True)
    for name in args.configs:
        config = ROOT/'configs'/f'{name}.json'
        predictions = output/f'{args.split}-{name}.json'
        score = output/f'{args.split}-{name}-score.json'
        start = time.perf_counter()
        commands = [
            [sys.executable,'-m','mp3_sql.predict','--split',args.split,'--workers','4',
             '--method',str(ROOT/'v2'/'submission.py'),'--checkpoint',str(config),'--output',str(predictions)],
            [sys.executable,'-m','mp3_sql.score','--split',args.split,'--workers','4',
             '--predictions',str(predictions),'--output',str(score)]]
        for stage,cmd in zip(['predict','score'],commands):
            r = subprocess.run(cmd,cwd=args.package,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                               timeout=max(1,180-(time.perf_counter()-start)),text=True,encoding='utf8')
            (output/f'{args.split}-{name}-{stage}.log').write_text(r.stdout,encoding='utf8')
            if r.returncode:
                print(r.stdout,flush=True)
                raise RuntimeError(f'{name} {stage} failed')
        s=json.loads(score.read_text(encoding='utf8'))
        summary={'variant':name,'split':args.split,'correct':s['correct'],'n':s['n'],
                 'accuracy':s['accuracy'],'calls':s['mean_tool_calls'],'wall_seconds':time.perf_counter()-start}
        (output/f'{args.split}-{name}-summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf8')
        print(json.dumps(summary),flush=True)

if __name__=='__main__': main()
