"""Check inferred memories and synthesized control against C/Python vectors."""
import json
import argparse
import os
from pathlib import Path
import subprocess
import time
from common import ROOT, CONFIGS, sha, save_json


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--lengths',type=int,nargs='+',default=list(CONFIGS))
    args=parser.parse_args()
    start=time.time()
    vivado=Path('D:/vivado/Vivado/2022.2')
    env=os.environ.copy();env.setdefault('PROCESSOR_ARCHITECTURE','AMD64')
    for key in ['SystemRoot','windir','TEMP','TMP','USERPROFILE','APPDATA','LOCALAPPDATA','ComSpec']:
        if key in env: env[key]=os.path.normpath(env[key])
    verification=json.loads((ROOT/'reports/verification.json').read_text())
    assert verification['complete']
    results=[]
    previous_path=ROOT/'reports/netlist_verification.json'
    if set(args.lengths)!=set(CONFIGS) and previous_path.exists():
        previous=json.loads(previous_path.read_text())
        results=[entry for entry in previous['configurations'] if entry['N'] not in args.lengths]
        for entry in results:
            assert sha(ROOT/f'build/n{entry["N"]}/synthesis/netlist.v')==entry['netlist_sha256']
    for n in args.lengths:
        assert n in CONFIGS
        config=json.loads((ROOT/f'generated/n{n}/config.json').read_text())
        work=ROOT/f'build/n{n}/netlist_sim';work.mkdir(parents=True,exist_ok=True)
        source=ROOT/f'build/n{n}/vectors'
        selected=[0,1,4]
        for name in ['inputs.hex','expected.hex','meta.hex']:
            lines=(source/name).read_text().splitlines()
            stride=n if name=='inputs.hex' else 1
            (work/name).write_text(''.join('\n'.join(lines[j*stride:(j+1)*stride])+'\n' for j in selected))
        record=next(r for r in verification['configurations'] if r['N']==n)
        (work/'cycles.hex').write_text(''.join(f'{record["frames"][j]["rtl"]["cycles"]:08x}\n' for j in selected))
        (work/'netlist_config.vh').write_text(f'`define CODE_N {n}\n`define CODE_K {config["K"]}\n`define CODE_TOP proposed_n{n}\n')
        def batch(stage,args,timeout=600):
            command='call '+subprocess.list2cmdline([str(v) for v in args])
            launch=work/f'{stage}.cmd'
            launch.write_text('@echo off\n'+command+'\nexit /b %errorlevel%\n',encoding='ascii')
            with (work/f'{stage}.log').open('w',encoding='utf8') as log:
                result=subprocess.run([env.get('ComSpec','cmd.exe'),'/d','/c',str(launch)],cwd=work,env=env,
                                      stdout=log,stderr=subprocess.STDOUT,timeout=timeout)
            text=(work/f'{stage}.log').read_text(encoding='utf8',errors='replace')
            assert result.returncode==0,text[-6000:]
            return text
        netlist=ROOT/f'build/n{n}/synthesis/netlist.v'
        print(f'NETLIST_START N={n}',flush=True)
        batch('compile',[vivado/'bin/xvlog.bat','--sv',netlist,ROOT/'tb/tb_netlist.sv',vivado/'data/verilog/src/glbl.v'])
        batch('elaborate',[vivado/'bin/xelab.bat','tb_netlist','glbl','-L','unisims_ver','-s','scaling_netlist'])
        output=batch('simulation',[vivado/'bin/xsim.bat','scaling_netlist','-runall'])
        assert f'NETLIST_ALL_PASS N={n} frames=3' in output,output[-4000:]
        results.append(dict(N=n,passed=True,frames=3,vector_indices=selected,
            simulation='Post-synthesis functional, no SDF',cycle_counts_match_RTL=True,
            netlist_sha256=sha(netlist)))
        results.sort(key=lambda entry:entry['N'])
        save_json(ROOT/'reports/netlist_verification.json',dict(complete=(len(results)==len(CONFIGS)),
            configurations=results,elapsed_seconds=time.time()-start))
        print(f'NETLIST_PASS N={n}',flush=True)
    print(f'NETLIST_VERIFICATION_COMPLETE seconds={time.time()-start:.1f}',flush=True)


if __name__=='__main__':main()
