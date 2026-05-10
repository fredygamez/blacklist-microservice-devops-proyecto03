"""
test_application.py
===================
Pruebas unitarias para el microservicio de Black List. (Proyecto 2 Entrega 2 CI)

Estrategia de aislamiento:
- SQLite en memoria (sqlite:///:memory:) reemplaza a PostgreSQL/RDS.
- db.create_all() antes de cada test y db.drop_all() al terminar.
- No requiere conexión de red ni motor de base de datos externo.

Cobertura (13 escenarios — 1+ por endpoint según rúbrica):
  GET  /                   → health check (200)
  POST /blacklists         → éxito (201), sin token (401), token inválido (401),
                             sin email (400), sin app_uuid (400),
                             blocked_reason > 255 chars (400),
                             blocked_reason = 255 chars exactos (201),
                             normalización de email a minúsculas
  GET  /blacklists/<email> → encontrado (200, in_blacklist true),
                             no encontrado (200, in_blacklist false),
                             sin token (401),
                             sin blocked_reason → string vacío (no None)

Ejecución desde la raíz del repositorio (modo CodeBuild):
    pytest src/test_application.py -v

Ejecución desde dentro de src/:
    pytest test_application.py -v
"""

import pytest
import os

# FORZANDO SQLITE ANTES DE CUALQUIER IMPORTACIÓN DE LA APP
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
os.environ['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'

# Ahora sí importamos la app y la db
from src.application import application as app, db

@pytest.fixture(autouse=True)
def setup_database():
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    
    with app.app_context():
        db.create_all() # Crea las tablas en memoria
        yield
        db.session.remove()
        db.drop_all()

@pytest.fixture
def client():
    return app.test_client()

# ---------------------------------------------------------------------------
# Import compatible con ejecución desde la raíz (CodeBuild) y desde src/
# ---------------------------------------------------------------------------
try:
    # Ejecución desde la raíz del repo: pytest src/test_application.py
    from src.application import application as app, db, STATIC_BEARER_TOKEN
except ModuleNotFoundError:
    # Ejecución desde dentro de src/: pytest test_application.py
    from application import application as app, db, STATIC_BEARER_TOKEN


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    """
    Configura la app en modo TESTING con SQLite en memoria.
    Crea el esquema antes de cada test y lo destruye al terminar,
    garantizando tests completamente independientes entre sí.
    """
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    with app.test_client() as client:
        with app.app_context():
            db.create_all()
            yield client
            db.session.remove()
            db.drop_all()


@pytest.fixture
def auth_headers():
    """Cabeceras con Bearer Token estático válido (leído desde application.py)."""
    return {
        'Authorization': f'Bearer {STATIC_BEARER_TOKEN}',
        'Content-Type': 'application/json'
    }


@pytest.fixture
def no_auth_headers():
    """Cabeceras sin token de autorización."""
    return {'Content-Type': 'application/json'}


# ---------------------------------------------------------------------------
# Helper compartido
# ---------------------------------------------------------------------------

def agregar_email(client, auth_headers, email='test@ejemplo.com', reason='Razón de prueba.'):
    """Inserta un email en la lista negra. Precondición para tests de GET."""
    return client.post('/blacklists', json={
        'email': email,
        'app_uuid': '550e8400-e29b-41d4-a716-446655440000',
        'blocked_reason': reason
    }, headers=auth_headers)


# ===========================================================================
# GET /  — Health Check
# ===========================================================================

class TestHealthCheck:

    def test_retorna_200_y_estado_ok(self, client):
        """
        GET / debe retornar HTTP 200 con campo 'estado': 'OK'.

        NOTA: La clave del JSON es 'estado' (no 'status').
        Verificado contra application.py → jsonify({'estado': 'OK', ...})
        """
        response = client.get('/')

        assert response.status_code == 200 # 999  <- pruebas intencionales de errores para activar pipeline

        data = response.get_json()
        assert data is not None
        assert data['estado'] == 'OK'   # ← 'estado', no 'status'
        assert 'servicio' in data
        assert 'version' in data


# ===========================================================================
# POST /blacklists
# ===========================================================================

class TestPostBlacklist:

    def test_exito_retorna_201(self, client, auth_headers):
        """
        POST con token válido, email y app_uuid → HTTP 201.
        La respuesta debe incluir 'mensaje' con el email y un 'id' entero.
        """
        payload = {
            'email': 'usuario@ejemplo.com',
            'app_uuid': '550e8400-e29b-41d4-a716-446655440000',
            'blocked_reason': 'Actividad sospechosa.'
        }

        response = client.post('/blacklists', json=payload, headers=auth_headers)

        assert response.status_code == 201

        data = response.get_json()
        assert 'mensaje' in data
        # Verificar que el email aparece en el mensaje sin asumir texto exacto
        assert 'usuario@ejemplo.com' in data['mensaje']
        assert 'id' in data
        assert isinstance(data['id'], int)

    def test_sin_token_retorna_401(self, client, no_auth_headers):
        """POST sin cabecera Authorization → HTTP 401."""
        payload = {
            'email': 'usuario@ejemplo.com',
            'app_uuid': '550e8400-e29b-41d4-a716-446655440000'
        }

        response = client.post('/blacklists', json=payload, headers=no_auth_headers)

        assert response.status_code == 401
        assert 'mensaje' in response.get_json()

    def test_token_invalido_retorna_401(self, client):
        """POST con token incorrecto → HTTP 401."""
        headers = {
            'Authorization': 'Bearer token-incorrecto-xyz',
            'Content-Type': 'application/json'
        }
        payload = {
            'email': 'usuario@ejemplo.com',
            'app_uuid': '550e8400-e29b-41d4-a716-446655440000'
        }

        response = client.post('/blacklists', json=payload, headers=headers)

        assert response.status_code == 401

    def test_sin_campo_email_retorna_400(self, client, auth_headers):
        """POST sin 'email' → HTTP 400 con mensaje que menciona 'email'."""
        payload = {'app_uuid': '550e8400-e29b-41d4-a716-446655440000'}

        response = client.post('/blacklists', json=payload, headers=auth_headers)

        assert response.status_code == 400

        data = response.get_json()
        assert 'mensaje' in data
        assert 'email' in data['mensaje'].lower()

    def test_sin_campo_app_uuid_retorna_400(self, client, auth_headers):
        """POST sin 'app_uuid' → HTTP 400 con mensaje que menciona 'app_uuid'."""
        payload = {'email': 'usuario@ejemplo.com'}

        response = client.post('/blacklists', json=payload, headers=auth_headers)

        assert response.status_code == 400

        data = response.get_json()
        assert 'mensaje' in data
        assert 'app_uuid' in data['mensaje'].lower()

    def test_blocked_reason_256_chars_retorna_400(self, client, auth_headers):
        """
        POST con blocked_reason de 256 chars → HTTP 400.
        El mensaje de error debe mencionar '255' (el límite).
        """
        payload = {
            'email': 'usuario@ejemplo.com',
            'app_uuid': '550e8400-e29b-41d4-a716-446655440000',
            'blocked_reason': 'A' * 256
        }

        response = client.post('/blacklists', json=payload, headers=auth_headers)

        assert response.status_code == 400

        data = response.get_json()
        assert 'mensaje' in data
        assert '255' in data['mensaje']

    def test_blocked_reason_255_chars_exactos_retorna_201(self, client, auth_headers):
        """
        POST con blocked_reason de exactamente 255 chars → HTTP 201.
        Caso borde: el límite exacto debe ser aceptado.
        """
        payload = {
            'email': 'borde@ejemplo.com',
            'app_uuid': '550e8400-e29b-41d4-a716-446655440000',
            'blocked_reason': 'B' * 255
        }

        response = client.post('/blacklists', json=payload, headers=auth_headers)

        assert response.status_code == 201

    def test_email_se_normaliza_a_minusculas(self, client, auth_headers):
        """
        POST con email en mayúsculas → se guarda en minúsculas.
        La consulta posterior con minúsculas debe encontrarlo.
        """
        payload = {
            'email': 'MAYUSCULAS@EJEMPLO.COM',
            'app_uuid': '550e8400-e29b-41d4-a716-446655440000'
        }

        response_post = client.post('/blacklists', json=payload, headers=auth_headers)
        assert response_post.status_code == 201

        response_get = client.get('/blacklists/mayusculas@ejemplo.com', headers=auth_headers)
        assert response_get.get_json()['in_blacklist'] is True


# ===========================================================================
# GET /blacklists/<email>
# ===========================================================================

class TestGetBlacklist:

    def test_email_en_lista_retorna_in_blacklist_true(self, client, auth_headers):
        """
        GET email registrado → HTTP 200 con in_blacklist: true
        y blocked_reason con el valor guardado.

        NOTA: application.py no retorna el campo 'email' en el GET response.
        No se verifica ese campo para evitar falsos negativos
        (diferencia clave respecto a la versión de Gemini).
        """
        agregar_email(client, auth_headers, 'bloqueado@ejemplo.com', 'Fraude detectado.')

        response = client.get('/blacklists/bloqueado@ejemplo.com', headers=auth_headers)

        assert response.status_code == 200

        data = response.get_json()
        assert data['in_blacklist'] is True
        assert data['blocked_reason'] == 'Fraude detectado.'

    def test_email_no_en_lista_retorna_in_blacklist_false(self, client, auth_headers):
        """GET email no registrado → HTTP 200 con in_blacklist: false y blocked_reason vacío."""
        response = client.get('/blacklists/noesta@ejemplo.com', headers=auth_headers)

        assert response.status_code == 200

        data = response.get_json()
        assert data['in_blacklist'] is False
        assert data['blocked_reason'] == ''

    def test_sin_token_retorna_401(self, client, no_auth_headers):
        """GET sin token → HTTP 401."""
        response = client.get('/blacklists/cualquier@email.com', headers=no_auth_headers)

        assert response.status_code == 401
        assert 'mensaje' in response.get_json()

    def test_sin_blocked_reason_retorna_string_vacio_no_none(self, client, auth_headers):
        """
        GET email sin blocked_reason → 'blocked_reason' debe ser '' (string vacío),
        nunca None. Verificado contra application.py:
            return {'blocked_reason': entrada.blocked_reason or ''}
        """
        agregar_email(client, auth_headers, 'sinrazon@ejemplo.com', reason=None)

        response = client.get('/blacklists/sinrazon@ejemplo.com', headers=auth_headers)

        assert response.status_code == 200

        data = response.get_json()
        assert data['in_blacklist'] is True
        assert data['blocked_reason'] == ''
        assert data['blocked_reason'] is not None


# ===========================================================================
# Tabla resumen de cobertura
# ===========================================================================
# Endpoint             | Código | Escenario
# -------------------- | ------ | -----------------------------------------
# GET /                |   200  | Health check, campos 'estado'/'servicio'/'version'
# POST /blacklists     |   201  | Éxito con todos los campos
# POST /blacklists     |   401  | Sin Authorization header
# POST /blacklists     |   401  | Token incorrecto
# POST /blacklists     |   400  | Falta campo 'email'
# POST /blacklists     |   400  | Falta campo 'app_uuid'
# POST /blacklists     |   400  | blocked_reason 256 chars (supera límite)
# POST /blacklists     |   201  | blocked_reason 255 chars (caso borde válido)
# POST /blacklists     |   201  | Email en mayúsculas → normalizado a minúsculas
# GET  /blacklists/<e> |   200  | Email registrado → in_blacklist: true
# GET  /blacklists/<e> |   200  | Email no registrado → in_blacklist: false
# GET  /blacklists/<e> |   401  | Sin Authorization header
# GET  /blacklists/<e> |   200  | Sin blocked_reason → '' (no None)
# ===========================================================================
