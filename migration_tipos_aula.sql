BEGIN;

ALTER TABLE public.aula
    ADD COLUMN IF NOT EXISTS tipo_aula VARCHAR(20);

UPDATE public.aula
SET tipo_aula = CASE
    WHEN id_aula_origem IS NOT NULL THEN 'REPOSICAO'
    WHEN id_recorrencia IS NOT NULL THEN 'RECORRENTE'
    ELSE 'EXPERIMENTAL'
END
WHERE tipo_aula IS NULL;

ALTER TABLE public.aula
    ALTER COLUMN tipo_aula SET DEFAULT 'EXPERIMENTAL',
    ALTER COLUMN tipo_aula SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'aula_tipo_aula_check'
          AND conrelid = 'public.aula'::regclass
    ) THEN
        ALTER TABLE public.aula
            ADD CONSTRAINT aula_tipo_aula_check
            CHECK (tipo_aula IN ('REPOSICAO', 'RECORRENTE', 'EXPERIMENTAL'));
    END IF;
END
$$;

COMMIT;
