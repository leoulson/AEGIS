"""Offline terminal interface for AEGIS — no network or third-party dependencies."""
import argparse
import contextlib
import fcntl
import json
import sqlite3
from pathlib import Path
from .catalog import compile_catalog, normalize, render_card, STATE_LABELS

ROOT = Path(__file__).resolve().parents[1]
DB_DEFAULT = Path.home() / '.local' / 'share' / 'aegis' / 'library.sqlite3'


@contextlib.contextmanager
def data_access(database, write=False):
    database = Path(database).resolve()
    database.parent.mkdir(parents=True, exist_ok=True)
    with (database.parent / '.data.lock').open('a') as lock:
        fcntl.flock(lock, (fcntl.LOCK_EX if write else fcntl.LOCK_SH) | fcntl.LOCK_NB)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def initialize(database, source):
    database = Path(database)
    database.parent.mkdir(parents=True, exist_ok=True)
    docs = json.loads(Path(source).read_text(encoding='utf-8'))
    catalog = None
    if isinstance(docs, dict):
        # Recompute indexes from editorial data; never trust imported generated search text.
        original = dict(docs)
        original.pop('source_sha256', None)
        original['cards'] = [dict(card) for card in docs.get('cards', [])]
        for card in original['cards']:
            card.pop('search_text', None)
        catalog = compile_catalog(original, ROOT)
    elif not isinstance(docs, list):
        raise ValueError('Catálogo deve ser objeto editorial ou lista legada.')
    with data_access(database, write=True), contextlib.closing(sqlite3.connect(str(database))) as db, db:
        db.execute('CREATE TABLE IF NOT EXISTS documents (id TEXT PRIMARY KEY, title TEXT NOT NULL, category TEXT NOT NULL, source TEXT NOT NULL, reviewed TEXT NOT NULL, body TEXT NOT NULL)')
        if catalog is not None:
            db.execute('CREATE TABLE IF NOT EXISTS editorial_cards (id TEXT PRIMARY KEY, category TEXT NOT NULL, state TEXT NOT NULL, search_text TEXT NOT NULL, card_json TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS editorial_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
            # Only the managed editorial table is replaced. Existing user/legacy documents survive.
            db.execute('DELETE FROM editorial_cards')
            db.executemany('INSERT INTO editorial_cards VALUES (?,?,?,?,?)', [(c['id'], c['category'], c['editorial']['state'], c['search_text'], json.dumps(c, ensure_ascii=False)) for c in catalog['cards']])
            db.execute('INSERT OR REPLACE INTO editorial_metadata VALUES (?,?)', ('catalog', json.dumps({k: v for k, v in catalog.items() if k != 'cards'}, ensure_ascii=False)))
            return len(catalog['cards'])
        for doc in docs:
            db.execute('INSERT OR REPLACE INTO documents VALUES (?, ?, ?, ?, ?, ?)', tuple(doc[k] for k in ('id', 'title', 'category', 'source', 'reviewed', 'body')))
    return len(docs)


def has_editorial(db):
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='editorial_cards'").fetchone() is not None


def search(database, query, area=None, state=None, include_pending=False):
    with data_access(database), contextlib.closing(sqlite3.connect(str(database))) as db:
        db.row_factory = sqlite3.Row
        hits = []
        if has_editorial(db):
            conditions, parameters = ['instr(search_text, ?) > 0'], [normalize(query)]
            if not include_pending:
                conditions.append("state='reviewed'")
            if area:
                conditions.append('category=?');parameters.append(area)
            if state:
                conditions.append('state=?');parameters.append(state)
            rows = db.execute('SELECT card_json FROM editorial_cards WHERE ' + ' AND '.join(conditions) + ' ORDER BY id LIMIT 50', parameters)
            for row in rows:
                card = json.loads(row['card_json'])
                hits.append({'id': card['id'], 'title': card['title'], 'category': card['category'],
                             'editorial_state': card['editorial']['state'], 'reviewed': card['editorial']['reviewed_on'], 'lookup_id': 'editorial:' + card['id']})
        if not area and not state:
            hits += [dict(r, editorial_state='legacy_unverified') for r in db.execute('SELECT id, title, category, source, reviewed FROM documents WHERE title LIKE ? OR body LIKE ? OR category LIKE ? ORDER BY title LIMIT 50', ['%' + query + '%'] * 3)]
        return hits[:50]


def read(database, document_id, include_pending=False):
    with data_access(database), contextlib.closing(sqlite3.connect(str(database))) as db:
        db.row_factory = sqlite3.Row
        # Existing user IDs take precedence; editorial: is an explicit lookup namespace.
        legacy = db.execute('SELECT * FROM documents WHERE id=?', (document_id,)).fetchone()
        if legacy:
            return dict(legacy)
        if has_editorial(db):
            lookup = document_id.removeprefix('editorial:')
            row = db.execute('SELECT card_json FROM editorial_cards WHERE id=?', (lookup,)).fetchone()
            if row:
                card = json.loads(row['card_json'])
                if card['editorial']['state'] != 'reviewed' and not include_pending:
                    raise ValueError('Ficha pendente, não liberada para consulta assistencial. Use --include-pending somente para leitura editorial.')
                metadata = json.loads(db.execute("SELECT value FROM editorial_metadata WHERE key='catalog'").fetchone()[0])
                return dict(card, body=render_card(card, {s['id']: s for s in metadata['sources']}),
                            editorial_state=card['editorial']['state'])
        result = db.execute('SELECT * FROM documents WHERE id = ?', (document_id,)).fetchone()
        return dict(result) if result else None


def policy(database):
    with data_access(database), contextlib.closing(sqlite3.connect(str(database))) as db:
        if not has_editorial(db):
            raise ValueError('Importe o catálogo editorial antes de consultar a política.')
        meta = json.loads(db.execute("SELECT value FROM editorial_metadata WHERE key='catalog'").fetchone()[0])
        return meta['policy']


def main():
    p = argparse.ArgumentParser(description='AEGIS — biblioteca local offline para Raspberry Pi 2')
    p.add_argument('--db', default=str(DB_DEFAULT), help='Caminho do banco SQLite local')
    sub = p.add_subparsers(dest='command', required=True)
    boot = sub.add_parser('init', help='Importa o catálogo editorial local sem apagar documentos pessoais/legados')
    boot.add_argument('--source', default=str(ROOT / 'content' / 'catalog.json'))
    q = sub.add_parser('search', help='Busca em documentos armazenados')
    q.add_argument('query')
    q.add_argument('--area', choices=['urgencia','aps','crianca','mulher','medicamentos','seguranca'])
    q.add_argument('--state', choices=list(STATE_LABELS))
    q.add_argument('--include-pending', action='store_true', help='Oficina editorial: inclui fichas não liberadas')
    r = sub.add_parser('read', help='Lê documento armazenado')
    r.add_argument('id')
    r.add_argument('--include-pending', action='store_true', help='Leitura editorial; não é liberação assistencial')
    sub.add_parser('policy', help='Política editorial e direitos autorais offline')
    args = p.parse_args()
    if args.command == 'init':
        print('Documentos importados:', initialize(args.db, args.source))
    elif args.command == 'search':
        if not Path(args.db).exists():
            p.error('Banco não encontrado; execute init primeiro.')
        if args.state and args.state != 'reviewed' and not args.include_pending:
            p.error('Estados não revisados exigem --include-pending para leitura editorial.')
        hits = search(args.db, args.query, args.area, args.state, args.include_pending)
        for item in hits:
            label = STATE_LABELS.get(item['editorial_state'], 'Legado: revisão não verificada')
            print(item.get('lookup_id', item['id']) + ' | ' + item['title'] + ' | ' + item['category'] + ' | ' + label)
        if not hits:
            print('Nenhum resultado.')
    elif args.command == 'read':
        if not Path(args.db).exists():
            p.error('Banco não encontrado; execute init primeiro.')
        try:
            doc = read(args.db, args.id, args.include_pending)
        except ValueError as exc:
            p.error(str(exc))
        if not doc:
            p.error('Documento não encontrado.')
        if 'editorial_state' in doc:
            print(doc['body'])
        else:
            print('{title}\nCategoria: {category}\nOrigem: {source}\nData do campo legado (revisão não verificada): {reviewed}\n\n{body}'.format(**doc))
    elif args.command == 'policy':
        if not Path(args.db).exists():
            p.error('Banco não encontrado; execute init primeiro.')
        try:
            content = policy(args.db)
            print(content['title'] + '\n\n' + '\n\n'.join(s['title'] + '\n' + s['text'] for s in content['sections']))
        except (ValueError, sqlite3.Error) as exc:
            p.error(str(exc))

if __name__ == '__main__':
    main()
