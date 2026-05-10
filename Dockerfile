# Imagen base oficial Python-slim 3.11
FROM python:3.11-slim

# Definiendo directorio de trabajo dentro del contenedor
WORKDIR /app

# Copiar archivo de dependencias desde la carpeta local src/
COPY src/requirements.txt .

# Instalando dependencias Python sin guardar caché,reduce tamaño de imagen
RUN pip install --no-cache-dir -r requirements.txt

# Copiando el contenido de folder src local a la carpeta src de contenedor
COPY src/ ./src/

# Contenedor usara puerto 5000
EXPOSE 5000

# Comando que ejecuta la aplicación al iniciar contenedor
CMD ["python", "src/application.py"]