habilitar virtualizacion:

dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart
dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart
bcdedit /set hypervisorlaunchtype auto

ir a la bios y configurar que pueda adminitir remoto

docker run -d \
  --name pg_gestiondocumental \
  -e POSTGRES_USER=user_gestdocu \
  -e POSTGRES_PASSWORD=getiondocu654123] \
  -e POSTGRES_DB=gestiondocumental \
  -p 5432:5432 \
  -v pgdata_gestiondocumental:/var/lib/postgresql/data \
  postgres:17

docker-compose.yml
services:
  postgres:
    image: postgres:17
    container_name: pg_gestiondocumental
    restart: unless-stopped
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres123
      POSTGRES_DB: gestiondocumental
      TZ: America/Lima
    ports:
      - "5432:5432"
    volumes:
      - pgdata_gestiondocumental:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres -d gestiondocumental"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  pgdata_gestiondocumental:
  

borrar todo el sin volumen: docker compose down
borrar todo con todo y volumen (limpiar): docker compose down -v
levantar el proyecto: docker compose up -d

tablas:
DROP TABLE IF EXISTS movimientos_archivo CASCADE;
DROP TABLE IF EXISTS procesamiento CASCADE;
DROP TABLE IF EXISTS asiento_detalle CASCADE;
DROP TABLE IF EXISTS asientos CASCADE;
DROP TABLE IF EXISTS validaciones_starsoft CASCADE;
DROP TABLE IF EXISTS expediente_documentos CASCADE;
DROP TABLE IF EXISTS expedientes CASCADE;
DROP TABLE IF EXISTS archivos CASCADE;
DROP TABLE IF EXISTS documentos CASCADE;
DROP TABLE IF EXISTS correos_ingresados CASCADE;
DROP TABLE IF EXISTS proveedores CASCADE;

