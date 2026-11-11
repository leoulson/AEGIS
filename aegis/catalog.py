"""Editorial catalog validation/compilation shared by generator and terminal import."""
import datetime
import hashlib
import json
from pathlib import Path
import re
import unicodedata
from urllib.parse import urlsplit

STATES = {'draft', 'pending_professional_review', 'reviewed'}
STATE_LABELS = {'draft': 'Rascunho', 'pending_professional_review': 'Pendente de revisão profissional', 'reviewed': 'Revisado'}
SECTIONS = {'initial_assessment': 'Avaliação inicial', 'red_flags': 'Sinais de alerta',
            'source_based_actions': 'Condutas fundamentadas nas fontes', 'limits_and_referral': 'Limites, exceções e encaminhamento',
            'follow_up': 'Acompanhamento', 'evidence_context': 'Evidência complementar e aplicabilidade'}


def normalize(text):
    return ''.join(c for c in unicodedata.normalize('NFD', text.casefold()) if unicodedata.category(c) != 'Mn')


def canonical(data):
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def date(value):
    require(isinstance(value, str), 'Data deve ser ISO 8601, não uma revisão presumida.')
    datetime.date.fromisoformat(value)


def https(url):
    require(isinstance(url, str), 'URL inválida.')
    parsed = urlsplit(url)
    require(parsed.scheme == 'https' and bool(parsed.hostname) and not parsed.username and not parsed.password, 'Referência deve usar HTTPS sem credenciais.')


def indexed(items, name):
    require(isinstance(items, list), name + ' deve ser uma lista.')
    result = {}
    for row in items:
        require(isinstance(row, dict), name + ': objeto inválido.')
        identifier = row.get('id')
        require(isinstance(identifier, str) and re.fullmatch('[a-z][a-z0-9-]{1,79}', identifier), name + ': ID estável inválido.')
        require(identifier not in result, name + ': IDs duplicados.')
        result[identifier] = row
    return result


def validate(data, root=None):
    require(isinstance(data, dict) and type(data.get('format')) is int and data['format'] == 1, 'Formato editorial inválido.')
    for field in ('catalog_id', 'edition', 'tagline', 'presentation', 'notice'):
        require(nonempty(data.get(field)), 'Campo ausente: ' + field)
    areas = indexed(data.get('areas'), 'Áreas')
    require(len(areas) == 6, 'As seis áreas de navegação devem estar descritas, inclusive as planejadas.')
    for area in areas.values():
        require(nonempty(area.get('title')), 'Área sem título.')
    sources = indexed(data.get('sources'), 'Fontes')
    for source in sources.values():
        for field in ('title', 'citation', 'edition', 'appraisal'):
            require(nonempty(source.get(field)), 'Fonte sem ' + field)
        require(source.get('verified') is True, 'Fonte não verificada não pode fundamentar este catálogo inicial.')
        date(source.get('consulted_on'))
        https(source.get('url'))
        for url in source.get('verification_urls', []):
            https(url)
        require(isinstance(source.get('verification'), dict) and nonempty(source['verification'].get('method')), 'Fonte sem método de verificação.')
        rights = source.get('reproduction', {})
        require(rights.get('status') in ('verified', 'not_established') and nonempty(rights.get('terms')) and nonempty(rights.get('evidence')), 'Direitos da fonte não documentados.')
        require(isinstance(source.get('pending'), list) and all(nonempty(n) for n in source['pending']), 'Pendências da fonte não descritas.')
    cards = indexed(data.get('cards'), 'Fichas')
    require(bool(cards), 'Catálogo vazio.')
    for card in cards.values():
        for field in ('title', 'summary', 'audience', 'population', 'context', 'objective'):
            require(nonempty(card.get(field)), 'Ficha sem ' + field)
        require(card.get('category') in areas, 'Área da ficha desconhecida.')
        require(isinstance(card.get('keywords'), list) and bool(card['keywords']) and all(nonempty(k) for k in card['keywords']), 'Palavras-chave inválidas.')
        editorial = card.get('editorial', {})
        state = editorial.get('state')
        require(state in STATES, 'Estado editorial inválido.')
        date(editorial.get('source_consulted_on'))
        require(nonempty(editorial.get('provenance')), 'Proveniência editorial ausente.')
        require(isinstance(editorial.get('notes'), list) and all(nonempty(n) for n in editorial['notes']), 'Pendências editoriais inválidas.')
        if state != 'reviewed':
            require(editorial.get('reviewer') is None and editorial.get('reviewed_on') is None, 'Não atribuir revisão clínica fictícia a material pendente.')
        else:
            require(nonempty(editorial.get('reviewer')), 'Revisão exige responsável real.')
            date(editorial.get('reviewed_on'))
            evidence = editorial.get('review_document')
            require(nonempty(evidence), 'Revisão exige registro documental.')
            require(evidence.startswith('content/reviews/') and '..' not in Path(evidence).parts, 'Registro de revisão fora da pasta editorial.')
            if root is not None:
                record = (Path(root) / evidence).resolve()
                require(record.is_relative_to((Path(root) / 'content/reviews').resolve()) and record.is_file(), 'Registro de revisão clínica não encontrado.')
        sections = card.get('sections')
        require(isinstance(sections, dict) and set(sections) == set(SECTIONS), 'Seções estruturadas ausentes ou desconhecidas.')
        count = 0
        for points in sections.values():
            require(isinstance(points, list), 'Seção deve conter itens, ou lista vazia quando não aplicável.')
            for point in points:
                require(isinstance(point, dict) and nonempty(point.get('text')), 'Afirmação sem texto.')
                require(point.get('kind') in ('synthesis', 'editorial', 'quotation'), 'Distinguir síntese, observação editorial e texto original.')
                require(isinstance(point.get('citations'), list) and bool(point['citations']), 'Afirmação sem vínculo à fonte.')
                for cite in point['citations']:
                    require(cite.get('source_id') in sources and nonempty(cite.get('locator')), 'Fonte/localização da afirmação inválida.')
                    if point['kind'] == 'quotation':
                        require(sources[cite['source_id']]['reproduction']['status'] == 'verified', 'Transcrição sem permissão verificada.')
                count += 1
        require(count > 0, 'Ficha sem conteúdo local.')
        require(nonempty(card.get('rights', {}).get('text_license')) and nonempty(card['rights'].get('terms')), 'Condições de reprodução da ficha ausentes.')
    policy = data.get('policy', {})
    require(nonempty(policy.get('title')) and isinstance(policy.get('sections'), list) and bool(policy['sections']), 'Política editorial ausente.')
    require(all(nonempty(s.get('title')) and nonempty(s.get('text')) for s in policy['sections']), 'Política editorial incompleta.')
    return data


