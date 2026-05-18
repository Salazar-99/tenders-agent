from pathlib import Path

from google.adk.agents import (  # pyright: ignore[reportMissingImports]
    Agent,
    ParallelAgent,
    SequentialAgent,
)
from google.adk.models import Gemini  # pyright: ignore[reportMissingImports]
from google.adk.tools.mcp_tool import (  # pyright: ignore[reportMissingImports]
    MCPToolset,
    StdioConnectionParams,
)
from google.genai import types  # pyright: ignore[reportMissingImports]
from mcp import StdioServerParameters  # pyright: ignore[reportMissingImports]

from .config import settings

PROMPTS_DIR = Path(__file__).with_name("prompts")

_RETRY_STATUS_CODES = (408, 429, 500, 502, 503, 504)


def _gemini_llm() -> Gemini:
    return Gemini(
        model=settings.gemini_model,
        retry_options=types.HttpRetryOptions(
            attempts=settings.gemini_http_retry_attempts,
            initial_delay=settings.gemini_http_retry_initial_delay_sec,
            max_delay=settings.gemini_http_retry_max_delay_sec,
            exp_base=2.0,
            http_status_codes=_RETRY_STATUS_CODES,
        ),
    )


def get_tenders_platform_summary() -> dict[str, str]:
    """Return a short summary of the QueryTenders platform."""
    return {
        "status": "success",
        "platform": "QueryTenders",
        "summary": "QueryTenders helps analyze Spark jobs and surface optimization recommendations.",
    }


def _load_agent_prompt(prompt_name: str) -> str:
    prompt_file = PROMPTS_DIR / f"{prompt_name}.md"
    prompt = prompt_file.read_text(encoding="utf-8").strip()
    if not prompt:
        raise ValueError(f"Prompt file is empty: {prompt_file}")

    return prompt


def _build_clickhouse_toolset() -> MCPToolset:
    return MCPToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command=settings.clickhouse_mcp_command,
                args=[],
                env=settings.clickhouse_mcp_env(),
            ),
            timeout=20,
        )
    )


def _build_specialist_agent(
    *,
    name: str,
    description: str,
    prompt_name: str,
    output_key: str | None = None,
) -> Agent:
    kwargs = {"output_key": output_key} if output_key else {}
    return Agent(
        model=_gemini_llm(),
        name=name,
        description=description,
        instruction=_load_agent_prompt(prompt_name),
        tools=[_build_clickhouse_toolset()],
        **kwargs,
    )


skew_agent = _build_specialist_agent(
    name="skew_agent",
    description="Diagnoses Spark data skew and task imbalance using ClickHouse telemetry.",
    prompt_name="skew",
)

general_agent = _build_specialist_agent(
    name="general_agent",
    description=(
        "Answers broad Spark and QueryTenders telemetry questions using ClickHouse, "
        "including slowest apps, shuffle volume, SQL history, and run summaries."
    ),
    prompt_name="general",
)

spill_agent = _build_specialist_agent(
    name="spill_agent",
    description="Diagnoses Spark memory and disk spills using ClickHouse telemetry.",
    prompt_name="spill",
)

gc_pressure_agent = _build_specialist_agent(
    name="gc_pressure_agent",
    description="Diagnoses Spark JVM garbage collection pressure using ClickHouse telemetry.",
    prompt_name="gc_pressure",
)

provisioning_agent = _build_specialist_agent(
    name="provisioning_agent",
    description="Diagnoses Spark executor, core, memory, and provisioning issues using ClickHouse telemetry.",
    prompt_name="provisioning",
)

_COMPREHENSIVE_PARALLEL_SUB_AGENTS = [
    _build_specialist_agent(
        name="parallel_skew_agent",
        description="Runs skew diagnostics as part of a parallel Spark job review.",
        prompt_name="skew",
        output_key="parallel_skew_diagnostics",
    ),
    _build_specialist_agent(
        name="parallel_spill_agent",
        description="Runs spill diagnostics as part of a parallel Spark job review.",
        prompt_name="spill",
        output_key="parallel_spill_diagnostics",
    ),
    _build_specialist_agent(
        name="parallel_gc_pressure_agent",
        description="Runs GC pressure diagnostics as part of a parallel Spark job review.",
        prompt_name="gc_pressure",
        output_key="parallel_gc_pressure_diagnostics",
    ),
    _build_specialist_agent(
        name="parallel_provisioning_agent",
        description="Runs provisioning diagnostics as part of a parallel Spark job review.",
        prompt_name="provisioning",
        output_key="parallel_provisioning_diagnostics",
    ),
]

parallel_diagnostics_agent = (
    ParallelAgent(
        name="parallel_diagnostics_agent",
        description=(
            "Runs skew, spill, GC pressure, and provisioning diagnostics concurrently "
            "for a comprehensive Spark job review."
        ),
        sub_agents=list(_COMPREHENSIVE_PARALLEL_SUB_AGENTS),
    )
    if settings.parallel_comprehensive_diagnostics
    else SequentialAgent(
        name="parallel_diagnostics_agent",
        description=(
            "Runs skew, spill, GC pressure, and provisioning diagnostics sequentially "
            "for a comprehensive Spark job review (reduces Gemini input-token bursts)."
        ),
        sub_agents=list(_COMPREHENSIVE_PARALLEL_SUB_AGENTS),
    )
)

root_agent = Agent(
    model=_gemini_llm(),
    name="tenders_agent",
    description="Routes QueryTenders Spark questions to the right telemetry agent.",
    instruction=_load_agent_prompt("root"),
    tools=[get_tenders_platform_summary],
    sub_agents=[
        general_agent,
        skew_agent,
        spill_agent,
        gc_pressure_agent,
        provisioning_agent,
        parallel_diagnostics_agent,
    ],
)
