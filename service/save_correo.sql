INSERT INTO correos_ingresados (
    message_id,
    remitente_email,
    asunto,
    fecha_correo,
    cantidad_adjuntos,
    estado_correo,
    leido,
    procesado
)
VALUES (
    {{$json.messageId ? `'${$json.messageId.replace(/'/g, "''")}'` : 'NULL'}},
    {{$json.from ? `'${$json.from.replace(/'/g, "''")}'` : 'NULL'}},
    {{$json.subject ? `'${$json.subject.replace(/'/g, "''")}'` : 'NULL'}},
    {{$json.date ? `'${$json.date}'` : 'NULL'}},
    1,
    'descargado',
    false,
    false
)
ON CONFLICT (message_id) DO UPDATE
SET
    remitente_email = EXCLUDED.remitente_email,
    asunto = EXCLUDED.asunto,
    fecha_correo = EXCLUDED.fecha_correo,
    cantidad_adjuntos = EXCLUDED.cantidad_adjuntos,
    actualizado_en = NOW()
RETURNING id;