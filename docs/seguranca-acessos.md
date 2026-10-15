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

## Banco de dados por ambiente

Em cada aplicativo do Streamlit Community Cloud, configure `APP_ENV` como
`staging` para treinamento ou `production` para o evento oficial, e `DATABASE_URL`
com a URL PostgreSQL daquele ambiente. Os valores de teste e producao devem
apontar para bancos/branches Neon distintos. O app nao usa SQLite como fallback
em ambientes hospedados e falha explicitamente se a URL estiver ausente ou
apontar para SQLite.

Para desenvolvimento local sem PostgreSQL, configure `APP_ENV=development`; o
app pode entao usar `data.db`. Nunca configure esse ambiente local no app de
producao.

## Sessao de login

Depois do login, o navegador recebe um token aleatorio com validade de ate 12
horas; o banco armazena somente o hash desse token. Atualizar a pagina deve
restaurar a sessao enquanto o cookie e o registro no banco ainda forem validos.
O logout revoga o registro e remove o cookie.

O cookie usa `SameSite=Lax` e `Secure` em conexoes HTTPS. Ele nao e `HttpOnly`,
pois a implementacao atual usa um componente de cookies do Streamlit. Nao
compartilhe o cookie e encerre a sessao ao usar um dispositivo compartilhado.

## Contas de juizes

Crie as contas de juizes pela aba **Juizes** do painel de administrador. A senha
inicial deve ter pelo menos 12 caracteres; o juiz precisa troca-la no primeiro
acesso. O administrador pode redefini-la pelo mesmo painel, e a senha nova
tambem sera temporaria. O codigo armazena hashes bcrypt, nunca as senhas em
texto aberto.
