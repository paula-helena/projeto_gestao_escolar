import os
import calendar
import hashlib
import secrets
import smtplib
import ssl
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from email.message import EmailMessage
from flask import (
    Flask, request, jsonify, render_template, redirect, url_for, session, flash,
    get_flashed_messages,
)
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

SENHA_PADRAO = 'mrdave'
app.config.update(
    SMTP_SERVER=os.getenv('SMTP_SERVER'),
    SMTP_PORT=int(os.getenv('SMTP_PORT', '587')),
    SMTP_USERNAME=os.getenv('SMTP_USERNAME'),
    SMTP_PASSWORD=os.getenv('SMTP_PASSWORD'),
    SMTP_USE_TLS=os.getenv('SMTP_USE_TLS', 'true').lower() == 'true',
    SMTP_USE_SSL=os.getenv('SMTP_USE_SSL', 'false').lower() == 'true',
    SMTP_FROM_EMAIL=os.getenv('SMTP_FROM_EMAIL'),
    PUBLIC_BASE_URL=os.getenv('PUBLIC_BASE_URL'),
)


def enviar_email_redefinicao(destinatario, link):
    servidor_smtp = app.config['SMTP_SERVER']
    remetente = app.config['SMTP_FROM_EMAIL']
    if not servidor_smtp or not remetente or not app.config['PUBLIC_BASE_URL']:
        raise RuntimeError(
            'SMTP_SERVER, SMTP_FROM_EMAIL e PUBLIC_BASE_URL precisam estar configurados.'
        )
    if app.config['SMTP_USE_TLS'] and app.config['SMTP_USE_SSL']:
        raise RuntimeError('SMTP_USE_TLS e SMTP_USE_SSL não podem estar ativos juntos.')
    if bool(app.config['SMTP_USERNAME']) != bool(app.config['SMTP_PASSWORD']):
        raise RuntimeError('SMTP_USERNAME e SMTP_PASSWORD precisam ser configurados juntos.')

    mensagem = EmailMessage()
    mensagem['Subject'] = 'Redefinição de senha - Mr. Dave Idiomas'
    mensagem['From'] = remetente
    mensagem['To'] = destinatario
    mensagem.set_content(
        'Recebemos uma solicitação para redefinir sua senha.\n\n'
        f'Acesse este link em até 1 hora para escolher uma nova senha:\n{link}\n\n'
        'Se você não solicitou a redefinição, ignore esta mensagem.'
    )

    contexto_ssl = ssl.create_default_context()
    if app.config['SMTP_USE_SSL']:
        with smtplib.SMTP_SSL(
            servidor_smtp, app.config['SMTP_PORT'], context=contexto_ssl, timeout=15
        ) as servidor:
            if app.config['SMTP_USERNAME']:
                servidor.login(app.config['SMTP_USERNAME'], app.config['SMTP_PASSWORD'])
            servidor.send_message(mensagem)
    else:
        with smtplib.SMTP(
            servidor_smtp, app.config['SMTP_PORT'], timeout=15
        ) as servidor:
            if app.config['SMTP_USE_TLS']:
                servidor.starttls(context=contexto_ssl)
            if app.config['SMTP_USERNAME']:
                servidor.login(app.config['SMTP_USERNAME'], app.config['SMTP_PASSWORD'])
            servidor.send_message(mensagem)

DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://postgres:admin123@localhost:5432/gestao_escolar')

# ==================================================
# HELPERS DE AGENDAMENTO
# ==================================================
def adicionar_meses(data, quantidade):
    mes = data.month - 1 + quantidade
    ano = data.year + mes // 12
    mes = mes % 12 + 1
    dia = min(data.day, calendar.monthrange(ano, mes)[1])
    return date(ano, mes, dia)


def data_fim_recorrencia(inicio, duracao):
    meses = {'mes': 1, 'trimestre': 3, 'semestre': 6, 'ano': 12}
    if duracao == 'sempre':
        return None
    return adicionar_meses(inicio, meses[duracao])


def validar_horario_aula(valor):
    try:
        return datetime.strptime(valor, '%Y-%m-%dT%H:%M')
    except (TypeError, ValueError):
        raise ValueError('Informe uma data e horário válidos.')


