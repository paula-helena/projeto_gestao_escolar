import unittest
from datetime import date, datetime, time
from decimal import Decimal
from unittest.mock import patch

import app
from app import (
    adicionar_meses,
    data_fim_recorrencia,
    expandir_recorrencias,
    validar_horario_aula,
)


class AgendamentoTests(unittest.TestCase):
    def test_adicionar_meses_preserva_o_dia_quando_existe(self):
        self.assertEqual(adicionar_meses(date(2026, 1, 15), 1), date(2026, 2, 15))

    def test_adicionar_meses_ajusta_ao_fim_do_mes(self):
        self.assertEqual(adicionar_meses(date(2026, 1, 31), 1), date(2026, 2, 28))

    def test_fim_de_recorrencia_usa_periodos_de_calendario(self):
        inicio = date(2026, 11, 18)
        self.assertEqual(data_fim_recorrencia(inicio, 'mes'), date(2026, 12, 18))
        self.assertEqual(data_fim_recorrencia(inicio, 'trimestre'), date(2027, 2, 18))
        self.assertEqual(data_fim_recorrencia(inicio, 'semestre'), date(2027, 5, 18))
        self.assertEqual(data_fim_recorrencia(inicio, 'ano'), date(2027, 11, 18))
        self.assertIsNone(data_fim_recorrencia(inicio, 'sempre'))

    def test_validar_data_hora_local(self):
        self.assertEqual(
            validar_horario_aula('2026-11-02T20:00'),
            datetime(2026, 11, 2, 20, 0),
        )
        with self.assertRaises(ValueError):
            validar_horario_aula('data-invalida')

    def test_expansao_cria_somente_os_dias_selecionados(self):
        class CursorFake:
            def __init__(self):
                self.ultima_consulta = ''
                self.inseridos = []
                self.atualizacao = None
                self.proximo_id = 1

            def execute(self, consulta, parametros=None):
                self.ultima_consulta = consulta
                if 'INSERT INTO public.aula (' in consulta:
                    self.inseridos.append(parametros[2])
                    self.proximo_id += 1
                if 'UPDATE public.aula_recorrencia' in consulta:
                    self.atualizacao = parametros

            def fetchall(self):
                if 'FROM public.aula_recorrencia' in self.ultima_consulta:
                    return [(
                        10, 4, 8, 'Conversação', date(2026, 11, 2),
                        time(20, 0), [1, 3], None, date(2026, 11, 1),
                    )]
                return []

            def fetchone(self):
                if 'INSERT INTO public.aula (' in self.ultima_consulta:
                    return (self.proximo_id - 1,)
                return None

        cursor = CursorFake()
        expandir_recorrencias(
            cursor, 'PROFESSOR', 4, date(2026, 11, 8)
        )
        self.assertEqual(
            cursor.inseridos,
            [datetime(2026, 11, 2, 20), datetime(2026, 11, 4, 20)],
        )
        self.assertEqual(
            cursor.ultima_consulta.strip().splitlines()[0],
            'UPDATE public.aula_recorrencia',
        )
        self.assertEqual(cursor.atualizacao, (date(2026, 11, 8), 10))


class FakeCursor:
    def __init__(self):
        self.queries = []
        self.query = ''
        self.params = None
        self.result_one = None
        self.result_all = []
        self.rowcount = 1
        self.recorrencia = None
        self.next_aula_id = 100

    def execute(self, query, params=None):
        self.query = query
        self.params = params
        self.queries.append((query, params))
        self.result_one = None
        self.result_all = []
        sql = ' '.join(query.split())

        if 'SELECT id_aluno, nome FROM public.aluno' in sql:
            self.result_all = [(7, 'Aluno Teste')]
        elif 'SELECT id_material, titulo' in sql:
            self.result_all = []
        elif 'SELECT id_tema, titulo' in sql:
            self.result_all = []
        elif 'SELECT 1 FROM public.aluno' in sql:
            self.result_one = (1,)
        elif 'SELECT a.tema, aa.id_aluno' in sql:
            self.result_one = ('Conversação', 7)
        elif 'UPDATE public.aula AS a' in sql and "SET status = 'REAGENDADA'" in sql:
            self.rowcount = 1
        elif 'INSERT INTO public.aula_recorrencia (' in sql:
            self.recorrencia = params
            self.result_one = (44,)
        elif 'SELECT id_recorrencia, id_professor' in sql:
            if self.recorrencia:
                params = self.recorrencia
                self.result_all = [(
                    44, params[0], params[1], params[2], params[3], params[4],
                    params[5], params[6], params[7],
                )]
        elif 'RETURNING id_aula' in sql:
            self.next_aula_id += 1
            self.result_one = (self.next_aula_id,)
        elif 'SELECT timezone(' in sql:
            if '::date' in sql:
                self.result_one = (date(2026, 11, 2),)
            else:
                self.result_one = (datetime(2026, 11, 2, 20),)
        elif 'SELECT a.id_aula, a.data_hora, a.tema, a.status, p.nome' in sql:
            self.result_one = (
                55, datetime(2026, 11, 2, 20), None, 'AGENDADA',
                'Professor Teste', 'Aluno Teste', Decimal('8'), Decimal('9'), True,
            )
        elif 'SELECT a.id_aula, a.data_hora, a.tema, a.status' in sql:
            self.result_all = []
        elif 'SELECT anotacao FROM public.aula_anotacao' in sql:
            self.result_one = ('anotação privada de teste',)
        elif 'SELECT m.id_material, m.titulo, m.link_arquivo' in sql:
            self.result_all = []

    def fetchone(self):
        return self.result_one

    def fetchall(self):
        return self.result_all

    def close(self):
        pass


