"""Reproduce exports, functional checks, synthesis, netlist checks and collection."""
import argparse
import subprocess
import sys
from common import ROOT, CONFIGS


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--lengths',type=int,nargs='+',default=list(CONFIGS))
    args=parser.parse_args()
    assert all(n in CONFIGS for n in args.lengths)
    steps=[('prepare.py',[]),('verify.py',args.lengths),('run_synthesis.py',args.lengths),
           ('verify_netlist.py',args.lengths),('collect.py',[])]
    for name,lengths in steps:
        command=[sys.executable,'-u',str(ROOT/'scripts'/name)]
        if lengths: command+=['--lengths']+[str(n) for n in lengths]
        print(f'PIPELINE {name}',flush=True)
        subprocess.run(command,cwd=ROOT,check=True)


if __name__=='__main__':main()