CREATE TABLE proveedores (
    id BIGSERIAL PRIMARY KEY,
    ruc VARCHAR(15) UNIQUE,
    nombre TEXT,
    direccion TEXT,
    creado_en TIMESTAMP NOT NULL DEFAULT NOW(),
    actualizado_en TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE correos_ingresados (
    id BIGSERIAL PRIMARY KEY,
    origen VARCHAR(30) NOT NULL DEFAULT 'correo',
    proveedor_correo VARCHAR(30) NOT NULL DEFAULT 'imap',
    message_id TEXT,
    thread_id TEXT,
    remitente_nombre TEXT,
    remitente_email TEXT,
    reply_to TEXT,
    destinatario_para TEXT,
    destinatario_cc TEXT,
    destinatario_cco TEXT,
    asunto TEXT NOT NULL,
    cuerpo_texto TEXT,
    cuerpo_html TEXT,
    fecha_correo TIMESTAMP,
    fecha_recepcion TIMESTAMP NOT NULL DEFAULT NOW(),
    leido BOOLEAN NOT NULL DEFAULT FALSE,
    procesado BOOLEAN NOT NULL DEFAULT FALSE,
    estado_correo VARCHAR(30) NOT NULL DEFAULT 'pendiente',
    cantidad_adjuntos INTEGER NOT NULL DEFAULT 0,
    observacion TEXT,
    creado_en TIMESTAMP NOT NULL DEFAULT NOW(),
    actualizado_en TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX ux_correos_ingresados_message_id
ON correos_ingresados(message_id)
WHERE message_id IS NOT NULL;

CREATE TABLE documentos (
    id BIGSERIAL PRIMARY KEY,
    correo_id BIGINT REFERENCES correos_ingresados(id) ON DELETE SET NULL,
    proveedor_id BIGINT REFERENCES proveedores(id) ON DELETE SET NULL,
    tipo_documental VARCHAR(30),
    tipo_doc VARCHAR(10),
    serie VARCHAR(20),
    numero VARCHAR(30),
    ruc VARCHAR(15),
    razon_social TEXT,
    fecha_emision DATE,
    fecha_vencimiento DATE,
    moneda VARCHAR(10),
    importe NUMERIC(14,2),
    igv NUMERIC(14,2),
    base_imponible NUMERIC(14,2),
    saldo NUMERIC(14,2),
    clave_documental TEXT,
    estado_documento VARCHAR(30) NOT NULL DEFAULT 'pendiente',
    observacion TEXT,
    creado_en TIMESTAMP NOT NULL DEFAULT NOW(),
    actualizado_en TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX ux_documentos_clave_documental
ON documentos(clave_documental)
WHERE clave_documental IS NOT NULL;

CREATE INDEX idx_documentos_busqueda
ON documentos(tipo_doc, serie, numero, ruc);

CREATE INDEX idx_documentos_correo
ON documentos(correo_id);

CREATE TABLE archivos (
    id BIGSERIAL PRIMARY KEY,
    documento_id BIGINT REFERENCES documentos(id) ON DELETE CASCADE,
    correo_id BIGINT REFERENCES correos_ingresados(id) ON DELETE SET NULL,
    nombre_archivo_original TEXT NOT NULL,
    nombre_archivo_actual TEXT NOT NULL,
    extension VARCHAR(20),
    mime_type VARCHAR(100),
    tamano_bytes BIGINT,
    hash_sha256 VARCHAR(64) NOT NULL,
    ruta_temporal TEXT,
    ruta_final TEXT,
    es_principal BOOLEAN NOT NULL DEFAULT FALSE,
    estado_archivo VARCHAR(30) NOT NULL DEFAULT 'pendiente',
    creado_en TIMESTAMP NOT NULL DEFAULT NOW(),
    actualizado_en TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX ux_archivos_hash_sha256
ON archivos(hash_sha256);

CREATE INDEX idx_archivos_documento
ON archivos(documento_id);

CREATE TABLE expedientes (
    id BIGSERIAL PRIMARY KEY,
    clave_documental TEXT NOT NULL,
    anio INTEGER,
    mes INTEGER,
    asiento_contable VARCHAR(30),
    carpeta_relativa TEXT,
    estado_expediente VARCHAR(30) NOT NULL DEFAULT 'abierto',
    creado_en TIMESTAMP NOT NULL DEFAULT NOW(),
    actualizado_en TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX ux_expedientes_clave_documental
ON expedientes(clave_documental);

CREATE TABLE expediente_documentos (
    id BIGSERIAL PRIMARY KEY,
    expediente_id BIGINT NOT NULL REFERENCES expedientes(id) ON DELETE CASCADE,
    documento_id BIGINT NOT NULL REFERENCES documentos(id) ON DELETE CASCADE,
    rol_documento VARCHAR(30) NOT NULL,
    creado_en TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX ux_expediente_documentos_unico
ON expediente_documentos(expediente_id, documento_id, rol_documento);

CREATE TABLE validaciones_starsoft (
    id BIGSERIAL PRIMARY KEY,
    documento_id BIGINT NOT NULL REFERENCES documentos(id) ON DELETE CASCADE,
    existe_en_compras BOOLEAN NOT NULL DEFAULT FALSE,
    existe_en_ctapag BOOLEAN NOT NULL DEFAULT FALSE,
    existe_en_contabilidad BOOLEAN NOT NULL DEFAULT FALSE,
    existe_en_banco BOOLEAN NOT NULL DEFAULT FALSE,
    id_comcab BIGINT,
    id_comprobante_ctapag TEXT,
    fecha_compra DATE,
    fecha_registro_ctapag DATE,
    fecha_asiento DATE,
    importe_compra NUMERIC(14,2),
    importe_ctapag NUMERIC(14,2),
    saldo_ctapag NUMERIC(14,2),
    corden_ctapag VARCHAR(20),
    estado_ctapag VARCHAR(10),
    subdiario VARCHAR(10),
    numero_comprobante_contable VARCHAR(20),
    asiento_contable VARCHAR(30),
    documento_contable TEXT,
    anexo_contable TEXT,
    observacion TEXT,
    fecha_validacion TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_validaciones_documento
ON validaciones_starsoft(documento_id);

CREATE TABLE asientos (
    id BIGSERIAL PRIMARY KEY,
    documento_id BIGINT REFERENCES documentos(id) ON DELETE SET NULL,
    subdiario VARCHAR(10) NOT NULL,
    numero_comprobante VARCHAR(20) NOT NULL,
    asiento_contable VARCHAR(30) NOT NULL,
    fecha DATE,
    glosa TEXT,
    creado_en TIMESTAMP NOT NULL DEFAULT NOW(),
    actualizado_en TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX ux_asientos_unico
ON asientos(subdiario, numero_comprobante);

CREATE TABLE asiento_detalle (
    id BIGSERIAL PRIMARY KEY,
    asiento_id BIGINT NOT NULL REFERENCES asientos(id) ON DELETE CASCADE,
    secuencia VARCHAR(10),
    cuenta VARCHAR(30),
    anexo VARCHAR(20),
    documento_ref TEXT,
    fecha_doc DATE,
    debe NUMERIC(14,2),
    haber NUMERIC(14,2),
    glosa TEXT,
    creado_en TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_asiento_detalle_asiento
ON asiento_detalle(asiento_id);

CREATE TABLE procesamiento (
    id BIGSERIAL PRIMARY KEY,
    documento_id BIGINT NOT NULL REFERENCES documentos(id) ON DELETE CASCADE,
    estado VARCHAR(30) NOT NULL DEFAULT 'pendiente',
    paso_actual VARCHAR(100),
    intentos INTEGER NOT NULL DEFAULT 0,
    mensaje TEXT,
    fecha_inicio TIMESTAMP,
    fecha_fin TIMESTAMP,
    actualizado_en TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_procesamiento_documento
ON procesamiento(documento_id);

CREATE TABLE movimientos_archivo (
    id BIGSERIAL PRIMARY KEY,
    archivo_id BIGINT NOT NULL REFERENCES archivos(id) ON DELETE CASCADE,
    documento_id BIGINT REFERENCES documentos(id) ON DELETE SET NULL,
    accion VARCHAR(50) NOT NULL,
    ruta_origen TEXT,
    ruta_destino TEXT,
    detalle TEXT,
    creado_en TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_movimientos_archivo_archivo
ON movimientos_archivo(archivo_id);

ALTER TABLE correos_ingresados
ADD CONSTRAINT uq_correos_ingresados_message_id UNIQUE (message_id);

ALTER TABLE archivos
ALTER COLUMN hash_sha256 DROP NOT NULL;

