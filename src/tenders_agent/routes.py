import json
from time import perf_counter
from typing import Annotated
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Header  # pyright: ignore[reportMissingImports]
from google.genai import types  # pyright: ignore[reportMissingImports]
from pydantic import BaseModel, ConfigDict, Field  # pyright: ignore[reportMissingImports]

from .auth import api_key_validator
from .session import get_runner

router = APIRouter()


class QueryRequest(BaseModel):
    """Request payload for routing user input to the root ADK agent."""

    user_id: str = Field(default="default_user", min_length=1)
    session_id: str | None = Field(default=None, min_length=1)
    current_file: str | None = None
    message: str | None = Field(default=None, min_length=1)
    query: str | None = Field(default=None, min_length=1)

    def text(self) -> str:
        text = (self.message or self.query or "").strip()
        if not text:
            raise HTTPException(status_code=422, detail="message or query is required.")

        return text


class QueryResponse(BaseModel):
    user_id: str
    session_id: str
    current_file: str | None = None
    response: str
    events: list[dict[str, Any]]


class ChatMessage(BaseModel):
    """Single chat message used to preserve context between turns."""

    role: str
    content: str


class ChatRequest(BaseModel):
    """Request model for the chat endpoint."""

    query: str | None = Field(default=None, min_length=1)
    message: str | None = Field(default=None, min_length=1)
    history: list[ChatMessage] | None = None

    def text(self) -> str:
        text = (self.query or self.message or "").strip()
        if not text:
            raise HTTPException(status_code=422, detail="query or message is required.")

        return text


class OptimizeRequest(BaseModel):
    """Request model for the optimize endpoint."""

    query: str = Field(min_length=1)


class OptimizeResponse(BaseModel):
    """Response model for the optimize endpoint."""

    result: str
    processing_time_ms: float


class ChatResponse(BaseModel):
    """Response model for the chat endpoint."""

    result: str
    processing_time_ms: float


class JobLoopRequest(BaseModel):
    """Request for the jobLoop endpoint."""

    model_config = ConfigDict(extra="allow")

    app_id: str | None = None
    loop_id: str | None = None
    iteration_number: int | None = None
    prior_iteration_spark_confs: list[dict[str, Any]] = Field(default_factory=list)
    prompt: str | None = None


class JobLoopResponse(BaseModel):
    """Response from jobLoop with the next Spark config and control flags."""

    analysis_summary: str
    result: str
    processing_time_ms: float
    validated_spark_conf: dict[str, Any]
    change_reasoning: dict[str, str] = Field(default_factory=dict)
    should_continue: bool
    stop_reason: str | None = None
    validation_warnings: list[str] | None = None


@router.post("/query", tags=["agent"])
async def query(
    request: QueryRequest,
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> QueryResponse:
    await api_key_validator.validate(x_api_key)

    return await _run_agent(request)


@router.post("/chat", response_model=ChatResponse, tags=["agent"])
async def chat(request: ChatRequest) -> ChatResponse:
    """Chat endpoint for the UI agent experience."""
    history = "\n".join(
        f"{message.role}: {message.content}" for message in request.history or []
    )
    request_text = request.text()
    message = (
        request_text
        if not history
        else f"Conversation so far:\n{history}\n\n{request_text}"
    )
    started = perf_counter()
    response = await _run_agent(QueryRequest(message=message))

    return ChatResponse(
        result=response.response,
        processing_time_ms=(perf_counter() - started) * 1000,
    )


@router.post("/optimize", response_model=OptimizeResponse, tags=["agent"])
async def optimize(request: OptimizeRequest) -> OptimizeResponse:
    """Run the agent against an optimization prompt."""
    started = perf_counter()
    response = await _run_agent(QueryRequest(message=request.query))

    return OptimizeResponse(
        result=response.response,
        processing_time_ms=(perf_counter() - started) * 1000,
    )


@router.post("/jobLoop", tags=["agent"])
async def job_loop(request: JobLoopRequest) -> JobLoopResponse:
    """Analyze an optimization loop iteration and return the next Spark config."""
    prompt_payload = request.model_dump(mode="json", exclude_none=True)
    message = (
        "Recommend the next Spark configuration for this optimization loop. "
        "If you can produce a machine-readable answer, return JSON with "
        "`validated_spark_conf` and `should_continue`.\n\n"
        f"{json.dumps(prompt_payload, indent=2)}"
    )
    started = perf_counter()
    response = await _run_agent(QueryRequest(message=message))
    parsed = _try_parse_json_object(response.response)
    latest_conf = request.prior_iteration_spark_confs[-1] if request.prior_iteration_spark_confs else {}
    validated_spark_conf = parsed.get("validated_spark_conf", latest_conf)
    should_continue = parsed.get("should_continue", True)

    return JobLoopResponse(
        analysis_summary="Next config based on prior iteration.",
        result=response.response,
        processing_time_ms=(perf_counter() - started) * 1000,
        validated_spark_conf=validated_spark_conf
        if isinstance(validated_spark_conf, dict)
        else latest_conf,
        should_continue=should_continue if isinstance(should_continue, bool) else True,
    )


async def _run_agent(request: QueryRequest) -> QueryResponse:
    runner = get_runner()
    session_id = request.session_id or str(uuid4())
    current_file_context = (
        request.current_file.strip() if request.current_file else ""
    ) or "MISSING"
    request_text = request.text()
    new_message = types.Content(
        role="user",
        parts=[
            types.Part.from_text(
                text=(
                    f"Current file: {current_file_context}\n\n"
                    f"User request: {request_text}"
                )
            )
        ],
    )

    events: list[dict[str, Any]] = []
    final_response_parts: list[str] = []

    async for event in runner.run_async(
        user_id=request.user_id,
        session_id=session_id,
        new_message=new_message,
    ):
        events.append(event.model_dump(mode="json", exclude_none=True))

        if event.author != "user" and event.is_final_response() and event.content:
            final_response_parts.extend(
                part.text for part in event.content.parts if part.text
            )

    return QueryResponse(
        user_id=request.user_id,
        session_id=session_id,
        current_file=None if current_file_context == "MISSING" else current_file_context,
        response="".join(final_response_parts),
        events=events,
    )


def _try_parse_json_object(text: str) -> dict[str, Any]:
    decoder = json.JSONDecoder()
    for index, character in enumerate(text):
        if character != "{":
            continue
        try:
            parsed, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed

    return {}
