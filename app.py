from flask import Flask, render_template
import psycopg2

# 1. Inicializa o servidor web (O Maestro)
app = Flask(__name__)

# 2. String de Conexão: O mapa até o cofre
DATABASE_URL = "postgresql://postgres:admin123@localhost:5432/gestao_escolar"

# 3. Define a Rota (A porta de entrada)
@app.route('/')
def listar_alunos():
    # A. Abre a porta do banco de dados
    conexao = psycopg2.connect(DATABASE_URL)
    cursor = conexao.cursor()
    
    # B. Envia o pedido (Query SQL)
    cursor.execute("SELECT id, nome, email, cidade FROM alunos;")
    lista_de_alunos = cursor.fetchall() 
    
    # C. Fecha as portas (Segurança e Limpeza)
    cursor.close()
    conexao.close()
    
    # D. Devolve a resposta visual para o usuário
    return render_template('alunos.html', alunos=lista_de_alunos)

# 4. Mantém o servidor ligado e ouvindo
if __name__ == '__main__':
    app.run(debug=True)