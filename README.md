# projeto_gestao_escolar
Projeto Gestão Escolar - UNIVESP

## Atualização do banco de dados

Antes de publicar a versão `dia01114`, aplique uma vez a migração no PostgreSQL já existente:

```powershell
psql $env:DATABASE_URL -v ON_ERROR_STOP=1 -f migration_dia01114.sql
```

Também é possível executar o conteúdo de `migration_dia01114.sql` pelo editor SQL do provedor do banco. Não publique nem compartilhe o valor de `DATABASE_URL`.

## Agendamento de aulas

As aulas recorrentes são semanais: todos os dias selecionados usam o mesmo horário. Mês, trimestre, semestre e ano correspondem a 1, 3, 6 e 12 meses a partir da primeira data. A opção “Para sempre” cria aulas com até 90 dias de antecedência e amplia esse horizonte quando a agenda é consultada. Aulas agendadas vencidas passam a concluídas quando a agenda ou os detalhes da aula são consultados.
