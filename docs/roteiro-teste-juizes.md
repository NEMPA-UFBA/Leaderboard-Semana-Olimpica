# Roteiro de treinamento dos juízes

Este roteiro serve para treinar os seis juízes antes da competição e verificar
os fluxos principais do painel.

## 1. Preparação segura

- Faça os testes em uma implantação de treinamento conectada ao Neon de teste,
  nunca no banco Neon `production`. Se o app publicado estiver conectado ao
  banco de produção, não registre respostas de teste nele.
- Uma branch Neon é apenas uma cópia isolada do banco; ela não cria um endereço
  para os juízes acessarem. Use uma implantação separada do Streamlit Community
  Cloud para treinamento e configure nela o `DATABASE_URL` da branch de teste.
  Não altere os Secrets da implantação de produção.
- Confira a data de expiração da branch de teste. Se ela expirar em um dia,
  seus dados serão removidos; mantenha-a ativa até o fim do treinamento ou
  crie uma branch de teste estável.
- Crie uma conta individual para cada juiz. Não compartilhem usuário ou senha.
- Entregue senhas temporárias individualmente; cada juiz deve trocá-la no
  primeiro acesso.
- Prepare uma regata de treinamento, pelo menos três questões e equipes com o
  prefixo `TESTE -`.
- Combine quem será o administrador responsável por iniciar/parar a regata e
  por encerrar a sessão de treinamento.
- Cada juiz deve usar sua própria sessão de navegador ou dispositivo. Não
  testem concorrência compartilhando a mesma conta.

## 2. Primeiro acesso

Cada juiz deve:

1. Abrir o endereço de treinamento e entrar com sua conta individual.
2. Trocar a senha temporária quando solicitado.
3. Confirmar que o painel mostra seu nome e o horário de Brasília.
4. Atualizar a página e confirmar que continua autenticado.
5. Localizar a regata ativa, a equipe de teste e a questão combinada.

Não enviem senhas, cookies ou links de conexão do banco em grupos de mensagens.

## 3. Reserva exclusiva da questão

Façam este teste com dois juízes ao mesmo tempo:

1. O juiz A seleciona uma equipe e a Questão 1. A tela deve informar que a
   questão está reservada para ele.
2. O juiz B seleciona a mesma questão. Deve ver quem a reservou e não deve
   conseguir registrar, corrigir ou excluir tentativas.
3. O juiz A clica em **Liberar esta questão**.
4. O juiz B clica em **Assumir questão**. Agora os controles devem ficar
   disponíveis para ele.
5. O juiz A tenta usar a tela antiga. A operação deve ser recusada se o token
   da sessão anterior já tiver sido substituído.
6. O juiz B libera a questão ao terminar.

Repitam o teste com uma sessão nova da mesma conta do juiz A. Ela deve conseguir
retomar a reserva antiga; uma sessão de outro juiz deve continuar bloqueada.

Uma questão pode ficar reservada por até 90 segundos sem renovação. Enquanto o
painel está aberto, a reserva é renovada automaticamente. Ao terminar, usem
**Liberar esta questão**, em vez de deixar uma reserva ativa.

Ao trocar de equipe mantendo a mesma questão, a reserva deve ser liberada e a
questão deve ficar disponível; para continuar os lançamentos nessa questão, o
juiz precisa clicar em **Assumir questão** novamente. Ao selecionar outra
questão, a anterior deve ser liberada e a nova reservada se estiver disponível.
Os botões **Acertou** e **Errou** mantêm a reserva para permitir as próximas
tentativas da mesma equipe e questão.

## 4. Questões diferentes em paralelo

Com dois juízes:

1. O juiz A assume a Questão 2.
2. O juiz B assume a Questão 3.
3. Os dois confirmam que conseguem operar questões diferentes ao mesmo tempo.
4. Cada juiz libera sua questão ao terminar.

A reserva é por questão, não por equipe. Assim, não se deve abrir duas sessões
de juízes para corrigir simultaneamente a mesma questão.

## 5. Pontuação

Usem uma equipe de teste diferente para cada cenário, sempre na mesma questão.
Um juiz deve registrar as tentativas sequencialmente:

| Equipe de teste | Sequência | Resultado esperado |
|---|---|---|
| `TESTE - Acerto 1` | Acertar na primeira tentativa | 100 pontos |
| `TESTE - Acerto 2` | Errar e depois acertar | 80 pontos |
| `TESTE - Acerto 3` | Errar duas vezes e depois acertar | 50 pontos |
| `TESTE - Bloqueio` | Errar três vezes | 0 pontos e sem nova tentativa |

Confiram o histórico de tentativas e os pontos no placar após cada cenário.

## 6. Revisão e exclusão

Em uma equipe de teste separada:

1. Registre uma tentativa.
2. Abra a correção, altere o resultado e confirme. Verifique o resultado e o
   nome do juiz no histórico.
3. Abra outra correção e cancele. O resultado anterior deve permanecer igual.
4. Exclua uma tentativa de teste e confira se a numeração e a pontuação das
   tentativas restantes foram recalculadas.

Não use equipes ou tentativas reais para este exercício.

## 7. Encerramento e comunicação de problemas

- O administrador deve confirmar que todos liberaram suas questões antes de
  parar a regata de treinamento.
- Não apaguem dados diretamente no banco. Se for necessário limpar o ambiente,
  confirmem primeiro que estão conectados ao Neon de teste.
- Ao relatar um problema, anotem navegador/dispositivo, horário, usuário,
  regata, questão, equipe e o texto exato exibido. Uma captura de tela ajuda;
  não incluam senhas nem dados de conexão.

## Checklist do administrador

- [ ] O app de treinamento usa o Neon de teste.
- [ ] O endereço de treinamento é uma implantação separada da produção.
- [ ] Existem seis contas individuais e cada juiz consegue entrar.
- [ ] A regata de treinamento e as equipes `TESTE -` estão preparadas.
- [ ] Os seis juízes conhecem o fluxo de reservar e liberar a questão.
- [ ] Os quatro resultados de pontuação foram conferidos.
- [ ] Correção, cancelamento e exclusão foram testados com dados de teste.
- [ ] Nenhuma tentativa de treinamento foi registrada no Neon de produção.
