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
# 10. SEÇÃO DE AGENDA INTERATIVA (PASSOS 13 E 14)
# ==================================================
import calendar
from datetime import datetime
from api_feriados import obter_feriados

@app.route('/agenda')
def agenda_interativa():
    hoje = datetime.now()
    try:
        mes = int(request.args.get('mes', hoje.month))
        ano = int(request.args.get('ano', hoje.year))
    except ValueError:
        mes = hoje.month
        ano = hoje.year

    visao = request.args.get('visao', 'lista') # 'lista' ou 'calendario'

    # 1. Busca aulas do banco
    conexao = psycopg2.connect(DATABASE_URL)
    cursor = conexao.cursor()
    aulas = []
    try:
        cursor.execute("""
            SELECT a.data_aula, a.horario_inicio, t.titulo, a.link_aula, p.nome 
            FROM Aula a
            JOIN Tema t ON a.id_tema = t.id_tema
            JOIN Professor p ON a.id_professor = p.id_professor
            ORDER BY a.data_aula ASC
        """)
        for row in cursor.fetchall():
            data_original = str(row[0]) # YYYY-MM-DD
            partes = data_original.split('-')
            data_formatada = f"{partes[2]}-{partes[1]}-{partes[0]}" if len(partes) == 3 else data_original
            
            aulas.append({
                'data_iso': data_original,
                'data': data_formatada,
                'horario': str(row[1])[:5],
                'titulo': row[2],
                'link': row[3],
                'professor': row[4],
                'tipo': 'Aula Agendada'
            })
    except Exception as e:
        print(f"Erro ao buscar aulas: {e}")
    finally:
        cursor.close()
        conexao.close()

    # 2. Busca feriados da API
    feriados_br = obter_feriados()
    feriados = []
    for f in feriados_br:
        data_original = f['data'] # YYYY-MM-DD
        partes = data_original.split('-')
        data_formatada = f"{partes[2]}-{partes[1]}-{partes[0]}" if len(partes) == 3 else data_original
        feriados.append({
            'data_iso': data_original,
            'data': data_formatada,
            'horario': 'Dia Todo',
            'titulo': f['nome'],
            'link': None,
            'professor': '-',
            'tipo': 'Feriado Nacional'
        })

    eventos_totais = aulas + feriados
    eventos_totais.sort(key=lambda x: x['data_iso'])

    # Mapear eventos por data ISO (ex: '2026-09-30': [evento1, evento2])
    eventos_por_data = {}
    for ev in eventos_totais:
        d = ev['data_iso']
        if d not in eventos_por_data:
            eventos_por_data[d] = []
        eventos_por_data[d].append(ev)

    # Navegação de meses
    mes_anterior = mes - 1 if mes > 1 else 12
    ano_anterior = ano if mes > 1 else ano - 1
    mes_proximo = mes + 1 if mes < 12 else 1
    ano_proximo = ano if mes < 12 else ano + 1

    meses_pt = ['', 'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 
                'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro']
    nome_mes_atual = meses_pt[mes]

    # Gerar a matriz do calendário do mês (iniciando em Segunda-feira ou Domingo. Usaremos calendar.Calendar(firstweekday=6) para Domingo)
    cal = calendar.Calendar(firstweekday=6) # 6 = Domingo como primeiro dia da semana
    matriz_calendario = cal.monthdayscalendar(ano, mes)

    return render_template('agenda.html', 
                           eventos=eventos_totais,
                           eventos_por_data=eventos_por_data,
                           matriz_calendario=matriz_calendario,
                           visao=visao,
                           mes_atual=mes,
                           ano_atual=ano,
                           nome_mes=nome_mes_atual,
                           mes_anterior=mes_anterior,
                           ano_anterior=ano_anterior,
                           mes_proximo=mes_proximo,
                           ano_proximo=ano_proximo)

# ==================================================
# 7. INICIALIZAÇÃO DO SERVIDOR
# ==================================================
if __name__ == '__main__':
    app.run(debug=True)