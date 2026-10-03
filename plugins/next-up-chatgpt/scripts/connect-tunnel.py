#!/usr/bin/env python3
"""Connect this plugin through an existing OpenAI tunnel; never print the key."""

import argparse
import getpass
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tunnel-id', required=True, help='Tunnel ID from OpenAI Platform (not an API key)')
    args = parser.parse_args()
    if not re.fullmatch(r'tunnel_[a-zA-Z0-9]+', args.tunnel_id):
        parser.error('Expected a tunnel_... identifier')
    root = Path(__file__).resolve().parents[1]
    node = shutil.which('node')
    client = shutil.which('tunnel-client') or str(Path.home() / '.local/bin/tunnel-client')
    if not node or not Path(client).is_file():
        sys.exit('Install Node.js and the official OpenAI tunnel-client first.')
    if not (root / 'dist/card.html').is_file():
        sys.exit('Run npm ci && npm run build in the plugin directory first.')

    private_dir = Path.home() / '.config/next-up-chatgpt'
    private_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    private_dir.chmod(0o700)
    key_file = private_dir / 'runtime-key'
    if key_file.is_symlink():
        sys.exit('Refusing a symlink at the runtime key path.')
    if not key_file.exists():
        if not sys.stdin.isatty():
            sys.exit('Run this command in your terminal. The key must be entered through hidden interactive input.')
        key = getpass.getpass('OpenAI runtime API key (hidden; never paste it into chat): ').strip()
        if not key.startswith('sk-') or any(char.isspace() for char in key):
            sys.exit('Expected an OpenAI runtime API key. Nothing was saved.')
        descriptor = os.open(key_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'w') as handle:
            handle.write(key)
        del key
        print('Saved the runtime credential privately outside the repository.')
    else:
        key_file.chmod(0o600)
        print('Using the existing private runtime credential.')

    command = shlex.join([node, str(root / 'server/stdio.mjs')])
    result = subprocess.run([
        client, 'runtimes', 'connect', '--alias', 'next-up-chatgpt',
        '--profile', 'next-up-chatgpt', '--tunnel-id', args.tunnel_id,
        '--mcp-command', command, '--runtime-api-key', f'file:{key_file}',
    ])
    if result.returncode:
        sys.exit(result.returncode)
    subprocess.run([client, 'runtimes', 'status', 'next-up-chatgpt', '--json'], check=True)
    print('Check that status reports process_running, healthy, and ready before connecting the plugin in ChatGPT.')


if __name__ == '__main__':
    main()
