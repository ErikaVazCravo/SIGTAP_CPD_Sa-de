# CPD Saúde - SIGTAP

Aplicação Streamlit para consulta aos procedimentos SIGTAP por competência. As tabelas estão em `dados_sigtap/`, em arquivos ZIP com nome `TabelaUnificada_AAAAMM_*.zip`.

## Execução local

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

## Publicação no Streamlit Community Cloud

Conecte o repositório ao Streamlit Community Cloud, escolha a branch e informe `streamlit_app.py` como arquivo principal. Para acrescentar competências, adicione o ZIP SIGTAP à pasta `dados_sigtap` e envie a alteração ao GitHub. Não há necessidade de descompactar os arquivos.

Os dados publicados em repositório público ficam acessíveis publicamente. Os filtros de CBO retornam procedimentos associados a pelo menos um dos CBOs selecionados; filtros de tipos diferentes são combinados.
