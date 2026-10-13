# Estado da publicacao e pendencias

Atualizado em 2026-10-13.

## Branches e publicacao

- O trabalho de suporte PostgreSQL, bootstrap seguro e migracao SQLite-Neon foi
  incorporado ao `master` da NEMPA pelo PR #1.
- A branch `feat/concorrencia-auditoria-equipes` foi criada a partir do
  `origin/master` atualizado para implementar o escopo operacional anterior ao
  evento de 14/10/2026.
- A branch anterior `integracao/nempa-com-funcionalidades-upstream` e a branch
  `roberto/auditoria-codigo` foram mantidas sem novas alteracoes.
- O usuario informou que os Secrets do Streamlit para PostgreSQL e senha inicial
  do admin ja estao configurados. Os valores nao foram inspecionados nem devem
  ser registrados neste documento ou enviados por chat.
- A branch Neon `production` e distinta da branch GitHub usada pelo Streamlit.
  A branch selecionada nas configuracoes de deploy nao foi verificada nesta
  sessao.

## Escopo implementado na branch de trabalho

- Serializar submissao, correcao e exclusao de tentativas por equipe/questao no
  PostgreSQL e impedir numeros duplicados por equipe/questao.
- Reservar cada questao para uma sessao de juiz, renovar a reserva a cada 30
  segundos, libera-la ao trocar de questao ou navegar para fora do painel do
  juiz, e expira-la apos 90 segundos sem renovacao; permitir que uma nova sessao
  do mesmo juiz assuma a reserva antiga e invalidar o token anterior; validar a
  reserva tambem no backend.
- Registrar correcoes e exclusoes em `audit_log`, incluindo ator, equipe,
  tentativa, acao e valores alterados; mostrar no historico quem registrou e
  quem fez a ultima correcao.
- Armazenar nome do juiz separado do login e mostrar registros em horario de
  Brasilia, independentemente do fuso do servidor.
- Permitir a qualquer juiz autenticado revisar tentativas de outros juizes.
- Permitir ao admin criar e excluir varias equipes de uma vez, ordenar nomes
  ignorando acentos e proteger equipes que ja tenham tentativas.
- Registrar tags de dificuldade, disciplina, area e tags personalizadas nas
  questoes, mantendo dificuldade e tags fora das telas publica e dos juizes.
- Permitir ao juiz escolher explicitamente o novo resultado ao corrigir uma
  tentativa, ou cancelar sem alterar o resultado existente.
- Exibir equipes em ordem alfabetica e indicar quais ja possuem tentativas na
  questao selecionada; atualizar a area de pontuacao em fragmento para reduzir
  recarregamentos visuais desnecessarios.
- Manter o login por 12 horas entre recarregamentos usando um token aleatorio
  em cookie; o banco armazena somente o hash do token, e o logout revoga a
  sessao. O cookie nao e HttpOnly porque a autenticacao usa o componente de
  cookies do Streamlit.
- Preservar o cadastro manual existente de regatas, questoes e equipes.
- Manter o importador SQLite compatível com bancos antigos sem auditoria e
  preservar os registros de auditoria quando existirem.

Essas alteracoes estao em uma branch de trabalho e ainda nao foram publicadas.
As migracoes de nome e fuso horario foram aplicadas na branch Neon de teste.
As tabelas de tags e de sessoes de login ainda nao foram aplicadas ao Neon
nesta sessao; o app as cria ao iniciar conectado a um banco. Confirme a branch
Neon antes de iniciar e nao use `production` para esse teste.
O teste de concorrencia e exclusividade de reserva PostgreSQL foi executado nessa branch com
`POSTGRES_TEST_DATABASE_URL`; ele nao usa automaticamente os Secrets do
Streamlit. Se o nome interno do banco nao contiver `test`, tambem exige a
confirmacao explicita `POSTGRES_TEST_BRANCH_CONFIRMED=1`.

## Validacao antes do evento

1. A suite automatizada passou com 68 testes e 1 teste ignorado; o teste PostgreSQL passou
   separadamente na branch de teste.
2. Fazer teste em navegador real para confirmar que o login sobrevive a
   recarregamentos, que o logout encerra a sessao e que navegadores comuns,
   anonimos e moveis aceitam cookies. A sessao dura 12 horas; o cookie nao e
   HttpOnly.
3. Fazer um teste visual com dois navegadores para confirmar a reserva, a
   liberacao ao navegar para outra tela e a retomada pelo mesmo juiz em uma nova
   sessao; testar tambem correcao/cancelamento, tags e indicacao de tentativas
   na selecao de equipes.
4. Fazer e testar a restauracao de um backup em ambiente separado.
5. Revisar e aprovar um PR antes de implantar. Nao alterar o banco Neon de
   producao como parte dos testes.

## Fora do escopo imediato

- Separacao dos resultados por evento e arquivo historico de competicoes.
- Importacao/exportacao de pacotes de questoes com Markdown/LaTeX e imagens.
- Restauracao de placares antigos, incluindo o evento de fevereiro de 2026.
- Cadastro de escolas e estudantes.

Esses itens devem ser planejados depois do evento de 14/10, com migracoes e
testes proprios.
