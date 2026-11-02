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
        perfil_solicitado = request.form.get('perfil')

        conexao = psycopg2.connect(DATABASE_URL)
        cursor = conexao.cursor()

        try:
            perfis = {
                'ALUNO': ('public.aluno', 'id_aluno'),
                'PROFESSOR': ('public.professor', 'id_professor'),
            }
            candidatos = (
                [perfil_solicitado]
                if perfil_solicitado in perfis
                else ['ALUNO', 'PROFESSOR'] if perfil_solicitado is None else []
            )
            usuario = None
            perfil = None
            for candidato in candidatos:
                tabela, id_coluna = perfis[candidato]
                cursor.execute(
                    f"SELECT {id_coluna}, nome, email, senha FROM {tabela} WHERE email = %s",
                    (email,)
                )
                usuario = cursor.fetchone()
                if usuario:
                    perfil = candidato
                    break

            if usuario:
                senha_banco = usuario[3]

                # Valida se a senha usa hash bcrypt ou se é texto puro
                if senha_banco.startswith('$2b$') or senha_banco.startswith('$2a$'):
                    senha_valida = bcrypt.check_password_hash(senha_banco, senha)
                else:
                    senha_valida = (senha_banco == senha)

                # 3. Autentica e salva a sessão
                if senha_valida:
                    session['user_id'] = usuario[0]
                    session['nome'] = usuario[1]
                    session['email'] = usuario[2]
                    session['perfil'] = perfil

                    flash(f'Bem-vindo(a), {usuario[1]}!', 'success')

                    # Redireciona ambos os perfis para a rota unificada listar_aulas
                    return redirect(url_for('listar_aulas'))

            # Se não encontrou o usuário ou a senha estava incorreta
            flash('E-mail ou senha incorretos. Tente novamente.', 'danger')

        except Exception as e:
            flash(f'Erro ao processar login: {str(e)}', 'danger')

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
@app.route('/aulas/nova', methods=['GET', 'POST'])
@login_required('PROFESSOR')
def nova_aula():
    """Rota para o professor cadastrar uma nova aula vinculando a um aluno e a um tema"""
    conexao = psycopg2.connect(DATABASE_URL)
    cursor = conexao.cursor()

    if request.method == 'POST':
        data_hora = request.form.get('data_hora')
        tema = request.form.get('tema') # Recebe o nome do tema escolhido no dropdown
        id_aluno = request.form.get('id_aluno')
       
        try:
            # 1. Cria a aula na tabela aula
            cursor.execute("""
                INSERT INTO public.aula (id_professor, data_hora, tema, status)
                VALUES (%s, %s, %s, 'AGENDADA') RETURNING id_aula
            """, (session.get('user_id'), data_hora, tema))
           
            nova_aula_id = cursor.fetchone()[0]

            # 2. Se o aluno foi selecionado, cria o vínculo na tabela aula_aluno
            if id_aluno:
                cursor.execute("""
                    INSERT INTO public.aula_aluno (id_aluno, id_aula, presenca)
                    VALUES (%s, %s, FALSE)
                """, (id_aluno, nova_aula_id))

            conexao.commit()
            flash('Aula agendada e vinculada ao aluno com sucesso!', 'success')
            return redirect(url_for('listar_aulas'))
        except Exception as e:
            conexao.rollback()
            flash(f'Erro ao agendar aula: {str(e)}', 'danger')
            return redirect(url_for('nova_aula'))
        finally:
            cursor.close()
            conexao.close()
           
    # Método GET: Apenas busca alunos e temas para carregar na tela
    try:
        # Busca os alunos cadastrados para o dropdown
        cursor.execute("SELECT id_aluno, nome FROM public.aluno ORDER BY nome")
        alunos = cursor.fetchall()
       
        # Busca os temas cadastrados para o dropdown
        cursor.execute("SELECT id_tema, titulo FROM public.tema ORDER BY titulo")
        temas = cursor.fetchall()

        return render_template('nova_aula.html', alunos=alunos, temas=temas)
    except Exception as e:
        flash(f'Erro ao carregar dados de agendamento: {str(e)}', 'danger')
        return redirect(url_for('listar_aulas'))
    finally:
        cursor.close()
        conexao.close()


