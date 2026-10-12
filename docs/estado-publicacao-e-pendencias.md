# Estado da publicacao e pendencias

Atualizado em 2026-10-12.

## Estado atual

- A branch local de trabalho e `integracao/nempa-com-funcionalidades-upstream`,
  baseada no historico NEMPA.
- As alteracoes listadas abaixo ainda nao foram staged, commitadas, enviadas ao
  GitHub nem publicadas no Streamlit. O codigo do app online continua sendo o
  anterior.
- O arquivo `.env` permanece ignorado pelo Git. Nunca registrar neste documento
  nem enviar por chat os valores de `DATABASE_URL` ou `ADMIN_INITIAL_PASSWORD`.
- O usuario informou que configurou os Secrets do app Streamlit NEMPA. Os
  valores nao foram inspecionados. O alvo e
  `leaderboard-semana-olimpica.streamlit.app`, nao o app V2
  `semana-olimpica.streamlit.app`.
- No projeto Neon existem a branch padrao `production` e a branch
  `leaderboard-teste`. A URL do `.env` local aponta para `leaderboard-teste`;
  ela contem dados de teste e nao deve ser usada nos Secrets do app de producao.
- Uma verificacao somente leitura encontrou no banco de teste 4 usuarios,
  4 equipes, 2 regatas, 6 questoes e 48 tentativas. O banco tinha cerca de
  14 MB, incluindo aproximadamente 5,8 MB de imagens. O painel Neon estava
  mostrando a branch `production`, diferente da branch local de teste; por isso,
  um indicador vazio nessa tela nao significa que o banco de teste esteja vazio.
- A numeracao de questoes esta implementada por regata, reiniciando em 1 e
  ordenada por nivel (facil, medio, dificil) e ID. O seletor do Juiz mostra
  `Questao N — nivel`, sem trecho do enunciado.
- A suite local passou com 34 testes; sintaxe e `git diff --check` tambem
  passaram.

## Organizacao sugerida dos commits

Stage e confira um grupo por vez. Evite `git add .` e `git add -A`; use os
caminhos explicitos abaixo. Antes de cada commit, confira `git status --short`,
`git diff --cached --check` e `git diff --cached --stat`.

### 1. Contas, protecao de senha e suporte PostgreSQL

Arquivos:

```text
.gitignore
auth.py
database.py
models.py
pages/1_Admin.py
requirements.txt
tests/test_auth.py
tests/test_database.py
docs/seguranca-acessos.md
```

Stage:

```bash
git add .gitignore auth.py database.py models.py pages/1_Admin.py requirements.txt tests/test_auth.py tests/test_database.py docs/seguranca-acessos.md
```

Mensagem sugerida:

```text
feat: secure account bootstrap and add PostgreSQL support
```

### 2. Fluxo do juiz, pontuacao e numeracao das questoes

Arquivos:

```text
app.py
pages/2_Juiz.py
pages/3_Leaderboard.py
pages/4_Questoes.py
scoring.py
question_utils.py
tests/test_scoring.py
tests/test_question_utils.py
docs/conteudo-questoes-e-dados.md
```

Stage:

```bash
git add app.py pages/2_Juiz.py pages/3_Leaderboard.py pages/4_Questoes.py scoring.py question_utils.py tests/test_scoring.py tests/test_question_utils.py docs/conteudo-questoes-e-dados.md
```

Mensagem sugerida:

```text
feat: improve judge workflow and number regatta questions
```

### 3. Importacao protegida do SQLite para Neon

Arquivos:

```text
scripts/migrate_sqlite_to_neon.py
tests/test_migration.py
docs/migracao-sqlite-neon.md
```

Stage:

```bash
git add scripts/migrate_sqlite_to_neon.py tests/test_migration.py docs/migracao-sqlite-neon.md
```

Mensagem sugerida:

```text
feat: add guarded SQLite-to-Neon migration
```

### 4. Registro do estado e das pendencias

Arquivo:

```text
docs/estado-publicacao-e-pendencias.md
```

Stage:

```bash
git add docs/estado-publicacao-e-pendencias.md
```

Mensagem sugerida:

```text
docs: record release status and follow-ups
```

Depois de cada commit, confira o `git status --short`. Quando os quatro grupos
estiverem commitados, rode novamente:

```bash
./venv_leaderboard/bin/python -m pytest -q tests
```

## Proximas etapas para publicar

1. Confirmar nos Secrets do app Streamlit que `DATABASE_URL` aponta para a
   branch Neon `production`, e nao para `leaderboard-teste`. O usuario informou
   que ja configurou os Secrets; essa associacao ainda precisa ser validada no
   primeiro deploy.
2. Confirmar nas configuracoes do Streamlit qual branch GitHub e implantada.
   As alteracoes locais estao na branch de integracao e ainda nao chegaram ao
   deploy.
3. Fazer os commits acima, enviar a branch ao GitHub e abrir/revisar um PR para
   a branch que alimenta o app NEMPA. Nao publicar diretamente na V2.
4. Acompanhar a construcao do Streamlit Cloud e testar o app publicado: login
   do admin, troca inicial de senha, cadastro de juiz, criacao de regata,
   equipes e questoes, registro/correcao/exclusao de tentativas.
5. Como a branch de producao deve comecar limpa, cadastrar nela os dados
   definitivos da competicao. Nao copiar a branch de teste inteira, pois ela
   contem contas e tentativas de teste.
6. Depois do primeiro login e da troca da senha inicial do admin, considerar
   remover `ADMIN_INITIAL_PASSWORD` dos Secrets. Nunca registrar o valor em Git.

## Pendencias antes de uso real com varios juizes

- Proteger o registro simultaneo de tentativas com transacao e restricao unica
  adequada, e testar dois juizes registrando a mesma equipe/questao ao mesmo
  tempo.
- Criar trilha de auditoria para correcoes e exclusoes, identificando quem fez
  cada alteracao.
- Definir e testar uma rotina de backup e restauracao do PostgreSQL antes do
  evento.
- Revisar as migracoes legadas em `database.py`: uma delas recria a tabela de
  tentativas usando SQL especifico do SQLite. A branch de producao deve partir
  vazia, mas essa migracao precisa de tratamento PostgreSQL antes de reutilizar
  o codigo com um banco legado.
- Confirmar que o `requirements.txt` atual, com versoes fixadas, constroi sem
  erros no Streamlit Community Cloud.
