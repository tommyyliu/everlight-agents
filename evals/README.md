Eforos evals

Purpose
- Run small, manual eval scenarios to inspect how Eforos organizes and stores information across models and prompts
- No automated scoring; we capture raw prompts and notes that get saved

What gets saved
- evals/out/<scenario_name>/config.json: the scenario config and timestamp
- evals/out/<scenario_name>/prompt.txt: the full augmented prompt sent to the model (single-message scenarios only)
- evals/out/<scenario_name>/notes.json: any notes Eforos created via create_note
- evals/out/<scenario_name>/tool_calls.ndjson: line-delimited JSON of tool calls made by the agent (if any)

Prereqs
- testing.postgresql must be installed (already in test extras)
- Google GenAI credentials for both text generation (via Genkit) and embeddings if Eforos calls create_note
- Optional: GENKIT_MODEL env var to override default model

Configure scenarios
- Edit evals/eforos_scenarios.json
- Each scenario supports:
  - name: unique name for output dir
  - model: model id (e.g., googleai/gemini-2.5-flash)
  - message: the input message/context to process
  - channel: channel name (usually raw_data_entries)
  - prompt_path: path to a prompt file to use for Eforos (e.g., ai/default_prompts/eforos.md)

Run
- From repo root:
  - python evals/run_eforos_evals.py list
  - python evals/run_eforos_evals.py run --name <scenario_name>
  - python evals/run_eforos_evals.py run --model googleai/gemini-2.5-flash --prompt eforos_v1

Notes
- The runner creates a new user and an Eforos agent per scenario
- If model calls fail (e.g., missing credentials), the script will still write config and prompt; notes.json may be empty