def expandir_recorrencias(cursor, perfil, user_id, data_limite):
    filtro = 'id_professor = %s' if perfil == 'PROFESSOR' else 'id_aluno = %s'
    cursor.execute(f"""
        SELECT id_recorrencia, id_professor, id_aluno, tema, inicio, hora,
               dias_semana, fim_em, gerada_ate
        FROM public.aula_recorrencia
        WHERE ativa = TRUE AND {filtro}
        ORDER BY id_recorrencia
        FOR UPDATE
    """, (user_id,))
    recorrencias = cursor.fetchall()

    for recorrencia in recorrencias:
        (id_recorrencia, id_professor, id_aluno, tema, inicio, horario,
         dias_semana, fim_em, gerada_ate) = recorrencia
        limite = data_limite
        if fim_em:
            limite = min(limite, fim_em)
        dia = max(inicio, gerada_ate + timedelta(days=1))
        if dia > limite:
            continue

        cursor.execute("""
            SELECT id_material
            FROM public.aula_recorrencia_material
            WHERE id_recorrencia = %s
        """, (id_recorrencia,))
        materiais = [linha[0] for linha in cursor.fetchall()]

        while dia <= limite:
            if dia.isoweekday() in dias_semana:
                data_hora = datetime.combine(dia, horario)
                cursor.execute("""
                    INSERT INTO public.aula (
                        id_professor, tema, data_hora, status, id_recorrencia
                    )
                    VALUES (%s, %s, %s, 'AGENDADA', %s)
                    ON CONFLICT (id_recorrencia, data_hora)
                    WHERE id_recorrencia IS NOT NULL DO NOTHING
                    RETURNING id_aula
                """, (id_professor, tema, data_hora, id_recorrencia))
                aula = cursor.fetchone()
                if aula:
                    id_aula = aula[0]
                    cursor.execute("""
                        INSERT INTO public.aula_aluno (id_aluno, id_aula, presenca)
                        VALUES (%s, %s, FALSE)
                        ON CONFLICT (id_aluno, id_aula) DO NOTHING
                    """, (id_aluno, id_aula))
                    for id_material in materiais:
                        cursor.execute("""
                            INSERT INTO public.aula_material (id_aula, id_material)
                            VALUES (%s, %s)
                            ON CONFLICT (id_aula, id_material) DO NOTHING
                        """, (id_aula, id_material))
            dia += timedelta(days=1)

        cursor.execute("""
            UPDATE public.aula_recorrencia
            SET gerada_ate = %s
            WHERE id_recorrencia = %s
        """, (limite, id_recorrencia))


def materiais_selecionados(cursor, ids_materiais, id_professor):
    try:
        ids = sorted({int(valor) for valor in ids_materiais})
    except (TypeError, ValueError):
        raise ValueError('Seleção de material inválida.')
    if not ids:
        return []
    cursor.execute("""
        SELECT id_material
        FROM public.material_didatico
        WHERE id_professor = %s AND id_material = ANY(%s)
    """, (id_professor, ids))
    encontrados = {linha[0] for linha in cursor.fetchall()}
    if encontrados != set(ids):
        raise ValueError('Selecione somente materiais cadastrados por você.')
    return ids


def criar_aula(cursor, id_professor, id_aluno, tema, data_hora,
               id_recorrencia=None, id_aula_origem=None, ids_materiais=()):
    cursor.execute("""
        INSERT INTO public.aula (
            id_professor, tema, data_hora, status, id_recorrencia, id_aula_origem
        )
        VALUES (%s, %s, %s, 'AGENDADA', %s, %s)
        RETURNING id_aula
    """, (
        id_professor, tema or None, data_hora, id_recorrencia, id_aula_origem
    ))
    id_aula = cursor.fetchone()[0]

    if id_aluno:
        cursor.execute("""
            INSERT INTO public.aula_aluno (id_aluno, id_aula, presenca)
            VALUES (%s, %s, FALSE)
            ON CONFLICT (id_aluno, id_aula) DO NOTHING
        """, (id_aluno, id_aula))

    for id_material in ids_materiais:
        cursor.execute("""
            INSERT INTO public.aula_material (id_aula, id_material)
            VALUES (%s, %s)
            ON CONFLICT (id_aula, id_material) DO NOTHING
        """, (id_aula, id_material))
    return id_aula


