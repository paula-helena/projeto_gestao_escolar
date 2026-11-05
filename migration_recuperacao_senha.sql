CREATE TABLE IF NOT EXISTS public.redefinicao_senha (
    id_redefinicao SERIAL PRIMARY KEY,
    perfil VARCHAR(10) NOT NULL
        CHECK (perfil IN ('ALUNO', 'PROFESSOR')),
    id_usuario INTEGER NOT NULL,
    token_hash CHAR(64) NOT NULL UNIQUE,
    criada_em TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expira_em TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS redefinicao_senha_usuario_idx
    ON public.redefinicao_senha (perfil, id_usuario);

CREATE INDEX IF NOT EXISTS redefinicao_senha_expira_em_idx
    ON public.redefinicao_senha (expira_em);