@app.route('/aulas', methods=['GET'])
@login_required()
def listar_aulas():
    """Lista apenas as aulas do professor ou aluno autenticado."""
    conexao = psycopg2.connect(DATABASE_URL)
    cursor = conexao.cursor()
    try:
        if session.get('perfil') == 'PROFESSOR':
            cursor.execute("""
                SELECT a.id_aula, a.data_hora, a.tema, a.status,
                       COALESCE(al.nome, 'Não vinculado'), p.nome
                FROM public.aula AS a
                JOIN public.professor AS p ON p.id_professor = a.id_professor
                LEFT JOIN public.aula_aluno AS aa ON aa.id_aula = a.id_aula
                LEFT JOIN public.aluno AS al ON al.id_aluno = aa.id_aluno
                WHERE a.id_professor = %s
                ORDER BY a.data_hora
            """, (session['user_id'],))
        else:
            cursor.execute("""
                SELECT a.id_aula, a.data_hora, a.tema, a.status,
                       al.nome, p.nome
                FROM public.aula AS a
                JOIN public.aula_aluno AS aa ON aa.id_aula = a.id_aula
                JOIN public.aluno AS al ON al.id_aluno = aa.id_aluno
                JOIN public.professor AS p ON p.id_professor = a.id_professor
                WHERE aa.id_aluno = %s
                ORDER BY a.data_hora
            """, (session['user_id'],))
        aulas = cursor.fetchall()
        return render_template('aulas.html', aulas=aulas)
    finally:
        cursor.close()
        conexao.close()


@app.route('/aulas/editar/<int:id_aula>', methods=['GET'])
@login_required('PROFESSOR')
def editar_aula_form(id_aula):
    conexao = psycopg2.connect(DATABASE_URL)
    cursor = conexao.cursor()
    try:
        cursor.execute("""
            SELECT id_aula, data_hora, tema, status
            FROM public.aula
            WHERE id_aula = %s AND id_professor = %s
        """, (id_aula, session['user_id']))
        aula = cursor.fetchone()
        if not aula:
            flash('Aula não encontrada.', 'danger')
            return redirect(url_for('listar_aulas'))

        cursor.execute("SELECT id_tema, titulo FROM public.tema ORDER BY titulo")
        temas = cursor.fetchall()
        return render_template('editar_aula.html', aula=aula, temas=temas)
    finally:
        cursor.close()
        conexao.close()


@app.route('/aulas/atualizar/<int:id_aula>', methods=['POST'])
@login_required('PROFESSOR')
def atualizar_aula(id_aula):
    conexao = psycopg2.connect(DATABASE_URL)
    cursor = conexao.cursor()
    try:
        cursor.execute("""
            UPDATE public.aula
            SET tema = %s, data_hora = %s, status = %s
            WHERE id_aula = %s AND id_professor = %s
            RETURNING id_aula
        """, (
            request.form.get('tema'),
            request.form.get('data_hora'),
            request.form.get('status'),
            id_aula,
            session['user_id'],
        ))
        if not cursor.fetchone():
            conexao.rollback()
            flash('Aula não encontrada.', 'danger')
            return redirect(url_for('listar_aulas'))
        conexao.commit()
        flash('Aula atualizada com sucesso!', 'success')
        return redirect(url_for('listar_aulas'))
    except Exception:
        conexao.rollback()
        raise
    finally:
        cursor.close()
        conexao.close()


@app.route('/aulas/excluir/<int:id_aula>', methods=['POST'])
@login_required('PROFESSOR')
def excluir_aula(id_aula):
    conexao = psycopg2.connect(DATABASE_URL)
    cursor = conexao.cursor()
    try:
        cursor.execute(
            "DELETE FROM public.aula WHERE id_aula = %s AND id_professor = %s",
            (id_aula, session['user_id'])
        )
        if cursor.rowcount == 0:
            flash('Aula não encontrada.', 'danger')
        else:
            conexao.commit()
            flash('Aula excluída com sucesso!', 'info')
        return redirect(url_for('listar_aulas'))
    except Exception:
        conexao.rollback()
        raise
    finally:
        cursor.close()
        conexao.close()


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
       
@app.route('/alunos', methods=['GET'])
@login_required('PROFESSOR')
def gerenciar_alunos():
    conexao = psycopg2.connect(DATABASE_URL)
    cursor = conexao.cursor()


    cursor.execute("SELECT id_aluno, nome, email, cidade, uf FROM Aluno ORDER BY id_aluno DESC")
    alunos = cursor.fetchall()
   
    cursor.close()
    conexao.close()
    return render_template('alunos.html', alunos=alunos)


@app.route('/alunos/editar/<int:id_aluno>', methods=['GET'])
@login_required('PROFESSOR')
def editar_aluno_form(id_aluno):
    conexao = psycopg2.connect(DATABASE_URL)
    cursor = conexao.cursor()


    cursor.execute("SELECT id_aluno, nome, email, cep, logradouro, bairro, cidade, uf, numero, complemento FROM Aluno WHERE id_aluno = %s", (id_aluno,))
    aluno = cursor.fetchone()


    cursor.close()
    conexao.close()


    if not aluno:
        flash('Aluno não encontrado.', 'danger')
        return redirect(url_for('gerenciar_alunos'))


    return render_template('editar_aluno.html', aluno=aluno)


