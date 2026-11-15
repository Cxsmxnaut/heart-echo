export const MODEL_ARTIFACTS = Object.freeze({
  e2b: { alias: 'care-gemma4-e2b', path: '.cache/models/gemma-4-E2B-it-Q4_K_M.gguf', url: 'https://huggingface.co/unsloth/gemma-4-E2B-it-GGUF/resolve/0314792d7f1f7e229411f620751375812bb9faf2/gemma-4-E2B-it-Q4_K_M.gguf', sha256: '740185b21d22ceb83a11c3aa62ad5842ef32c70f6096d756bbee85a1e4ec34b8' },
  e4b: { alias: 'care-gemma4-e4b', path: '.cache/models/e4b/gemma-4-E4B-it-Q4_K_M.gguf', url: 'https://huggingface.co/unsloth/gemma-4-E4B-it-GGUF/resolve/bfc15c382204943c3a8fff0c750b94ae2364d7a3/gemma-4-E4B-it-Q4_K_M.gguf', sha256: '85a896a047553e842f25297ee5b031d64ff30147d9c4af17b1e4b394cd1fab87' },
});
export function selectedArtifact(env = process.env) {
  const key = env.MODEL_VARIANT || 'e4b'; if (!Object.hasOwn(MODEL_ARTIFACTS, key)) throw Error('MODEL_VARIANT must be e2b or e4b.');
  return MODEL_ARTIFACTS[key];
}

export function selectedCareAdapter(env = process.env) {
  const variant = env.MODEL_VARIANT || 'e4b';
  selectedArtifact(env);
  const mode = env.CARE_MODEL_ADAPTER || (variant === 'e4b' ? 'trained' : 'off');
  if (!['trained', 'off'].includes(mode)) throw Error('CARE_MODEL_ADAPTER must be trained or off.');
  if (mode === 'off') return null;
  if (variant !== 'e4b') throw Error('The trained care adapter requires the E4B model.');
  return {
    path: 'finetuning/exports/care-e4b-seed001-lora-f16.gguf',
    sha256: '513abc53c84f42116bec06877c6691de83d6c224e921f15039315121fc9ea6e3',
  };
}
