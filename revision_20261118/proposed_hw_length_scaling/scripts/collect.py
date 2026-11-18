"""Collect unmodified Vivado report rows, keeping memories separate from logic."""
import csv
import json
import re
from common import ROOT, CONFIGS, ACTIVE, sha, save_json


def resource_report(path):
    text=path.read_text()
    def value(label):
        for line in text.splitlines():
            columns=[x.strip() for x in line.split('|')]
            if len(columns)>2 and columns[1].rstrip('*').strip()==label:
                return float(columns[2])
        raise ValueError(f'Missing {label}: {path}')
    return dict(LUTs=int(value('CLB LUTs')), Logic=int(value('LUT as Logic')),
        LUTRAM=int(value('LUT as Memory')), FFs=int(value('CLB Registers')),
        BRAM_tiles=value('Block RAM Tile'), DSPs=int(value('DSPs')))


def main():
    synth=json.loads((ROOT/'reports/synthesis.json').read_text())
    assert synth['complete']
    verification=json.loads((ROOT/'reports/verification.json').read_text())
    netlist=json.loads((ROOT/'reports/netlist_verification.json').read_text())
    assert verification['complete'] and netlist['complete']
    for name,digest in verification['rtl_hashes'].items():
        assert sha(ROOT/'rtl'/name)==digest, 'RTL changed after verification'
    manifest=json.loads((ROOT/'provenance/manifest.json').read_text())
    for entry in manifest['files']:
        assert sha(ROOT/entry['snapshot'])==entry['sha256'], 'Snapshot changed'
        assert sha(entry['source'])==entry['sha256'], 'Original source changed'
    rows=[]
    for n in CONFIGS:
        config=json.loads((ROOT/f'generated/n{n}/config.json').read_text())
        report=ROOT/f'build/n{n}/synthesis/utilization_synth.rpt'
        sr=next(v for v in synth['configurations'] if v['N']==n)
        nr=next(v for v in netlist['configurations'] if v['N']==n)
        vr=next(v for v in verification['configurations'] if v['N']==n)
        assert sr['passed'] and nr['passed'] and vr['passed']
        assert sha(report)==sr['report_sha256']
        assert sha(ROOT/f'build/n{n}/synthesis/netlist.v')==nr['netlist_sha256']
        for frame in vr['frames']:
            assert frame['rtl']['CN']==2*config['edges']*frame['iterations']
            assert frame['rtl']['VN']==(n+config['edges'])*frame['iterations']
        record=dict(N=n,K=config['K'],Z=config['Z'],Edges=config['edges'],**resource_report(report))
        record.update(LUT_per_input_bit=record['LUTs']/n,
            Logic_per_input_bit=record['Logic']/n,LUTRAM_per_input_bit=record['LUTRAM']/n,
            message_update_cycles=n+3*config['edges'],
            full_iteration_cycles=n+4*config['edges'],report_sha256=sha(report))
        rows.append(record)
    original=ACTIVE.parent/'UPELDPC.runs/synth_1/proposed_formal_stream_utilization_synth.rpt'
    baseline=resource_report(original)
    fields=['LUTs','Logic','LUTRAM','FFs','BRAM_tiles','DSPs']
    save_json(ROOT/'reports/scaling_resources.json',dict(
        part='xczu3eg-sfvc784-1-i',tool='Vivado 2022.2',stage='OOC synthesis',clock_constraint=None,
        matrix_policy='Actual existing paper configurations; base matrix and degrees vary with length.',
        scope='Five-bit flooding NMS; channel/variable LUTRAM; edge-message BRAM; 64-bit output stream.',
        rows=rows,production_4096_baseline=baseline,
        delta_4096_vs_production={key:rows[-1][key]-baseline[key] for key in fields}))
    with (ROOT/'reports/scaling_resources.csv').open('w',newline='',encoding='utf-8-sig') as out:
        writer=csv.DictWriter(out,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    lines=['| N | K | Z | Edges | LUTs | Logic | LUTRAM | FFs | BRAM tiles | DSPs | LUT/N | Logic/N |',
           '|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for r in rows:
        lines.append('| '+ ' | '.join(str(r[key]) for key in ['N','K','Z','Edges','LUTs','Logic','LUTRAM','FFs','BRAM_tiles','DSPs'])+
                     f' | {r["LUT_per_input_bit"]:.3f} | {r["Logic_per_input_bit"]:.3f} |')
    lines.extend(['','All configurations use the same parameterized RTL, 5-bit arithmetic, memory policy, FPGA part and OOC synthesis mode.',
        'No clock constraint is applied, matching the existing production resource-comparison boundary.',
        'Matrices are the existing paper configurations; this is not a fixed-protograph Z-only experiment.',
        'These results are synthesis resources, not post-route resources or achieved operating frequency.'])
    (ROOT/'reports/scaling_resources.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
    print('\n'.join(lines))


if __name__=='__main__':main()
