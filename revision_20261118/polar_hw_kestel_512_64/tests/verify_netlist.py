"""Vivado functional simulation of synthesized RAMs and instruction ROMs."""
import json,os,subprocess
from pathlib import Path
from verify_architecture import inputs,reference,polar_frozen_set
ROOT=Path(__file__).resolve().parents[1]
VIVADO=Path('D:/vivado/Vivado/2022.2')

def run(command,cwd,log):
    result=subprocess.run([str(x) for x in command],cwd=cwd,capture_output=True,text=True)
    log.write_text(result.stdout+'\n'+result.stderr,encoding='utf8')
    if result.returncode:
        print(result.stdout[-4000:]);print(result.stderr[-2000:]);raise SystemExit(result.returncode)
    return result.stdout

def main():
    os.environ.setdefault('PROCESSOR_ARCHITECTURE','AMD64')
    vectors=inputs(8,8); frozen=polar_frozen_set(); results=[]
    for variant,fast in [('exact8',False),('fast8',True)]:
        work=ROOT/'build/netlist_sim'/variant;work.mkdir(parents=True,exist_ok=True)
        (work/'input.hex').write_text(''.join(f'{v&255:02x}\n' for a in vectors for v in a),encoding='ascii')
        expected=[reference(a,frozen,8,fast) for a in vectors]
        (work/'expected.hex').write_text(''.join(f'{sum(v<<i for i,v in enumerate(row)):016x}\n' for row in expected),encoding='ascii')
        run([VIVADO/'bin/xvlog.bat','--sv','-d','SYNTH_NETLIST',ROOT/'build'/variant/'netlist.v',
             ROOT/'tb/tb_compare.sv',VIVADO/'data/verilog/src/glbl.v'],work,work/'compile.log')
        run([VIVADO/'bin/xelab.bat','tb_compare','glbl','-L','unisims_ver','-s','decoder_sim'],work,work/'elaborate.log')
        out=run([VIVADO/'bin/xsim.bat','decoder_sim','-runall'],work,work/'simulation.log')
        if 'PASS frames=8' not in out:raise RuntimeError(out[-4000:])
        print(variant+': '+next(line for line in out.splitlines() if 'PASS frames=' in line),flush=True)
        results.append(dict(variant=variant,frames=8,passed=True,simulation='post-synthesis functional, no SDF'))
    (ROOT/'build/netlist_verification.json').write_text(json.dumps(results,indent=2),encoding='utf8')

if __name__=='__main__':main()
