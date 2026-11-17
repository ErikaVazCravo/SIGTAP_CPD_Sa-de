from pathlib import Path
from functools import lru_cache
import csv
import io
import re
import unicodedata
import zipfile
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)
BASE = Path(__file__).resolve().parent / 'dados_sigtap'

def versions():
    result = {}
    for path in sorted(BASE.glob('TabelaUnificada_*.zip')):
        m = re.search(r'TabelaUnificada_(\d{6})', path.name, re.I)
        if m: result[m.group(1)] = path
    return dict(sorted(result.items(), reverse=True))

def normal(text):
    return ''.join(c for c in unicodedata.normalize('NFKD', str(text).upper()) if not unicodedata.combining(c))

def layout(z, name):
    filename = name + '_layout.txt'
    if filename not in z.namelist(): return []
    rows = csv.reader(io.StringIO(z.read(filename).decode('latin-1')))
    next(rows, None)
    fields = []
    for row in rows:
        if len(row) >= 4:
            try: fields.append((row[0].strip(), int(row[2])-1, int(row[3])))
            except ValueError: pass
    return fields

def records(z, name):
    filename = name + '.txt'
    if filename not in z.namelist(): return
    fields = layout(z, name)
    if not fields: return
    with z.open(filename) as stream:
        for line in stream:
            text = line.decode('latin-1').rstrip('\r\n')
            yield {key: text[start:end].strip() for key, start, end in fields}

@lru_cache(maxsize=4)
def procedures(version, filename, modified):
    with zipfile.ZipFile(filename) as z:
        return list(records(z, 'tb_procedimento'))

def version_path(version):
    path = versions().get(version)
    if path is None: raise ValueError('Competência não encontrada na pasta SIGTAP.')
    return path

def procs(version):
    p = version_path(version)
    return procedures(version, str(p), p.stat().st_mtime_ns)

@app.get('/')
def home(): return render_template('consulta.html')

@app.get('/api/versoes')
def api_versions(): return jsonify(list(versions()))

@app.get('/api/classificacoes')
def classifications():
    try:
        version = request.args.get('competencia', '')
        with zipfile.ZipFile(version_path(version)) as z:
            groups = [{'codigo': r['CO_GRUPO'], 'nome': r['NO_GRUPO']} for r in records(z, 'tb_grupo')]
            subgroups = [{'codigo': r['CO_GRUPO'] + r['CO_SUB_GRUPO'], 'nome': r['NO_SUB_GRUPO']} for r in records(z, 'tb_sub_grupo')]
            forms = [{'codigo': r['CO_GRUPO'] + r['CO_SUB_GRUPO'] + r['CO_FORMA_ORGANIZACAO'], 'nome': r['NO_FORMA_ORGANIZACAO']} for r in records(z, 'tb_forma_organizacao')]
            options = {}
            for name, table, code, label in [('modalidade','tb_modalidade','CO_MODALIDADE','NO_MODALIDADE'), ('financiamento','tb_financiamento','CO_FINANCIAMENTO','NO_FINANCIAMENTO'), ('registro','tb_registro','CO_REGISTRO','NO_REGISTRO'), ('atributo','tb_detalhe','CO_DETALHE','NO_DETALHE'), ('cbo','tb_ocupacao','CO_OCUPACAO','NO_OCUPACAO'), ('regra','tb_regra_condicionada','CO_REGRA_CONDICIONADA','NO_REGRA_CONDICIONADA')]:
                options[name] = [{'codigo':r[code], 'nome':r[label]} for r in records(z, table)]
        return jsonify(grupos=groups, subgrupos=subgroups, formas=forms, **options)
    except (ValueError, OSError, zipfile.BadZipFile) as e:
        return jsonify(error=str(e)), 400

