import hashlib
import unittest
from unittest.mock import Mock, patch

import app


class RecuperacaoSenhaTests(unittest.TestCase):
    def setUp(self):
        app.app.config['TESTING'] = True
        self.client = app.app.test_client()

    def tearDown(self):
        app.app.config['TESTING'] = False

    @staticmethod
    def conexao_mock(registro=None):
        cursor = Mock()
        cursor.fetchone.return_value = registro
        cursor.rowcount = 1
        conexao = Mock()
        conexao.cursor.return_value = cursor
        return conexao, cursor

    @patch('app.psycopg2.connect')
    def test_novo_aluno_recebe_senha_padrao_independente_do_json(self, conectar):
        conexao, cursor = self.conexao_mock((19, 'Aluno Novo'))
        conectar.return_value = conexao

        resposta = self.client.post('/api/alunos', json={
            'nome': 'Aluno Novo',
            'email': 'aluno@example.com',
            'senha': 'senha-fornecida-pelo-cliente',
            'cep': '01001000',
            'logradouro': 'Praça da Sé',
            'bairro': 'Sé',
            'cidade': 'São Paulo',
            'uf': 'SP',
            'numero': '1',
        })

        self.assertEqual(resposta.status_code, 201)
        parametros = cursor.execute.call_args.args[1]
        self.assertTrue(app.bcrypt.check_password_hash(parametros[2], 'mrdave'))
        self.assertFalse(
            app.bcrypt.check_password_hash(
                parametros[2], 'senha-fornecida-pelo-cliente'
            )
        )

    @patch('app.psycopg2.connect')
    def test_novo_professor_recebe_senha_padrao(self, conectar):
        conexao, cursor = self.conexao_mock((23, 'Professor Novo'))
        conectar.return_value = conexao
        with self.client.session_transaction() as sessao:
            sessao.update(user_id=1, perfil='PROFESSOR')

        resposta = self.client.post('/api/professores', json={
            'nome': 'Professor Novo',
            'email': 'professor@example.com',
            'disciplina': 'Inglês',
            'cep': '01001000',
            'logradouro': 'Praça da Sé',
            'bairro': 'Sé',
            'cidade': 'São Paulo',
            'uf': 'SP',
            'numero': '1',
        })

        self.assertEqual(resposta.status_code, 201)
        parametros = cursor.execute.call_args.args[1]
        self.assertTrue(app.bcrypt.check_password_hash(parametros[2], 'mrdave'))

    @patch('app.enviar_email_redefinicao')
    @patch('app.psycopg2.connect')
    def test_solicitacao_envia_link_temporario_para_conta_existente(
        self, conectar, enviar_email
    ):
        conexao, cursor = self.conexao_mock((42,))
        conectar.return_value = conexao

        with patch.dict(app.app.config, {
            'SMTP_SERVER': 'smtp.example.com',
            'SMTP_FROM_EMAIL': 'noreply@example.com',
            'PUBLIC_BASE_URL': 'https://app.example.com',
        }):
            resposta = self.client.post('/esqueci-senha', data={
                'perfil': 'ALUNO',
                'email': 'aluno@example.com',
            })

        self.assertEqual(resposta.status_code, 200)
        self.assertIn(
            'você receberá um link',
            resposta.get_data(as_text=True),
        )
        enviar_email.assert_called_once()
        self.assertEqual(enviar_email.call_args.args[0], 'aluno@example.com')
        link = enviar_email.call_args.args[1]
        self.assertTrue(link.startswith('https://app.example.com/redefinir-senha/'))
        token = link.rsplit('/', 1)[1]
        insercao = next(
            chamada for chamada in cursor.execute.call_args_list
            if 'INSERT INTO public.redefinicao_senha' in chamada.args[0]
        )
        self.assertEqual(
            insercao.args[1][2],
            hashlib.sha256(token.encode('utf-8')).hexdigest(),
        )

    @patch('app.psycopg2.connect')
    def test_email_nao_cadastrado_recebe_mensagem_generica(self, conectar):
        conexao, _ = self.conexao_mock(None)
        conectar.return_value = conexao

        with patch.dict(app.app.config, {
            'SMTP_SERVER': 'smtp.example.com',
            'SMTP_FROM_EMAIL': 'noreply@example.com',
            'PUBLIC_BASE_URL': 'https://app.example.com',
        }), patch('app.enviar_email_redefinicao') as enviar_email:
            resposta = self.client.post('/esqueci-senha', data={
                'perfil': 'ALUNO',
                'email': 'desconhecido@example.com',
            })

        self.assertEqual(resposta.status_code, 200)
        self.assertIn(
            'você receberá um link',
            resposta.get_data(as_text=True),
        )
        enviar_email.assert_not_called()

    def test_smtp_nao_configurado_nao_tenta_enviar_email(self):
        with patch.dict(app.app.config, {
            'SMTP_SERVER': None,
            'SMTP_FROM_EMAIL': None,
        }), patch('app.psycopg2.connect') as conectar:
            resposta = self.client.post('/esqueci-senha', data={
                'perfil': 'ALUNO',
                'email': 'aluno@example.com',
            })

        self.assertEqual(resposta.status_code, 200)
        self.assertIn('temporariamente indisponível', resposta.get_data(as_text=True))
        conectar.assert_not_called()

    @patch('app.psycopg2.connect')
    def test_token_valido_atualiza_senha_e_invalida_tokens_da_conta(self, conectar):
        conexao, cursor = self.conexao_mock(('ALUNO', 42))
        conectar.return_value = conexao

        resposta = self.client.post(
            '/redefinir-senha/token-de-teste',
            data={'senha': 'nova-senha-segura', 'confirmacao': 'nova-senha-segura'},
        )

        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(resposta.headers['Location'], '/login')
        atualizacao = next(
            chamada for chamada in cursor.execute.call_args_list
            if 'UPDATE public.aluno SET senha' in chamada.args[0]
        )
        self.assertTrue(
            app.bcrypt.check_password_hash(
                atualizacao.args[1][0], 'nova-senha-segura'
            )
        )
        self.assertEqual(atualizacao.args[1][1], 42)
        cursor.execute.assert_any_call(
            unittest.mock.ANY,
            ('ALUNO', 42),
        )
        self.assertTrue(conexao.commit.called)

    @patch('app.psycopg2.connect')
    def test_token_invalido_nao_altera_senha(self, conectar):
        conexao, cursor = self.conexao_mock(None)
        conectar.return_value = conexao

        resposta = self.client.post(
            '/redefinir-senha/token-expirado',
            data={'senha': 'nova-senha-segura', 'confirmacao': 'nova-senha-segura'},
        )

        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(resposta.headers['Location'], '/esqueci-senha')
        self.assertFalse(any(
            'UPDATE public.' in chamada.args[0]
            for chamada in cursor.execute.call_args_list
        ))

    def test_senha_curta_nao_inicia_transacao(self):
        with patch('app.psycopg2.connect') as conectar:
            resposta = self.client.post(
                '/redefinir-senha/token-de-teste',
                data={'senha': 'curta', 'confirmacao': 'curta'},
            )

        self.assertEqual(resposta.status_code, 200)
        self.assertIn('pelo menos 8 caracteres', resposta.get_data(as_text=True))
        conectar.assert_not_called()

    def test_link_fazer_login_nao_aparece_para_professor_logado(self):
        with self.client.session_transaction() as sessao:
            sessao.update(user_id=1, perfil='PROFESSOR')

        resposta = self.client.get('/cadastro')

        self.assertEqual(resposta.status_code, 200)
        self.assertNotIn('Faça Login', resposta.get_data(as_text=True))


if __name__ == '__main__':
    unittest.main()
