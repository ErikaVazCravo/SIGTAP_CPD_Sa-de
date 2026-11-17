import streamlit as st
from sigtap import app as api

st.set_page_config(page_title='CPD Saúde - SIGTAP', page_icon='✳', layout='wide')
st.markdown('''<style>
.block-container {max-width:1120px;padding-top:2rem}
</style>''', unsafe_allow_html=True)
st.title('✳ CPD Saúde - SIGTAP')
st.caption('CONSULTA DE PROCEDIMENTOS DO SUS')
st.markdown('### Encontre o procedimento que você procura')
st.write('Pesquise por código, nome ou classificação e consulte as informações da competência desejada.')

@st.cache_data(ttl=3600, show_spinner=False)
def get_json(path, params=None):
    with api.test_client() as client:
        response = client.get(path, query_string=params or {})
        result = response.get_json()
        if response.status_code != 200: raise ValueError(result.get('error','Erro na consulta.'))
        return result

def option_name(item): return item['codigo'] + ' — ' + item['nome']
def label(field): return field.replace('CO_', '').replace('TP_', '').replace('QT_', '').replace('VL_', '').replace('_',' ').capitalize()
def cash(value): return 'R$ {:,.2f}'.format(int(value or 0)/100).replace(',', 'X').replace('.', ',').replace('X', '.')
def display(value): return '—' if not value or value == '9999' else str(int(value)) if str(value).isdigit() else value

def current_options(items): return {x['codigo']:option_name(x) for x in items}
versions = get_json('/api/versoes')
if not versions:
    st.error('Nenhuma tabela SIGTAP foi encontrada em dados_sigtap.'); st.stop()
version = st.selectbox('Competência', versions, format_func=lambda x:x[4:]+'/'+x[:4], key='version')
options = get_json('/api/classificacoes', {'competencia':version})
if st.session_state.get('loaded_version') != version:
    for key in ['grupo','subgrupo','forma','modalidade','complexidade','financiamento','registro','sexo','atributo','cbo','regra']:
        st.session_state.pop(key, None)
    st.session_state.loaded_version = version
    st.session_state.pop('result', None); st.session_state.pop('selected', None)

def choose(title, key, items, all_label):
    lookup=current_options(items)
    return st.selectbox(title, ['']+list(lookup), format_func=lambda x:lookup.get(x,all_label), key=key)

def clear_all():
    for key in ['texto','grupo','subgrupo','forma','modalidade','complexidade','financiamento','registro','sexo','atributo','cbo','regra','result','selected']:
        st.session_state.pop(key,None)
    st.session_state['version'] = versions[0]

# Classification selectors are outside the form so dependent lists update immediately.
with st.container(border=True):
    query=st.text_input('Código ou nome do procedimento', placeholder='Ex.: consulta médica ou 0301010072', key='texto')
    col1,col2,col3=st.columns(3)
    with col1: group=choose('Grupo','grupo',options['grupos'],'Todos os grupos')
    with col2:
        sub_options=[x for x in options['subgrupos'] if group and x['codigo'].startswith(group)]
        if st.session_state.get('subgrupo') not in ['']+[x['codigo'] for x in sub_options]: st.session_state['subgrupo']=''
        sub=choose('Subgrupo','subgrupo',sub_options,'Todos os subgrupos')
    with col3:
        form_options=[x for x in options['formas'] if sub and x['codigo'].startswith(sub)]
        if st.session_state.get('forma') not in ['']+[x['codigo'] for x in form_options]: st.session_state['forma']=''
        form=choose('Forma de organização','forma',form_options,'Todas as formas')
    a,b,c=st.columns(3)
    with a: modality=choose('Modalidade de atendimento','modalidade',options['modalidade'],'Todas as modalidades')
    with b: complexity=st.selectbox('Complexidade',['','1','2','3'],format_func=lambda x:{'':'Todas as complexidades','1':'Atenção básica','2':'Média complexidade','3':'Alta complexidade'}[x],key='complexidade')
    with c: financing=choose('Financiamento','financiamento',options['financiamento'],'Todos os financiamentos')
    a,b,c=st.columns(3)
    with a: registry=choose('Instrumento de registro','registro',options['registro'],'Todos os instrumentos')
    with b: sex=st.selectbox('Sexo',['','I','F','M'],format_func=lambda x:{'':'Todos','I':'Ambos','F':'Feminino','M':'Masculino'}[x],key='sexo')
    with c: attribute=choose('Atributos complementares','atributo',options['atributo'],'Todos os atributos')
    a,b=st.columns(2)
    with a:
        cbo_lookup=current_options(options['cbo'])
        cbos=st.multiselect('CBO — pesquise pelo código ou nome', list(cbo_lookup),format_func=lambda x:cbo_lookup[x],key='cbo',placeholder='Digite para pesquisar e selecione um ou mais CBOs')
    with b: rule=choose('Regra condicionada','regra',options['regra'],'Todas as regras')
    st.caption('Os filtros podem ser combinados. Para vários CBOs, basta que o procedimento corresponda a um deles.')
    left,clear,submit=st.columns([6,1,1])
    with clear: st.button('Limpar',on_click=clear_all,use_container_width=True)
    with submit: search=st.button('Pesquisar →',type='primary',use_container_width=True)

