"""Full-row C/Python references, complete codewords, handshakes and production lockstep."""
import ctypes
import argparse
import json
import random
import re
import time
from common import ROOT, FORMAL, CONFIGS, run, load_source, bits, sha, save_json


def decode_python(llr, rows, limit):
    channel = [max(-15,min(15,x)) for x in llr]
    v = list(channel)
    messages = [[0]*len(row) for row in rows]
    for it in range(1,max(1,min(200,limit))+1):
        for row,old in zip(rows,messages):
            ext=[max(-15,min(15,v[c]-msg)) for c,msg in zip(row,old)]
            mags=list(map(abs,ext)); ordered=sorted(mags)
            first=mags.index(ordered[0]); sign=sum(x<0 for x in ext)%2
            for j in range(len(row)):
                mag=ordered[1] if j==first else ordered[0]
                old[j]=(-1 if sign^(ext[j]<0) else 1)*(mag-(mag>>2))
        v=list(channel)
        for row,msg in zip(rows,messages):
            for c,x in zip(row,msg): v[c]=max(-15,min(15,v[c]+x))
        out=[int(x<0) for x in v]
        if all(sum(out[c] for c in row)%2==0 for row in rows): return out,it,0
    return out,it,1


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--lengths',type=int,nargs='+',default=list(CONFIGS))
    args_cli=parser.parse_args()
    start=time.time()
    work=ROOT/'build'
    work.mkdir(exist_ok=True)
    run(['gcc','-O2','-shared',ROOT/'tests/reference5.c','-o',work/'reference5.dll'])
    lib=ctypes.CDLL(str(work/'reference5.dll'))
    lib.decode5.argtypes=[ctypes.c_int,ctypes.c_int,ctypes.POINTER(ctypes.c_uint32),
        ctypes.POINTER(ctypes.c_uint16),ctypes.POINTER(ctypes.c_int8),ctypes.POINTER(ctypes.c_uint8),ctypes.c_int]
    report=[]
    previous_path=ROOT/'reports/verification.json'
    if set(args_cli.lengths)!=set(CONFIGS) and previous_path.exists():
        previous=json.loads(previous_path.read_text())
        assert all(sha(ROOT/'rtl'/name)==digest for name,digest in previous['rtl_hashes'].items())
        report=[entry for entry in previous['configurations'] if entry['N'] not in args_cli.lengths]
    for n in args_cli.lengths:
        assert n in CONFIGS
        cfg=json.loads((ROOT/f'generated/n{n}/config.json').read_text())
        data=json.loads((ROOT/f'generated/n{n}/matrix.json').read_text())
        k,z,rows,positions=cfg['K'],cfg['Z'],data['rows'],data['information_positions']
        source=load_source(n,ROOT/f'provenance/n{n}')
        offsets=[0]
        for row in rows: offsets.append(offsets[-1]+len(row))
        flat=[c for row in rows for c in row]
        coff=(ctypes.c_uint32*len(offsets))(*offsets)
        ccol=(ctypes.c_uint16*len(flat))(*flat)
        rng=random.Random(20261027+n)
        truth=0
        msg=[rng.getrandbits(1) for _ in range(k)]
        for b,row in zip(msg,source['generator']):
            if b: truth ^= bits(row)
        code=[(truth>>c)&1 for c in range(n)]
        assert [code[c] for c in positions]==msg
        assert all(sum(code[c] for c in row)%2==0 for row in rows)
        clean=[-35 if b else 35 for b in code]
        def noisy(p):
            result=[(-1 if b else 1)*rng.choice([2,4,6,9,14,20,28,35])*
                    (-1 if rng.random()<p else 1) for b in code]
            # Functional erasures, not an FER experiment or an aging profile.
            for j in range(n//32): result[(j*29)%n]=0
            return result
        frames=[('all_positive',[35]*n,200),('nonzero_codeword',clean,200),
            ('erased_noise',noisy(.025),12),('noise_failure',noisy(.18),4),
            ('signed_extremes',[rng.choice([-128,-127,127,0]) for _ in range(n)],2),
            ('zero_llr',[0]*n,0),('all_negative',[-35]*n,1),
            ('random_integer',[rng.randint(-128,127) for _ in range(n)],5),
            ('limit_clamp',[35]*n,255),
            ('full_200_failure',[rng.choice([-127,127]) for _ in range(n)],200)]
        records=[]; outputs=[]; full=[]; metas=[]
        vectors=work/f'n{n}'/'vectors';vectors.mkdir(parents=True,exist_ok=True)
        for name,llr,limit in frames:
            out=(ctypes.c_uint8*n)()
            rc=lib.decode5(n,n-k,coff,ccol,(ctypes.c_int8*n)(*llr),out,limit)
            actual,it,fail=list(out),rc or max(1,min(200,limit)),int(rc==0)
            py,pyit,pyfail=decode_python(llr,rows,limit)
            assert (actual,it,fail)==(py,pyit,pyfail),(n,name)
            outputs.append(sum(actual[c]<<j for j,c in enumerate(positions)))
            full.append(sum(b<<j for j,b in enumerate(actual)))
            metas.append((limit<<16)|(fail<<8)|it)
            records.append(dict(name=name,limit=limit,iterations=it,syndrome_fail=fail,
                                payload_matches_transmitted=([actual[c] for c in positions]==msg) if name!='all_positive' else None))
        (vectors/'inputs.hex').write_text(''.join(f'{x&255:02x}\n' for _,llr,_ in frames for x in llr))
        (vectors/'expected.hex').write_text(''.join(f'{v:0{k//4}x}\n' for v in outputs))
        (vectors/'full.hex').write_text(''.join(f'{v:0{n//4}x}\n' for v in full))
        (vectors/'meta.hex').write_text(''.join(f'{v:06x}\n' for v in metas))
        args=['iverilog','-g2012','-s','tb_stream',
              f'-Ptb_stream.N={n}',f'-Ptb_stream.K={k}',f'-Ptb_stream.Z={z}',
              f'-Ptb_stream.BASE_EDGES={cfg["base_edges"]}',
              f'-Ptb_stream.MAX_ROW_DEGREE={cfg["max_row_degree"]}',
              f'-Ptb_stream.FRAMES={len(frames)}',
              f'-Ptb_stream.MATRIX_DIR="{(ROOT/f"generated/n{n}").as_posix()}"',
              f'-Ptb_stream.VECTOR_DIR="{vectors.as_posix()}"',
              '-o',work/f'n{n}/sim.vvp',ROOT/'rtl/formal_nms_core.sv',
              ROOT/'rtl/proposed_formal_stream.sv',ROOT/'tb/tb_stream.sv']
        if n==4096:
            legacy='\n'.join((ROOT/'provenance/production_rtl'/name).read_text() for name in ['formal_nms_core.sv','proposed_formal_stream.sv'])
            for name in ['formal_nms_core','formal_sync_ram','formal_async_ram','proposed_formal_stream']:
                legacy=re.sub(r'\b'+name+r'\b',name+'_legacy',legacy)
            for name in ['base_edges.hex','base_rows.hex','output_positions.hex']:
                legacy=legacy.replace('generated/'+name,(ROOT/f'generated/n4096/{name}').as_posix())
            legacy_file=work/'production_lockstep.sv';legacy_file.write_text(legacy)
            args.insert(1,'-DLOCKSTEP')
            args.append(legacy_file)
        run(args)
        print(f'REFERENCE_PASS N={n}; starting RTL ({len(frames)} vectors)',flush=True)
        output=run(['vvp',work/f'n{n}/sim.vvp'],timeout=900)
        (work/f'n{n}/simulation.log').write_text(output)
        assert f'ALL_PASS N={n} frames={len(frames)}' in output,output
        if n==4096: assert 'LOCKSTEP_PASS' in output
        lines=re.findall(r'^PASS N=.*',output,re.M)
        assert len(lines)==len(frames)
        for record,line in zip(records,lines):
            record['rtl']={key:int(value) for key,value in re.findall(r'(\w+)=(\d+)',line)}
            assert record['iterations']==record['rtl']['iterations'] and record['syndrome_fail']==record['rtl']['fail']
        # Replay a prefix with deterministic input gaps and output backpressure.
        stalled=run(['vvp',work/f'n{n}/sim.vvp','+stalls','+frames=4'],timeout=900)
        (work/f'n{n}/backpressure.log').write_text(stalled)
        assert f'ALL_PASS N={n} frames=4 stalls=1' in stalled
        entry=dict(N=n,passed=True,C_python_agreement=True,full_codeword_checked=True,
                   reset_abort_checked=True,backpressure_checked=True,
                   production_cycle_lockstep=(n==4096),frames=records)
        report.append(entry)
        report.sort(key=lambda entry:entry['N'])
        save_json(ROOT/'reports/verification.json',dict(complete=(len(report)==len(CONFIGS)),configurations=report,
            rtl_hashes={p.name:sha(p) for p in (ROOT/'rtl').glob('*.sv')},elapsed_seconds=time.time()-start))
        print(f'RTL_PASS N={n} frames={len(frames)} continuous+stalled production_lockstep={n==4096}',flush=True)
    print(f'VERIFICATION_COMPLETE seconds={time.time()-start:.1f}',flush=True)


if __name__=='__main__': main()
