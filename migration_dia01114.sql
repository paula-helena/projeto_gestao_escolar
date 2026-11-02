BEGIN;

ALTER TABLE public.aula
    ALTER COLUMN tema DROP NOT NULL,
    ADD COLUMN IF NOT EXISTS id_recorrencia INTEGER,
    ADD COLUMN IF NOT EXISTS id_aula_origem INTEGER;

ALTER TABLE public.aula_aluno
    ADD COLUMN IF NOT EXISTS revisar BOOLEAN NOT NULL DEFAULT FALSE;

UPDATE public.aula
SET status = 'CONCLUIDA'
WHERE status = 'REALIZADA';

CREATE TABLE IF NOT EXISTS public.aula_recorrencia (
    id_recorrencia SERIAL PRIMARY KEY,
    id_professor INTEGER NOT NULL REFERENCES public.professor(id_professor),
    id_aluno INTEGER NOT NULL REFERENCES public.aluno(id_aluno),
    tema VARCHAR(150),
    inicio DATE NOT NULL,
    hora TIME NOT NULL,
    dias_semana INTEGER[] NOT NULL,
    fim_em DATE,
    gerada_ate DATE NOT NULL,
    ativa BOOLEAN NOT NULL DEFAULT TRUE,
    criada_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'aula_id_recorrencia_fkey'
          AND conrelid = 'public.aula'::regclass
    ) THEN
        ALTER TABLE public.aula
            ADD CONSTRAINT aula_id_recorrencia_fkey
            FOREIGN KEY (id_recorrencia)
            REFERENCES public.aula_recorrencia(id_recorrencia)
            ON DELETE SET NULL;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'aula_id_aula_origem_fkey'
          AND conrelid = 'public.aula'::regclass
    ) THEN
        ALTER TABLE public.aula
            ADD CONSTRAINT aula_id_aula_origem_fkey
            FOREIGN KEY (id_aula_origem)
            REFERENCES public.aula(id_aula)
            ON DELETE SET NULL;
    END IF;
END
$$;

CREATE UNIQUE INDEX IF NOT EXISTS aula_recorrencia_data_hora_unica
    ON public.aula (id_recorrencia, data_hora)
    WHERE id_recorrencia IS NOT NULL;

CREATE TABLE IF NOT EXISTS public.aula_recorrencia_material (
    id_recorrencia INTEGER NOT NULL
        REFERENCES public.aula_recorrencia(id_recorrencia) ON DELETE CASCADE,
    id_material INTEGER NOT NULL
        REFERENCES public.material_didatico(id_material) ON DELETE CASCADE,
    PRIMARY KEY (id_recorrencia, id_material)
);

CREATE TABLE IF NOT EXISTS public.aula_material (
    id_aula INTEGER NOT NULL
        REFERENCES public.aula(id_aula) ON DELETE CASCADE,
    id_material INTEGER NOT NULL
        REFERENCES public.material_didatico(id_material) ON DELETE CASCADE,
    PRIMARY KEY (id_aula, id_material)
);

CREATE TABLE IF NOT EXISTS public.aula_anotacao (
    id_anotacao SERIAL PRIMARY KEY,
    id_aula INTEGER NOT NULL
        REFERENCES public.aula(id_aula) ON DELETE CASCADE,
    perfil_usuario VARCHAR(10) NOT NULL
        CHECK (perfil_usuario IN ('ALUNO', 'PROFESSOR')),
    id_usuario INTEGER NOT NULL,
    anotacao TEXT NOT NULL DEFAULT '',
    criada_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    atualizada_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (id_aula, perfil_usuario, id_usuario)
);

COMMIT;
