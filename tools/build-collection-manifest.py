#!/usr/bin/env python3
"""Author a reference from publisher source, NEVER certify an installed/damaged collection."""
import argparse
import hashlib
from pathlib import Path
import re
import sys

SOURCE = Path(__file__).resolve().parents[1] / 'aegis-linux'
sys.path.insert(0, str(SOURCE))
from updater import canonical, file_hash, openssl, public_id, version, UpdateError
from device_services import relative, MAX_FILES


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True, help='Publisher original source directory, not installed data')
    parser.add_argument('--output', type=Path, required=True, help='Separate output directory')
    parser.add_argument('--package-id', required=True)
    parser.add_argument('--version', required=True)
    parser.add_argument('--private-key', type=Path)
    parser.add_argument('--public-key', type=Path)
    args = parser.parse_args()
    version(args.version)
    if not re.fullmatch('[a-zA-Z0-9._-]{1,80}', args.package_id):
        raise UpdateError('Identificador inválido.')
    if args.output.resolve().is_relative_to(args.source.resolve()):
        raise UpdateError('A saída deve ficar fora da origem.')
    files = {}
    for path in sorted(args.source.rglob('*')):
        if path.is_symlink():
            raise UpdateError('Links não são permitidos.')
        if path.is_file():
            name = relative(path.relative_to(args.source).as_posix())
            if name in ('manifest.json', 'manifest.sig'):
                raise UpdateError('Use a origem original, sem manifesto prévio; não use a instalação atual como referência.')
            files[name] = {'size': path.stat().st_size, 'sha256': file_hash(path)}
        if len(files) > MAX_FILES:
            raise UpdateError('Arquivos demais.')
    if not files:
        raise UpdateError('Origem vazia.')
    manifest = {'format': 1, 'package_id': args.package_id, 'version': args.version, 'files': files}
    if args.private_key or args.public_key:
        if not args.private_key or not args.public_key:
            raise UpdateError('Forneça ambas as chaves para assinatura.')
        if args.private_key.resolve().is_relative_to(SOURCE.parent):
            raise UpdateError('A chave privada deve permanecer fora do repositório.')
        if openssl(['pkey', '-in', str(args.private_key), '-pubout']) != args.public_key.read_bytes():
            raise UpdateError('Chaves não correspondem.')
        bits = openssl(['pkey', '-pubin', '-in', str(args.public_key), '-text', '-noout']).decode()
        if 'Public-Key: (3072 bit)' not in bits and 'Public-Key: (4096 bit)' not in bits:
            raise UpdateError('Use RSA 3072 ou 4096 bits.')
        manifest['key_id'] = public_id(args.public_key)
    args.output.mkdir(parents=True, exist_ok=True)
    output = args.output / 'manifest.json'
    with output.open('xb') as fd:
        fd.write(canonical(manifest))
    if args.private_key:
        sig = args.output / 'manifest.sig'
        if sig.exists():
            raise UpdateError('Assinatura de saída já existe.')
        openssl(['dgst', '-sha256', '-sign', str(args.private_key), '-out', str(sig),
                 '-sigopt', 'rsa_padding_mode:pss', '-sigopt', 'rsa_pss_saltlen:digest', str(output)])
    print(output)


if __name__ == '__main__':
    main()
