# Step 6: AI insights (Hugging Face)

**Status:** not started. This log will be filled in as the step is built.

## The goal

Turn each detected spike into a plain-English summary, for example: "Recalls jumped in March 2019, driven almost entirely by one company's mass recall over contamination concerns."

## The design rule

**The AI only writes from facts your code computed.**

1. SQL and pandas find the spike and its numbers (step 5).
2. The AI turns those numbers into a sentence.
3. The response includes the facts too, so anyone can check the AI didn't invent anything.
4. If the AI service is down, the API falls back to a plain template summary instead of failing.

## Setup needed before starting

1. A free account at [huggingface.co](https://huggingface.co).
2. **Settings → Access Tokens** → create a token with **Read** access.
3. Add it to `.env` with single quotes (never paste it in a chat):

   ```powershell
   Add-Content .env 'HF_TOKEN=paste_your_token_here'
   ```

4. Optional: the Hugging Face connector in Claude, for searching models.

## To fill in when built

- Files added or changed
- Which model was used, and why
- New endpoints
- Tests and how they were proven to fail
- Problems hit and fixes
- Git commits
