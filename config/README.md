# Configuration

Configuration is stored at ~/.sdk-test-agent/config.json (not in this directory).

## Interactive config (CLI)
`ash
python cli.py /config url https://api.openai.com/v1
python cli.py /config model gpt-4o
python cli.py /config set --api-key sk-...
python cli.py /config show
`

## Environment variables
- OPENAI_API_KEY ！ API key (required)
- SDK_ROOT ！ Default SDK root directory
- SDK_OUTPUT_ROOT ！ Default output directory
- SDK_LOG_LEVEL ！ Logging level (default: INFO)
- SDK_MODEL ！ Model name override
