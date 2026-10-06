"""Server-owned module identifiers; requests cannot select arbitrary prompts/tools."""
EMULATED_MODULE = 'congestion-control-emulated'
REAL_WORLD_MODULE = 'congestion-control-real-world'
LEO_MODULE = 'leo-emergency-failover'
HTTP2_MODULE = 'http2-compliance-study'
RELIABLE_MODULE = 'reliable-sketch-study'
RELIABLE_ANALYSIS_VERSION = 'reliable-assessment-v1'
IPV6_MODULE = 'ipv6-dns-study'
IPV6_ANALYSIS_VERSION = 'ipv6-dns-assessment-v1'
CHAT_MODULES = (EMULATED_MODULE, REAL_WORLD_MODULE, LEO_MODULE, HTTP2_MODULE, RELIABLE_MODULE, IPV6_MODULE)
REAL_WORLD_ANALYSIS_VERSION = 'real-world-chat-v1'
LEO_ANALYSIS_VERSION = 'leo-failover-chat-v1'
HTTP2_ANALYSIS_VERSION = 'http2-assessment-v3'
