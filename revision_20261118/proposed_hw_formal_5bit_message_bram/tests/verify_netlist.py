"""Check synthesized five-bit RAM and logic against dedicated C/Python vectors."""
from pathlib import Path
import json,os,subprocess,hashlib,time
ROOT=Path(__file__).resolve().parents[1]
VIVADO=Path('D:/vivado/Vivado/2022.2')
def run(args,log):
    p=subprocess.run([str(x) for x in args],cwd=ROOT,capture_output=True,text=True)
    log.write_text(p.stdout+'\n'+p.stderr,encoding='utf8')
    if p.returncode:raise RuntimeError((p.stdout+p.stderr)[-5000:])
    return p.stdout
def main():
    os.environ.setdefault('PROCESSOR_ARCHITECTURE','AMD64');start=time.time()
    work=ROOT/'build/netlist_sim';work.mkdir(exist_ok=True)
    netlist=ROOT/'build/message_bram/netlist.v'
    run([VIVADO/'bin/xvlog.bat','--sv','-d','SYNTH_NETLIST',netlist,
         ROOT/'tb/tb_stream.sv',VIVADO/'data/verilog/src/glbl.v'],work/'compile.log')
    run([VIVADO/'bin/xelab.bat','tb_stream','glbl','-L','unisims_ver','-s','formal_netlist_sim'],work/'elaborate.log')
    output=run([VIVADO/'bin/xsim.bat','formal_netlist_sim','-runall'],work/'simulation.log')
    assert 'ALL_PASS frames=3' in output,output[-5000:]
    result=dict(passed=True,frames=3,vector_indices=[0,1,4],simulation='Post-synthesis functional; no SDF',
                netlist_sha256=hashlib.sha256(netlist.read_bytes()).hexdigest(),seconds=time.time()-start)
    (ROOT/'reports/netlist_verification.json').write_text(json.dumps(result,indent=2),encoding='utf8')
    print(output[-2500:]);print(json.dumps(result,indent=2))
if __name__=='__main__':main()
