"""Paths and lossless parsing of the existing, frozen H/G matrix sources."""
from pathlib import Path
import hashlib
import json
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
# Released artifact uses frozen inputs, independent of the development workspace.
FORMAL = ROOT.parent / 'proposed_hw_formal_5bit_message_bram'
ACTIVE = ROOT / 'provenance/production_snapshot'
CONFIGS = {1024: ('standard', ROOT / 'provenance/n1024'),
           2048: ('medium', ROOT / 'provenance/n2048'),
           4096: ('long', ROOT / 'provenance/n4096')}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf8')


def run(args, cwd=ROOT, timeout=300):
    proc = subprocess.run([str(x) for x in args], cwd=cwd, capture_output=True,
                          text=True, encoding='utf8', errors='replace', timeout=timeout)
    if proc.returncode:
        raise RuntimeError(f'{args[0]} exited {proc.returncode}\n{proc.stdout}\n{proc.stderr}')
    return proc.stdout + proc.stderr


def array(text, name):
    match = re.search(r'\b' + re.escape(name) + r'\s*(?:\[[^\]]*\])+\s*=\s*\{', text)
    if not match:
        raise ValueError(f'Missing C array {name}')
    start = match.end()
    depth = 1
    pos = start
    while depth:
        depth += (text[pos] == '{') - (text[pos] == '}')
        pos += 1
    return text[start:pos-1]


def load_source(n, directory=None):
    suffix, source = CONFIGS[n]
    source = Path(directory) if directory is not None else source
    text = (source / f'matrix_data_1_2_{suffix}.c').read_text(encoding='utf8')
    header = (source / f'h_matrix_1_2_{suffix}.h').read_text(encoding='utf8')
    def macro(name):
        return int(re.search(r'#define\s+' + name + r'\s+(\d+)', header)[1])
    k = macro('K_1_2_' + suffix.upper())
    z = macro('EXPANSION_FACTOR_Z')
    def rows(prefix):
        degree = [int(x) for x in re.findall(r'\d+', array(text, prefix+'_row_degrees_1_2_'+suffix))]
        raw = re.findall(r'\{([^{}]*)\}', array(text, prefix+'_row_indices_1_2_'+suffix))
        assert len(degree) == len(raw)
        return [[int(x) for x in re.findall(r'\d+', r)][:d] for r,d in zip(raw,degree)]
    h = rows('H')
    g = rows('G')
    assert len(h) == n-k and len(g) == k
    return dict(N=n, K=k, M=n-k, Z=z, rows=h, generator=g)


def gf2_rank(values):
    pivots = {}
    for value in values:
        while value:
            pivot = value.bit_length()-1
            if pivot not in pivots:
                pivots[pivot] = value
                break
            value ^= pivots[pivot]
    return len(pivots)


def bits(indices):
    return sum(1 << c for c in indices)
