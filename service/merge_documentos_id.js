return items.map(item => {
  item.json.documento_id = item.json.id;
  delete item.json.id;
  return item;
});