@app.route('/alunos/atualizar/<int:id_aluno>', methods=['POST'])
@login_required('PROFESSOR')
def atualizar_aluno(id_aluno):
    nome = request.form.get('nome')
    email = request.form.get('email')
    cep = request.form.get('cep')
    logradouro = request.form.get('logradouro')
    bairro = request.form.get('bairro')
    cidade = request.form.get('cidade')
    uf = request.form.get('uf')
    numero = request.form.get('numero')
    complemento = request.form.get('complemento')


    conexao = psycopg2.connect(DATABASE_URL)
    cursor = conexao.cursor()


    cursor.execute(
        """UPDATE Aluno SET nome = %s, email = %s, cep = %s, logradouro = %s,
           bairro = %s, cidade = %s, uf = %s, numero = %s, complemento = %s WHERE id_aluno = %s""",
        (nome, email, cep, logradouro, bairro, cidade, uf, numero, complemento, id_aluno)
    )
    conexao.commit()


    cursor.close()
    conexao.close()


    flash('Cadastro do aluno atualizado com sucesso!', 'success')
    return redirect(url_for('gerenciar_alunos'))


@app.route('/alunos/excluir/<int:id_aluno>', methods=['POST'])
@login_required('PROFESSOR')
def excluir_aluno(id_aluno):
    conexao = psycopg2.connect(DATABASE_URL)
    cursor = conexao.cursor()


    cursor.execute("DELETE FROM Aluno WHERE id_aluno = %s", (id_aluno,))
    conexao.commit()


    cursor.close()
    conexao.close()
   
    flash('Aluno excluído com sucesso!', 'info')
    return redirect(url_for('gerenciar_alunos'))  




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
       
@app.route('/professores', methods=['GET'])
@login_required('PROFESSOR')
def gerenciar_professores():
    conexao = psycopg2.connect(DATABASE_URL)
    cursor = conexao.cursor()


    cursor.execute("SELECT id_professor, nome, email, disciplina, cidade, uf FROM Professor ORDER BY id_professor DESC")
    professores = cursor.fetchall()
   
    cursor.close()
    conexao.close()
    return render_template('professores.html', professores=professores)


@app.route('/professores/editar/<int:id_professor>', methods=['GET'])
@login_required('PROFESSOR')
def editar_professor_form(id_professor):
    conexao = psycopg2.connect(DATABASE_URL)
    cursor = conexao.cursor()


    cursor.execute("SELECT id_professor, nome, email, disciplina, cep, logradouro, bairro, cidade, uf, numero, complemento FROM Professor WHERE id_professor = %s", (id_professor,))
    professor = cursor.fetchone()


    cursor.close()
    conexao.close()


    if not professor:
        flash('Professor não encontrado.', 'danger')
        return redirect(url_for('gerenciar_professores'))


    return render_template('editar_professor.html', professor=professor)


@app.route('/professores/atualizar/<int:id_professor>', methods=['POST'])
@login_required('PROFESSOR')
def atualizar_professor(id_professor):
    nome = request.form.get('nome')
    email = request.form.get('email')
    disciplina = request.form.get('disciplina')
    cep = request.form.get('cep')
    logradouro = request.form.get('logradouro')
    bairro = request.form.get('bairro')
    cidade = request.form.get('cidade')
    uf = request.form.get('uf')
    numero = request.form.get('numero')
    complemento = request.form.get('complemento')


    conexao = psycopg2.connect(DATABASE_URL)
    cursor = conexao.cursor()


    cursor.execute(
        """UPDATE Professor SET nome = %s, email = %s, disciplina = %s, cep = %s, logradouro = %s,
           bairro = %s, cidade = %s, uf = %s, numero = %s, complemento = %s WHERE id_professor = %s""",
        (nome, email, disciplina, cep, logradouro, bairro, cidade, uf, numero, complemento, id_professor)
    )
    conexao.commit()


    cursor.close()
    conexao.close()


    flash('Cadastro do professor atualizado com sucesso!', 'success')
    return redirect(url_for('gerenciar_professores'))


@app.route('/professores/excluir/<int:id_professor>', methods=['POST'])
@login_required('PROFESSOR')
def excluir_professor(id_professor):
    conexao = psycopg2.connect(DATABASE_URL)
    cursor = conexao.cursor()


    cursor.execute("DELETE FROM Professor WHERE id_professor = %s", (id_professor,))
    conexao.commit()


    cursor.close()
    conexao.close()
   
    flash('Professor excluído com sucesso!', 'info')
    return redirect(url_for('gerenciar_professores'))




# ==================================================
# 8. GESTÃO DE TEMAS
# ==================================================

