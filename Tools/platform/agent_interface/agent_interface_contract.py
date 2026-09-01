"""Stable machine identity shared by agent-interface producers and consumers.

This is the single machine owner for the generated interface-projection
envelope and for the environment names that bind a Host, the MCP transport,
and child Tool processes.  It contains no IO, generation, transport, or
governance judgment; those responsibilities remain with its consumers.
"""

PROJECTION_ARTIFACT_KIND = "agent-interface-projection"
PROJECTION_SCHEMA_VERSION = 4
MCP_FORM = "mcp"

PATH_EXTENSION_KEY = "x-cambium-path"
WORKSPACE_EXTENSION_KEY = "x-cambium-workspace"

SOURCE_DISTRIBUTION_TARGET = "source-distribution"
CARRIED_RUNTIME_TARGET = "carried-runtime"

WORKSPACE_ENV = "CAMBIUM_WORKSPACE_ROOT"
EXECUTION_CONTEXT_ENV = "CAMBIUM_EXECUTION_CONTEXT_ID"
INTERFACE_SOURCE_HASH_ENV = "CAMBIUM_INTERFACE_SOURCE_HASH"
INTERFACE_PROJECTION_ENV = "CAMBIUM_INTERFACE_PROJECTION"
PATH_CAPABILITIES_ENV = "CAMBIUM_PATH_CAPABILITIES"
PATH_CAPABILITIES_ACK_ENV = "CAMBIUM_PATH_CAPABILITIES_ACK_FD"
