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
return items.map(item => {
  item.json.documento_id = item.json.id;
  delete item.json.id;
  return item;
});