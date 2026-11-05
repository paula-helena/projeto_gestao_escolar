-- 1. Criação das tabelas independentes

CREATE TABLE Aluno (
    id_aluno SERIAL PRIMARY KEY,
    nome VARCHAR(100) NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    senha VARCHAR(255) NOT NULL,
    cep VARCHAR(9) NOT NULL,
    logradouro VARCHAR(150) NOT NULL,
    bairro VARCHAR(100) NOT NULL,
    cidade VARCHAR(100) NOT NULL,
    uf CHAR(2) NOT NULL,
    numero VARCHAR(20),
    complemento VARCHAR(100)
);

CREATE TABLE Professor (
    id_professor SERIAL PRIMARY KEY,
    nome VARCHAR(100) NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    senha VARCHAR(255) NOT NULL,
    disciplina VARCHAR(100) NOT NULL,
    cep VARCHAR(9) NOT NULL,
    logradouro VARCHAR(150) NOT NULL,
    bairro VARCHAR(100) NOT NULL,
    cidade VARCHAR(100) NOT NULL,
    uf CHAR(2) NOT NULL,
    numero VARCHAR(20),
    complemento VARCHAR(100)
);

CREATE TABLE Evento_Institucional (
    id_evento SERIAL PRIMARY KEY,
    titulo VARCHAR(150) NOT NULL,
    descricao TEXT,
    data_evento DATE NOT NULL,
    tipo VARCHAR(50) DEFAULT 'AVISO_SECRETARIA'
);


-- 2. Criação das tabelas dependentes

CREATE TABLE Aula (
    id_aula SERIAL PRIMARY KEY,
    id_professor INT NOT NULL,
    tema VARCHAR(150),
    tipo_aula VARCHAR(20) NOT NULL DEFAULT 'EXPERIMENTAL'
        CHECK (tipo_aula IN ('REPOSICAO', 'RECORRENTE', 'EXPERIMENTAL')),
    data_hora TIMESTAMP NOT NULL, -- Unificado para bater com o datetime-local do HTML
    status VARCHAR(50) DEFAULT 'AGENDADA',
    link_aula VARCHAR(255),
    FOREIGN KEY (id_professor) REFERENCES Professor(id_professor)
);

CREATE TABLE Material_Didatico (  -- Renomeado para bater com o backend
    id_material SERIAL PRIMARY KEY,
    id_professor INT NOT NULL,    -- Vinculado ao professor que cadastrou
    titulo VARCHAR(150) NOT NULL,
    descricao TEXT,
    link_arquivo VARCHAR(255) NOT NULL,
    FOREIGN KEY (id_professor) REFERENCES Professor(id_professor) ON DELETE CASCADE
);

CREATE TABLE Aula_Aluno (         -- Renomeado de Controle_Academico para bater com a query
    id_aluno INT NOT NULL,
    id_aula INT NOT NULL,
    presenca BOOLEAN DEFAULT FALSE,
    nota_oficial DECIMAL(5,2),      
    nota_autoavaliacao DECIMAL(5,2),
    revisar BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (id_aluno, id_aula), 
    FOREIGN KEY (id_aluno) REFERENCES Aluno(id_aluno) ON DELETE CASCADE,
    FOREIGN KEY (id_aula) REFERENCES Aula(id_aula) ON DELETE CASCADE
);

ALTER TABLE public.aula
    ALTER COLUMN tema DROP NOT NULL,
    ADD COLUMN IF NOT EXISTS id_recorrencia INTEGER,
    ADD COLUMN IF NOT EXISTS id_aula_origem INTEGER;

CREATE TABLE Aula_Recorrencia (
    id_recorrencia SERIAL PRIMARY KEY,
    id_professor INTEGER NOT NULL REFERENCES Professor(id_professor),
    id_aluno INTEGER NOT NULL REFERENCES Aluno(id_aluno),
    tema VARCHAR(150),
    inicio DATE NOT NULL,
    hora TIME NOT NULL,
    dias_semana INTEGER[] NOT NULL,
    fim_em DATE,
    gerada_ate DATE NOT NULL,
    ativa BOOLEAN NOT NULL DEFAULT TRUE,
    criada_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE public.aula
    ADD CONSTRAINT aula_id_recorrencia_fkey
        FOREIGN KEY (id_recorrencia)
        REFERENCES public.aula_recorrencia(id_recorrencia)
        ON DELETE SET NULL,
    ADD CONSTRAINT aula_id_aula_origem_fkey
        FOREIGN KEY (id_aula_origem)
        REFERENCES public.aula(id_aula)
        ON DELETE SET NULL;

CREATE UNIQUE INDEX aula_recorrencia_data_hora_unica
    ON public.aula (id_recorrencia, data_hora)
    WHERE id_recorrencia IS NOT NULL;

CREATE TABLE Aula_Recorrencia_Material (
    id_recorrencia INTEGER NOT NULL
        REFERENCES Aula_Recorrencia(id_recorrencia) ON DELETE CASCADE,
    id_material INTEGER NOT NULL
        REFERENCES Material_Didatico(id_material) ON DELETE CASCADE,
    PRIMARY KEY (id_recorrencia, id_material)
);

CREATE TABLE Aula_Material (
    id_aula INTEGER NOT NULL REFERENCES Aula(id_aula) ON DELETE CASCADE,
    id_material INTEGER NOT NULL
        REFERENCES Material_Didatico(id_material) ON DELETE CASCADE,
    PRIMARY KEY (id_aula, id_material)
);

CREATE TABLE Aula_Anotacao (
    id_anotacao SERIAL PRIMARY KEY,
    id_aula INTEGER NOT NULL REFERENCES Aula(id_aula) ON DELETE CASCADE,
    perfil_usuario VARCHAR(10) NOT NULL
        CHECK (perfil_usuario IN ('ALUNO', 'PROFESSOR')),
    id_usuario INTEGER NOT NULL,
    anotacao TEXT NOT NULL DEFAULT '',
    criada_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    atualizada_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (id_aula, perfil_usuario, id_usuario)
);