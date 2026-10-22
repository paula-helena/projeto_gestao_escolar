import os
from flask import Flask, request, jsonify, render_template, redirect, url_for, session, flash
import psycopg2
from flask_bcrypt import Bcrypt
from functools import wraps
from dotenv import load_dotenv

# Carrega as variáveis de ambiente do arquivo .env
load_dotenv()

# ==================================================
# 1. CONFIGURAÇÕES INICIAIS E SEGURANÇA
# ==================================================
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'chave_secreta_para_desenvolvimento')
bcrypt = Bcrypt(app)

DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://postgres:admin123@localhost:5432/gestao_escolar')

# ==================================================
# DECORATOR DE CONTROLE DE ACESSO (BLOQUEIO)
# ==================================================
def login_required(perfil_permitido=None):
    """
    Decorator para proteger rotas.
    - Se perfil_permitido for None: exige apenas que o usuário esteja logado.
    - Se perfil_permitido for especificado: valida se o perfil (ALUNO ou PROFESSOR) bate.
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                flash('Você precisa estar logado para acessar esta página.', 'warning')
                return redirect(url_for('login'))

            if perfil_permitido and session.get('perfil') != perfil_permitido:
                flash('Acesso negado: Você não tem permissão para acessar esta área.', 'danger')
                if session.get('perfil') == 'PROFESSOR':
                    return redirect(url_for('home_professor'))
                return redirect(url_for('home_aluno'))

            return f(*args, **kwargs)
        return decorated_function
    return decorator

# Disponibiliza os dados de sessão em todos os templates HTML
@app.context_processor
def inject_user():
    return dict(usuario_logado=session)


# ==================================================
# 2. ROTA PRINCIPAL (PÚBLICA)
# ==================================================
@app.route('/')
def home():
    # Se já estiver logado, redireciona para o respectivo painel
    if 'user_id' in session:
        if session.get('perfil') == 'PROFESSOR':
            return redirect(url_for('home_professor'))
        return redirect(url_for('home_aluno'))
    
    # ATUALIZAÇÃO AQUI: Aponta para o novo template
    return render_template('index.html')

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

            # 3. Valida se o usuário existe e se a senha confere
            if usuario and bcrypt.check_password_hash(usuario[3], senha):
                session['user_id'] = usuario[0]
                session['nome'] = usuario[1]
                session['email'] = usuario[2]
                session['perfil'] = perfil

                flash(f'Bem-vindo(a), {usuario[1]}!', 'success')

                if perfil == 'PROFESSOR':
                    return redirect(url_for('home_professor'))
                return redirect(url_for('home_aluno'))
            else:
                flash('E-mail ou senha incorretos. Tente novamente.', 'danger')
                return redirect(url_for('login'))

        finally:
            cursor.close()
            conexao.close()

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Você saiu do sistema com sucesso.', 'info')
    return redirect(url_for('login'))


# ==================================================
# 4. DASHBOARDS (PAINÉIS DE CONTROLE)
# ==================================================
@app.route('/home-professor')
@login_required('PROFESSOR')
def home_professor():
    return render_template('home_professor.html')

@app.route('/home-aluno')
@login_required('ALUNO')
def home_aluno():
    return render_template('home_aluno.html')


# ==================================================
# 5. GESTÃO DE AULAS (AGENDAMENTO)
# ==================================================
@app.route('/aulas', methods=['GET'])
@login_required()
def listar_aulas():
    """Rota para listar aulas (visão diferente para prof e aluno no template)"""
    conexao = psycopg2.connect(DATABASE_URL)
    cursor = conexao.cursor()
    
    try:
        if session.get('perfil') == 'PROFESSOR':
            cursor.execute("SELECT id_aula, data_hora, tema, status FROM Aula WHERE id_professor = %s ORDER BY data_hora", (session.get('user_id'),))
        else:
            cursor.execute("""
                SELECT a.id_aula, a.data_hora, a.tema, a.status 
                FROM Aula a
                JOIN Aula_Aluno aa ON a.id_aula = aa.id_aula
                WHERE aa.id_aluno = %s ORDER BY a.data_hora
            """, (session.get('user_id'),))
            
        aulas = cursor.fetchall()
        return render_template('aulas.html', aulas=aulas)
    finally:
        cursor.close()
        conexao.close()

@app.route('/aulas/nova', methods=['GET', 'POST'])
@login_required('PROFESSOR')
def nova_aula():
    """Rota para o professor cadastrar uma nova aula"""
    if request.method == 'POST':
        data_hora = request.form.get('data_hora')
        tema = request.form.get('tema')
        
        conexao = psycopg2.connect(DATABASE_URL)
        cursor = conexao.cursor()
        try:
            # CORREÇÃO: Fechamento correto das aspas triplas e uso do %s
            cursor.execute("""
                INSERT INTO Aula (id_professor, data_hora, tema, status) 
                VALUES (%s, %s, %s, 'AGENDADA')
            """, (session.get('user_id'), data_hora, tema))
            
            conexao.commit()
            flash('Aula agendada com sucesso!', 'success')
            return redirect(url_for('listar_aulas'))
        finally:
            cursor.close()
            conexao.close()
            
    return render_template('nova_aula.html')


# ==================================================
# 6. GESTÃO DE MATERIAIS DIDÁTICOS
# ==================================================
@app.route('/materiais', methods=['GET'])
@login_required()
def listar_materiais():
    """Lista materiais didáticos disponíveis"""
    conexao = psycopg2.connect(DATABASE_URL)
    cursor = conexao.cursor()
    try:
        cursor.execute("SELECT id_material, titulo, descricao, link_arquivo FROM Material_Didatico")
        materiais = cursor.fetchall()
        return render_template('materiais.html', materiais=materiais)
    finally:
        cursor.close()
        conexao.close()

@app.route('/materiais/novo', methods=['GET', 'POST'])
@login_required('PROFESSOR')
def novo_material():
    """Rota para o professor adicionar um novo material"""
    if request.method == 'POST':
        titulo = request.form.get('titulo')
        descricao = request.form.get('descricao')
        link_arquivo = request.form.get('link_arquivo')
        
        conexao = psycopg2.connect(DATABASE_URL)
        cursor = conexao.cursor()
        try:
            cursor.execute("""
                INSERT INTO Material_Didatico (id_professor, titulo, descricao, link_arquivo) 
                VALUES (%s, %s, %s, %s)
            """, (session.get('user_id'), titulo, descricao, link_arquivo))
            conexao.commit()
            flash('Material adicionado com sucesso!', 'success')
            return redirect(url_for('listar_materiais'))
        finally:
            cursor.close()
            conexao.close()
            
    return render_template('novo_material.html')


# ==================================================
# 7. SEÇÃO DE CADASTRO (ALUNOS E PROFESSORES)
# ==================================================
@app.route('/cadastro')
def pagina_cadastro():
    return render_template('cadastro_aluno.html')

@app.route('/api/alunos', methods=['POST'])
def cadastrar_aluno():
    dados = request.json
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

@app.route('/cadastro-professor')
@login_required('PROFESSOR')
def pagina_cadastro_professor():
    return render_template('cadastro_professor.html')

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
# 8. INICIALIZAÇÃO DO SERVIDOR
# ==================================================
if __name__ == '__main__':
    app.run(debug=True)