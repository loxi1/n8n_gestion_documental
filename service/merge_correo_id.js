return items.map(item => {
  item.json.correo_id = item.json.id;
  item.json.filePaths = item.json.filePath;
  delete item.json.id;
  return item;
});