@app.get('/api/busca')
def search():
    try:
        version = request.args.get('competencia', '')
        query = request.args.get('q', '').strip()
        group = request.args.get('grupo', '')
        sub = request.args.get('subgrupo', '')
        form = request.args.get('forma', '')
        for value, length in ((group, 2), (sub, 4), (form, 6)):
            if value and not re.fullmatch(r'\d{' + str(length) + r'}', value): raise ValueError('Filtro de classifica\u00e7\u00e3o inv\u00e1lido.')
        if sub and (not group or not sub.startswith(group)): raise ValueError('Subgrupo incompat\u00edvel com o grupo.')
        if form and (not sub or not form.startswith(sub)): raise ValueError('Forma de organiza\u00e7\u00e3o incompat\u00edvel com o subgrupo.')
        filters = {key:request.args.get(key, '') for key in ('modalidade','complexidade','financiamento','registro','sexo','atributo','cbo','regra')}
        if not query and not group and not any(filters.values()): return jsonify(error='Informe um termo ou selecione um filtro.'), 400
        if query and len(query) < 2: return jsonify(error='Digite pelo menos 2 caracteres.'), 400
        term = normal(query)
        digits = re.sub(r'\D', '', query)
        numeric = bool(digits) and not re.search(r'[A-Za-zÀ-ÿ]', query)
        matches = [p for p in procs(version) if p['CO_PROCEDIMENTO'].startswith(form or sub or group) and (digits in p['CO_PROCEDIMENTO'] if numeric else all(word in normal(p['NO_PROCEDIMENTO']) for word in term.split()))]
        for field, column in [('complexidade','TP_COMPLEXIDADE'), ('financiamento','CO_FINANCIAMENTO'), ('sexo','TP_SEXO')]:
            if filters[field]: matches = [p for p in matches if p.get(column) == filters[field]]
        selected_cbos = request.args.getlist('cbo')
        if any(not re.fullmatch(r'\d{6}', value) for value in selected_cbos): raise ValueError('CBO inv\u00e1lido.')
        relations = [('modalidade','rl_procedimento_modalidade','CO_MODALIDADE'), ('registro','rl_procedimento_registro','CO_REGISTRO'), ('atributo','rl_procedimento_detalhe','CO_DETALHE'), ('cbo','rl_procedimento_ocupacao','CO_OCUPACAO'), ('regra','rl_procedimento_regra_cond','CO_REGRA_CONDICIONADA')]
        if any(filters[field] for field, _, _ in relations):
            with zipfile.ZipFile(version_path(version)) as z:
                for field, table, column in relations:
                    if filters[field]:
                        codes = {r['CO_PROCEDIMENTO'] for r in records(z, table) if r.get(column) in (selected_cbos if field == 'cbo' else [filters[field]])}
                        matches = [p for p in matches if p['CO_PROCEDIMENTO'] in codes]
        try: page = max(1, int(request.args.get('pagina', 1)))
        except ValueError: page = 1
        size = 30
        return jsonify(total=len(matches), pagina=page, paginas=(len(matches)+size-1)//size, resultados=[{'codigo':p['CO_PROCEDIMENTO'],'nome':p['NO_PROCEDIMENTO']} for p in matches[(page-1)*size:page*size]])
    except (ValueError, OSError, zipfile.BadZipFile) as e: return jsonify(error=str(e)), 400

# Dictionary tables used to add labels to the source relationships.
REFS = {
 'CO_CID': ('tb_cid','CO_CID','NO_CID'), 'CO_OCUPACAO': ('tb_ocupacao','CO_OCUPACAO','NO_OCUPACAO'),
 'CO_MODALIDADE': ('tb_modalidade','CO_MODALIDADE','NO_MODALIDADE'), 'CO_REGISTRO': ('tb_registro','CO_REGISTRO','NO_REGISTRO'),
 'CO_TIPO_LEITO': ('tb_tipo_leito','CO_TIPO_LEITO','NO_TIPO_LEITO'), 'CO_DETALHE': ('tb_detalhe','CO_DETALHE','NO_DETALHE'),
 'CO_HABILITACAO': ('tb_habilitacao','CO_HABILITACAO','NO_HABILITACAO'), 'CO_SERVICO': ('tb_servico','CO_SERVICO','NO_SERVICO'),
 'CO_REGRA_CONDICIONADA': ('tb_regra_condicionada','CO_REGRA_CONDICIONADA','NO_REGRA_CONDICIONADA'),
 'CO_FINANCIAMENTO': ('tb_financiamento','CO_FINANCIAMENTO','NO_FINANCIAMENTO'), 'CO_RUBRICA': ('tb_rubrica','CO_RUBRICA','NO_RUBRICA'),
 'CO_RENASES': ('tb_renases','CO_RENASES','NO_RENASES'), 'CO_TUSS': ('tb_tuss','CO_TUSS','NO_TUSS'), 'CO_COMPONENTE_REDE': ('tb_componente_rede','CO_COMPONENTE_REDE','NO_COMPONENTE_REDE')}

@app.get('/api/procedimento/<codigo>')
def detail(codigo):
    try:
        version = request.args.get('competencia', '')
        if not re.fullmatch(r'\d{10}', codigo): raise ValueError('Código inválido.')
        proc = next((p for p in procs(version) if p['CO_PROCEDIMENTO'] == codigo), None)
        if not proc: return jsonify(error='Procedimento não encontrado nesta competência.'), 404
        with zipfile.ZipFile(version_path(version)) as z:
            dictionaries = {}
            for table, key, label in set(REFS.values()):
                dictionaries[(table,key,label)] = {r.get(key):r.get(label) for r in records(z, table)}
            for p in records(z, 'tb_descricao'):
                if p.get('CO_PROCEDIMENTO') == codigo:
                    description = p.get('DS_PROCEDIMENTO',''); break
            else: description = ''
            hierarchy = []
            for table, length, name in [('tb_grupo',2,'NO_GRUPO'), ('tb_sub_grupo',4,'NO_SUB_GRUPO'), ('tb_forma_organizacao',6,'NO_FORMA_ORGANIZACAO')]:
                for row in records(z, table):
                    key = row.get('CO_GRUPO','') + row.get('CO_SUB_GRUPO','') + row.get('CO_FORMA_ORGANIZACAO','')
                    if key == codigo[:length]:
                        hierarchy.append({'campo':table.replace('tb_',''), 'codigo':key, 'nome':row.get(name,'')})
                        break
            classifications = {(r.get('CO_SERVICO'),r.get('CO_CLASSIFICACAO')):r.get('NO_CLASSIFICACAO') for r in records(z, 'tb_servico_classificacao')}
            proc_names = {p['CO_PROCEDIMENTO']:p['NO_PROCEDIMENTO'] for p in procs(version)}
            relations = []
            for filename in sorted(z.namelist()):
                if not (filename.startswith('rl_procedimento_') and filename.endswith('_layout.txt')): continue
                table = filename[:-11]
                fields = layout(z, table)
                keys = [key for key, _, _ in fields if key in ('CO_PROCEDIMENTO', 'CO_PROCEDIMENTO_PRINCIPAL')]
                if not keys: continue
                rows = []
                for row in records(z, table):
                    direct = row.get(keys[0]) == codigo
                    reverse = table == 'rl_procedimento_compativel' and row.get('CO_PROCEDIMENTO_COMPATIVEL') == codigo
                    if not (direct or reverse): continue
                    enriched = []
                    if table == 'rl_procedimento_compativel':
                        enriched.append({'campo': 'PAPEL_NA_COMPATIBILIDADE', 'valor': 'Principal' if direct else 'Compatível', 'descricao': None})
                    for key, value in row.items():
                        if key == 'DT_COMPETENCIA' or not value: continue
                        if key == keys[0] and not (reverse and not direct): continue
                        ref = REFS.get(key)
                        label = dictionaries.get(ref, {}).get(value) if ref else None
                        if key in ('CO_REGISTRO_PRINCIPAL', 'CO_REGISTRO_COMPATIVEL'): label = dictionaries.get(REFS['CO_REGISTRO'], {}).get(value)
                        if key == 'CO_CLASSIFICACAO': label = classifications.get((row.get('CO_SERVICO'), value))
                        if key in ('CO_PROCEDIMENTO_PRINCIPAL','CO_PROCEDIMENTO_COMPATIVEL','CO_PROCEDIMENTO_ORIGEM','CO_PROCEDIMENTO_SIA_SIH'):
                            label = proc_names.get(value)
                        enriched.append({'campo':key,'valor':value,'descricao':label})
                    if enriched: rows.append(enriched)
                if rows: relations.append({'tabela':table,'itens':rows})
        return jsonify(procedimento=proc, descricao=description, relacionamentos=relations, hierarquia=hierarchy, competencia=version, financiamento=dictionaries.get(REFS['CO_FINANCIAMENTO'], {}).get(proc.get('CO_FINANCIAMENTO')), rubrica=dictionaries.get(REFS['CO_RUBRICA'], {}).get(proc.get('CO_RUBRICA')))
    except (ValueError, OSError, zipfile.BadZipFile) as e: return jsonify(error=str(e)), 400

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5051, debug=False)
