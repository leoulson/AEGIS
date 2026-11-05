#!/usr/bin/env python3
"""Build a format-1 AEGIS package. Signing key paths only, never private key output."""
import argparse
import datetime
import hashlib
from pathlib import Path
import sys
import tempfile
import zipfile

SOURCE = Path(__file__).resolve().parents[1] / 'aegis-linux'
sys.path.insert(0, str(SOURCE))
from updater import (APP_ID, MAX_EXPANDED, MAX_FILES, MAX_MANIFEST, MAX_PACKAGE,
                     REQUIRED, UPDATER_VERSION, UpdateError, canonical, openssl,
                     public_id, safe_path, version)


def build(source, output, release_version, notes, released_at, private, public, architectures):
    version(release_version)
    if private.resolve().is_relative_to(SOURCE.parent):
        raise UpdateError('A chave privada deve ficar fora do repositório.')
    datetime.date.fromisoformat(released_at)
    # A typo selecting the public key must never produce an unusable release.
    derived = openssl(['pkey', '-in', str(private), '-pubout'])
    if derived != public.read_bytes():
        raise UpdateError('A chave pública não corresponde à chave privada selecionada.')
    bits = openssl(['pkey', '-pubin', '-in', str(public), '-text', '-noout']).decode()
    if 'Public-Key: (3072 bit)' not in bits and 'Public-Key: (4096 bit)' not in bits:
        raise UpdateError('Use chave RSA de 3072 ou 4096 bits.')
    files = {}
    for path in sorted((source / 'app').rglob('*')):
        if path.is_symlink():
            raise UpdateError('Links não são permitidos na origem.')
        if path.is_file():
            name = safe_path(path.relative_to(source).as_posix())
            files[name] = {'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'size': path.stat().st_size}
    if not REQUIRED <= set(files) or len(files) > MAX_FILES or sum(f['size'] for f in files.values()) > MAX_EXPANDED:
        raise UpdateError('Origem incompleta ou acima do limite.')
    manifest = {'app_id': APP_ID, 'format': 1, 'version': release_version,
                'min_updater': UPDATER_VERSION, 'systems': ['Linux'],
                'architectures': architectures, 'notes': notes,
                'released_at': released_at, 'key_id': public_id(public), 'files': files}
    raw = canonical(manifest)
    if len(raw) > MAX_MANIFEST or len(notes) > 16000:
        raise UpdateError('Notas ou manifesto acima do limite.')
    output.mkdir(parents=True, exist_ok=True)
    target = output / ('aegis-' + release_version + '.aegis-update')
    if target.exists():
        raise UpdateError('Pacote de saída já existe; nada substituído.')
    with tempfile.TemporaryDirectory(dir=output) as tmp:
        msg, sig = Path(tmp) / 'manifest.json', Path(tmp) / 'manifest.sig'
        msg.write_bytes(raw)
        openssl(['dgst', '-sha256', '-sign', str(private), '-out', str(sig),
                 '-sigopt', 'rsa_padding_mode:pss', '-sigopt', 'rsa_pss_saltlen:digest', str(msg)])
        packed = Path(tmp) / 'package.zip'
        with zipfile.ZipFile(packed, 'w', compression=zipfile.ZIP_DEFLATED) as z:
            for name, data in [('manifest.json', raw), ('manifest.sig', sig.read_bytes())] + [(n, (source / n).read_bytes()) for n in files]:
                info = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                z.writestr(info, data)
        if packed.stat().st_size > MAX_PACKAGE:
            raise UpdateError('Pacote acima de 48 MiB.')
        # Exclusive creation prevents accidental overwrite, including concurrent builds.
        with target.open('xb') as out:
            out.write(packed.read_bytes())
        (output / ('aegis-' + release_version + '.manifest.json')).write_bytes(raw)
        (output / ('aegis-' + release_version + '.manifest.sig')).write_bytes(sig.read_bytes())
    return target


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, default=SOURCE)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--version', required=True)
    p.add_argument('--notes', type=Path, required=True)
    p.add_argument('--date', required=True, help='YYYY-MM-DD')
    p.add_argument('--private-key', type=Path, required=True)
    p.add_argument('--public-key', type=Path, required=True)
    p.add_argument('--architectures', nargs='+', default=['armv7l'])
    a = p.parse_args()
    print(build(a.source, a.output, a.version, a.notes.read_text(encoding='utf-8'), a.date,
                a.private_key, a.public_key, a.architectures))


if __name__ == '__main__':
    main()
