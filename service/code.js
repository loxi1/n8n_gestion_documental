const output = [];

function safeText(value) {
	return String(value || "")
		.normalize("NFD")
		.replace(/[\u0300-\u036f]/g, "")
		.replace(/[<>:"/\\|?*=@+\s]+/g, "_")
		.replace(/_+/g, "_")
		.replace(/^_+|_+$/g, "");
}

for (const item of items) {
	const binary = item.binary || {};
	const subject = item.json.subject || "";
	const messageId = item.json.messageId || item.json.message_id || null;
	const date = item.json.date || null;

	let fromEmail = "";
	let fromName = "";

	if (item.json.from?.value?.length) {
		fromEmail = item.json.from.value[0].address || "";
		fromName = item.json.from.value[0].name || "";
	} else if (typeof item.json.from === "string") {
		fromEmail = item.json.from;
	}

	const now = new Date();
	const year = now.getFullYear();
	const month = String(now.getMonth() + 1).padStart(2, "0");
	const day = String(now.getDate()).padStart(2, "0");
	const hour = String(now.getHours()).padStart(2, "0");
	const minute = String(now.getMinutes()).padStart(2, "0");
	const second = String(now.getSeconds()).padStart(2, "0");
	const ms = String(now.getMilliseconds()).padStart(3, "0");
	const stamp = `${year}${month}${day}${hour}${minute}${second}${ms}`;

	const safeMessageId = safeText(messageId || "sin_message_id").slice(0, 40);

	let fileIndex = 0;

	for (const key of Object.keys(binary)) {
		const file = binary[key];
		const fileName = file.fileName || "adjunto";
		const lowerName = fileName.toLowerCase();

		if (!lowerName.endsWith(".pdf")) {
			continue;
		}

		fileIndex++;
		
		const newFileName = `posible_documento_${stamp}_${safeMessageId}_${fileIndex}.pdf`;

		output.push({
			json: {
				subject,
				fromEmail,
				fromName,
				messageId,
				date,
				originalFileName: fileName,
				storedFileName: newFileName,
				tipoDetectado: "pendiente",
				filePath: `/files/inbox/${year}/${month}/${newFileName}`,
				relativePath: `inbox/${year}/${month}/${newFileName}`,
				mimeType: file.mimeType || "application/pdf",
				tamano_bytes: file.fileSize || null,
			},
			binary: {
				data: file,
			},
		});
	}
}

return output;