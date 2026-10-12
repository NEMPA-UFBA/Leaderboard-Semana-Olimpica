# Configuracao segura de acessos

## Senha inicial do administrador

O sistema nao cria mais um administrador com senha padrao. Quando o banco ainda
nao tem uma conta `admin`, configure `ADMIN_INITIAL_PASSWORD` antes de iniciar
o aplicativo. A senha deve ter pelo menos 12 caracteres e no maximo 72 bytes.

- No Streamlit Community Cloud, configure a chave `ADMIN_INITIAL_PASSWORD` na
  area **Settings > Secrets** do aplicativo.
- No desenvolvimento local, coloque a chave em `.streamlit/secrets.toml` ou
  defina a variavel de ambiente `ADMIN_INITIAL_PASSWORD`. O diretorio
  `.streamlit/` ja e ignorado pelo Git neste repositorio.

O valor e usado apenas para criar a conta inicial. No primeiro acesso, o
administrador precisa escolher uma nova senha. Depois disso, o banco armazena
somente o hash bcrypt. Se o banco for recriado, a chave de bootstrap sera
necessaria novamente.

Contas existentes que ainda usam a senha padrao antiga tambem sao obrigadas a
troca-la antes de acessar o painel. Nunca adicione o valor real da chave a este
repositorio, a arquivos de exemplo versionados, a logs ou a conversas.

## Contas de juizes

Crie as contas de juizes pela aba **Juizes** do painel de administrador. A senha
inicial deve ter pelo menos 12 caracteres; o juiz precisa troca-la no primeiro
acesso. O administrador pode redefini-la pelo mesmo painel, e a senha nova
tambem sera temporaria. O codigo armazena hashes bcrypt, nunca as senhas em
texto aberto.
