-- 1. Criação das tabelas independentes (Sem chaves estrangeiras)

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
    senha VARCHAR(255) NOT NULL
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


-- 2. Criação das tabelas dependentes (Com chaves estrangeiras)

CREATE TABLE Aula (
    id_aula SERIAL PRIMARY KEY,
    id_professor INT NOT NULL,
    id_tema INT,
    data_aula DATE NOT NULL,
    horario_inicio TIME NOT NULL,
    link_aula VARCHAR(255),
    FOREIGN KEY (id_professor) REFERENCES Professor(id_professor),
    FOREIGN KEY (id_tema) REFERENCES Tema(id_tema)
);

CREATE TABLE Material_Apoio (
    id_material SERIAL PRIMARY KEY,
    id_aula INT NOT NULL,
    tipo_material VARCHAR(50), 
    url_arquivo VARCHAR(255) NOT NULL,
    descricao VARCHAR(150),
    FOREIGN KEY (id_aula) REFERENCES Aula(id_aula) ON DELETE CASCADE
);

CREATE TABLE Controle_Academico (
    id_aluno INT NOT NULL,
    id_aula INT NOT NULL,
    presenca BOOLEAN DEFAULT FALSE,
    nota_oficial DECIMAL(5,2),      
    nota_autoavaliacao DECIMAL(5,2),
    PRIMARY KEY (id_aluno, id_aula), 
    FOREIGN KEY (id_aluno) REFERENCES Aluno(id_aluno) ON DELETE CASCADE,
    FOREIGN KEY (id_aula) REFERENCES Aula(id_aula) ON DELETE CASCADE
);