# projeto_gestao_escolar
Projeto Gestão Escolar - UNIVESP

## Atualização do banco de dados

Antes de publicar a versão `dia01114`, aplique uma vez a migração no PostgreSQL já existente:

```powershell
psql $env:DATABASE_URL -v ON_ERROR_STOP=1 -f migration_dia01114.sql
```

Também é possível executar o conteúdo de `migration_dia01114.sql` pelo editor SQL do provedor do banco. Não publique nem compartilhe o valor de `DATABASE_URL`.

## Recuperação de senha

Antes de publicar a funcionalidade, aplique uma vez `migration_recuperacao_senha.sql` no mesmo banco Neon usado pelo Render:

```powershell
psql $env:DATABASE_URL -v ON_ERROR_STOP=1 -f migration_recuperacao_senha.sql
```

Configure no ambiente do Render as variáveis SMTP do provedor de e-mail:

- `SMTP_SERVER`: servidor SMTP.
- `SMTP_PORT`: porta SMTP (padrão `587`).
- `SMTP_USERNAME` e `SMTP_PASSWORD`: credenciais SMTP; configure ambas ou deixe ambas vazias.
- `SMTP_USE_TLS`: `true` para STARTTLS (padrão); use `false` se o provedor não oferecer STARTTLS.
- `SMTP_USE_SSL`: `true` para TLS implícito, normalmente na porta `465`; não use junto com `SMTP_USE_TLS`.
- `SMTP_FROM_EMAIL`: endereço remetente autorizado pelo provedor.
- `PUBLIC_BASE_URL`: URL pública da aplicação, por exemplo `https://projeto-gestao-escolar.onrender.com`.

Não coloque credenciais SMTP no código ou no repositório. Até o SMTP ser configurado, a tela de recuperação informa que o serviço está temporariamente indisponível. Links são válidos por uma hora e podem ser usados uma única vez. Novos cadastros de aluno e professor usam a senha inicial `mrdave`; cada pessoa pode definir uma senha pessoal pela recuperação por e-mail.

## Agendamento de aulas

As aulas recorrentes são semanais: todos os dias selecionados usam o mesmo horário. Mês, trimestre, semestre e ano correspondem a 1, 3, 6 e 12 meses a partir da primeira data. A opção “Para sempre” cria aulas com até 90 dias de antecedência e amplia esse horizonte quando a agenda é consultada. Aulas agendadas vencidas passam a concluídas quando a agenda ou os detalhes da aula são consultados.