@app.route('/temas/novo', methods=['POST'])
@login_required('PROFESSOR')
def novo_tema():
    titulo = request.form.get('nome_tema', '').strip()
    if not titulo:
        flash('Informe o nome do tema.', 'warning')
        return redirect(url_for('nova_aula'))

    conexao = psycopg2.connect(DATABASE_URL)
    cursor = conexao.cursor()
    try:
        cursor.execute(
            "INSERT INTO public.tema (titulo) VALUES (%s)",
            (titulo,)
        )
        conexao.commit()
        flash('Tema cadastrado com sucesso!', 'success')
    except Exception:
        conexao.rollback()
        raise
    finally:
        cursor.close()
        conexao.close()
    return redirect(url_for('nova_aula'))


# Rota para Listar e Cadastrar Temas
@app.route('/temas', methods=['GET', 'POST'])
@login_required('PROFESSOR') # Ou o nível de acesso que preferir
def gerenciar_temas():
    conexao = psycopg2.connect(DATABASE_URL)
    cursor = conexao.cursor()


    if request.method == 'POST':
        titulo = request.form.get('titulo')
        descricao = request.form.get('descricao')
       
        cursor.execute(
            "INSERT INTO Tema (titulo, descricao) VALUES (%s, %s)",
            (titulo, descricao)
        )
        conexao.commit()
        flash('Tema cadastrado com sucesso!', 'success')
        return redirect(url_for('gerenciar_temas'))


    # Busca todos os temas cadastrados
    cursor.execute("SELECT id_tema, titulo, descricao FROM Tema ORDER BY id_tema DESC")
    temas = cursor.fetchall()
   
    cursor.close()
    conexao.close()
    return render_template('temas.html', temas=temas)


# Rota para Ver Detalhes do Tema e Materiais Relacionados
@app.route('/temas/<int:id_tema>')
@login_required('PROFESSOR')
def detalhe_tema(id_tema):
    conexao = psycopg2.connect(DATABASE_URL)
    cursor = conexao.cursor()


    # Busca o tema específico
    cursor.execute("SELECT id_tema, titulo, descricao FROM Tema WHERE id_tema = %s", (id_tema,))
    tema = cursor.fetchone()


    if not tema:
        flash('Tema não encontrado.', 'danger')
        return redirect(url_for('gerenciar_temas'))


    # Como a tabela Material_Didatico não tem FK direta para id_tema,
    # podemos buscar os materiais cujo título/descrição corresponda ou relacioná-los pelo título do tema:
    cursor.execute(
        "SELECT id_material, titulo, descricao, link_arquivo FROM Material_Didatico WHERE descricao ILIKE %s OR titulo ILIKE %s",
        (f"%{tema[1]}%", f"%{tema[1]}%")
    )
    materiais = cursor.fetchall()


    cursor.close()
    conexao.close()
    return render_template('detalhe_tema.html', tema=tema, materiais=materiais)


# Rota para Exibir o Formulário de Edição do Tema
@app.route('/temas/editar/<int:id_tema>', methods=['GET'])
@login_required('PROFESSOR')
def editar_tema_form(id_tema):
    conexao = psycopg2.connect(DATABASE_URL)
    cursor = conexao.cursor()


    cursor.execute("SELECT id_tema, titulo, descricao FROM Tema WHERE id_tema = %s", (id_tema,))
    tema = cursor.fetchone()


    cursor.close()
    conexao.close()


    if not tema:
        flash('Tema não encontrado.', 'danger')
        return redirect(url_for('gerenciar_temas'))


    return render_template('editar_tema.html', tema=tema)


# Rota para Salvar as Alterações do Tema
@app.route('/temas/atualizar/<int:id_tema>', methods=['POST'])
@login_required('PROFESSOR')
def atualizar_tema(id_tema):
    titulo = request.form.get('titulo')
    descricao = request.form.get('descricao')


    conexao = psycopg2.connect(DATABASE_URL)
    cursor = conexao.cursor()


    cursor.execute(
        "UPDATE Tema SET titulo = %s, descricao = %s WHERE id_tema = %s",
        (titulo, descricao, id_tema)
    )
    conexao.commit()


    cursor.close()
    conexao.close() # Garante que fecha a 'conexao' aberta acima


    flash('Tema atualizado com sucesso!', 'success')
    return redirect(url_for('gerenciar_temas'))


# Rota para Excluir Tema
@app.route('/temas/excluir/<int:id_tema>', methods=['POST'])
@login_required('PROFESSOR')
def excluir_tema(id_tema):
    conexao = psycopg2.connect(DATABASE_URL)
    cursor = conexao.cursor()


    cursor.execute("DELETE FROM Tema WHERE id_tema = %s", (id_tema,))
    conexao.commit()


    cursor.close()
    conexao.close()
    flash('Tema excluído com sucesso!', 'info')
    return redirect(url_for('gerenciar_temas'))


# ==================================================
# 9. INICIALIZAÇÃO DO SERVIDOR
# ==================================================
if __name__ == '__main__':
    app.run(debug=True)