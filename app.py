from flask import Flask, request, jsonify, render_template
import psycopg2
from flask_bcrypt import Bcrypt

# 1. Inicializa o servidor web (O Maestro) e a Segurança (O Segurança da Porta)
app = Flask(__name__)
bcrypt = Bcrypt(app)

# 2. String de Conexão: O mapa até o cofre
DATABASE_URL = "postgresql://postgres:admin123@localhost:5432/gestao_escolar"

# 3. Rota Visual (A Vitrine)
@app.route('/cadastro')
def pagina_cadastro():
    return render_template('cadastro_aluno.html')

# 4. Rota de API (A Porta dos Fundos - Recebe os dados do formulário)
@app.route('/api/alunos', methods=['POST'])
def cadastrar_aluno():
    dados = request.json  # Recebe o "pacote" JSON enviado pelo navegador
    
    # A. Embaralha a senha antes de salvar (Segurança)
    senha_hash = bcrypt.generate_password_hash(dados['senha']).decode('utf-8')
    
    conexao = psycopg2.connect(DATABASE_URL)
    cursor = conexao.cursor()
    
    try:
        # B. Envia o pedido de Inserção (SQL)
        cursor.execute("""
            INSERT INTO Aluno (nome, email, senha, cep, logradouro, bairro, cidade, uf, numero, complemento) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id_aluno, nome
        """, (
            dados['nome'], dados['email'], senha_hash, dados['cep'], 
            dados['logradouro'], dados['bairro'], dados['cidade'], 
            dados['uf'], dados['numero'], dados.get('complemento')
        ))
        
        novo_aluno = cursor.fetchone()
        conexao.commit() # Carimba a transação: "Pode salvar de vez!"
        
        # C. Devolve uma resposta de sucesso (Status 201: Criado)
        return jsonify({"mensagem": "Sucesso", "id": novo_aluno[0], "nome": novo_aluno[1]}), 201
        
    except psycopg2.IntegrityError:
        conexao.rollback() # Cancela a operação se der erro (ex: e-mail já existe)
        return jsonify({"erro": "E-mail já cadastrado no sistema."}), 400
    finally:
        cursor.close()
        conexao.close()

if __name__ == '__main__':
    app.run(debug=True)