def atualizar_status_aulas_concluidas(cursor, agora):
    cursor.execute("""
        UPDATE public.aula
        SET status = 'CONCLUIDA'
        WHERE status = 'AGENDADA' AND data_hora <= %s
    """, (agora,))


# ==================================================
# DECORATOR DE CONTROLE DE ACESSO
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
    if 'user_id' in session:
        if session.get('perfil') == 'PROFESSOR':
            return redirect(url_for('home_professor'))
        return redirect(url_for('home_aluno'))

    if request.method == 'POST':
        email = request.form.get('email')
        senha = request.form.get('senha')
        perfil_solicitado = request.form.get('perfil')

        conexao = None
        cursor = None
        try:
            conexao = psycopg2.connect(DATABASE_URL)
            cursor = conexao.cursor()

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

                    get_flashed_messages()
                    flash(f'Bem-vindo(a), {usuario[1]}!', 'success')
                    destino = (
                        'home_professor'
                        if perfil == 'PROFESSOR'
                        else 'home_aluno'
                    )
                    return redirect(url_for(destino))

            # Se não encontrou o usuário ou a senha estava incorreta
            flash('E-mail ou senha incorretos. Tente novamente.', 'danger')

        except psycopg2.Error:
            app.logger.exception('Erro de banco de dados ao processar login.')
            flash(
                'Não foi possível acessar o sistema no momento. Tente novamente mais tarde.',
                'danger'
            )

        finally:
            if cursor is not None:
                cursor.close()
            if conexao is not None:
                conexao.close()

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('Você saiu do sistema com sucesso.', 'info')
    return redirect(url_for('login'))


@app.route('/esqueci-senha', methods=['GET', 'POST'])
def esqueci_senha():
    if request.method == 'POST':
        perfil = request.form.get('perfil')
        email = (request.form.get('email') or '').strip()
        perfis = {
            'ALUNO': ('public.aluno', 'id_aluno'),
            'PROFESSOR': ('public.professor', 'id_professor'),
        }

        if perfil not in perfis or not email:
            flash('Informe o perfil e o e-mail cadastrados.', 'warning')
            return render_template('esqueci_senha.html')

        if (
            not app.config['SMTP_SERVER']
            or not app.config['SMTP_FROM_EMAIL']
            or not app.config['PUBLIC_BASE_URL']
        ):
            app.logger.error(
                'Recuperação de senha indisponível: SMTP_SERVER, SMTP_FROM_EMAIL '
                'ou PUBLIC_BASE_URL não configurado.'
            )
            flash(
                'A recuperação de senha está temporariamente indisponível. '
                'Tente novamente mais tarde.',
                'danger',
            )
            return render_template('esqueci_senha.html')

        tabela, id_coluna = perfis[perfil]
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode('utf-8')).hexdigest()
        usuario = None
        conexao = None
        cursor = None
        try:
            conexao = psycopg2.connect(DATABASE_URL)
            cursor = conexao.cursor()
            cursor.execute(
                f'SELECT {id_coluna} FROM {tabela} WHERE email = %s',
                (email,),
            )
            registro = cursor.fetchone()
            if registro:
                usuario = registro[0]
                cursor.execute("""
                    DELETE FROM public.redefinicao_senha
                    WHERE expira_em <= CURRENT_TIMESTAMP
                """)
                cursor.execute("""
                    INSERT INTO public.redefinicao_senha
                        (perfil, id_usuario, token_hash, expira_em)
                    VALUES (%s, %s, %s, CURRENT_TIMESTAMP + INTERVAL '1 hour')
                """, (perfil, usuario, token_hash))
            conexao.commit()
        except psycopg2.Error:
            if conexao is not None:
                conexao.rollback()
            app.logger.exception('Erro ao criar solicitação de redefinição de senha.')
            flash(
                'Não foi possível processar a solicitação. Tente novamente mais tarde.',
                'danger',
            )
            return render_template('esqueci_senha.html')
        finally:
            if cursor is not None:
                cursor.close()
            if conexao is not None:
                conexao.close()

        if usuario is not None:
            base_url = app.config['PUBLIC_BASE_URL'].rstrip('/')
            link = f'{base_url}{url_for("redefinir_senha", token=token)}'
            try:
                enviar_email_redefinicao(email, link)
            except (OSError, RuntimeError, ValueError, smtplib.SMTPException):
                app.logger.exception('Erro ao enviar e-mail de redefinição de senha.')
                conexao = None
                cursor = None
                try:
                    conexao = psycopg2.connect(DATABASE_URL)
                    cursor = conexao.cursor()
                    cursor.execute(
                        'DELETE FROM public.redefinicao_senha WHERE token_hash = %s',
                        (token_hash,),
                    )
                    conexao.commit()
                except psycopg2.Error:
                    if conexao is not None:
                        conexao.rollback()
                    app.logger.exception(
                        'Erro ao invalidar token cujo e-mail não foi enviado.'
                    )
                finally:
                    if cursor is not None:
                        cursor.close()
                    if conexao is not None:
                        conexao.close()
                flash(
                    'Se o perfil e o e-mail corresponderem a uma conta, '
                    'você receberá um link para redefinir a senha.',
                    'info',
                )
                return render_template('esqueci_senha.html')

        flash(
            'Se o perfil e o e-mail corresponderem a uma conta, '
            'você receberá um link para redefinir a senha.',
            'info',
        )
        return render_template('esqueci_senha.html')

    return render_template('esqueci_senha.html')


