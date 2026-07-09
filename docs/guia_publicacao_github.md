# Guia De Publicação No GitHub

Este guia mostra como publicar o projeto de forma profissional sem expor dados
privados, arquivos do Capital IQ ou teses reais.

## Objetivo Da Página Do GitHub

O GitHub deve provar três coisas:

1. Você sabe construir uma ferramenta de análise financeira robusta.
2. Você entende valuation, comps, data quality e tese de investimento.
3. Você sabe proteger dados licenciados e confidenciais.

O repositório não deve tentar provar que você tem acesso ao Capital IQ mostrando
dados brutos. O ideal é mostrar a arquitetura, a demo pública, os prints
sanitizados e a metodologia.

## Estrutura Que Deve Ser Publicada

```text
portfolio-company-monitoring-dashboard/
  .github/
    workflows/
      tests.yml
  data/
    reference/
    sample/
      assumptions/
      public_demo/
      theses/
    templates/
  docs/
    capital_iq_import_guide.md
    data_dictionary.md
    github_portfolio_strategy.md
    guia_publicacao_github.md
    methodology.md
  reports/
    sample/
      01_watchlist_home.png
      02_peer_benchmarking.png
      03_valuation_case.png
      04_football_field.png
      05_multiples_scorecard.png
      06_data_audit.png
      ic_memo_TOTS3.html
      valuation_case_TOTS3.html
  scripts/
  src/
  tests/
  .gitattributes
  .gitignore
  LICENSE
  README.md
  pyproject.toml
  requirements.txt
```

## Arquivos E Pastas Para Subir

Subir:

| Caminho | Por que subir |
| --- | --- |
| `README.md` | Página principal do GitHub, em português. |
| `src/` | Código principal do sistema. |
| `scripts/` | Automação do Capital IQ, manutenção e geração de prints. |
| `tests/` | Prova de robustez e cuidado com qualidade. |
| `.github/workflows/` | CI/testes automáticos no GitHub. |
| `data/sample/` | Demo pública que roda sem Capital IQ. |
| `data/templates/` | Templates para importação e teses. |
| `data/reference/` | Parâmetros públicos/de referência. |
| `reports/sample/` | Prints e outputs sanitizados. |
| `docs/` | Metodologia, dicionário de dados e guia de publicação. |
| `requirements.txt` / `pyproject.toml` | Instalação do projeto. |
| `.gitignore` | Proteção contra vazamento de arquivos privados. |

## Arquivos E Pastas Para Não Subir

Não subir em hipótese alguma:

| Caminho | Motivo |
| --- | --- |
| `data_private/` | Dados reais, exports, teses privadas, relatórios privados. |
| `data/processed/` | Build local, pode conter outputs intermediários. |
| `reports/private/` | Relatórios privados. |
| `tmp/` | Arquivos temporários e renders locais. |
| `.venv/` | Ambiente local. |
| `.streamlit/secrets.toml` | Segredos locais. |
| `*.xlsb` | Workbooks privados do Capital IQ. |
| Decks originais | Podem conter dados licenciados do Capital IQ. |
| Screenshots privados | Podem revelar watchlist, peer sets e números licenciados. |

## Prints Que Devem Aparecer No README

Use somente estes prints públicos:

```text
reports/sample/01_watchlist_home.png
reports/sample/02_peer_benchmarking.png
reports/sample/03_valuation_case.png
reports/sample/04_football_field.png
reports/sample/05_multiples_scorecard.png
reports/sample/06_data_audit.png
```

Eles são bons porque mostram o produto sem revelar sua base privada.

## Checklist Antes Do Push

Rode:

```powershell
git status --short
python scripts/check_git_hygiene.py
pytest
```

Confira se estes comandos retornam que os arquivos são ignorados:

```powershell
git check-ignore data_private/universe.csv
git check-ignore data_private/theses/EXCHANGE_TICKER.yaml
git check-ignore data_private/assumptions/EXCHANGE_TICKER.yaml
git check-ignore data_private/reports/ic_memo_PRIVATE.html
git check-ignore tmp/qualquer_arquivo.png
```

Faça uma busca por termos privados antes de publicar:

```powershell
rg -n "PRIVATE_MODE_MARKER|PRIVATE_TICKER|PRIVATE_COMPANY" README.md docs reports/sample data/sample
```

Observação: mencionar `data_private` na documentação é aceitável quando for para
explicar a política de confidencialidade. O problema é publicar arquivos ou
números privados. Também procure manualmente por caminhos locais da sua máquina
em screenshots e HTMLs públicos.

## Nome Recomendado Do Repositório

Boas opções:

- `valuation-workbench`
- `capital-iq-valuation-workbench`
- `investment-analysis-workbench`
- `public-equity-valuation-dashboard`

Minha preferência: **`valuation-workbench`**. É mais limpo, mais institucional e
não parece dependente de uma única fonte de dados.

## Descrição Curta Do GitHub

Use:

> Workbench de análise de investimentos em Python: Capital IQ ingestion,
> peer benchmarking, DCF, data audit, valuation case e IC memo com demo pública.

## Tópicos Do GitHub

Use estes tópicos:

```text
python
finance
valuation
private-equity
investment-banking
capital-iq
streamlit
plotly
pandas
dcf
comparable-companies
financial-analysis
```

## Como Explicar Para Recrutadores

Mensagem curta:

> Eu construí uma ferramenta que transforma exports do Capital IQ em um workflow
> de análise de investimento: valida os dados, compara empresas contra peers,
> calcula múltiplos, monta DCF, gera football field e exporta um memo de IC
> combinando dados quantitativos com uma tese escrita pelo analista. No GitHub,
> publiquei apenas a demo sanitizada; os dados licenciados ficam privados.

Mensagem mais completa:

> O projeto nasceu de casos de valuation que eu havia feito manualmente em Excel
> e PowerPoint. Eu transformei esse processo em software: o sistema puxa dados
> via Capital IQ, normaliza os financials, revisa peer groups, audita qualidade
> de dados, calcula valuation e junta tudo em outputs que lembram materiais de
> um time de investimento. A parte mais importante é que o sistema não tenta
> substituir o analista; ele cria uma estrutura para organizar a tese, as
> premissas e as perguntas de diligência.

## Ordem Recomendada Para Publicar

1. Confirmar que `data_private/` está ignorado.
2. Rodar a demo pública.
3. Gerar screenshots públicos.
4. Rodar testes.
5. Ler o README no preview do GitHub.
6. Fazer o primeiro commit.
7. Subir o repo privado primeiro, revisar no GitHub, depois tornar público se
   estiver confortável.

## Frase Para O CV

> Desenvolvi uma valuation workbench em Python integrada ao Capital IQ, capaz de
> transformar exports financeiros, peer sets, estimativas e teses escritas pelo
> analista em dashboards de monitoramento, análises de comps, DCF, football
> field, data audit e memos de comitê de investimento, com demo pública e
> proteção de dados licenciados.
