from flask import Flask, request, jsonify, render_template
import psycopg2
from flask_bcrypt import Bcrypt

# ==================================================
# 1. CONFIGURAÇÕES INICIAIS E SEGURANÇA
# ==================================================
app = Flask(__name__)
bcrypt = Bcrypt(app)

DATABASE_URL = "postgresql://postgres:admin123@localhost:5432/gestao_escolar"


# ==================================================
# 2. Rota para o endereço principal (http://127.0.0.1:5000/)
# ==================================================

@app.route('/')
def home():
    return "<h1>Sistema de Gestão Escolar</h1><p>Acesse <a href='/cadastro'>/cadastro</a> para Alunos ou <a href='/cadastro-professor'>/cadastro-professor</a> para Professores.</p>"


# ==================================================
# 3. SEÇÃO DE ALUNOS
# ==================================================

# Rota Visual (Vitrine)
@app.route('/cadastro')
def pagina_cadastro():
    return render_template('cadastro_aluno.html')

# Rota de API (Cadastro do Aluno)
@app.route('/api/alunos', methods=['POST'])
def cadastrar_aluno():
    dados = request.json
    
    # Embaralha a senha antes de salvar
    senha_hash = bcrypt.generate_password_hash(dados['senha']).decode('utf-8')
    
    conexao = psycopg2.connect(DATABASE_URL)
    cursor = conexao.cursor()
    
    try:
        cursor.execute("""
            INSERT INTO Aluno (nome, email, senha, cep, logradouro, bairro, cidade, uf, numero, complemento) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id_aluno, nome
        """, (
            dados['nome'], dados['email'], senha_hash, dados['cep'], 
            dados['logradouro'], dados['bairro'], dados['cidade'], 
            dados['uf'], dados['numero'], dados.get('complemento')
        ))
        
        novo_aluno = cursor.fetchone()
        conexao.commit()
        
        return jsonify({"mensagem": "Sucesso", "id": novo_aluno[0], "nome": novo_aluno[1]}), 201
        
    except psycopg2.IntegrityError:
        conexao.rollback()
        return jsonify({"erro": "E-mail já cadastrado no sistema."}), 400
    finally:
        cursor.close()
        conexao.close()


# ==================================================
# 4. SEÇÃO DE PROFESSORES
# ==================================================

# Rota Visual (Vitrine)
@app.route('/cadastro-professor')
def pagina_cadastro_professor():
    return render_template('cadastro_professor.html')

# Rota de API (Cadastro do Professor)
@app.route('/api/professores', methods=['POST'])
def cadastrar_professor():
    dados = request.json
    
    # Embaralha a senha antes de salvar
    senha_hash = bcrypt.generate_password_hash(dados['senha']).decode('utf-8')
    
    conexao = psycopg2.connect(DATABASE_URL)
    cursor = conexao.cursor()
    
    try:
        cursor.execute("""
            INSERT INTO Professor (nome, email, senha, disciplina, cep, logradouro, bairro, cidade, uf, numero, complemento) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id_professor, nome
        """, (
            dados['nome'], dados['email'], senha_hash, dados['disciplina'],
            dados['cep'], dados['logradouro'], dados['bairro'], dados['cidade'], 
            dados['uf'], dados['numero'], dados.get('complemento')
        ))
        
        novo_prof = cursor.fetchone()
        conexao.commit()
        
        return jsonify({"mensagem": "Sucesso", "id": novo_prof[0], "nome": novo_prof[1]}), 201
        
    except psycopg2.IntegrityError:
        conexao.rollback()
        return jsonify({"erro": "E-mail já cadastrado no sistema."}), 400
    finally:
        cursor.close()
        conexao.close()


# ==================================================
# 5. INICIALIZAÇÃO DO SERVIDO
# ==================================================
if __name__ == '__main__':
    app.run(debug=True)