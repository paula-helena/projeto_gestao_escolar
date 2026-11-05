import unittest
from unittest.mock import Mock, patch

import app


class NavegacaoESenhaTests(unittest.TestCase):
    def setUp(self):
        app.app.config['TESTING'] = True
        self.client = app.app.test_client()

    def tearDown(self):
        app.app.config['TESTING'] = False

    def autenticar(self, perfil):
        with self.client.session_transaction() as sessao:
            sessao.update(
                user_id=4,
                perfil=perfil,
                nome='Usuário Teste',
            )

    def test_barra_do_professor_tem_home_novo_cadastro_e_menu(self):
        self.autenticar('PROFESSOR')
        resposta = self.client.get('/home-professor')
        pagina = resposta.get_data(as_text=True)

        self.assertEqual(resposta.status_code, 200)
        self.assertIn('href="/home-professor">', pagina)
        self.assertIn('Novo Cadastro', pagina)
        self.assertIn('aria-label="Abrir opções de navegação"', pagina)
        self.assertIn('Gerenciar alunos', pagina)
        self.assertIn('Gerenciar professores', pagina)
        self.assertIn('Mudar senha', pagina)
        self.assertIn('Agendar nova aula', pagina)
        self.assertIn('Adicionar material', pagina)

    def test_barra_e_home_do_aluno_mostram_apenas_rotas_de_aluno(self):
        self.autenticar('ALUNO')
        resposta = self.client.get('/home-aluno')
        pagina = resposta.get_data(as_text=True)

        self.assertEqual(resposta.status_code, 200)
        self.assertIn('href="/home-aluno">', pagina)
        self.assertNotIn('Novo Cadastro', pagina)
        self.assertIn('Minhas aulas', pagina)
        self.assertIn('Materiais das minhas aulas', pagina)
        self.assertIn('Mudar senha', pagina)
        self.assertNotIn('Gerenciar alunos', pagina)
        self.assertNotIn('Agendar nova aula', pagina)

    @patch('app.psycopg2.connect')
    def test_aluno_visualiza_somente_materiais_vinculados_as_suas_aulas(self, conectar):
        self.autenticar('ALUNO')
        cursor = Mock()
        cursor.fetchall.return_value = []
        conexao = Mock()
        conexao.cursor.return_value = cursor
        conectar.return_value = conexao

        resposta = self.client.get('/materiais')

        self.assertEqual(resposta.status_code, 200)
        consulta, parametros = cursor.execute.call_args.args
        self.assertIn('JOIN public.aula_material', consulta)
        self.assertIn('JOIN public.aula_aluno', consulta)
        self.assertIn('WHERE aa.id_aluno = %s', consulta)
        self.assertEqual(parametros, (4,))

    @patch('app.psycopg2.connect')
    def test_aluno_nao_abre_material_nao_vinculado_a_suas_aulas(self, conectar):
        self.autenticar('ALUNO')
        cursor = Mock()
        cursor.fetchone.return_value = None
        conexao = Mock()
        conexao.cursor.return_value = cursor
        conectar.return_value = conexao

        resposta = self.client.get('/materiais/23/arquivo')

        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(resposta.location, '/materiais')
        consulta, parametros = cursor.execute.call_args.args
        self.assertIn('JOIN public.aula_aluno', consulta)
        self.assertEqual(parametros, (23, 4))

    def test_professor_pode_mudar_sua_senha(self):
        self.autenticar('PROFESSOR')
        cursor = Mock()
        cursor.fetchone.return_value = ('$2b$hash-atual',)
        conexao = Mock()
        conexao.cursor.return_value = cursor
        with (
            patch('app.psycopg2.connect', return_value=conexao),
            patch.object(app.bcrypt, 'check_password_hash', return_value=True),
            patch.object(app.bcrypt, 'generate_password_hash', return_value=b'$2b$hash-novo'),
        ):
            resposta = self.client.post('/alterar-senha', data={
                'senha_atual': 'senha-antiga',
                'nova_senha': 'senha-nova-123',
                'confirmacao': 'senha-nova-123',
            })

        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(resposta.location, '/home-professor')
        consulta_update, parametros = cursor.execute.call_args_list[-1].args
        self.assertIn('UPDATE public.professor SET senha', consulta_update)
        self.assertEqual(parametros, ('$2b$hash-novo', 4))
        conexao.commit.assert_called_once_with()

    def test_aluno_pode_mudar_sua_senha(self):
        self.autenticar('ALUNO')
        cursor = Mock()
        cursor.fetchone.return_value = ('$2b$hash-atual',)
        conexao = Mock()
        conexao.cursor.return_value = cursor
        with (
            patch('app.psycopg2.connect', return_value=conexao),
            patch.object(app.bcrypt, 'check_password_hash', return_value=True),
            patch.object(app.bcrypt, 'generate_password_hash', return_value=b'$2b$hash-novo'),
        ):
            resposta = self.client.post('/alterar-senha', data={
                'senha_atual': 'senha-antiga',
                'nova_senha': 'senha-nova-123',
                'confirmacao': 'senha-nova-123',
            })

        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(resposta.location, '/home-aluno')
        consulta_update, parametros = cursor.execute.call_args_list[-1].args
        self.assertIn('UPDATE public.aluno SET senha', consulta_update)
        self.assertEqual(parametros, ('$2b$hash-novo', 4))

    def test_senha_atual_incorreta_nao_atualiza_cadastro(self):
        self.autenticar('ALUNO')
        cursor = Mock()
        cursor.fetchone.return_value = ('$2b$hash-atual',)
        conexao = Mock()
        conexao.cursor.return_value = cursor
        with (
            patch('app.psycopg2.connect', return_value=conexao),
            patch.object(app.bcrypt, 'check_password_hash', return_value=False),
        ):
            resposta = self.client.post(
                '/alterar-senha',
                data={
                    'senha_atual': 'senha-errada',
                    'nova_senha': 'senha-nova-123',
                    'confirmacao': 'senha-nova-123',
                },
                follow_redirects=True,
            )

        self.assertEqual(resposta.status_code, 200)
        self.assertIn('senha atual está incorreta', resposta.get_data(as_text=True))
        self.assertFalse(any(
            'UPDATE ' in chamada.args[0]
            for chamada in cursor.execute.call_args_list
        ))
        conexao.commit.assert_not_called()

    def test_novo_cadastro_do_professor_abre_selecao_de_perfil(self):
        self.autenticar('PROFESSOR')
        resposta = self.client.get('/cadastro')

        self.assertEqual(resposta.status_code, 200)
        self.assertIn('Cadastrar Professor', resposta.get_data(as_text=True))
        self.assertIn('Cadastrar Aluno', resposta.get_data(as_text=True))

    def test_cadastro_de_aluno_tem_rota_direta(self):
        resposta = self.client.get('/cadastro-aluno')

        self.assertEqual(resposta.status_code, 200)
        self.assertIn('Cadastro de Aluno', resposta.get_data(as_text=True))

    def test_aluno_logado_nao_acessa_tela_de_novo_cadastro(self):
        self.autenticar('ALUNO')
        resposta = self.client.get('/cadastro-aluno')

        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(resposta.location, '/home-aluno')


if __name__ == '__main__':
    unittest.main()
