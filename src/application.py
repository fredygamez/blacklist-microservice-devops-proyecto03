import os
from datetime import datetime
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_marshmallow import Marshmallow
from flask_restful import Api, Resource
from flask_jwt_extended import JWTManager, create_access_token

# ---------------------------------------------------------------------------
# Configuración de la aplicación
# ---------------------------------------------------------------------------
# [TEST-03]: Esta Nota es para pruebas e iniciar CodeBuild 26apr2026. 
application = Flask(__name__)

# PRIORIDAD 1: Buscar variable de entorno DATABASE_URL (usada por los tests)
# PRIORIDAD 2: Buscar variables de RDS (producción)
# PRIORIDAD 3: Usar localhost (desarrollo local)
db_uri = os.environ.get('DATABASE_URL') or os.environ.get('SQLALCHEMY_DATABASE_URI')

if not db_uri:
    db_user = os.environ.get('RDS_USERNAME', 'postgres')
    db_pass = os.environ.get('RDS_PASSWORD', 'postgres')
    db_host = os.environ.get('RDS_HOSTNAME', 'localhost')
    db_port = os.environ.get('RDS_PORT', '5432')
    db_name = os.environ.get('RDS_DB_NAME', 'blacklist_db')
    db_uri = f"postgresql://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"

application.config['SQLALCHEMY_DATABASE_URI'] = db_uri
application.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Clave secreta para JWT – se puede configurar vía variable de entorno
application.config['JWT_SECRET_KEY'] = os.environ.get(
    'JWT_SECRET_KEY', 'clave-secreta-estatica-devops-2026'
)

# Token estático de autorización (Bearer Token fijo para simplicidad)
STATIC_BEARER_TOKEN = os.environ.get(
    'STATIC_BEARER_TOKEN', 'token-secreto-blacklist-2026'
)

# ---------------------------------------------------------------------------
# Extensiones
# ---------------------------------------------------------------------------
db = SQLAlchemy(application)
ma = Marshmallow(application)
api = Api(application)
jwt = JWTManager(application)

# ---------------------------------------------------------------------------
# Modelo de datos
# ---------------------------------------------------------------------------
class BlacklistEntry(db.Model):
    """Modelo que representa una entrada en la lista negra global."""
    __tablename__ = 'blacklist'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    email = db.Column(db.String(255), nullable=False, index=True)
    app_uuid = db.Column(db.String(36), nullable=False)
    blocked_reason = db.Column(db.String(255), nullable=True)
    ip_address = db.Column(db.String(45), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self):
        return f'<BlacklistEntry {self.email}>'

# ---------------------------------------------------------------------------
# Schema de Marshmallow
# ---------------------------------------------------------------------------
class BlacklistEntrySchema(ma.SQLAlchemyAutoSchema):
    class Meta:
        model = BlacklistEntry
        load_instance = True

blacklist_schema = BlacklistEntrySchema()

# ---------------------------------------------------------------------------
# Funciones auxiliares
# ---------------------------------------------------------------------------
def validar_token():
    """Valida el Bearer Token estático en el encabezado Authorization."""
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return False
    token = auth_header.split('Bearer ')[-1].strip()
    return token == STATIC_BEARER_TOKEN


def obtener_ip_cliente():
    """Obtiene la dirección IP real del cliente, considerando proxies."""
    if request.headers.get('X-Forwarded-For'):
        return request.headers['X-Forwarded-For'].split(',')[0].strip()
    return request.remote_addr or '0.0.0.0'

