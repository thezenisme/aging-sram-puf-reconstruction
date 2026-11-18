"""Check RTL with independent recursive SC / fast-SSC fixed-point models.
All output files stay in this copied project. These are functional tests,
not FER measurements. Baseline source is read-only.
"""
from __future__ import annotations
import argparse, hashlib, json, random, re, subprocess, sys, tempfile
from pathlib import Path
from check_core import polar_frozen_set, encode, N, K
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT  # Frozen baseline core is included in rtl/.

def reference(llr,frozen,q,fast):
    lo,hi=-(1<<(q-1)),(1<<(q-1))-1
    def visit(a,start):
        size=len(a); flags=[start+i in frozen for i in range(size)]
        if all(flags): return [0]*size,[0]*size
        if size==1:
            b=int(a[0]<0); return [b],[b]
        if fast and ((all(flags[:-1]) and not flags[-1]) or
                     (flags[0] and not any(flags[1:])) or not any(flags)):
            if all(flags[:-1]) and not flags[-1]:
                beta=[int(sum(a)<0)]*size
            else:
                beta=[int(v<0) for v in a]
                if flags[0] and not any(flags[1:]) and sum(beta)%2:
                    beta[min(range(size),key=lambda i:abs(a[i]))]^=1
            u=beta.copy(); step=1
            while step<size:
                for begin in range(0,size,2*step):
                    for j in range(step): u[begin+j]^=u[begin+step+j]
                step*=2
            return u,beta
        h=size//2
        left=[(-1 if (x<0)!=(y<0) else 1)*min(abs(x),abs(y),hi)
              for x,y in zip(a[:h],a[h:])]
        ul,bl=visit(left,start)
        right=[max(lo,min(hi,y+(-x if b else x))) for x,y,b in zip(a[:h],a[h:],bl)]
        ur,br=visit(right,start+h)
        return ul+ur,[x^y for x,y in zip(bl,br)]+br
    return [v for i,v in enumerate(visit(llr,0)[0]) if i not in frozen]

def inputs(q,frames):
    rng=random.Random(20261014+q); frozen=polar_frozen_set(); lo,hi=-(1<<(q-1)),(1<<(q-1))-1
    vectors=[]
    for frame in range(frames):
        if frame==0: a=[0]*N
        elif frame==1: a=[lo]*N
        elif frame==2: a=[hi]*N
        elif frame==3: a=[lo,hi,0,1,-1,lo,0,hi]*(N//8)
        elif frame%4==0: a=[rng.randint(lo,hi) for _ in range(N)]
        elif frame%4==1: a=[rng.choice([-1,0,1]) for _ in range(N)]
        else:
            u=[0]*N
            for i in range(N):
                if i not in frozen: u[i]=rng.randrange(2)
            codeword=encode(u)
            a=[(-1 if bit else 1)*rng.randint(1,hi) for bit in codeword]
            if frame>=8:
                for i in rng.sample(range(N),frame%97): a[i]=-a[i]
            else:
                message=[v for i,v in enumerate(u) if i not in frozen]
                assert reference(a,frozen,q,False)==message
                assert reference(a,frozen,q,True)==message
        vectors.append(a)
    return vectors

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--frames',type=int,default=128);args=parser.parse_args()
    frozen=polar_frozen_set(); results=[]; differences={}; wrappers=[]
    baseline_hash=hashlib.sha256((BASE/'rtl/polar_sc_core.sv').read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix='polar_arch_') as temp:
        tmp=Path(temp)
        for q in (8,4):
            vectors=inputs(q,args.frames)
            expected_by_mode={fast:[reference(a,frozen,q,fast) for a in vectors] for fast in (False,True)}
            differences[str(q)]=sum(a!=b for a,b in zip(expected_by_mode[False],expected_by_mode[True]))
            (tmp/'inputs.hex').write_text(''.join(f'{v & ((1<<q)-1):0{(q+3)//4}x}\n' for a in vectors for v in a),encoding='ascii')
            for name,fast,baseline in [('original',False,True),('exact',False,False),('fast',True,False)]:
                expected=expected_by_mode[fast]
                (tmp/'expected.hex').write_text(''.join(f'{sum(v<<i for i,v in enumerate(row)):016x}\n' for row in expected),encoding='ascii')
                command=['iverilog','-g2012','-s','tb_compare','-o',str(tmp/'sim.vvp'),
                         f'-Ptb_compare.Q={q}',f'-Ptb_compare.FAST={int(fast)}',f'-Ptb_compare.BASELINE={int(baseline)}',
                         str(BASE/'rtl/polar_sc_core.sv'),str(ROOT/'rtl/polar_sc_kestel.sv'),str(ROOT/'tb/tb_compare.sv')]
                subprocess.run(command,cwd=ROOT,check=True)
                run=subprocess.run(['vvp',str(tmp/'sim.vvp'),f'+stimuli={tmp}/inputs.hex',f'+expected={tmp}/expected.hex',
                                    f'+frames={args.frames}'],cwd=ROOT,check=False,capture_output=True,text=True)
                print(run.stdout.strip(),flush=True)
                if run.returncode:
                    print(run.stderr,flush=True)
                    raise SystemExit(run.returncode)
                cycles=int(re.search(r'decode_cycles=(\d+)',run.stdout)[1])
                results.append(dict(version=name,llr_bits=q,frames=args.frames,decode_cycles=cycles,
                                    cycles_with_512_inputs=cycles+512,passed=True))
        vectors=inputs(8,32)
        (tmp/'inputs.hex').write_text(''.join(f'{v & 255:02x}\n' for a in vectors for v in a),encoding='ascii')
        for name,fast in [('exact',False),('fast',True)]:
            expected=[reference(a,frozen,8,fast) for a in vectors]
            (tmp/'expected.hex').write_text(''.join(f'{sum(v<<i for i,v in enumerate(row)):016x}\n' for row in expected),encoding='ascii')
            subprocess.run(['iverilog','-g2012','-s','tb_polar_sc_2048','-o',str(tmp/'wrapper.vvp'),
                            f'-Ptb_polar_sc_2048.FAST={int(fast)}',
                            str(ROOT/'rtl/polar_sc_kestel.sv'),str(ROOT/'rtl/polar_sc_2048.sv'),
                            str(ROOT/'tb/tb_polar_sc_2048.sv')],cwd=ROOT,check=True)
            run=subprocess.run(['vvp',str(tmp/'wrapper.vvp'),f'+stimuli={tmp}/inputs.hex',f'+expected={tmp}/expected.hex'],
                               cwd=ROOT,capture_output=True,text=True,check=False)
            print(run.stdout.strip(),flush=True)
            if run.returncode: raise SystemExit(run.stderr)
            cycles=int(re.search(r'in (\d+) cycles',run.stdout)[1])
            wrappers.append(dict(mode=name,llr_bits=8,blocks=32,total_input_bits=16384,output_bits=2048,cycles=cycles,passed=True))
    (ROOT/'build').mkdir(exist_ok=True)
    report=dict(results=results,wrappers=wrappers,fast_vs_exact_different_frames=differences,
                note='Random stress vectors include saturation and ties; this is not a BER/FER experiment.',
                baseline_core_sha256=baseline_hash)
    (ROOT/'build/verification.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