@app.route('/redefinir-senha/<token>', methods=['GET', 'POST'])
def redefinir_senha(token):
    if request.method == 'POST':
        senha = request.form.get('senha') or ''
        confirmacao = request.form.get('confirmacao') or ''
        if len(senha) < 8:
            flash('A nova senha precisa ter pelo menos 8 caracteres.', 'warning')
            return render_template('redefinir_senha.html', token=token)
        if senha != confirmacao:
            flash('As senhas informadas não coincidem.', 'warning')
            return render_template('redefinir_senha.html', token=token)

        token_hash = hashlib.sha256(token.encode('utf-8')).hexdigest()
        conexao = None
        cursor = None
        try:
            conexao = psycopg2.connect(DATABASE_URL)
            cursor = conexao.cursor()
            cursor.execute("""
                SELECT perfil, id_usuario
                FROM public.redefinicao_senha
                WHERE token_hash = %s AND expira_em > CURRENT_TIMESTAMP
                FOR UPDATE
            """, (token_hash,))
            registro = cursor.fetchone()
            if not registro:
                conexao.rollback()
                flash('Este link é inválido ou expirou. Solicite uma nova redefinição.', 'danger')
                return redirect(url_for('esqueci_senha'))

            perfil, id_usuario = registro
            tabelas = {
                'ALUNO': ('public.aluno', 'id_aluno'),
                'PROFESSOR': ('public.professor', 'id_professor'),
            }
            if perfil not in tabelas:
                conexao.rollback()
                app.logger.error('Token de redefinição contém perfil inválido.')
                flash('Não foi possível redefinir a senha. Solicite um novo link.', 'danger')
                return redirect(url_for('esqueci_senha'))

            tabela, id_coluna = tabelas[perfil]
            senha_hash = bcrypt.generate_password_hash(senha).decode('utf-8')
            cursor.execute(
                f'UPDATE {tabela} SET senha = %s WHERE {id_coluna} = %s',
                (senha_hash, id_usuario),
            )
            if cursor.rowcount != 1:
                conexao.rollback()
                flash('Este link é inválido ou expirou. Solicite uma nova redefinição.', 'danger')
                return redirect(url_for('esqueci_senha'))
            cursor.execute("""
                DELETE FROM public.redefinicao_senha
                WHERE perfil = %s AND id_usuario = %s
            """, (perfil, id_usuario))
            conexao.commit()
        except psycopg2.Error:
            if conexao is not None:
                conexao.rollback()
            app.logger.exception('Erro ao redefinir senha.')
            flash('Não foi possível redefinir a senha. Tente novamente mais tarde.', 'danger')
            return render_template('redefinir_senha.html', token=token)
        finally:
            if cursor is not None:
                cursor.close()
            if conexao is not None:
                conexao.close()

        session.clear()
        flash('Sua senha foi alterada. Entre com sua nova senha.', 'success')
        return redirect(url_for('login'))

    return render_template('redefinir_senha.html', token=token)


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
    """Cria uma aula avulsa, uma reposição ou uma série semanal."""
    conexao = psycopg2.connect(DATABASE_URL)
    cursor = conexao.cursor()

    if request.method == 'GET':
        try:
            id_aula_origem = request.args.get('reposicao_de', type=int)
            reposicao = None
            if id_aula_origem:
                cursor.execute("""
                    SELECT a.id_aula, a.tema, aa.id_aluno, al.nome
                    FROM public.aula AS a
                    LEFT JOIN public.aula_aluno AS aa ON aa.id_aula = a.id_aula
                    LEFT JOIN public.aluno AS al ON al.id_aluno = aa.id_aluno
                    WHERE a.id_aula = %s AND a.id_professor = %s
                      AND a.status = 'REAGENDADA'
                      AND NOT EXISTS (
                          SELECT 1 FROM public.aula AS reposicao
                          WHERE reposicao.id_aula_origem = a.id_aula
                      )
                """, (id_aula_origem, session['user_id']))
                reposicao = cursor.fetchone()
                if not reposicao:
                    flash('Aula de origem não está disponível para reposição.', 'warning')
                    return redirect(url_for('listar_aulas'))

            cursor.execute("SELECT id_aluno, nome FROM public.aluno ORDER BY nome")
            alunos = cursor.fetchall()
            cursor.execute("""
                SELECT id_material, titulo
                FROM public.material_didatico
                WHERE id_professor = %s
                ORDER BY titulo
            """, (session['user_id'],))
            materiais = cursor.fetchall()
            cursor.execute("SELECT id_tema, titulo FROM public.tema ORDER BY titulo")
            temas = cursor.fetchall()
            return render_template(
                'nova_aula.html',
                alunos=alunos,
                temas=temas,
                materiais=materiais,
                reposicao=reposicao,
            )
        finally:
            cursor.close()
            conexao.close()

    try:
        tema = request.form.get('tema', '').strip() or None
        if tema and len(tema) > 150:
            raise ValueError('O tema deve ter no máximo 150 caracteres.')

        id_aula_origem = request.form.get('reposicao_de', type=int)
        id_aluno = request.form.get('id_aluno', type=int)
        if id_aula_origem:
            cursor.execute("""
                SELECT a.tema, aa.id_aluno
                FROM public.aula AS a
                LEFT JOIN public.aula_aluno AS aa ON aa.id_aula = a.id_aula
                WHERE a.id_aula = %s AND a.id_professor = %s
                  AND a.status = 'REAGENDADA'
                  AND NOT EXISTS (
                      SELECT 1 FROM public.aula AS reposicao
                      WHERE reposicao.id_aula_origem = a.id_aula
                  )
            """, (id_aula_origem, session['user_id']))
            origem = cursor.fetchone()
            if not origem:
                raise ValueError('Aula de origem não está disponível para reposição.')
            tema = tema or origem[0]
            id_aluno = origem[1] or id_aluno

        if not id_aluno:
            raise ValueError('Selecione um aluno.')
        cursor.execute(
            "SELECT 1 FROM public.aluno WHERE id_aluno = %s",
            (id_aluno,)
        )
        if not cursor.fetchone():
            raise ValueError('Aluno selecionado não encontrado.')

        ids_materiais = materiais_selecionados(
            cursor, request.form.getlist('materiais'), session['user_id']
        )
        data_hora = validar_horario_aula(request.form.get('data_hora'))

        if request.form.get('modo') == 'recorrente' and not id_aula_origem:
            cursor.execute("""
                SELECT timezone('America/Sao_Paulo', CURRENT_TIMESTAMP)::date
            """)
            hoje = cursor.fetchone()[0]
            if data_hora.date() < hoje:
                raise ValueError('A primeira data da recorrência deve ser hoje ou futura.')

            try:
                dias_semana = sorted({
                    int(valor) for valor in request.form.getlist('dias_semana')
                })
            except ValueError:
                raise ValueError('Selecione dias da semana válidos.')
            if not dias_semana or any(dia not in range(1, 8) for dia in dias_semana):
                raise ValueError('Selecione pelo menos um dia da semana.')

            duracao = request.form.get('duracao')
            if duracao not in ('sempre', 'mes', 'trimestre', 'semestre', 'ano'):
                raise ValueError('Selecione uma duração válida para a recorrência.')
            fim_em = data_fim_recorrencia(data_hora.date(), duracao)

            cursor.execute("""
                INSERT INTO public.aula_recorrencia (
                    id_professor, id_aluno, tema, inicio, hora,
                    dias_semana, fim_em, gerada_ate
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id_recorrencia
            """, (
                session['user_id'], id_aluno, tema, data_hora.date(),
                data_hora.time(), dias_semana, fim_em,
                data_hora.date() - timedelta(days=1),
            ))
            id_recorrencia = cursor.fetchone()[0]
            for id_material in ids_materiais:
                cursor.execute("""
                    INSERT INTO public.aula_recorrencia_material (
                        id_recorrencia, id_material
                    )
                    VALUES (%s, %s)
                """, (id_recorrencia, id_material))

            limite = (
                fim_em
                if fim_em
                else max(hoje, data_hora.date()) + timedelta(days=90)
            )
            expandir_recorrencias(
                cursor, 'PROFESSOR', session['user_id'], limite
            )
            mensagem = 'Aulas recorrentes agendadas com sucesso!'
        else:
            criar_aula(
                cursor,
                session['user_id'],
                id_aluno,
                tema,
                data_hora,
                id_aula_origem=id_aula_origem,
                ids_materiais=ids_materiais,
            )
            mensagem = (
                'Aula de reposição agendada com sucesso!'
                if id_aula_origem else 'Aula agendada com sucesso!'
            )

        conexao.commit()
        flash(mensagem, 'success')
        return redirect(url_for('listar_aulas'))
    except ValueError as erro:
        conexao.rollback()
        flash(str(erro), 'warning')
        return redirect(url_for('nova_aula', reposicao_de=id_aula_origem))
    except Exception:
        conexao.rollback()
        raise
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
        periodo = request.args.get('periodo', 'mes')
        intervalos = {'mes': 1, 'trimestre': 3, 'semestre': 6, 'ano': 12}
        if periodo not in intervalos:
            periodo = 'mes'

        ordenacao = request.args.get('ordenacao', 'data')
        if ordenacao not in ('data', 'status'):
            ordenacao = 'data'
        direcao = request.args.get('direcao', 'asc').lower()
        if direcao not in ('asc', 'desc'):
            direcao = 'asc'

        cursor.execute("""
            SELECT timezone('America/Sao_Paulo', CURRENT_TIMESTAMP)
        """)
        agora = cursor.fetchone()[0]
        expandir_recorrencias(
            cursor,
            session['perfil'],
            session['user_id'],
            agora.date() + timedelta(days=90),
        )
        atualizar_status_aulas_concluidas(cursor, agora)

        inicio_periodo = agora.date().replace(day=1)
        if periodo in ('trimestre', 'semestre'):
            meses_periodo = intervalos[periodo]
            mes_inicio = ((inicio_periodo.month - 1) // meses_periodo) * meses_periodo + 1
            inicio_periodo = inicio_periodo.replace(month=mes_inicio)
        fim_periodo = adicionar_meses(inicio_periodo, intervalos[periodo])

        coluna_ordem = (
            "CASE a.status WHEN 'AGENDADA' THEN 1 WHEN 'CONCLUIDA' THEN 2 "
            "WHEN 'CANCELADA' THEN 3 WHEN 'REAGENDADA' THEN 4 ELSE 5 END"
            if ordenacao == 'status' else 'a.data_hora'
        )
        parametros = [session['user_id']]
        if session.get('perfil') == 'PROFESSOR':
            consulta = """
                SELECT a.id_aula, a.data_hora, a.tema, a.status,
                       COALESCE(al.nome, 'Não vinculado'), p.nome,
                       COALESCE(aa.revisar, FALSE)
                FROM public.aula AS a
                JOIN public.professor AS p ON p.id_professor = a.id_professor
                LEFT JOIN public.aula_aluno AS aa ON aa.id_aula = a.id_aula
                LEFT JOIN public.aluno AS al ON al.id_aluno = aa.id_aluno
                WHERE a.id_professor = %s
            """
        else:
            consulta = """
                SELECT a.id_aula, a.data_hora, a.tema, a.status,
                       al.nome, p.nome, COALESCE(aa.revisar, FALSE)
                FROM public.aula AS a
                JOIN public.aula_aluno AS aa ON aa.id_aula = a.id_aula
                JOIN public.aluno AS al ON al.id_aluno = aa.id_aluno
                JOIN public.professor AS p ON p.id_professor = a.id_professor
                WHERE aa.id_aluno = %s
            """
        consulta += " AND a.data_hora >= %s AND a.data_hora < %s"
        parametros.extend((inicio_periodo, fim_periodo))
        consulta += f" ORDER BY {coluna_ordem} {direcao}, a.data_hora {direcao}, a.id_aula {direcao}"
        cursor.execute(consulta, parametros)
        aulas = cursor.fetchall()
        conexao.commit()
        return render_template(
            'aulas.html',
            aulas=aulas,
            periodo=periodo,
            ordenacao=ordenacao,
            direcao=direcao,
        )
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
    tema = request.form.get('tema', '').strip() or None
    status = request.form.get('status')
    if status not in ('AGENDADA', 'CONCLUIDA', 'CANCELADA', 'REAGENDADA'):
        flash('Status de aula inválido.', 'warning')
        return redirect(url_for('editar_aula_form', id_aula=id_aula))
    try:
        data_hora = validar_horario_aula(request.form.get('data_hora'))
    except ValueError as erro:
        flash(str(erro), 'warning')
        return redirect(url_for('editar_aula_form', id_aula=id_aula))

    conexao = psycopg2.connect(DATABASE_URL)
    cursor = conexao.cursor()
    try:
        cursor.execute("""
            UPDATE public.aula
            SET tema = %s, data_hora = %s, status = %s
            WHERE id_aula = %s AND id_professor = %s
            RETURNING id_aula
        """, (
            tema,
            data_hora,
            status,
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


@app.route('/aulas/<int:id_aula>/cancelar', methods=['POST'])
@login_required('PROFESSOR')
def cancelar_aula(id_aula):
    conexao = psycopg2.connect(DATABASE_URL)
    cursor = conexao.cursor()
    try:
        cursor.execute("""
            UPDATE public.aula
            SET status = 'CANCELADA'
            WHERE id_aula = %s AND id_professor = %s
              AND status IN ('AGENDADA', 'CONCLUIDA')
        """, (id_aula, session['user_id']))
        if cursor.rowcount == 0:
            flash('Aula não encontrada ou não pode ser cancelada.', 'warning')
        else:
            conexao.commit()
            flash('Aula cancelada.', 'info')
        return redirect(url_for('listar_aulas'))
    except Exception:
        conexao.rollback()
        raise
    finally:
        cursor.close()
        conexao.close()


@app.route('/aulas/<int:id_aula>/reagendar', methods=['POST'])
@login_required('PROFESSOR')
def iniciar_reagendamento(id_aula):
    conexao = psycopg2.connect(DATABASE_URL)
    cursor = conexao.cursor()
    try:
        cursor.execute("""
            UPDATE public.aula AS a
            SET status = 'REAGENDADA'
            WHERE a.id_aula = %s AND a.id_professor = %s
              AND a.status IN ('AGENDADA', 'CONCLUIDA')
              AND NOT EXISTS (
                  SELECT 1 FROM public.aula AS reposicao
                  WHERE reposicao.id_aula_origem = a.id_aula
              )
        """, (id_aula, session['user_id']))
        if cursor.rowcount == 0:
            flash('Aula não encontrada ou já possui reposição.', 'warning')
            return redirect(url_for('listar_aulas'))
        conexao.commit()
        return redirect(url_for('nova_aula', reposicao_de=id_aula))
    except Exception:
        conexao.rollback()
        raise
    finally:
        cursor.close()
        conexao.close()


@app.route('/aulas/<int:id_aula>/mais', methods=['GET', 'POST'])
@login_required()
def detalhes_aula(id_aula):
    perfil = session.get('perfil')
    id_usuario = session.get('user_id')
    conexao = psycopg2.connect(DATABASE_URL)
    cursor = conexao.cursor()
    try:
        cursor.execute("""
            SELECT timezone('America/Sao_Paulo', CURRENT_TIMESTAMP)
        """)
        agora = cursor.fetchone()[0]
        atualizar_status_aulas_concluidas(cursor, agora)

        cursor.execute("""
            SELECT a.id_aula, a.data_hora, a.tema, a.status,
                   p.nome, al.nome, aa.nota_autoavaliacao,
                   aa.nota_oficial, COALESCE(aa.revisar, FALSE)
            FROM public.aula AS a
            JOIN public.professor AS p ON p.id_professor = a.id_professor
            LEFT JOIN public.aula_aluno AS aa ON aa.id_aula = a.id_aula
            LEFT JOIN public.aluno AS al ON al.id_aluno = aa.id_aluno
            WHERE a.id_aula = %s
              AND (a.id_professor = %s OR aa.id_aluno = %s)
        """, (
            id_aula,
            id_usuario if perfil == 'PROFESSOR' else -1,
            id_usuario if perfil == 'ALUNO' else -1,
        ))
        aula = cursor.fetchone()
        if not aula:
            flash('Aula não encontrada ou sem permissão de acesso.', 'warning')
            return redirect(url_for('listar_aulas'))

        if request.method == 'POST':
            anotacao = request.form.get('anotacao', '').strip()
            if len(anotacao) > 5000:
                raise ValueError('A anotação deve ter no máximo 5.000 caracteres.')
            cursor.execute("""
                INSERT INTO public.aula_anotacao (
                    id_aula, perfil_usuario, id_usuario, anotacao
                )
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (id_aula, perfil_usuario, id_usuario)
                DO UPDATE SET anotacao = EXCLUDED.anotacao,
                              atualizada_em = CURRENT_TIMESTAMP
            """, (id_aula, perfil, id_usuario, anotacao))

            revisar = request.form.get('revisar') == 'on'
            cursor.execute("""
                UPDATE public.aula_aluno AS aa
                SET revisar = %s
                FROM public.aula AS a
                WHERE aa.id_aula = a.id_aula
                  AND a.id_aula = %s
                  AND (a.id_professor = %s OR aa.id_aluno = %s)
            """, (
                revisar,
                id_aula,
                id_usuario if perfil == 'PROFESSOR' else -1,
                id_usuario if perfil == 'ALUNO' else -1,
            ))

            nota = request.form.get('nota', '').strip()
            if nota:
                try:
                    nota = Decimal(nota)
                except InvalidOperation:
                    raise ValueError('Informe uma nota numérica entre 0 e 10.')
                if not nota.is_finite() or not Decimal('0') <= nota <= Decimal('10'):
                    raise ValueError('A nota deve estar entre 0 e 10.')

            if perfil == 'ALUNO':
                cursor.execute("""
                    UPDATE public.aula_aluno
                    SET nota_autoavaliacao = %s
                    WHERE id_aula = %s AND id_aluno = %s
                """, (nota if nota != '' else None, id_aula, id_usuario))
            else:
                cursor.execute("""
                    UPDATE public.aula_aluno
                    SET nota_oficial = %s
                    WHERE id_aula = %s
                """, (nota if nota != '' else None, id_aula))

            conexao.commit()
            flash('Informações da aula salvas.', 'success')
            return redirect(url_for('detalhes_aula', id_aula=id_aula))

        cursor.execute("""
            SELECT anotacao
            FROM public.aula_anotacao
            WHERE id_aula = %s AND perfil_usuario = %s AND id_usuario = %s
        """, (id_aula, perfil, id_usuario))
        anotacao = cursor.fetchone()
        cursor.execute("""
            SELECT m.id_material, m.titulo, m.link_arquivo
            FROM public.aula_material AS am
            JOIN public.material_didatico AS m ON m.id_material = am.id_material
            WHERE am.id_aula = %s
            ORDER BY m.titulo
        """, (id_aula,))
        materiais = cursor.fetchall()
        conexao.commit()
        return render_template(
            'detalhe_aula.html',
            aula=aula,
            anotacao=anotacao[0] if anotacao else '',
            materiais=materiais,
            perfil=perfil,
        )
    except ValueError as erro:
        conexao.rollback()
        flash(str(erro), 'warning')
        return redirect(url_for('detalhes_aula', id_aula=id_aula))
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
    senha_hash = bcrypt.generate_password_hash(SENHA_PADRAO).decode('utf-8')
   
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
    senha_hash = bcrypt.generate_password_hash(SENHA_PADRAO).decode('utf-8')
   
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