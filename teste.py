import os
import psycopg2
from dotenv import load_dotenv

# Carrega o .env
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

print("🔌 Tentando conectar ao banco...")
try:
    conexao = psycopg2.connect(DATABASE_URL)
    cursor = conexao.cursor()
    print("✅ Conectado com sucesso!\n")

    # 1. Lista Professores
    print("=== PROFESSORES CADASTRADOS ===")
    try:
        cursor.execute("SELECT id_professor, nome, email, senha FROM public.professor")
        professores = cursor.fetchall()
        if professores:
            for p in professores:
                # Mostra o ID, Nome, Email e se a senha parece ser Bcrypt ($2b$) ou texto comum
                status_senha = "Hash (Bcrypt)" if p[3].startswith('$2b$') else "Texto Puro"
                print(f"ID: {p[0]} | Nome: {p[1]} | Email: {p[2]} | Senha: [{status_senha}]")
        else:
            print("Nenhum professor cadastrado.")
    except Exception as e:
        print(f"Erro ao ler professores: {e}")

    print("\n=== ALUNOS CADASTRADOS ===")
    # 2. Lista Alunos
    try:
        cursor.execute("SELECT id_aluno, nome, email, senha FROM public.aluno")
        alunos = cursor.fetchall()
        if alunos:
            for a in alunos:
                status_senha = "Hash (Bcrypt)" if a[3].startswith('$2b$') else "Texto Puro"
                print(f"ID: {a[0]} | Nome: {a[1]} | Email: {a[2]} | Senha: [{status_senha}]")
        else:
            print("Nenhum aluno cadastrado.")
    except Exception as e:
        print(f"Erro ao ler alunos: {e}")

    cursor.close()
    conexao.close()

except Exception as e:
    print(f"❌ Erro de conexão com o banco: {e}")