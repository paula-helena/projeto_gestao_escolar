import io
import unittest
import zipfile
from unittest.mock import Mock, patch

import app


class MateriaisUploadTests(unittest.TestCase):
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
    @patch('app.cliente_armazenamento')
    def test_anexa_pdf_ao_armazenamento_e_salva_chave_no_banco(
        self, criar_cliente, conectar
    ):
        conexao, cursor = self.conexao_mock()
        conectar.return_value = conexao
        armazenamento = Mock()
        criar_cliente.return_value = armazenamento

        resposta = self.client.post('/materiais/novo', data={
            'titulo': 'Apostila',
            'descricao': 'Material em PDF',
            'arquivo': (io.BytesIO(b'%PDF-1.7\nconteudo'), 'apostila.pdf'),
        })

        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(resposta.headers['Location'], '/materiais')
        armazenamento.upload_fileobj.assert_called_once()
        parametros = cursor.execute.call_args.args[1]
        self.assertEqual(parametros[0:3], (4, 'Apostila', 'Material em PDF'))
        self.assertRegex(parametros[3], r'^s3://materiais/[0-9a-f]{32}\.pdf$')
        self.assertEqual(
            armazenamento.upload_fileobj.call_args.kwargs['ExtraArgs']['ContentType'],
            'application/pdf',
        )
        conexao.commit.assert_called_once_with()

    @patch('app.psycopg2.connect')
    @patch('app.cliente_armazenamento')
    def test_aceita_apresentacoes_ppt_e_pptx(
        self, criar_cliente, conectar
    ):
        pptx = io.BytesIO()
        with zipfile.ZipFile(pptx, 'w') as pacote:
            pacote.writestr('[Content_Types].xml', '<Types/>')
            pacote.writestr('ppt/presentation.xml', '<presentation/>')

        arquivos = (
            ('apresentacao.ppt', b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1conteudo'),
            ('apresentacao.pptx', pptx.getvalue()),
        )
        for nome, conteudo in arquivos:
            conexao, _ = self.conexao_mock()
            conectar.return_value = conexao
            resposta = self.client.post('/materiais/novo', data={
                'titulo': 'Apresentação',
                'descricao': 'Slides',
                'arquivo': (io.BytesIO(conteudo), nome),
            })
            self.assertEqual(resposta.status_code, 302)

        self.assertEqual(criar_cliente.return_value.upload_fileobj.call_count, 2)

    @patch('app.psycopg2.connect')
    @patch('app.cliente_armazenamento')
    def test_rejeita_extensao_nao_permitida(self, criar_cliente, conectar):
        resposta = self.client.post(
            '/materiais/novo',
            data={
                'titulo': 'Arquivo',
                'descricao': 'Não permitido',
                'arquivo': (io.BytesIO(b'%PDF-1.7\nconteudo'), 'arquivo.exe'),
            },
            follow_redirects=True,
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertIn('Anexe um arquivo PDF, PPT ou PPTX', resposta.get_data(as_text=True))
        criar_cliente.assert_not_called()
        conectar.assert_not_called()

    @patch('app.psycopg2.connect')
    @patch('app.cliente_armazenamento')
    def test_rejeita_arquivo_com_extensao_pdf_e_conteudo_invalido(
        self, criar_cliente, conectar
    ):
        resposta = self.client.post(
            '/materiais/novo',
            data={
                'titulo': 'Arquivo',
                'descricao': 'PDF inválido',
                'arquivo': (io.BytesIO(b'conteudo invalido'), 'arquivo.pdf'),
            },
            follow_redirects=True,
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertIn('não corresponde à extensão', resposta.get_data(as_text=True))
        criar_cliente.assert_not_called()
        conectar.assert_not_called()

    @patch('app.cliente_armazenamento')
    def test_rejeita_arquivo_acima_do_limite(self, criar_cliente):
        with patch.object(app, 'LIMITE_ARQUIVO_BYTES', 8):
            resposta = self.client.post(
                '/materiais/novo',
                data={
                    'titulo': 'Arquivo',
                    'descricao': 'Maior que o limite',
                    'arquivo': (io.BytesIO(b'%PDF-1.7 conteudo'), 'arquivo.pdf'),
                },
                follow_redirects=True,
            )

        self.assertEqual(resposta.status_code, 200)
        self.assertIn('no máximo 25 MB', resposta.get_data(as_text=True))
        criar_cliente.assert_not_called()

    @patch('app.psycopg2.connect')
    @patch('app.cliente_armazenamento')
    def test_aceita_link_externo_https_sem_usar_s3(self, criar_cliente, conectar):
        conexao, cursor = self.conexao_mock()
        conectar.return_value = conexao

        resposta = self.client.post('/materiais/novo', data={
            'titulo': 'Material externo',
            'descricao': 'Link externo',
            'link_arquivo': 'https://exemplo.com/material.pdf',
        })

        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(cursor.execute.call_args.args[1][3], 'https://exemplo.com/material.pdf')
        criar_cliente.assert_not_called()

    @patch('app.psycopg2.connect')
    @patch('app.cliente_armazenamento')
    def test_gera_url_assinada_para_arquivo_s3(self, criar_cliente, conectar):
        conexao, _ = self.conexao_mock('s3://materiais/arquivo.pdf')
        conectar.return_value = conexao
        armazenamento = Mock()
        armazenamento.generate_presigned_url.return_value = (
            'https://bucket.example/arquivo.pdf?assinatura=temporaria'
        )
        criar_cliente.return_value = armazenamento

        resposta = self.client.get('/materiais/7/arquivo')

        self.assertEqual(resposta.status_code, 302)
        self.assertIn('assinatura=temporaria', resposta.headers['Location'])
        self.assertEqual(
            armazenamento.generate_presigned_url.call_args.kwargs['ExpiresIn'],
            600,
        )

    @patch('app.psycopg2.connect')
    def test_abre_link_externo_https(self, conectar):
        conexao, _ = self.conexao_mock('https://exemplo.com/material.pdf')
        conectar.return_value = conexao

        resposta = self.client.get('/materiais/7/arquivo')

        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(resposta.headers['Location'], 'https://exemplo.com/material.pdf')

    @patch('app.psycopg2.connect')
    def test_rejeita_link_externo_com_esquema_nao_http(self, conectar):
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
