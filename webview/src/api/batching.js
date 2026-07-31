export const CARD_GEN_CHUNK_SIZE_LARGE = 6000;
export const CARD_GEN_CHUNK_SIZE_LEGACY = 3000;

export function getCardGenChunkSize(model) {
  if (/gpt-5\.6/i.test(model || "")) {
    return CARD_GEN_CHUNK_SIZE_LARGE;
  }

  return CARD_GEN_CHUNK_SIZE_LEGACY;
}

export function batchChunks(chunks, maxChars) {
  const batches = [];
  let currentBatch = "";

  for (let chunk of chunks) {
    if (currentBatch && currentBatch.length + chunk.length > maxChars) {
      batches.push(currentBatch);
      currentBatch = "";
    }

    if (!currentBatch) {
      currentBatch = chunk;
    } else {
      currentBatch += "\n\n" + chunk;
    }
  }

  if (currentBatch) {
    batches.push(currentBatch);
  }

  return batches;
}