if search:
    try:
        params={'competencia':version,'q':query,'grupo':group,'subgrupo':sub,'forma':form,'modalidade':modality,'complexidade':complexity,'financiamento':financing,'registro':registry,'sexo':sex,'atributo':attribute,'cbo':cbos,'regra':rule,'pagina':1}
        get_json('/api/busca',params)
        st.session_state.result=params;st.session_state.page=1;st.session_state.pop('selected',None)
    except ValueError as e: st.error(str(e))

def show_detail(code):
    j=get_json('/api/procedimento/'+code,{'competencia':version});p=j['procedimento']
    if st.button('← Voltar aos resultados'): st.session_state.pop('selected',None);st.rerun()
    st.caption('PROCEDIMENTO · '+code);st.subheader(p['NO_PROCEDIMENTO'])
    st.markdown('#### Classificação')
    for h in j['hierarquia']: st.write(f"**{label(h['campo'])}:** {h['codigo']} — {h['nome']}")
    st.write('**Competência:** '+version[4:]+'/'+version[:4])
    rel={g['tabela'].replace('rl_procedimento_',''):g['itens'] for g in j['relacionamentos']}
    def related(key): return ' | '.join(' · '.join(f.get('descricao') or f['valor'] for f in row) for row in rel.get(key,[])) or '—'
    st.markdown('#### Informações do procedimento')
    facts=[('Modalidade de atendimento',related('modalidade')),('Complexidade',{'1':'Atenção básica','2':'Média complexidade','3':'Alta complexidade'}.get(p['TP_COMPLEXIDADE'],p['TP_COMPLEXIDADE'])),('Financiamento',j['financiamento'] or p['CO_FINANCIAMENTO']),('Subtipo de financiamento',j['rubrica'] or p['CO_RUBRICA'] or '—'),('Instrumento de registro',related('registro')),('Sexo',{'I':'Ambos','F':'Feminino','M':'Masculino'}.get(p['TP_SEXO'],p['TP_SEXO'])),('Média de permanência',display(p['QT_DIAS_PERMANENCIA'])),('Tempo de permanência',display(p['QT_TEMPO_PERMANENCIA'])),('Quantidade máxima',display(p['QT_MAXIMA_EXECUCAO'])),('Idade mínima',display(p['VL_IDADE_MINIMA'])+' meses'),('Idade máxima',display(p['VL_IDADE_MAXIMA'])+' meses'),('Pontos',display(p['QT_PONTOS'])),('Atributos complementares',related('detalhe'))]
    for i in range(0,len(facts),2):
        cols=st.columns(2)
        for col,(name,value) in zip(cols,facts[i:i+2]): col.write(f'**{name}:** {value}')
    st.markdown('#### Valores')
    a,b=st.columns(2)
    with a:
        with st.container(border=True):
            st.markdown('**Ambulatorial**');st.write('Serviço ambulatorial: '+cash(p['VL_SA']));st.write('Total ambulatorial: '+cash(p['VL_SA']))
    with b:
        with st.container(border=True):
            st.markdown('**Hospitalar**');st.write('Serviço hospitalar: '+cash(p['VL_SH']));st.write('Serviço profissional: '+cash(p['VL_SP']));st.write('Total hospitalar: '+cash(int(p['VL_SH'])+int(p['VL_SP'])))
    st.markdown('#### Informações relacionadas')
    names={'cid':'CID','ocupacao':'CBO','leito':'Leito','servico':'Serviço / classificação','habilitacao':'Habilitação','comp_rede':'Redes','origem':'Origem','regra_cond':'Regra condicionada','renases':'Renases','tuss':'TUSS','compativel':'Compatibilidade','sia_sih':'SIA / SIH','incremento':'Incrementos'}
    groups=[(names.get(k,label(k)),rows) for k,rows in rel.items() if k not in ('modalidade','registro','detalhe')]
    if any(name == 'Compatibilidade' for name, _ in groups):
        st.caption('Os tipos 1, 2 e 3 seguem o layout da tabela. O tipo 5 para APAC principal e secund\u00e1rio foi conferido na consulta SIGTAP. Outras regras legais podem estabelecer exig\u00eancias adicionais.')
    tabs=st.tabs(['Descrição']+[name for name,rows in groups])
    with tabs[0]: st.write(j['descricao'] or 'Descrição não disponível nesta competência.')
    for tab,(group_name,rows) in zip(tabs[1:],groups):
        with tab:
            for row in rows:
                if group_name == 'Compatibilidade':
                    fields = {x['campo']: x for x in row}
                    def field_text(key):
                        field = fields.get(key)
                        if not field:
                            if key == 'CO_PROCEDIMENTO_PRINCIPAL': return code + ' - ' + p['NO_PROCEDIMENTO']
                            return '\u2014'
                        return field['valor'] + (' \u2014 ' + field['descricao'] if field.get('descricao') else '')
                    with st.container(border=True):
                        st.caption('Papel na compatibilidade: ' + field_text('PAPEL_NA_COMPATIBILIDADE'))
                        st.write('**Procedimento principal:** ' + field_text('CO_PROCEDIMENTO_PRINCIPAL'))
                        st.write('**Procedimento compat\u00edvel:** ' + field_text('CO_PROCEDIMENTO_COMPATIVEL'))
                        left, right = st.columns(2)
                        left.write('**Registro principal:** ' + field_text('CO_REGISTRO_PRINCIPAL'))
                        right.write('**Registro compat\u00edvel:** ' + field_text('CO_REGISTRO_COMPATIVEL'))
                        left, right = st.columns(2)
                        type_code = fields.get('TP_COMPATIBILIDADE', {}).get('valor', '')
                        type_labels = {'1':'Compat\u00edvel', '2':'Incompat\u00edvel / excludente', '3':'Concomitante'}
                        if type_code == '5' and fields.get('CO_REGISTRO_PRINCIPAL', {}).get('valor') == '06' and fields.get('CO_REGISTRO_COMPATIVEL', {}).get('valor') == '07':
                            type_text = 'Obrigat\u00f3ria (APAC principal x APAC secund\u00e1rio)'
                        else:
                            type_text = type_labels.get(type_code, 'N\u00e3o identificado; consulte o SIGTAP')
                        left.write('**Tipo de compatibilidade:** ' + type_text + ' (c\u00f3digo ' + (type_code or '\u2014') + ')')
                        right.write('**Quantidade permitida:** ' + display(fields.get('QT_PERMITIDA', {}).get('valor')))
                else:
                    st.write(' \u00b7 '.join(f"**{label(x['campo'])}:** {x['valor']}"+(f" \u2014 {x['descricao']}" if x.get('descricao') else '') for x in row))

if st.session_state.get('selected'):
    try: show_detail(st.session_state.selected)
    except ValueError as e: st.error(str(e))
elif st.session_state.get('result'):
    params=st.session_state.result.copy();params['pagina']=st.session_state.get('page',1)
    try:
        j=get_json('/api/busca',params);st.markdown('### Resultados');st.caption(f"{j['total']} procedimento(s) encontrado(s)")
        if not j['total']: st.info('Nenhum procedimento encontrado. Ajuste os filtros e tente novamente.')
        for item in j['resultados']:
            if st.button(item['codigo']+' — '+item['nome'],key='proc_'+item['codigo'],use_container_width=True): st.session_state.selected=item['codigo'];st.rerun()
        if j['paginas']>1:
            a,b,c=st.columns([1,3,1])
            if a.button('← Anterior',disabled=j['pagina']<=1): st.session_state.page-=1;st.rerun()
            b.write(f"Página {j['pagina']} de {j['paginas']}")
            if c.button('Próxima →',disabled=j['pagina']>=j['paginas']): st.session_state.page+=1;st.rerun()
    except ValueError as e: st.error(str(e))
else:
    st.markdown('### Resultados');st.info('Informe um código, nome ou filtro para iniciar a pesquisa.')
