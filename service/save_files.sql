INSERT INTO archivos (
    documento_id,
    correo_id,
    nombre_archivo_original,
    nombre_archivo_actual,
    extension,
    mime_type,
    tamano_bytes,
    hash_sha256,
    ruta_temporal,
    es_principal,
    estado_archivo
)
VALUES (
    {{$json.documento_id}},
    {{$json.correo_id}},
    {{$json.originalFileName ? `'${$json.originalFileName.replace(/'/g, "''")}'` : 'NULL'}},
    {{$json.storedFileName ? `'${$json.storedFileName.replace(/'/g, "''")}'` : 'NULL'}},
    '.pdf',
    {{$json.mimeType ? `'${$json.mimeType.replace(/'/g, "''")}'` : `'application/pdf'`}},
    {{$json.tamano_bytes ? $json.tamano_bytes : 'NULL'}},
    {{$json.hash_sha256 ? `'${$json.hash_sha256}'` : 'NULL'}},
    {{$json.relativePath ? `'${$json.relativePath.replace(/'/g, "''")}'` : 'NULL'}},
    true,
    'descargado'
)
RETURNING id;