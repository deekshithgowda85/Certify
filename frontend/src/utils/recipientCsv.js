const REQUIRED_HEADERS = ['name', 'email', 'course_name', 'completion_date']

function parseRows(text) {
  const rows = []
  let row = []
  let field = ''
  let quoted = false

  for (let index = 0; index < text.length; index += 1) {
    const character = text[index]

    if (quoted) {
      if (character === '"' && text[index + 1] === '"') {
        field += '"'
        index += 1
      } else if (character === '"') {
        quoted = false
      } else {
        field += character
      }
    } else if (character === '"' && field.length === 0) {
      quoted = true
    } else if (character === ',') {
      row.push(field)
      field = ''
    } else if (character === '\n' || character === '\r') {
      if (character === '\r' && text[index + 1] === '\n') index += 1
      row.push(field)
      if (row.some(value => value.trim())) rows.push(row)
      row = []
      field = ''
    } else {
      field += character
    }
  }

  if (quoted) throw new Error('The CSV file has an unclosed quoted field.')
  row.push(field)
  if (row.some(value => value.trim())) rows.push(row)
  return rows
}

function normalizeHeader(value) {
  return value
    .replace(/^\uFEFF/, '')
    .trim()
    .toLowerCase()
    .replace(/[\s-]+/g, '_')
}

function normalizeDate(value) {
  const date = value.trim()
  if (!date) return ''
  const isoDate = date.match(/^(\d{4})-(\d{2})-(\d{2})$/)
  if (isoDate) {
    const [, year, month, day] = isoDate
    if (isValidDate(Number(year), Number(month), Number(day))) return date
    throw new Error(`Invalid completion date "${date}".`)
  }

  throw new Error(`Unsupported completion date "${date}". Use YYYY-MM-DD.`)
}

function isValidDate(year, month, day) {
  const date = new Date(Date.UTC(year, month - 1, day))
  return date.getUTCFullYear() === year && date.getUTCMonth() === month - 1 && date.getUTCDate() === day
}

export function parseRecipientCsv(text, maxRecipients) {
  const rows = parseRows(text)
  if (rows.length < 2) throw new Error('The CSV must include a header row and at least one participant.')

  const headers = rows[0].map(normalizeHeader)
  const positions = Object.fromEntries(headers.map((header, index) => [header, index]))
  const missing = REQUIRED_HEADERS.filter(header => positions[header] === undefined)
  if (missing.length) throw new Error(`Missing CSV column(s): ${missing.join(', ')}.`)

  const recipients = rows.slice(1).map(row => ({
    name: (row[positions.name] || '').trim(),
    email: (row[positions.email] || '').trim(),
    course_name: (row[positions.course_name] || '').trim(),
    completion_date: normalizeDate(row[positions.completion_date] || ''),
  }))

  if (!recipients.length) throw new Error('The CSV does not contain any participant rows.')
  if (recipients.length > maxRecipients) {
    throw new Error(`The CSV contains ${recipients.length.toLocaleString()} participants; the maximum is ${maxRecipients.toLocaleString()}.`)
  }
  return recipients
}
