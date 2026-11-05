import unittest
from unittest.mock import Mock, patch

import app


class MateriaisLinkTests(unittest.TestCase):
    def setUp(self):
        app.app.config['TESTING'] = True
        self.client = app.app.test_client()
        with self.client.session_transaction() as sessao:
            sessao.update(user_id=4, perfil='PROFESSOR', nome='Professor Teste')

    def tearDown(self):
        app.app.config['TESTING'] = False

    @staticmethod
    def conexao_mock(link=None):
        cursor = Mock()
        cursor.fetchone.return_value = (link,) if link is not None else None
        conexao = Mock()
        conexao.cursor.return_value = cursor
        return conexao, cursor

    @patch('app.psycopg2.connect')
    def test_cadastra_link_de_pasta_do_google_drive(self, conectar):
        conexao, cursor = self.conexao_mock()
        conectar.return_value = conexao

        resposta = self.client.post('/materiais/novo', data={
            'titulo': 'Apostila',
            'descricao': 'Materiais da turma',
            'link_arquivo': 'https://drive.google.com/drive/folders/abc123?usp=sharing',
        })

        self.assertEqual(resposta.status_code, 302)
        parametros = cursor.execute.call_args.args[1]
        self.assertEqual(parametros, (
            4,
            'Apostila',
            'Materiais da turma',
            'https://drive.google.com/drive/folders/abc123?usp=sharing',
        ))
        conexao.commit.assert_called_once_with()

    @patch('app.psycopg2.connect')
    def test_rejeita_link_que_nao_e_pasta_do_google_drive(self, conectar):
        resposta = self.client.post(
            '/materiais/novo',
            data={
                'titulo': 'Apostila',
                'descricao': 'Link externo',
                'link_arquivo': 'https://drive.google.com/file/d/abc123/view',
            },
            follow_redirects=True,
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertIn('pasta do Google Drive', resposta.get_data(as_text=True))
        conectar.assert_not_called()

    @patch('app.psycopg2.connect')
    def test_rejeita_link_com_dominio_nao_confiavel(self, conectar):
        resposta = self.client.post(
            '/materiais/novo',
            data={
                'titulo': 'Apostila',
                'descricao': 'Link falso',
                'link_arquivo': 'https://drive.google.com.example.org/drive/folders/abc123',
            },
            follow_redirects=True,
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertIn('pasta do Google Drive', resposta.get_data(as_text=True))
        conectar.assert_not_called()

    @patch('app.psycopg2.connect')
    def test_abre_link_do_material(self, conectar):
        conexao, _ = self.conexao_mock(
            'https://drive.google.com/drive/folders/abc123'
        )
        conectar.return_value = conexao

        resposta = self.client.get('/materiais/7/arquivo')

        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(
            resposta.headers['Location'],
            'https://drive.google.com/drive/folders/abc123',
        )

    @patch('app.psycopg2.connect')
    def test_rejeita_link_salvo_com_esquema_nao_http(self, conectar):
        conexao, _ = self.conexao_mock('javascript:alert(1)')
        conectar.return_value = conexao

        resposta = self.client.get('/materiais/7/arquivo')

        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(resposta.headers['Location'], '/materiais')

    def test_agendamento_de_temas_pre_cadastrados_foi_removido(self):
        with patch('app.psycopg2.connect') as conectar:
            resposta = self.client.get('/temas')

        self.assertEqual(resposta.status_code, 404)
        conectar.assert_not_called()


if __name__ == '__main__':
    unittest.main()
