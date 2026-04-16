INSERT INTO documentos (
    correo_id,
    estado_documento,
    observacion
)
VALUES (
    {{$json.correo_id}},
    'pendiente',
    'Documento descargado desde n8n'
)
RETURNING id;