class FakeConnection:
    def __init__(self):
        self.fake_cursor = FakeCursor()
        self.committed = False

    def cursor(self):
        return self.fake_cursor

    def commit(self):
        self.committed = True

    def rollback(self):
        pass

    def close(self):
        pass


class AgendaRouteTests(unittest.TestCase):
    def setUp(self):
        app.app.config['TESTING'] = True
        self.client = app.app.test_client()
        with self.client.session_transaction() as state:
            state.update(user_id=4, perfil='PROFESSOR', nome='Professor Teste')

    def test_formulario_oferece_tema_opcional_e_recorrencia(self):
        conexao = FakeConnection()
        with patch.object(app.psycopg2, 'connect', return_value=conexao):
            resposta = self.client.get('/aulas/nova')
        self.assertEqual(resposta.status_code, 200)
        pagina = resposta.get_data(as_text=True)
        self.assertIn('Tema da aula (opcional)', pagina)
        self.assertIn('Aula recorrente semanal', pagina)
        self.assertIn('Para sempre', pagina)

    def test_aula_avulsa_sem_tema_pode_ser_agendada(self):
        conexao = FakeConnection()
        with patch.object(app.psycopg2, 'connect', return_value=conexao):
            resposta = self.client.post('/aulas/nova', data={
                'modo': 'avulsa',
                'id_aluno': '7',
                'tema': '',
                'data_hora': '2026-11-03T20:00',
            })
        self.assertEqual(resposta.status_code, 302)
        self.assertTrue(conexao.committed)
        insercao = next(
            (query, params) for query, params in conexao.fake_cursor.queries
            if 'INSERT INTO public.aula (' in query
        )
        self.assertIsNone(insercao[1][1])

    def test_aula_recorrente_gera_ocorrencias_nos_dias_selecionados(self):
        conexao = FakeConnection()
        with patch.object(app.psycopg2, 'connect', return_value=conexao):
            resposta = self.client.post('/aulas/nova', data={
                'modo': 'recorrente',
                'id_aluno': '7',
                'tema': '',
                'data_hora': '2026-11-02T20:00',
                'dias_semana': ['1', '3'],
                'duracao': 'mes',
            })
        self.assertEqual(resposta.status_code, 302)
        self.assertTrue(conexao.committed)
        aulas = [
            parametros[2] for query, parametros in conexao.fake_cursor.queries
            if 'INSERT INTO public.aula (' in query
        ]
        self.assertGreater(len(aulas), 0)
        self.assertTrue(all(aula.weekday() in (0, 2) for aula in aulas))
        self.assertTrue(all(aula.time() == time(20, 0) for aula in aulas))

    def test_reposicao_e_avulsa_e_vinculada_a_aula_de_origem(self):
        conexao = FakeConnection()
        with patch.object(app.psycopg2, 'connect', return_value=conexao):
            resposta = self.client.post('/aulas/nova', data={
                'modo': 'recorrente',
                'reposicao_de': '55',
                'id_aluno': '7',
                'tema': '',
                'data_hora': '2026-11-03T20:00',
                'dias_semana': ['1', '3'],
                'duracao': 'ano',
            })
        self.assertEqual(resposta.status_code, 302)
        insercoes_aula = [
            parametros for query, parametros in conexao.fake_cursor.queries
            if 'INSERT INTO public.aula (' in query
        ]
        self.assertEqual(len(insercoes_aula), 1)
        self.assertEqual(insercoes_aula[0][-1], 55)
        self.assertFalse(any(
            'INSERT INTO public.aula_recorrencia' in query
            for query, _ in conexao.fake_cursor.queries
        ))

    def test_acao_reagendar_abre_formulario_de_reposicao(self):
        conexao = FakeConnection()
        with patch.object(app.psycopg2, 'connect', return_value=conexao):
            resposta = self.client.post('/aulas/55/reagendar')
        self.assertEqual(resposta.status_code, 302)
        self.assertIn('/aulas/nova?reposicao_de=55', resposta.location)
        self.assertTrue(conexao.committed)

    def test_agenda_exibe_filtros_de_periodo(self):
        conexao = FakeConnection()
        with patch.object(app.psycopg2, 'connect', return_value=conexao):
            resposta = self.client.get('/aulas?periodo=trimestre&ordenacao=status&direcao=desc')
        self.assertEqual(resposta.status_code, 200)
        pagina = resposta.get_data(as_text=True)
        self.assertIn('Aulas do trimestre', pagina)
        self.assertIn('Decrescente', pagina)
        consulta_agenda = next(
            query for query, _ in conexao.fake_cursor.queries
            if 'SELECT a.id_aula, a.data_hora, a.tema, a.status' in query
        )
        self.assertIn('ORDER BY CASE a.status', consulta_agenda)
        self.assertIn(' desc,', consulta_agenda.lower())
        self.assertEqual(
            next(
                parametros for query, parametros in conexao.fake_cursor.queries
                if 'SELECT a.id_aula, a.data_hora, a.tema, a.status' in query
            ),
            [4, date(2026, 10, 1), date(2027, 1, 1)],
        )
        consulta_status, parametros_status = next(
            (query, parametros)
            for query, parametros in conexao.fake_cursor.queries
            if "SET status = 'CONCLUIDA'" in query
        )
        self.assertIn('WHERE status =', consulta_status)
        self.assertEqual(parametros_status, (datetime(2026, 11, 2, 20),))

    def test_detalhes_exibem_nota_compartilhada_e_anotacao_do_usuario(self):
        conexao = FakeConnection()
        with patch.object(app.psycopg2, 'connect', return_value=conexao):
            resposta = self.client.get('/aulas/55/mais')
        self.assertEqual(resposta.status_code, 200)
        pagina = resposta.get_data(as_text=True)
        self.assertIn('anotação privada de teste', pagina)
        self.assertIn('Autoavaliação do aluno', pagina)
        self.assertIn('Nota do professor', pagina)

    def test_anotacao_privada_e_consultada_por_perfil_e_usuario(self):
        conexao = FakeConnection()
        with self.client.session_transaction() as state:
            state.update(user_id=8, perfil='ALUNO', nome='Aluno Teste')
        with patch.object(app.psycopg2, 'connect', return_value=conexao):
            resposta = self.client.get('/aulas/55/mais')
        self.assertEqual(resposta.status_code, 200)
        parametros = next(
            parametros for query, parametros in conexao.fake_cursor.queries
            if 'SELECT anotacao FROM public.aula_anotacao' in ' '.join(query.split())
        )
        self.assertEqual(parametros, (55, 'ALUNO', 8))

    def test_aluno_salva_autoavaliacao_e_anotacao_privada(self):
        conexao = FakeConnection()
        with self.client.session_transaction() as state:
            state.update(user_id=8, perfil='ALUNO', nome='Aluno Teste')
        with patch.object(app.psycopg2, 'connect', return_value=conexao):
            resposta = self.client.post('/aulas/55/mais', data={
                'anotacao': 'Minha nota privada',
                'nota': '9.5',
                'revisar': 'on',
            })
        self.assertEqual(resposta.status_code, 302)
        self.assertTrue(conexao.committed)
        nota = next(
            parametros for query, parametros in conexao.fake_cursor.queries
            if 'SET nota_autoavaliacao' in query
        )
        self.assertEqual(nota, (Decimal('9.5'), 55, 8))
        self.assertFalse(any(
            'SET nota_oficial' in query for query, _ in conexao.fake_cursor.queries
        ))


if __name__ == '__main__':
    unittest.main()
