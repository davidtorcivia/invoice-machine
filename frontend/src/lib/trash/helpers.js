export function getTrashItemIcon(type) {
  return type === 'client' ? 'users' : 'invoice';
}

export function getTrashItemName(item) {
  return item.type === 'client' ? item.name : `Invoice #${item.name}`;
}