def compile_catalog(data, root=None):
    validate(data, root)
    result = json.loads(json.dumps(data, ensure_ascii=False))
    result['source_sha256'] = hashlib.sha256(canonical(data)).hexdigest()
    area_names = {a['id']: a['title'] for a in data['areas']}
    references = {s['id']: s for s in data['sources']}
    for card in result['cards']:
        parts = [card[k] for k in ('title', 'summary', 'population', 'context', 'objective')]
        parts += card['keywords'] + [area_names[card['category']]]
        parts += [point['text'] for points in card['sections'].values() for point in points]
        used = {cite['source_id'] for points in card['sections'].values() for point in points for cite in point['citations']}
        parts += [references[identifier]['citation'] for identifier in sorted(used)]
        card['search_text'] = normalize(' '.join(parts))
    return result


def render_card(card, sources):
    editorial = card['editorial']
    lines = [card['title'], 'Estado editorial: ' + STATE_LABELS[editorial['state']],
             'Público: ' + card['audience'], 'População: ' + card['population'],
             'Contexto: ' + card['context'], 'Objetivo: ' + card['objective'],
             'Consulta documental: ' + editorial['source_consulted_on'],
             'Revisão clínica: ' + ((editorial['reviewer'] + ' — ' + editorial['reviewed_on']) if editorial['state'] == 'reviewed' else 'Não realizada/documentada. Não liberado para consulta assistencial.')]
    used = []
    for field, title in SECTIONS.items():
        if not card['sections'][field]:
            continue
        lines += ['', title]
        for point in card['sections'][field]:
            kind = {'synthesis': 'Síntese AEGIS', 'editorial': 'Observação editorial', 'quotation': 'Texto original citado'}[point['kind']]
            lines.append(kind + ': ' + point['text'])
            for cite in point['citations']:
                lines.append('  [' + cite['source_id'] + '] ' + cite['locator'])
                if cite['source_id'] not in used:
                    used.append(cite['source_id'])
    lines += ['', 'Pendências: ' + ' '.join(editorial['notes']), '', 'Referências']
    for identifier in used:
        source = sources[identifier]
        lines += [source['citation'], source['url'], 'Edição: ' + source['edition'],
                  'Consulta: ' + source['consulted_on'], 'Avaliação crítica: ' + source['appraisal'],
                  'Direitos: ' + source['reproduction']['terms'], 'Pendências da fonte: ' + ' '.join(source['pending'])]
    lines += ['', 'Reprodução: ' + card['rights']['terms']]
    return '\n'.join(lines)
