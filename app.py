from flask import Flask, request, jsonify, render_template, redirect, url_for, session, flash
import psycopg2
from flask_bcrypt import Bcrypt
from functools import wraps

# ==================================================
# 1. CONFIGURAÇÕES INICIAIS E SEGURANÇA
# ==================================================
app = Flask(__name__)
app.secret_key = 'chave_secreta_para_desenvolvimento'  # Necessário para gerenciar session e mensagens flash
bcrypt = Bcrypt(app)

DATABASE_URL = "postgresql://postgres:admin123@localhost:5432/gestao_escolar"


# ==================================================
# DECORATOR DE CONTROLE DE ACESSO (BLOQUEIO)
# ==================================================
def login_required(perfil_permitido=None):
    """
    Decorator para proteger rotas.
    - Se perfil_permitido for None: exige apenas que o usuário esteja logado.
    - Se perfil_permitido for especificado (ex: 'PROFESSOR'): valida se o perfil bate.
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # 1. Verifica se o usuário está logado
            if 'user_id' not in session:
                flash('Você precisa estar logado para acessar esta página.', 'warning')
                return redirect(url_for('login'))

            # 2. Verifica permissão de perfil (se houver restrição)
            if perfil_permitido and session.get('perfil') != perfil_permitido:
                flash('Acesso negado: Você não tem permissão para acessar esta área.', 'danger')
                return redirect(url_for('home'))

            return f(*args, **kwargs)
        return decorated_function
    return decorator


# Disponibiliza os dados de sessão em todos os templates HTML automaticamente
@app.context_processor
def inject_user():
    return dict(usuario_logado=session)


# ==================================================
# 2. ROTA PRINCIPAL (PÚBLICA)
# ==================================================

@app.route('/')
def home():
    return render_template('base.html')


# ==================================================
# 3. SEÇÃO DE AUTENTICAÇÃO (LOGIN E LOGOUT)
# ==================================================

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        senha = request.form.get('senha')

        conexao = psycopg2.connect(DATABASE_URL)
        cursor = conexao.cursor()

        try:
            # 1. Procura na tabela Aluno
            cursor.execute("SELECT id_aluno, nome, email, senha FROM Aluno WHERE email = %s", (email,))
            usuario = cursor.fetchone()
            perfil = 'ALUNO'

            # 2. Se não encontrar em Aluno, procura em Professor
            if not usuario:
                cursor.execute("SELECT id_professor, nome, email, senha FROM Professor WHERE email = %s", (email,))
                usuario = cursor.fetchone()
                perfil = 'PROFESSOR'

            # 3. Valida se o usuário existe e se a senha criptografada bate
            if usuario and bcrypt.check_password_hash(usuario[3], senha):
                session['user_id'] = usuario[0]
                session['nome'] = usuario[1]
                session['email'] = usuario[2]
                session['perfil'] = perfil

                flash(f'Bem-vindo(a), {usuario[1]}!', 'success')

                # Redireciona conforme o perfil do usuário
                if perfil == 'PROFESSOR':
                    return redirect(url_for('home_professor'))
                return redirect(url_for('home'))
            else:
                flash('E-mail ou senha incorretos. Tente novamente.', 'danger')
                return redirect(url_for('login'))

        finally:
            cursor.close()
            conexao.close()

    # Requisição GET renderiza a página de login
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('Você saiu do sistema com sucesso.', 'info')
    return redirect(url_for('login'))


# ==================================================
# 4. SEÇÃO DE HOME PROFESSORES (PROTEGIDA)
# ==================================================

@app.route('/home-professor')
@login_required('PROFESSOR')  # Apenas PROFESSOR pode acessar
def home_professor():
    professor = {
        'nome': session.get('nome'),
        'materia': 'Matemática'
    }
    return render_template('home_professor.html', professor=professor)


# ==================================================
# 5. SEÇÃO DE CADASTRO DE ALUNOS (PÚBLICA OU AUTO-CADASTRO)
# ==================================================

# Rota Visual
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
# 6. SEÇÃO DE CADASTRO DE PROFESSORES (PROTEGIDA - APENAS PROFESSORES CADASTRAREM OUTROS)
# ==================================================

# Rota Visual (Somente Professor)
@app.route('/cadastro-professor')
@login_required('PROFESSOR')
def pagina_cadastro_professor():
    return render_template('cadastro_professor.html')

# Rota de API (Somente Professor)
@app.route('/api/professores', methods=['POST'])
@login_required('PROFESSOR')
def cadastrar_professor():
    dados = request.json
    
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
# 9. SEÇÃO DE AGENDAMENTO DE AULA (PASSO 11)
# ==================================================

@app.route('/aulas/nova', methods=['GET', 'POST'])
@login_required('PROFESSOR')
def agendar_aula():
    conexao = psycopg2.connect(DATABASE_URL)
    cursor = conexao.cursor()

    if request.method == 'POST':
        id_tema = request.form.get('id_tema')
        data_aula = request.form.get('data_aula')
        horario_inicio = request.form.get('horario_inicio')
        link_aula = request.form.get('link_aula')
        
        # Pega o id do professor logado através da sessão atual
        id_professor = session.get('user_id')

        try:
            cursor.execute(
                """
                INSERT INTO Aula (id_professor, id_tema, data_aula, horario_inicio, link_aula) 
                VALUES (%s, %s, %s, %s, %s)
                """,
                (id_professor, id_tema, data_aula, horario_inicio, link_aula)
            )
            conexao.commit()
            flash('Aula agendada com sucesso!', 'success')
            return redirect(url_for('agendar_aula'))
        except Exception as e:
            conexao.rollback()
            flash(f'Erro ao agendar aula: {e}', 'danger')
        finally:
            cursor.close()
            conexao.close()

    # Método GET: Busca os temas cadastrados para popular o <select> no formulário
    try:
        cursor.execute("SELECT id_tema, titulo FROM Tema ORDER BY titulo ASC")
        temas = cursor.fetchall()
    except Exception:
        temas = []
    finally:
        cursor.close()
        conexao.close()

    return render_template('agendar_aula.html', temas=temas)

# ==================================================
# 7. INICIALIZAÇÃO DO SERVIDOR
# ==================================================
if __name__ == '__main__':
    app.run(debug=True)