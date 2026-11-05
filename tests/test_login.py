import unittest
from unittest.mock import Mock, patch

import app


class LoginTests(unittest.TestCase):
    def setUp(self):
        app.app.config['TESTING'] = True
        self.client = app.app.test_client()

    def tearDown(self):
        app.app.config['TESTING'] = False

    @patch(
        'app.psycopg2.connect',
        side_effect=app.psycopg2.OperationalError('database unavailable'),
    )
    def test_falha_de_conexao_mostra_mensagem_sem_retornar_500(self, conectar):
        resposta = self.client.post(
            '/login',
            data={
                'perfil': 'ALUNO',
                'email': 'aluno@example.com',
                'senha': 'senha-de-teste',
            },
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertIn(
            'Não foi possível acessar o sistema',
            resposta.get_data(as_text=True),
        )
        self.assertNotIn('database unavailable', resposta.get_data(as_text=True))
        conectar.assert_called_once_with(app.DATABASE_URL)

    @patch('app.psycopg2.connect')
    def test_login_valido_de_aluno_redireciona_para_home_aluno(self, conectar):
        cursor = Mock()
        cursor.fetchone.return_value = (
            42,
            'Aluno Teste',
            'aluno@example.com',
            app.bcrypt.generate_password_hash('senha-de-teste').decode('utf-8'),
        )
        conexao = Mock()
        conexao.cursor.return_value = cursor
        conectar.return_value = conexao

        resposta = self.client.post(
            '/login',
            data={
                'perfil': 'ALUNO',
                'email': 'aluno@example.com',
                'senha': 'senha-de-teste',
            },
        )

        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(resposta.headers['Location'], '/home-aluno')
        with self.client.session_transaction() as sessao:
            self.assertEqual(sessao['user_id'], 42)
            self.assertEqual(sessao['perfil'], 'ALUNO')
        cursor.close.assert_called_once_with()
        conexao.close.assert_called_once_with()

    @patch('app.psycopg2.connect')
    def test_login_valido_de_professor_redireciona_para_home_professor(
        self, conectar
    ):
        cursor = Mock()
        cursor.fetchone.return_value = (
            7,
            'Professor Teste',
            'professor@example.com',
            app.bcrypt.generate_password_hash('senha-de-teste').decode('utf-8'),
            False,
        )
        conexao = Mock()
        conexao.cursor.return_value = cursor
        conectar.return_value = conexao

        resposta = self.client.post(
            '/login',
            data={
                'perfil': 'PROFESSOR',
                'email': 'professor@example.com',
                'senha': 'senha-de-teste',
            },
        )

        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(resposta.headers['Location'], '/home-professor')
        with self.client.session_transaction() as sessao:
            self.assertEqual(sessao['user_id'], 7)
            self.assertEqual(sessao['perfil'], 'PROFESSOR')
            self.assertFalse(sessao['is_admin'])

    @patch('app.psycopg2.connect')
    def test_login_de_professor_administrador_salva_permissao_na_sessao(
        self, conectar
    ):
        cursor = Mock()
        cursor.fetchone.return_value = (
            7,
            'Professora Administradora',
            'phfe1997@gmail.com',
            app.bcrypt.generate_password_hash('senha-de-teste').decode('utf-8'),
            True,
        )
        conexao = Mock()
        conexao.cursor.return_value = cursor
        conectar.return_value = conexao

        resposta = self.client.post(
            '/login',
            data={
                'perfil': 'PROFESSOR',
                'email': 'phfe1997@gmail.com',
                'senha': 'senha-de-teste',
            },
        )

        self.assertEqual(resposta.status_code, 302)
        with self.client.session_transaction() as sessao:
            self.assertTrue(sessao['is_admin'])

    @patch('app.psycopg2.connect')
    def test_login_valido_remove_aviso_de_credenciais_incorretas_antigo(
        self, conectar
    ):
        cursor = Mock()
        cursor.fetchone.return_value = (
            42,
            'Aluno Teste',
            'aluno@example.com',
            app.bcrypt.generate_password_hash('senha-de-teste').decode('utf-8'),
        )
        conexao = Mock()
        conexao.cursor.return_value = cursor
        conectar.return_value = conexao

        with self.client.session_transaction() as sessao:
            sessao['_flashes'] = [
                ('danger', 'E-mail ou senha incorretos. Tente novamente.')
            ]

        resposta = self.client.post(
            '/login',
            data={
                'perfil': 'ALUNO',
                'email': 'aluno@example.com',
                'senha': 'senha-de-teste',
            },
            follow_redirects=True,
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertNotIn(
            'E-mail ou senha incorretos',
            resposta.get_data(as_text=True),
        )
        self.assertIn('Bem-vindo(a), Aluno Teste!', resposta.get_data(as_text=True))

    def test_usuario_logado_que_abre_login_volta_para_sua_home(self):
        with self.client.session_transaction() as sessao:
            sessao['user_id'] = 7
            sessao['perfil'] = 'PROFESSOR'

        resposta = self.client.get('/login')

        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(resposta.headers['Location'], '/home-professor')


if __name__ == '__main__':
    unittest.main()
