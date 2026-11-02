from flask import Flask
from flask_bcrypt import Bcrypt

app = Flask(__name__)
bcrypt = Bcrypt(app)

# Substitua 'suasenhaaqui' pela senha que você deseja usar
senha_plana = "mrdave2026"
hash_gerado = bcrypt.generate_password_hash(senha_plana).decode('utf-8')

print(hash_gerado)