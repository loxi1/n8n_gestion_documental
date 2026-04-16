const now = new Date();
const year = now.getFullYear();
const month = String(now.getMonth() + 1).padStart(2, '0');

const output = [];

for (const item of items) {
    const binary = item.binary || {};
    const subject = item.json.subject || '';
    const from = item.json.from || '';

    for (const key of Object.keys(binary)) {
        const file = binary[key];
        const fileName = file.fileName || 'adjunto';
        const lowerName = fileName.toLowerCase();

        // Solo PDFs por ahora
        if (!lowerName.endsWith('.pdf')) {
            continue;
        }

        let tipoDetectado = 'pdf_otro';

        if (
            lowerName.includes('factura') ||
            lowerName.includes('f001') ||
            lowerName.includes('f002') ||
            subject.toLowerCase().includes('factura')
        ) {
            tipoDetectado = 'factura_posible';
        }

        output.push({
            json: {
                subject,
                from,
                originalFileName: fileName,
                tipoDetectado,
                filePath: `/files/inbox/${year}/${month}/${fileName}`,
            },
            binary: {
                data: file, // <- nombre fijo
            },
        });
    }
}

return output;