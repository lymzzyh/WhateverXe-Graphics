#!/usr/bin/env python3
"""Build the pinned UHD770 WEX source and preserved Graphics payloads together."""
import argparse
import concurrent.futures
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()


def run(root, *args):
    subprocess.run([str(a) for a in args], cwd=root, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wex-source', type=Path, default=ROOT.parent/'WhateverXe')
    parser.add_argument('--sdk', type=Path)
    parser.add_argument('--lilu', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT/'dist/UHD770')
    parser.add_argument('--verify', action='store_true', help='also run WEX CPU and final Graphics package tests')
    parser.add_argument('--rcodesign', default='rcodesign')
    args = parser.parse_args()
    wex = args.wex_source.resolve()
    pin = json.loads((ROOT/'docs/uhd770-source.json').read_text())
    revision = git(wex, 'rev-parse', 'HEAD')
    if revision != pin['wex_commit']:
        parser.error('WEX must be at the commit in docs/uhd770-source.json: '+pin['wex_commit'])
    for root in (wex, ROOT):
        if git(root, 'status', '--porcelain', '--untracked-files=normal'):
            parser.error('commit source changes before a pinned build: '+str(root))
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    (out/'source-build.json').unlink(missing_ok=True)
    options = []
    for flag, path in (('--sdk', args.sdk), ('--lilu', args.lilu)):
        if path:
            options += [flag, path.resolve()]
    if args.verify:
        run(wex, sys.executable, 'tools/test.py')

    def build(configuration):
        command = [sys.executable, 'tools/build.py', '--output', out/configuration, *options]
        if configuration == 'RELEASE':
            command += ['--release']
        # Independent object directories and complete per-configuration logs.
        with (out/(configuration+'.log')).open('w') as log:
            subprocess.run([str(a) for a in command], cwd=wex, stdout=log, stderr=log, check=True)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(build, ('DEBUG', 'RELEASE')))
    # Never replace the signed Compat bundle with the development build.
    run(ROOT, sys.executable, 'tools/build.py', '--output', out/'Graphics')
    version = json.loads((ROOT/'tools/policy.json').read_text())['package_version']
    package = out/'Graphics'/f'WhateverXe-Graphics-{version}.pkg'
    if args.verify:
        run(ROOT, sys.executable, 'tools/test.py', package, '--rcodesign', args.rcodesign)
    manifest = {
        'wex_commit': revision,
        'graphics_commit': git(ROOT, 'rev-parse', 'HEAD'),
        'verification_run': args.verify,
        'graphics_package_sha256': hashlib.sha256(package.read_bytes()).hexdigest(),
        'wex_builds': {name: json.loads((out/name/'build-manifest.json').read_text())
                       for name in ('DEBUG', 'RELEASE')},
        'payload_policy': 'Preserved Mod-signed Graphics payloads; generated Compat is development-only.',
    }
    (out/'source-build.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print('UHD770 build complete: '+str(out))


if __name__ == '__main__':
    main()
