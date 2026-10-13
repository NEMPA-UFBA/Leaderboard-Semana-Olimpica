# Batalha Olímpica — Leaderboard

Aplicação web de apoio à Batalha Olímpica, uma competição matemática em que
juízes registram as tentativas das equipes e o público acompanha a pontuação.

## Funcionalidades

- **Leaderboard público:** placar atualizado automaticamente com a pontuação
  das equipes.
- **Questões:** exibição das questões da regata ativa.
- **Painel do juiz:** registro, revisão e exclusão de tentativas, com histórico
  das ações.
- **Reserva de questão:** evita que dois juízes lancem ou corrijam
  simultaneamente a mesma questão.
- **Painel administrativo:** gerenciamento de juízes, equipes, regatas,
  questões e tags.

### Pontuação

- Acerto na primeira tentativa: **100 pontos**.
- Acerto na segunda tentativa: **80 pontos**.
- Acerto na terceira tentativa: **50 pontos**.
- Resposta errada: **0 pontos**. Após três erros, a equipe não pode tentar
  novamente aquela questão.
- Após um acerto, não são aceitas novas tentativas para aquela equipe e questão.

## Tecnologias

- Python e [Streamlit](https://streamlit.io/) para a aplicação web.
- SQLAlchemy para acesso aos dados.
- SQLite como banco local padrão; PostgreSQL/Neon para ambientes implantados.
- Pytest para os testes automatizados.

## Executar localmente

1. Instale uma versão de Python compatível com as dependências em
   [`requirements.txt`](./requirements.txt).
2. Crie e ative um ambiente virtual:

   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

   No Windows, ative-o com:

   ```powershell
   venv\Scripts\Activate.ps1
   ```

3. Instale as dependências:

   ```bash
   python -m pip install -r requirements.txt
   ```

4. Crie um arquivo `.env` local, não versionado, e defina uma senha inicial
   forte para a conta administrativa:

   ```dotenv
   ADMIN_INITIAL_PASSWORD=defina-uma-senha-temporaria-forte
   ```

   Sem `DATABASE_URL`, a aplicação usa o SQLite local (`data.db`). Para usar
   PostgreSQL localmente, defina também `DATABASE_URL` no `.env`.

5. Inicie a aplicação:

   ```bash
   streamlit run app.py
   ```

Na primeira inicialização de um banco sem a conta `admin`, a aplicação cria
essa conta usando `ADMIN_INITIAL_PASSWORD` e exige a troca da senha no primeiro
acesso. Essa variável não redefine a senha de uma conta `admin` já existente.

## Testes

Com o ambiente virtual ativo, execute:

```bash
python -m pytest -q
```

## Banco de dados e implantação

- A aplicação local pode usar o SQLite padrão ou um PostgreSQL definido em
  `DATABASE_URL`.
- No Streamlit Community Cloud, configure `DATABASE_URL` nos Secrets do app.
- Mantenha configurações e credenciais distintas para produção e treinamento.
  Nunca coloque URLs de conexão, senhas ou outros Secrets no código ou neste
  repositório.
- `ADMIN_INITIAL_PASSWORD` só é necessário quando o banco ainda não tem a conta
  administrativa inicial.

## Dados das questões

Os arquivos locais usados para cadastrar as questões reais, incluindo imagens e
gabaritos, não fazem parte do repositório. O script
[`scripts/seed_questoes_reais.py`](./scripts/seed_questoes_reais.py) espera os
dados privados em `.local-seeds/questoes_reais.json` e as imagens locais em
`static/`. Esses caminhos são ignorados pelo Git. O gabarito não é armazenado
no banco da aplicação; mantenha-o em local apropriado e não o publique.

## Documentação

- [Roteiro de treinamento dos juízes](./docs/roteiro-teste-juizes.md)

## Contribuições

Use branches de trabalho e envie alterações por pull request para `master`.
Execute os testes automatizados antes de solicitar revisão. Não faça push
direto para `master`.
