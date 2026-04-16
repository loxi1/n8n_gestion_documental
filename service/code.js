const now = new Date();

const year = now.getFullYear();
const month = String(now.getMonth() + 1).padStart(2, '0');
const day = String(now.getDate()).padStart(2, '0');
const hour = String(now.getHours()).padStart(2, '0');
const minute = String(now.getMinutes()).padStart(2, '0');
const second = String(now.getSeconds()).padStart(2, '0');
const ms = String(now.getMilliseconds()).padStart(3, '0');

const stamp = `${year}${month}${day}${hour}${minute}${second}${ms}`;

const output = [];

for (const item of items) {
    const binary = item.binary || {};
    const subject = item.json.subject || '';
    const from = item.json.from || '';
    const messageId = item.json.messageId || item.json.message_id || null;
    const date = item.json.date || null;

    for (const key of Object.keys(binary)) {
        const file = binary[key];
        const fileName = file.fileName || 'adjunto';
        const lowerName = fileName.toLowerCase();

        if (!lowerName.endsWith('.pdf')) {
            continue;
        }

        const newFileName = `posible_documento_${stamp}.pdf`;

        output.push({
            json: {
                subject,
                from,
                messageId,
                date,
                originalFileName: fileName,
                storedFileName: newFileName,
                tipoDetectado: 'pendiente',
                filePath: `/files/inbox/${year}/${month}/${newFileName}`,
                relativePath: `inbox/${year}/${month}/${newFileName}`,
            },
            binary: {
                data: file,
            },
        });
    }
}

return output;