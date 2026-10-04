MODEL_ID = 'us.anthropic.claude-sonnet-4-6'
MODEL_REGION = 'us-east-1'
MODEL_TEMPERATURE = 0
HTTP2_MODEL_ID = MODEL_ID

def model_id_for_module(module_id):
    return HTTP2_MODEL_ID if module_id == 'http2-compliance-study' else MODEL_ID
