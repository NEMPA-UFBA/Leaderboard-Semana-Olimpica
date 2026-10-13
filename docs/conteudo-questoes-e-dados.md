# Conteudo das questoes e armazenamento

## Formatacao de enunciados

A tela de questoes renderiza cada enunciado com `st.markdown`. Isso permite
combinar Markdown com expressoes matematicas suportadas pelo KaTeX; nao e um
compilador de documentos LaTeX completos.

As questoes recebem um numero de exibicao sequencial dentro da regata, reiniciado
em cada regata. A ordem e pelo ID da questao, que corresponde a ordem em que ela
foi cadastrada. Esse numero aparece no painel Admin, na aba Questoes e no seletor
do Juiz; ele nao e um campo separado no banco. A pagina Leaderboard mostra
atualmente apenas o ranking, nao os enunciados.

Exemplos:

```text
Resolva *com atencao*:

- Primeiro item
- Segundo item

Expressao inline: $2x + 3 = 7$

Expressao em bloco:
$$
\frac{a}{b} = c
$$
```

Use Markdown para listas, italico (`*texto*`) e negrito (`**texto**`). Ambientes
de documento como `itemize`, `center` ou `equation` nao sao necessarios para esse
fluxo; para matematica, use delimitadores `$...$` ou `$$...$$` e comandos
suportados pelo KaTeX.

## Textos e imagens

Os enunciados sao guardados na tabela `questoes` do banco configurado para o
app. As imagens enviadas no painel sao gravadas como dados binarios na coluna
`questoes.imagem`; o nome original fica em `questoes.imagem_filename`.

Sem `DATABASE_URL`, o banco local e `data.db`, ao lado de `database.py`. Esse
arquivo e ignorado pelo Git e nao e enviado junto com o codigo. Com
`DATABASE_URL` configurada, o app local usa o banco PostgreSQL indicado pela URL;
nesse caso, os dados gravados localmente sao persistidos no Neon e nao no
`data.db`.

No Streamlit Community Cloud, arquivos criados durante a execucao ficam no
filesystem local do app e nao sao armazenamento persistente garantido entre
reinicializacoes ou novos deploys. Para dados que precisam sobreviver a esses
ciclos, use um banco externo gerenciado; mantenha as imagens nesse banco ou em
um armazenamento de objetos persistente. Consulte a documentacao oficial sobre
[organizacao de arquivos no Community Cloud](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/file-organization)
e [Markdown no Streamlit](https://docs.streamlit.io/develop/api-reference/text/st.markdown).

## Catalogo privado e seed seletivo

O arquivo `.local-seeds/questoes_reais.json` funciona como catalogo local de
juizes, regatas e questoes. Ele e ignorado pelo Git porque pode conter
enunciados e gabaritos. Cada questao informa seu nivel, tags categorizadas,
imagem opcional e, se necessario, um `rotulo` curto para facilitar a selecao.
O campo `imagem` associa explicitamente a questao a um caminho relativo, como
`static/Q1_matematica.png`.

JSON nao aceita comentarios. Use os campos `rotulo` e `tags` como metadados
estruturados, em vez de comentarios no arquivo; assim o seed pode exibi-los e
validar as categorias. O menu nao mostra enunciados nem gabaritos.

Para abrir o assistente interativo de selecao, execute na raiz do projeto:

```bash
python scripts/seed_questoes_reais.py --target test --interactive
```

O assistente permite selecionar juizes (`J`), criar uma regata (`R`) e/ou
inserir questoes (`Q`), inclusive combinacoes como `JRQ`. Ao selecionar
questoes, informe a quantidade e os codigos exibidos no catalogo, na ordem
desejada. Uma regata criada pelo assistente fica inativa; ative-a depois pelo
painel administrativo quando estiver pronta para exibicao. Sem `--apply`, o
comando mostra uma previa e nao grava dados. Acrescente `--apply` para gravar
no alvo escolhido; o script pede uma confirmacao explicita. A opcao `test` usa
`DATABASE_URL` do `.env`; producao exige uma opcao e confirmacao separadas.
