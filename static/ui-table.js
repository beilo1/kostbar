export function columnHeading(label) {
  return `<th scope="col">${label}</th>`;
}

export function table(labels, rows, empty, heading = columnHeading) {
  if (!rows && empty !== undefined) return `<p class="admin-empty">${empty}</p>`;
  return '<div class="table-wrap"><table><thead><tr>' + labels.map(heading).join('') +
    '</tr></thead><tbody>' + rows + '</tbody></table></div>';
}
