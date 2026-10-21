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

CREATE TABLE Tema (
    id_tema SERIAL PRIMARY KEY,
    titulo VARCHAR(150) NOT NULL,
    descricao TEXT
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
    tema VARCHAR(150) NOT NULL,  -- Alterado para receber o texto direto do form
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
    PRIMARY KEY (id_aluno, id_aula), 
    FOREIGN KEY (id_aluno) REFERENCES Aluno(id_aluno) ON DELETE CASCADE,
    FOREIGN KEY (id_aula) REFERENCES Aula(id_aula) ON DELETE CASCADE
);