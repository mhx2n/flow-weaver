# Mistral fallback reliability fix

## Goal
Ensure placeholder/login responses from Gemini or Perplexity never end the solve flow when any usable Mistral key is available.

## Changes
- Add a final runtime fallback layer after all existing bot patches.
- Load Mistral keys from the owner-managed key list, environment configuration, and registered Mistral providers without exposing secrets.
- Rotate across keys and supported Mistral models, record failures, and continue until a valid answer is returned.
- Apply the same fallback to normal answers and MCQ/quiz JSON answers.
- Preserve the original error only when every Mistral key/model genuinely fails, while showing users a clean Bengali message without internal provider details.

## Verification
- Compile every Python section.
- Run isolated fallback tests with mocked provider responses for placeholder rejection, key rotation, valid text, and MCQ JSON recovery.
