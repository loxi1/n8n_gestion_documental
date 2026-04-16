return items.map(item => {
  item.json.correo_id = item.json.id;
  delete item.json.id;
  return item;
});