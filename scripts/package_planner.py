#!/usr/bin/env python3
"""Build a static planner distribution from an existing UI and this engine adapter.

Does not mutate either source checkout or publish anything. Verifies every input
release file and rejects assets over the Cloudflare Pages per-file limit.
"""
import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path


def sha(path):
    return hashlib.file_digest(path.open('rb'), 'sha256').hexdigest()


def package(repo, app_source, release, out):
    repo, app_source, release, out = (Path(p).resolve() for p in (repo, app_source, release, out))
    if out.exists():raise ValueError('Output must be a new directory; existing deployments are never overwritten.')
    manifest = json.loads((release/'build-manifest.json').read_text())
    if manifest.get('synthetic') is not False:raise ValueError('A real data release is required.')
    for name, digest in manifest['files'].items():
        path = (release/name).resolve()
        if not path.is_relative_to(release) or not path.is_file() or sha(path) != digest:
            raise ValueError(f'Release integrity failure: {name}')
    with tempfile.TemporaryDirectory(prefix='cosmic-package-') as d:
        root = Path(d)
        # UI authors retain their checkout; only a disposable build copy changes.
        shutil.copytree(app_source/'apps/planner', root/'apps/planner', ignore=shutil.ignore_patterns('node_modules','dist'))
        shutil.copytree(repo/'apps/atlas/src', root/'apps/atlas/src')
        shutil.copytree(repo/'contracts', root/'contracts')
        shutil.copytree(release, root/'apps/atlas/public/data/planner-v1', ignore=shutil.ignore_patterns('*.gz','*.br'))
        app = root/'apps/planner'
        subprocess.run(['npm','ci','--no-audit','--no-fund'],cwd=app,check=True)
        subprocess.run(['npm','run','build'],cwd=app,check=True)
        dist = app/'dist'
        (dist/'_headers').write_text('/assets/*\n  Cache-Control: public, max-age=31536000, immutable\n/data/*\n  Cache-Control: no-cache\n/\n  Cache-Control: no-cache\n/index.html\n  Cache-Control: no-cache\n')
        # A real 404 for missing data prevents SPA fallback returning HTML as JSON.
        (dist/'404.html').write_text('<!doctype html><title>Not found</title><h1>File not found</h1>')
        files = [p for p in dist.rglob('*') if p.is_file()]
        oversized = [str(p.relative_to(dist)) for p in files if p.stat().st_size > 25*1024*1024]
        if oversized:raise ValueError(f'Assets exceed 25 MiB: {oversized}')
        receipt = {'releaseManifestSha256':sha(release/'build-manifest.json'),
                   'appSourceCommit':subprocess.check_output(['git','-C',str(app_source),'rev-parse','HEAD'],text=True).strip(),
                   'engineSourceCommit':subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip(),
                   'compiledEngine':'TypeScript bundled by Vite; Python optimization runs at release time',
                   'files':{str(p.relative_to(dist)):sha(p) for p in sorted(files)},
                   'largestAssetBytes':max(p.stat().st_size for p in files),
                   'startupCellsBytes':(dist/'data/planner-v1/cells.bin').stat().st_size}
        (dist/'deployment-receipt.json').write_text(json.dumps(receipt,sort_keys=True,indent=2)+'\n')
        out.parent.mkdir(parents=True,exist_ok=True)
        shutil.copytree(dist,out)
    return {'out':str(out),'files':len(receipt['files']),'startupCellsBytes':receipt['startupCellsBytes'],
            'largestAssetBytes':receipt['largestAssetBytes'],'receiptSha256':sha(out/'deployment-receipt.json')}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--app-source',type=Path,required=True)
    parser.add_argument('--release',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(package(args.repo,args.app_source,args.release,args.out),indent=2))
