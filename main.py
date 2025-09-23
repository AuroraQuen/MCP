from mcp.server.fastmcp import FastMCP
from pydantic import field

mcp = FastMCP(
    name = "Hello MCP Server",
    description = "A simple MCP server example",
    host = "0.0.0.0",
    port = 3000,
    stateless_http = True,
    debug = False
)

@mcp.tool(
    title= "Echo Tool",
    description= "A tool that echoes the input text",
    input= field(str, description="The text to echo")
)
def echo_tool(input: str) -> str:
    return input