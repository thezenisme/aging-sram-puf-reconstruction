"""Message-only BRAM: preserve five-bit arithmetic and exact cycle counts."""
from pathlib import Path
import ctypes,hashlib,json,os,random,re,subprocess,time
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run(cmd,cwd=ROOT):
    p=subprocess.run([str(v) for v in cmd],cwd=cwd,capture_output=True,text=True)
    if p.returncode:raise RuntimeError(p.stdout+'\n'+p.stderr)
    return p.stdout
def decode_python(llr,rows,limit):
    llr=[max(-15,min(15,x)) for x in llr]
    v=list(llr);messages=[[0]*len(r) for r in rows]
    for it in range(1,max(1,min(limit,200))+1):
        for r,old in zip(rows,messages):
            ext=[max(-15,min(15,v[c]-m)) for c,m in zip(r,old)]
            mags=[abs(x) for x in ext];a=sorted(mags)
            n1=a[0]-(a[0]>>2);n2=a[1]-(a[1]>>2)
            pos=mags.index(a[0]);sign=sum(x<0 for x in ext)%2
            for k in range(len(r)):old[k]=(-1 if sign^(ext[k]<0) else 1)*(n2 if k==pos else n1)
        v=list(llr)
        for r,msg in zip(rows,messages):
            for c,m in zip(r,msg):v[c]=max(-15,min(15,v[c]+m))
        bits=[int(x<0) for x in v]
        if all(sum(bits[c] for c in r)%2==0 for r in rows):return bits,it,0
    return bits,it,1
