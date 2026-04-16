INSERT INTO documentos (
    correo_id,
    estado_documento,
    observacion
)
VALUES (
    {{$json.id}},
    'pendiente',
    'Documento descargado desde n8n'
)
RETURNING id;