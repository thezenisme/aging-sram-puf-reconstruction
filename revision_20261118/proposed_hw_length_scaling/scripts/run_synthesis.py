"""Run fresh OOC synthesis only after all functional checks have passed."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time
from common import ROOT, CONFIGS, sha, save_json


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--vivado',default='D:/vivado/Vivado/2022.2/bin/vivado.bat')
    parser.add_argument('--lengths',type=int,nargs='+',default=list(CONFIGS))
    args=parser.parse_args()
    verification=json.loads((ROOT/'reports/verification.json').read_text())
    assert verification['complete'] and all(v['passed'] for v in verification['configurations'])
    for name,digest in verification['rtl_hashes'].items():
        assert sha(ROOT/'rtl'/name)==digest,'RTL changed after verification; rerun verify.py'
    start=time.time()
    records=[]
    previous_path=ROOT/'reports/synthesis.json'
    if set(args.lengths)!=set(CONFIGS) and previous_path.exists():
        previous=json.loads(previous_path.read_text())
        records=[entry for entry in previous['configurations'] if entry['N'] not in args.lengths]
        for entry in records:
            assert sha(ROOT/f'build/n{entry["N"]}/synthesis/utilization_synth.rpt')==entry['report_sha256']
    env=os.environ.copy()
    for key in ['SystemRoot','windir','TEMP','TMP','USERPROFILE','APPDATA','LOCALAPPDATA','ComSpec']:
        if key in env:
            env[key]=os.path.normpath(env[key])
    # The Codex shell may omit this Windows variable; Xilinx loader requires it.
    env.setdefault('PROCESSOR_ARCHITECTURE','AMD64')
    for n in args.lengths:
        assert n in CONFIGS
        output=ROOT/f'build/n{n}/synthesis'
        output.mkdir(parents=True,exist_ok=True)
        command=f'call "{args.vivado}" -mode batch -log "{output / "vivado.log"}" -journal "{output / "vivado.jou"}" -source "{ROOT / "scripts/synth.tcl"}" -tclargs {n}'
        launcher=output/'run_vivado.cmd'
        launcher.write_text('@echo off\n'+command+'\nexit /b %errorlevel%\n',encoding='ascii')
        print(f'SYNTHESIS_START N={n}',flush=True)
        with (output/'console.log').open('w',encoding='utf8') as log:
            result=subprocess.run([env.get('ComSpec','cmd.exe'),'/d','/c',str(launcher)],
                                  cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=1200)
        console=(output/'console.log').read_text(encoding='utf8',errors='replace')
        assert result.returncode==0 and f'SCALING_SYNTH_COMPLETE N={n}' in console, console[-6000:]
        records.append(dict(N=n,passed=True,report_sha256=sha(output/'utilization_synth.rpt'),
            part='xczu3eg-sfvc784-1-i',tool='Vivado 2022.2',mode='out_of_context',clock_constraint=None))
        records.sort(key=lambda entry:entry['N'])
        save_json(ROOT/'reports/synthesis.json',dict(complete=(len(records)==len(CONFIGS)),
            configurations=records,elapsed_seconds=time.time()-start))
        print(f'SYNTHESIS_PASS N={n}',flush=True)
    print(f'SYNTHESIS_COMPLETE seconds={time.time()-start:.1f}',flush=True)


if __name__=='__main__':main()
