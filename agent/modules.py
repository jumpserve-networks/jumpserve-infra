"""Server-owned module identifiers; requests cannot select arbitrary prompts/tools."""
EMULATED_MODULE = 'congestion-control-emulated'
REAL_WORLD_MODULE = 'congestion-control-real-world'
CHAT_MODULES = (EMULATED_MODULE, REAL_WORLD_MODULE)
REAL_WORLD_ANALYSIS_VERSION = 'real-world-chat-v1'