# ---------------------------------------------------------------------------
# Recursos REST
# ---------------------------------------------------------------------------
class BlacklistResource(Resource):
    """
    POST /blacklists
    Agrega un email a la lista negra global.
    """
    def post(self):
        # Validar autorización
        if not validar_token():
            return {'mensaje': 'Token de autorización inválido o faltante.'}, 401

        # Obtener datos del cuerpo de la solicitud
        datos = request.get_json(silent=True)
        if not datos:
            return {'mensaje': 'El cuerpo de la solicitud debe ser JSON válido.'}, 400

        email = datos.get('email')
        app_uuid = datos.get('app_uuid')
        blocked_reason = datos.get('blocked_reason')

        # Validaciones de campos requeridos
        if not email or not isinstance(email, str) or email.strip() == '':
            return {'mensaje': 'El campo "email" es requerido.'}, 400

        if not app_uuid or not isinstance(app_uuid, str) or app_uuid.strip() == '':
            return {'mensaje': 'El campo "app_uuid" es requerido y debe ser un UUID.'}, 400

        # Validar longitud del motivo
        if blocked_reason and len(blocked_reason) > 255:
            return {
                'mensaje': 'El campo "blocked_reason" no debe superar los 255 caracteres.'
            }, 400

        # Obtener IP y fecha/hora
        ip_address = obtener_ip_cliente()
        created_at = datetime.utcnow()

        # Crear nueva entrada en la lista negra
        nueva_entrada = BlacklistEntry(
            email=email.strip().lower(),
            app_uuid=app_uuid.strip(),
            blocked_reason=blocked_reason.strip() if blocked_reason else None,
            ip_address=ip_address,
            created_at=created_at
        )

        db.session.add(nueva_entrada)
        db.session.commit()

        return {
            'mensaje': f'El email {email} ha sido agregado exitosamente a la lista negra global.',
            'id': nueva_entrada.id
        }, 201


class BlacklistQueryResource(Resource):
    """
    GET /blacklists/<string:email>
    Consulta si un email está en la lista negra global.
    """
    def get(self, email):
        # Validar autorización
        if not validar_token():
            return {'mensaje': 'Token de autorización inválido o faltante.'}, 401

        # Buscar el email en la lista negra
        entrada = BlacklistEntry.query.filter_by(
            email=email.strip().lower()
        ).first()

        if entrada:
            return {
                'in_blacklist': True,
                'blocked_reason': entrada.blocked_reason or ''
            }, 200
        else:
            return {
                'in_blacklist': False,
                'blocked_reason': ''
            }, 200

# ---------------------------------------------------------------------------
# Endpoint de health check
# ---------------------------------------------------------------------------
@application.route('/')
def health_check():
    """Health check para AWS Elastic Beanstalk."""
    return jsonify({
        'estado': 'OK',
        'servicio': 'Microservicio de Lista Negra Global',
        'version': '6.1.0'
    }), 200

# ---------------------------------------------------------------------------
# Endpoint para generar un token JWT (utilidad para pruebas con Postman)
# ---------------------------------------------------------------------------
@application.route('/auth/token', methods=['POST'])
def generar_token():
    """
    Genera un JWT para pruebas. En producción el token estático es
    suficiente según los requerimientos del proyecto.
    """
    datos = request.get_json(silent=True)
    if not datos:
        return jsonify({'mensaje': 'Envíe credenciales en formato JSON.'}), 400

    username = datos.get('username', '')
    password = datos.get('password', '')

    # Credenciales estáticas para pruebas
    if username == 'admin' and password == 'admin123':
        token = create_access_token(identity=username)
        return jsonify({'token': token}), 200

    return jsonify({'mensaje': 'Credenciales inválidas.'}), 401

# ---------------------------------------------------------------------------
# Registro de rutas en la API
# ---------------------------------------------------------------------------
api.add_resource(BlacklistResource, '/blacklists')
api.add_resource(BlacklistQueryResource, '/blacklists/<string:email>')

# ---------------------------------------------------------------------------
# Crear tablas al iniciar la aplicación
# ---------------------------------------------------------------------------
try:
    with application.app_context():
        db.create_all()
except Exception as e:
    application.logger.warning(f'No se pudo crear las tablas al inicio: {e}')
    application.logger.warning('Las tablas se crearán cuando la BD esté disponible.')

# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    application.run(host='0.0.0.0', port=8000, debug=True) # '0.0.0.0' le dice a Flask escuchar todas las interfaces de red del contenedor
