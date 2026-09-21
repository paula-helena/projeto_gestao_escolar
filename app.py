from flask import Flask, request, jsonify, render_template, redirect, url_for, session, flash
import psycopg2
from flask_bcrypt import Bcrypt
from functools import wraps
import os
from werkzeug.utils import secure_filename

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
# 11. SEÇÃO DE MATERIAIS DE AULA (PASSOS 15 E 16)
# ==================================================

UPLOAD_FOLDER_PDF = 'static/uploads/pdf'
UPLOAD_FOLDER_VIDEO = 'static/uploads/video'


@app.route('/aula/<int:id_aula>/materiais', methods=['GET', 'POST'])
@login_required('PROFESSOR')
def gerenciar_materiais(id_aula):
    conexao = psycopg2.connect(DATABASE_URL)
    cursor = conexao.cursor()

    if request.method == 'POST':
        descricao = request.form.get('descricao')
        tipo_material = request.form.get('tipo_material') # 'PDF', 'Vídeo', 'Link'
        url_arquivo = ''

        try:
            if tipo_material == 'Link':
                url_arquivo = request.form.get('url_link')
            else:
                # Tratamento de upload de arquivo físico
                arquivo = request.files.get('arquivo')
                if arquivo and arquivo.filename != '':
                    nome_seguro = secure_filename(arquivo.filename)
                    
                    if tipo_material == 'PDF':
                        os.makedirs(UPLOAD_FOLDER_PDF, exist_ok=True)
                        caminho_completo = os.path.join(UPLOAD_FOLDER_PDF, nome_seguro)
                        arquivo.save(caminho_completo)
                        url_arquivo = f"uploads/pdf/{nome_seguro}"
                    elif tipo_material == 'Vídeo':
                        os.makedirs(UPLOAD_FOLDER_VIDEO, exist_ok=True)
                        caminho_completo = os.path.join(UPLOAD_FOLDER_VIDEO, nome_seguro)
                        arquivo.save(caminho_completo)
                        url_arquivo = f"uploads/video/{nome_seguro}"

            cursor.execute(
                """
                INSERT INTO material_apoio (id_aula, tipo_material, url_arquivo, descricao) 
                VALUES (%s, %s, %s, %s)
                """,
                (id_aula, tipo_material, url_arquivo, descricao)
            )
            conexao.commit()
            flash('Material cadastrado com sucesso!', 'success')
            return redirect(url_for('gerenciar_materiais', id_aula=id_aula))
        except Exception as e:
            conexao.rollback()
            flash(f'Erro ao salvar material: {e}', 'danger')

    # GET: Busca dados da aula e a lista de materiais cadastrados na tabela correta
    try:
        cursor.execute("""
            SELECT a.data_aula, t.titulo 
            FROM Aula a 
            JOIN Tema t ON a.id_tema = t.id_tema 
            WHERE a.id_aula = %s
        """, (id_aula,))
        aula = cursor.fetchone()

        cursor.execute("""
            SELECT id_material, tipo_material, url_arquivo, descricao 
            FROM material_apoio 
            WHERE id_aula = %s 
            ORDER BY id_material DESC
        """, (id_aula,))
        materiais = cursor.fetchall()
    except Exception as e:
        print(f"Erro ao buscar materiais: {e}")
        aula = None
        materiais = []
    finally:
        cursor.close()
        conexao.close()

    return render_template('materiais_aula.html', aula=aula, id_aula=id_aula, materiais=materiais)

# =================================================
# ROTA DE EXCLUSÃO DE MATERIAL (PASSO 17)
# ==================================================

@app.route('/material/<int:id_material>/excluir', methods=['POST'])
@login_required('PROFESSOR')
def excluir_material(id_material):
    conexao = psycopg2.connect(DATABASE_URL)
    cursor = conexao.cursor()
    
    id_aula = None
    try:
        # Busca o material para identificar o arquivo e a aula vinculada
        cursor.execute("SELECT id_aula, tipo_material, url_arquivo FROM material_apoio WHERE id_material = %s", (id_material,))
        material = cursor.fetchone()
        
        if material:
            id_aula = material[0]
            tipo_material = material[1]
            url_arquivo = material[2]
            
            # Se for um arquivo físico (PDF ou Vídeo), remove da pasta static
            if tipo_material != 'Link' and url_arquivo:
                caminho_fisico = os.path.join('static', url_arquivo)
                if os.path.exists(caminho_fisico):
                    os.remove(caminho_fisico)
            
            # Deleta o registro da tabela material_apoio
            cursor.execute("DELETE FROM material_apoio WHERE id_material = %s", (id_material,))
            conexao.commit()
            flash('Material excluído com sucesso!', 'success')
    except Exception as e:
        conexao.rollback()
        flash(f'Erro ao excluir material: {e}', 'danger')
    finally:
        cursor.close()
        conexao.close()
        
    # Redireciona de volta para a página de materiais daquela aula específica
    if id_aula:
        return redirect(url_for('gerenciar_materiais', id_aula=id_aula))
    return redirect(url_for('agenda_interativa'))

# ==================================================
# 7. INICIALIZAÇÃO DO SERVIDOR
# ==================================================
if __name__ == '__main__':
    app.run(debug=True)