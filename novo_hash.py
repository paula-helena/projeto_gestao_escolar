from flask_bcrypt import Bcrypt
bcrypt = Bcrypt()
novo_hash = bcrypt.generate_password_hash('digite_aqui_o_hash').decode('utf-8')
print(novo_hash)