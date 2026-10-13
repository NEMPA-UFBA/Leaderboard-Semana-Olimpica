# Copiar o banco local para uma branch Neon de teste

O banco local `data.db` contem dados de teste. A importacao copia usuarios (incluindo hashes de senha), equipes, regatas, questoes, imagens, tags associadas, tentativas e, quando existir, os registros de auditoria. Ela nao copia senhas em texto claro nem reservas temporarias de questoes. Bancos SQLite antigos sem auditoria ou tabelas de tags continuam aceitos; as tags padrao e as de dificuldade serao criadas/preenchidas quando o app inicializar.

## Criar a branch de teste

1. Entre no [Neon Console](https://console.neon.tech/) e abra o projeto.
2. Abra **Branches** e escolha **Create branch**.
3. Nomeie a branch, por exemplo `leaderboard-teste`, e escolha como parent a branch principal vazia.
4. Crie a branch. Branches Neon partem de um snapshot do parent; neste momento, o parent precisa estar vazio para que o importador aceite o destino.
5. Selecione a nova branch e copie a connection string PostgreSQL dela.

Confira que a connection string foi copiada da branch de teste, nao da branch principal. Branches sao isoladas: alteracoes na branch de teste nao aparecem automaticamente na principal.

## Apontar o app para a branch de teste

1. Feche o Streamlit local, se estiver rodando.
2. No `.env` local, coloque a connection string copiada na variavel `DATABASE_URL`, mantendo-a entre aspas:

   ```dotenv
   DATABASE_URL="postgresql://..."
   ```

3. Nao compartilhe nem versione o `.env`. O driver PostgreSQL e normalizado pelo app.

## Conferir e executar a importacao

No terminal integrado do VS Code, com a pasta do projeto como diretório atual, primeiro rode a previa:

```bash
./venv_leaderboard/bin/python -m scripts.migrate_sqlite_to_neon
```

A previa le `data.db` em modo somente leitura e exige que o destino Neon esteja vazio. Ela mostra somente as contagens das tabelas, nunca os dados de usuarios ou credenciais.

Confira que o destino e a branch de teste e que as contagens correspondem ao banco local. Para executar:

```bash
./venv_leaderboard/bin/python -m scripts.migrate_sqlite_to_neon --apply --confirm-test-branch
```

O importador recusa destinos que ja tenham tabelas, copia em uma transacao, preserva os IDs e imagens e verifica as contagens antes de concluir. Se a validacao falhar, a transacao e revertida.

Depois da importacao, inicie o app:

```bash
./venv_leaderboard/bin/python -m streamlit run app.py
```

O app continuara apontando para a branch de teste enquanto essa connection string permanecer em `DATABASE_URL`. As contas e tentativas importadas sao dados de teste; nao crie a branch de producao a partir desta branch se nao quiser levar esses dados junto.
