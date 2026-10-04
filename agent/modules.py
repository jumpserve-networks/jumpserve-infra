"""Server-owned module identifiers; requests cannot select arbitrary prompts/tools."""
EMULATED_MODULE = 'congestion-control-emulated'
REAL_WORLD_MODULE = 'congestion-control-real-world'
LEO_MODULE = 'leo-emergency-failover'
CHAT_MODULES = (EMULATED_MODULE, REAL_WORLD_MODULE, LEO_MODULE)
REAL_WORLD_ANALYSIS_VERSION = 'real-world-chat-v1'
LEO_ANALYSIS_VERSION = 'leo-failover-chat-v1'
