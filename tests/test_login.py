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
    def test_login_valido_com_senha_bcrypt_redireciona_para_aulas(self, conectar):
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
        self.assertEqual(resposta.headers['Location'], '/aulas')
        with self.client.session_transaction() as sessao:
            self.assertEqual(sessao['user_id'], 42)
            self.assertEqual(sessao['perfil'], 'ALUNO')
        cursor.close.assert_called_once_with()
        conexao.close.assert_called_once_with()


if __name__ == '__main__':
    unittest.main()