def main():
    start=time.time();work=ROOT/'build/verification';work.mkdir(parents=True,exist_ok=True)
    src=ROOT/'provenance/software'
    run(['gcc','-O2','-std=c99','-shared','-DTEST_LENGTH_LONG','-I'+str(src),ROOT/'tests/reference.c',src/'matrix_data_1_2_long.c','-o',work/'reference.dll'])
    lib=ctypes.CDLL(str(work/'reference.dll'))
    lib.reference_decode.argtypes=[ctypes.POINTER(ctypes.c_int8),ctypes.POINTER(ctypes.c_uint8),ctypes.c_int]
    lib.reference_decode5.argtypes=lib.reference_decode.argtypes
    lib.reference_encode.argtypes=[ctypes.POINTER(ctypes.c_uint8),ctypes.POINTER(ctypes.c_uint8)]
    matrix=json.loads((ROOT/'generated/matrix.json').read_text());rows=matrix['rows'];positions=matrix['information_positions']
    rng=random.Random(20261014)
    msg=[rng.getrandbits(1) for _ in range(2048)]
    code=(ctypes.c_uint8*4096)();lib.reference_encode((ctypes.c_uint8*2048)(*msg),code)
    code=list(code)
    assert all(sum(code[c] for c in r)%2==0 for r in rows)
    assert [code[c] for c in positions]==msg
    clean=[-35 if b else 35 for b in code]
    mags=[0,2,4,6,9,14,20,28,35]
    def noisy(p):
        v=clean.copy()
        for i in range(4096):
            a=rng.choice(mags[1:]);v[i]=(-a if code[i] else a)*(-1 if rng.random()<p else 1)
        # 128 test erasures spread within actual high-degree anchor groups.
        for j in range(128):v[(0,1280,2560)[j%3]+j//3]=0
        return v
    frames=[('all_positive',[35]*4096,200),('nonzero_codeword',clean,200),
        ('staircase_erased',noisy(.025),12),('noise_failure',noisy(.18),4),
        ('signed_extremes',[rng.choice([-128,-127,127,0]) for _ in range(4096)],2),
        ('zero_llr',[0]*4096,0),('all_negative',[-35]*4096,1),
        ('all_127',[127]*4096,3),('random_integer',[rng.randint(-128,127) for _ in range(4096)],5),
        ('limited_high_noise',noisy(.065),20),('limit_clamp',[35]*4096,255),
        ('full_200_iteration_failure',[rng.choice([-127,127]) for _ in range(4096)],200)]
    expected=[];metas=[];records=[];full=[]
    for name,llr,limit in frames:
        out=(ctypes.c_uint8*4096)();rc=lib.reference_decode5((ctypes.c_int8*4096)(*llr),out,limit)
        actual=list(out);it=rc or max(1,min(limit,200));fail=int(rc==0)
        py,pyit,pyfail=decode_python(llr,rows,limit)
        assert (actual,it,fail)==(py,pyit,pyfail),name
        old=(ctypes.c_uint8*4096)();old_rc=lib.reference_decode((ctypes.c_int8*4096)(*llr),old,limit)
        expected.append(sum(actual[c]<<i for i,c in enumerate(positions)))
        full.append(sum(b<<i for i,b in enumerate(actual)))
        metas.append((limit<<16)|(fail<<8)|it)
        truth=code if name in ['nonzero_codeword','staircase_erased','noise_failure','limited_high_noise'] else ([0]*4096 if name in ['all_positive','all_127','limit_clamp'] else None)
        records.append(dict(name=name,limit=limit,iterations=it,syndrome_fail=fail,
                            reference8_iterations=old_rc or max(1,min(limit,200)),
                            reference8_syndrome_fail=int(old_rc==0),
                            hard_bit_differences_from_8bit=sum(a!=b for a,b in zip(actual,old)),
                            codeword_bit_errors=(sum(a!=b for a,b in zip(actual,truth)) if truth is not None else None)))
    (work/'inputs.hex').write_text(''.join(f'{x&255:02x}\n' for _,llr,_ in frames for x in llr))
    (work/'expected.hex').write_text(''.join(f'{v:0512x}\n' for v in expected))
    (work/'full.hex').write_text(''.join(f'{v:01024x}\n' for v in full))
    (work/'meta.hex').write_text(''.join(f'{v:06x}\n' for v in metas))
    # Short post-synthesis vectors include saturation and a two-iteration
    # failure, without rerunning the 200-iteration RTL regression as gates.
    net=ROOT/'build/netlist_vectors';net.mkdir(exist_ok=True)
    selected=[0,1,4]
    (net/'inputs.hex').write_text(''.join(f'{x&255:02x}\n' for j in selected for x in frames[j][1]))
    (net/'expected.hex').write_text(''.join(f'{expected[j]:0512x}\n' for j in selected))
    (net/'full.hex').write_text(''.join(f'{full[j]:01024x}\n' for j in selected))
    (net/'meta.hex').write_text(''.join(f'{metas[j]:06x}\n' for j in selected))
    # Verify that the existing 5-bit inputs and expected results are unchanged.
    baseline=ROOT/'provenance/baseline_distributed'
    manifest=json.loads((baseline/'manifest.json').read_text())
    for name,h in manifest['file_hashes'].items():assert sha(baseline/name)==h,name
    baseline_provenance=json.loads((baseline/'reports/provenance.json').read_text())
    for name in ['inputs.hex','expected.hex','full.hex','meta.hex']:
        assert sha(work/name)==baseline_provenance['baseline_vector_hashes'][name],name
    # Generated, name-isolated baseline for cycle-by-cycle comparison. Never
    # modify the source baseline; compare all writes, consumed messages and
    # the public interface, including during abort/reset and backpressure.
    baseline_text='\n'.join((baseline/'rtl'/n).read_text() for n in ['formal_nms_core.sv','proposed_formal_stream.sv'])
    for old,new in [('formal_nms_core','baseline_nms_core'),('formal_async_ram','baseline_async_ram'),('proposed_formal_stream','baseline_formal_stream')]:
        baseline_text=baseline_text.replace(old,new)
    (work/'baseline_reference.sv').write_text(baseline_text,encoding='utf8')
    run(['iverilog','-g2012','-DLOCKSTEP','-s','tb_stream','-o',work/'sim.vvp',ROOT/'rtl/formal_nms_core.sv',ROOT/'rtl/proposed_formal_stream.sv',work/'baseline_reference.sv',ROOT/'tb/tb_stream.sv'])
    output=run(['vvp',work/'sim.vvp','+frames='+str(len(frames)),'+no_output_stalls'])
    (work/'simulation.log').write_text(output,encoding='utf8')
    assert f'ALL_PASS frames={len(frames)}' in output,output
    assert f'LOCKSTEP_PASS frames={len(frames)}' in output,output
    prefetch_reads=int(re.search(r'PREFETCH_PASS reads=(\d+)',output).group(1))
    assert prefetch_reads>0
    for record,line in zip(records,re.findall(r'PASS frame=.*',output)):
        record['cycles']=int(re.search(r'cycles=(\d+)',line).group(1));record['passed']=True
    previous=json.loads((baseline/'reports/rtl_verification.json').read_text())
    assert len(records)==len(previous['frames'])
    for a,b in zip(records,previous['frames']):
        for key in ['name','cycles','iterations','syndrome_fail','codeword_bit_errors']:
            assert a[key]==b[key],(a['name'],key,a[key],b[key])
    stalled=run(['vvp',work/'sim.vvp','+frames=3'])
    (work/'backpressure.log').write_text(stalled,encoding='utf8')
    assert 'ALL_PASS frames=3' in stalled,stalled
    result=dict(passed=True,reference='Explicit five-bit C variant plus independent Python; original C retained for differences',
        frames=records,seconds=time.time()-start,
        baseline_vector_hashes_match=True,baseline_cycles_match=True,backpressure_frames=3,
        lockstep_cycle_by_cycle=True,prefetch_checks=prefetch_reads,
        files={str(p.relative_to(ROOT)):sha(p) for p in [ROOT/'rtl/formal_nms_core.sv',ROOT/'rtl/proposed_formal_stream.sv',ROOT/'tb/tb_stream.sv',ROOT/'tests/reference.c']})
    (ROOT/'reports/rtl_verification.json').write_text(json.dumps(result,indent=2),encoding='utf8')
    print(output);print(json.dumps(result,indent=2))
if __name__=='__main__':main()
