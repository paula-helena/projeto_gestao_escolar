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

Os tipos de agendamento são reposição, recorrente e experimental. A experimental é uma aula única; a reposição deve partir de uma aula marcada como reagendada. As recorrentes são semanais: todos os dias selecionados usam o mesmo horário. Mês, trimestre, semestre e ano correspondem a 1, 3, 6 e 12 meses a partir da primeira data. A opção “Para sempre” cria aulas com até 90 dias de antecedência e amplia esse horizonte quando a agenda é consultada. Aulas agendadas vencidas passam a concluídas quando a agenda ou os detalhes da aula são consultados.

Antes de publicar a nova versão, aplique uma vez `migration_tipos_aula.sql` no PostgreSQL:

```powershell
psql $env:DATABASE_URL -v ON_ERROR_STOP=1 -f migration_tipos_aula.sql
```

O tema é texto livre e opcional, informado ao agendar ou editar uma aula. A aplicação não usa mais o cadastro prévio de temas. A tabela antiga e seus dados são mantidos no banco sem uso pela aplicação; a migração não os apaga.

## Arquivos de materiais

O professor pode anexar PDF, PPT ou PPTX de até 25 MB ao cadastrar um material. Os arquivos são privados no armazenamento e são servidos por links assinados que expiram em 10 minutos. Links externos HTTP/HTTPS continuam aceitos. Configure um bucket privado em armazenamento compatível com S3 e defina no Render:

- `S3_BUCKET`: nome do bucket.
- `S3_REGION`: região do bucket (padrão `us-east-1`).
- `S3_ACCESS_KEY_ID` e `S3_SECRET_ACCESS_KEY`: credenciais de acesso restrito ao bucket.
- `S3_ENDPOINT_URL`: endpoint do provedor S3-compatible; deixe vazio para AWS S3.

Não salve credenciais no código nem no repositório. Sem a configuração S3, links externos continuam funcionando, mas o envio de anexos fica indisponível.
