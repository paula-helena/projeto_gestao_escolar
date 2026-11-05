BEGIN;

ALTER TABLE public.aula
    ADD COLUMN IF NOT EXISTS link_aula VARCHAR(255);

ALTER TABLE public.aula_recorrencia
    ADD COLUMN IF NOT EXISTS link_aula VARCHAR(255);

COMMIT;
