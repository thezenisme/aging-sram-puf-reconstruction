"""Compile a fixed polar tree into four-lane microinstructions.

Sources: Kestel SOCC 2022 II-C / III-D (pruning, shared alpha/beta memories,
instruction controller). Addresses and finite-precision conventions are local.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
from check_core import polar_frozen_set, N, K, FROZEN_HEX

OPS = {name: i for i, name in enumerate([
    'END', 'F', 'G', 'G0', 'ZERO', 'HD', 'H', 'COPY',
    'REP_INIT', 'REP_ACC', 'REP_FILL', 'SPC_INIT', 'SPC_ACC',
    'SPC_FLIP', 'EXTRACT'])}

def classify(start, size, frozen, fast):
    flags = [i in frozen for i in range(start, start + size)]
    if all(flags):
        return 'ZERO'
    if size == 1:
        return 'HD'
    if fast:
        if all(flags[:-1]) and not flags[-1]:
            return 'REP'
        if flags[0] and not any(flags[1:]):
            return 'SPC'
        if not any(flags):
            return 'HD'
    return 'NODE'

def compile_tree(fast):
    frozen = polar_frozen_set()
    info = [i for i in range(N) if i not in frozen]
    alpha_base, beta_base = [], []
    aw = bw = 0
    for depth in range(10):
        size = N >> depth
        words = (size + 3) // 4
        alpha_base.append(aw)
        aw += words
        # Root beta is not needed after all constituent information is output.
        beta_base.append(bw)
        if depth:
            bw += 2 * words
    instructions = []
    nodes = Counter()

    def emit(op, aa=0, ab=0, bb=0, dst=0, sa=0, sb=0,
             count=4, mask=0, index=0, flags=0, run_log=0):
        fields = [(OPS[op],5),(aa,9),(ab,9),(bb,9),(dst,9),
                  (sa,2),(sb,2),(count,3),(mask,4),(index,6),(flags,3),(run_log,3)]
        value = shift = 0
        for v, width in fields:
            assert 0 <= v < 1 << width, (op, v, width)
            value |= v << shift
            shift += width
        instructions.append(dict(op=op, aa=aa, ab=ab, bb=bb, dst=dst,
                                 sa=sa, sb=sb, count=count, mask=mask,
                                 index=index, flags=flags, run_log=run_log, word=value))

    def extract(start, size, dest):
        # beta = u * F^(tensor log2(size)); the transform is its own inverse.
        for local in range(size):
            if start + local in frozen:
                continue
            words = []
            for offset in range(0, size, 4):
                mask = sum(1 << lane for lane in range(min(4, size-offset))
                           if ((offset+lane) & local) == local)
                if mask:
                    words.append((dest + offset//4, mask))
            for j, (addr, mask) in enumerate(words):
                emit('EXTRACT', aa=addr, mask=mask, index=info.index(start+local),
                     flags=(1 if j == 0 else 0) | (2 if j == len(words)-1 else 0))

    def visit(start, size, depth, side):
        abase = alpha_base[depth]
        bdest = beta_base[depth] + side*((size+3)//4)
        kind = classify(start, size, frozen, fast)
        nodes[kind] += 1
        if kind != 'NODE':
            if kind in ('REP','SPC'):
                emit(kind+'_INIT')
            for offset in range(0, size, 4):
                count = min(4,size-offset)
                if kind == 'REP':
                    emit('REP_ACC', aa=abase+offset//4, count=count)
                elif kind == 'SPC':
                    emit('SPC_ACC', aa=abase+offset//4, dst=bdest+offset//4, count=count)
                else:
                    emit(kind, aa=abase+offset//4, dst=bdest+offset//4, count=count)
            if kind == 'REP':
                for offset in range(0,size,4):
                    emit('REP_FILL', dst=bdest+offset//4, count=min(4,size-offset))
            elif kind == 'SPC':
                emit('SPC_FLIP')
            extract(start,size,bdest)
            return bdest
        half = size//2
        left_zero = classify(start,half,frozen,fast) == 'ZERO'
        if not left_zero:
            for offset in range(0,half,4):
                emit('F', aa=abase+offset//4, ab=abase+(half+offset)//4,
                     sa=offset%4, sb=(half+offset)%4, dst=alpha_base[depth+1]+offset//4,
                     count=min(4,half-offset))
        left = visit(start,half,depth+1,0)
        for offset in range(0,half,4):
            emit('G0' if left_zero else 'G', aa=abase+offset//4,
                 ab=abase+(half+offset)//4, bb=left+offset//4,
                 sa=offset%4, sb=(half+offset)%4,
                 dst=alpha_base[depth+1]+offset//4, count=min(4,half-offset))
        right = visit(start+half,half,depth+1,1)
        if depth:  # outputs already extracted; root combine has no consumer
            for offset in range(0,half,4):
                count = min(4,half-offset)
                emit('H', aa=left+offset//4, ab=right+offset//4,
                     dst=bdest+offset//4, count=count, flags=1 if half<4 else 0)
            if half >= 4:
                for offset in range(0,half,4):
                    emit('COPY', aa=right+offset//4, dst=bdest+(half+offset)//4)
        return bdest

    visit(0,N,0,0)
    emit('END')
    # Compile each vector operation to one instruction with an on-chip loop.
    # The per-word expansion above also makes address allocation auditable.
    expanded_count = len(instructions)
    strides = {'F':['aa','ab','dst'], 'G':['aa','ab','bb','dst'],
               'G0':['aa','ab','dst'], 'ZERO':['aa','dst'],
               'HD':['aa','dst'], 'H':['aa','ab','dst'],
               'COPY':['aa','dst'], 'REP_ACC':['aa'],
               'REP_FILL':['dst'], 'SPC_ACC':['aa','dst']}
    expanded = instructions
    instructions = []
    pos = 0
    while pos < len(expanded):
        first = expanded[pos]
        run = 1
        if first['op'] in strides:
            fields = strides[first['op']]
            while pos+run < len(expanded) and run < 128:
                other = expanded[pos+run]
                if any(other[key] != (value + run if key in fields else value)
                       for key,value in first.items() if key != 'word'):
                    break
                run += 1
        # A split into powers of two also supports irregular future schedules.
        run = 1 << (run.bit_length()-1)
        copied = {k:v for k,v in first.items() if k not in ('word','run_log')}
        emit(**copied, run_log=run.bit_length()-1)
        pos += run
    assert aw <= 512 and bw <= 512
    return instructions, dict(alpha_words=aw,beta_words=bw,nodes=dict(nodes),
                              instruction_count=len(instructions),expanded_count=expanded_count,
                              op_counts=dict(Counter(i['op'] for i in instructions)))

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--out',type=Path,default=ROOT/'generated')
    args=parser.parse_args()
    args.out.mkdir(parents=True,exist_ok=True)
    manifest={'N':N,'K':K,'lanes':4,'frozen_mask':FROZEN_HEX,'variants':{}}
    for mode,fast in [('exact',False),('fast',True)]:
        instructions,meta=compile_tree(fast)
        depth=1 << (len(instructions)-1).bit_length()
        content=''.join(f"{i['word']:016x}\n" for i in instructions)
        content += '0000000000000000\n'*(depth-len(instructions))
        (args.out/f'{mode}.mem').write_text(content,encoding='ascii')
        (args.out/f'{mode}_schedule.json').write_text(json.dumps(instructions,indent=2),encoding='utf8')
        meta.update(rom_depth=depth,rom_sha256=hashlib.sha256(content.encode()).hexdigest())
        manifest['variants'][mode]=meta
    (args.out/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf8')
    print(json.dumps(manifest,indent=2))

if __name__=='__main__':
    main()
