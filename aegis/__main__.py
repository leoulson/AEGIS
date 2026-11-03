"""Offline terminal interface for AEGIS — no network or third-party dependencies."""
import argparse
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_DEFAULT = Path.home() / '.local' / 'share' / 'aegis' / 'library.sqlite3'


def initialize(database, source):
    database = Path(database)
    database.parent.mkdir(parents=True, exist_ok=True)
    docs = json.loads(Path(source).read_text(encoding='utf-8'))
    with sqlite3.connect(str(database)) as db:
        db.execute('CREATE TABLE IF NOT EXISTS documents (id TEXT PRIMARY KEY, title TEXT NOT NULL, category TEXT NOT NULL, source TEXT NOT NULL, reviewed TEXT NOT NULL, body TEXT NOT NULL)')
        for doc in docs:
            db.execute('INSERT OR REPLACE INTO documents VALUES (?, ?, ?, ?, ?, ?)', tuple(doc[k] for k in ('id', 'title', 'category', 'source', 'reviewed', 'body')))
    return len(docs)


def search(database, query):
    with sqlite3.connect(str(database)) as db:
        db.row_factory = sqlite3.Row
        return [dict(r) for r in db.execute('SELECT id, title, category, source, reviewed FROM documents WHERE title LIKE ? OR body LIKE ? OR category LIKE ? ORDER BY title LIMIT 50', ['%' + query + '%'] * 3)]


def read(database, document_id):
    with sqlite3.connect(str(database)) as db:
        db.row_factory = sqlite3.Row
        result = db.execute('SELECT * FROM documents WHERE id = ?', (document_id,)).fetchone()
        return dict(result) if result else None


def main():
    p = argparse.ArgumentParser(description='AEGIS — biblioteca local offline para Raspberry Pi 2')
    p.add_argument('--db', default=str(DB_DEFAULT), help='Caminho do banco SQLite local')
    sub = p.add_subparsers(dest='command', required=True)
    boot = sub.add_parser('init', help='Importa o catálogo de demonstração')
    boot.add_argument('--source', default=str(ROOT / 'content' / 'demo.json'))
    q = sub.add_parser('search', help='Busca em documentos armazenados')
    q.add_argument('query')
    r = sub.add_parser('read', help='Lê documento armazenado')
    r.add_argument('id')
    args = p.parse_args()
    if args.command == 'init':
        print('Documentos importados:', initialize(args.db, args.source))
    elif args.command == 'search':
        if not Path(args.db).exists():
            p.error('Banco não encontrado; execute init primeiro.')
        hits = search(args.db, args.query)
        for item in hits:
            print('{id} | {title} | {category} | {reviewed}'.format(**item))
        if not hits:
            print('Nenhum resultado.')
    elif args.command == 'read':
        if not Path(args.db).exists():
            p.error('Banco não encontrado; execute init primeiro.')
        doc = read(args.db, args.id)
        if not doc:
            p.error('Documento não encontrado.')
        print('{title}\nCategoria: {category}\nOrigem: {source}\nRevisão: {reviewed}\n\n{body}'.format(**doc))

if __name__ == '__main__':
    main()
