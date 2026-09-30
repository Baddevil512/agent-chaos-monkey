"""
Core Middleware Decorator (@inject_chaos) for Agent Chaos Monkey.
Intercepts tool/function executions and injects simulated production faults.
"""

import time
import uuid
import random
import asyncio
import functools
import inspect
from typing import Callable, Optional, Union, List, Tuple, Any

from .config import FaultType, ChaosConfig, get_global_config
from .exceptions import (
    ChaosHTTPError,
    ChaosCorruptedJSONError,
    ChaosEmptyResponseError,
    ChaosEngineException
)
from .telemetry import get_tracker


def _select_fault(configured_faults: List[Union[FaultType, str]]) -> str:
    """Helper to pick a random fault type from configured list."""
    if not configured_faults:
        return FaultType.HTTP_502.value
    chosen = random.choice(configured_faults)
    if isinstance(chosen, FaultType):
        return chosen.value
    return str(chosen)


def inject_chaos(
    func: Optional[Callable] = None,
    *,
    rate: Optional[float] = None,
    faults: Optional[List[Union[FaultType, str]]] = None,
    latency_range: Optional[Tuple[float, float]] = None,
    enabled: bool = True,
    name: Optional[str] = None,
    raise_exceptions: Optional[bool] = None
):
    """
    Decorator for injecting chaos faults into Python functions and AI Agent tools.

    Usage:
        @inject_chaos(rate=0.6, faults=[FaultType.HTTP_502, FaultType.CORRUPTED_JSON])
        def fetch_user_data(user_id):
            ...

        @inject_chaos  # uses global defaults
        def process_payment(amount):
            ...
    """
    def decorator(fn: Callable) -> Callable:
        tool_name = name or getattr(fn, "__name__", "agent_tool")
        is_async = asyncio.iscoroutinefunction(fn)

        @functools.wraps(fn)
        def sync_wrapper(*args, **kwargs) -> Any:
            global_cfg = get_global_config()
            
            # Resolve actual effective configuration
            is_enabled = enabled and global_cfg.enabled
            effective_rate = rate if rate is not None else global_cfg.rate
            effective_faults = faults if faults is not None else global_cfg.fault_types
            effective_latency = latency_range if latency_range is not None else global_cfg.latency_range
            effective_raise = raise_exceptions if raise_exceptions is not None else global_cfg.raise_exceptions

            tracker = get_tracker()
            call_id = str(uuid.uuid4())[:8]

            # Decide whether to inject chaos fault
            should_inject = is_enabled and (random.random() < effective_rate)

            if not should_inject:
                start_time = time.perf_counter()
                try:
                    result = fn(*args, **kwargs)
                    exec_ms = (time.perf_counter() - start_time) * 1000.0
                    tracker.record_call(
                        call_id=call_id,
                        function_name=tool_name,
                        execution_time_ms=exec_ms,
                        status="SUCCESS",
                        input_args=(args, kwargs),
                        output_data=result
                    )
                    return result
                except ChaosEngineException as c_ex:
                    exec_ms = (time.perf_counter() - start_time) * 1000.0
                    tracker.record_call(
                        call_id=call_id,
                        function_name=tool_name,
                        execution_time_ms=exec_ms,
                        status="FALLBACK_HANDLED",
                        error_message=str(c_ex),
                        input_args=(args, kwargs)
                    )
                    raise
                except Exception as ex:
                    exec_ms = (time.perf_counter() - start_time) * 1000.0
                    tracker.record_call(
                        call_id=call_id,
                        function_name=tool_name,
                        execution_time_ms=exec_ms,
                        status="UNHANDLED_FAILURE",
                        error_message=str(ex),
                        input_args=(args, kwargs)
                    )
                    raise

            # --- CHAOS FAULT INJECTION ACTIVE ---
            fault_type = _select_fault(effective_faults)
            start_time = time.perf_counter()

            # 1. Network Latency Simulation
            if fault_type == FaultType.LATENCY.value:
                delay = random.uniform(effective_latency[0], effective_latency[1])
                time.sleep(delay)
                try:
                    result = fn(*args, **kwargs)
                    exec_ms = (time.perf_counter() - start_time) * 1000.0
                    tracker.record_call(
                        call_id=call_id,
                        function_name=tool_name,
                        execution_time_ms=exec_ms,
                        status="FAULT_INJECTED",
                        fault_type=fault_type,
                        input_args=(args, kwargs),
                        output_data=result
                    )
                    return result
                except Exception as ex:
                    exec_ms = (time.perf_counter() - start_time) * 1000.0
                    tracker.record_call(
                        call_id=call_id,
                        function_name=tool_name,
                        execution_time_ms=exec_ms,
                        status="UNHANDLED_FAILURE",
                        fault_type=fault_type,
                        error_message=str(ex),
                        input_args=(args, kwargs)
                    )
                    raise

            # 2. Upstream HTTP Errors (502, 503, 429)
            elif fault_type in (FaultType.HTTP_502.value, FaultType.HTTP_503.value, FaultType.HTTP_429.value):
                status_code = int(fault_type.split("_")[1])
                exc = ChaosHTTPError(status_code=status_code)
                exec_ms = (time.perf_counter() - start_time) * 1000.0
                tracker.record_call(
                    call_id=call_id,
                    function_name=tool_name,
                    execution_time_ms=exec_ms,
                    status="FAULT_INJECTED",
                    fault_type=fault_type,
                    error_message=str(exc),
                    input_args=(args, kwargs)
                )
                raise exc

            # 3. Truncated / Corrupted JSON Responses
            elif fault_type == FaultType.CORRUPTED_JSON.value:
                exec_ms = (time.perf_counter() - start_time) * 1000.0
                if effective_raise:
                    exc = ChaosCorruptedJSONError()
                    tracker.record_call(
                        call_id=call_id,
                        function_name=tool_name,
                        execution_time_ms=exec_ms,
                        status="FAULT_INJECTED",
                        fault_type=fault_type,
                        error_message=str(exc),
                        input_args=(args, kwargs)
                    )
                    raise exc
                else:
                    corrupted_payload = '{"status": "success", "data": [invalid json payload ... unterminated'
                    tracker.record_call(
                        call_id=call_id,
                        function_name=tool_name,
                        execution_time_ms=exec_ms,
                        status="FAULT_INJECTED",
                        fault_type=fault_type,
                        input_args=(args, kwargs),
                        output_data=corrupted_payload
                    )
                    return corrupted_payload

            # 4. Empty Response
            elif fault_type == FaultType.EMPTY_RESPONSE.value:
                exec_ms = (time.perf_counter() - start_time) * 1000.0
                if effective_raise:
                    exc = ChaosEmptyResponseError()
                    tracker.record_call(
                        call_id=call_id,
                        function_name=tool_name,
                        execution_time_ms=exec_ms,
                        status="FAULT_INJECTED",
                        fault_type=fault_type,
                        error_message=str(exc),
                        input_args=(args, kwargs)
                    )
                    raise exc
                else:
                    empty_payload = ""
                    tracker.record_call(
                        call_id=call_id,
                        function_name=tool_name,
                        execution_time_ms=exec_ms,
                        status="FAULT_INJECTED",
                        fault_type=fault_type,
                        input_args=(args, kwargs),
                        output_data=empty_payload
                    )
                    return empty_payload

            # Fallback for unhandled fault types
            exec_ms = (time.perf_counter() - start_time) * 1000.0
            exc = ChaosHTTPError(status_code=500, message=f"Unknown injected fault: {fault_type}")
            tracker.record_call(
                call_id=call_id,
                function_name=tool_name,
                execution_time_ms=exec_ms,
                status="FAULT_INJECTED",
                fault_type=fault_type,
                error_message=str(exc),
                input_args=(args, kwargs)
            )
            raise exc

        @functools.wraps(fn)
        async def async_wrapper(*args, **kwargs) -> Any:
            global_cfg = get_global_config()
            
            is_enabled = enabled and global_cfg.enabled
            effective_rate = rate if rate is not None else global_cfg.rate
            effective_faults = faults if faults is not None else global_cfg.fault_types
            effective_latency = latency_range if latency_range is not None else global_cfg.latency_range
            effective_raise = raise_exceptions if raise_exceptions is not None else global_cfg.raise_exceptions

            tracker = get_tracker()
            call_id = str(uuid.uuid4())[:8]

            should_inject = is_enabled and (random.random() < effective_rate)

            if not should_inject:
                start_time = time.perf_counter()
                try:
                    result = await fn(*args, **kwargs)
                    exec_ms = (time.perf_counter() - start_time) * 1000.0
                    tracker.record_call(
                        call_id=call_id,
                        function_name=tool_name,
                        execution_time_ms=exec_ms,
                        status="SUCCESS",
                        input_args=(args, kwargs),
                        output_data=result
                    )
                    return result
                except ChaosEngineException as c_ex:
                    exec_ms = (time.perf_counter() - start_time) * 1000.0
                    tracker.record_call(
                        call_id=call_id,
                        function_name=tool_name,
                        execution_time_ms=exec_ms,
                        status="FALLBACK_HANDLED",
                        error_message=str(c_ex),
                        input_args=(args, kwargs)
                    )
                    raise
                except Exception as ex:
                    exec_ms = (time.perf_counter() - start_time) * 1000.0
                    tracker.record_call(
                        call_id=call_id,
                        function_name=tool_name,
                        execution_time_ms=exec_ms,
                        status="UNHANDLED_FAILURE",
                        error_message=str(ex),
                        input_args=(args, kwargs)
                    )
                    raise

            # --- ASYNC CHAOS FAULT INJECTION ACTIVE ---
            fault_type = _select_fault(effective_faults)
            start_time = time.perf_counter()

            if fault_type == FaultType.LATENCY.value:
                delay = random.uniform(effective_latency[0], effective_latency[1])
                await asyncio.sleep(delay)
                try:
                    result = await fn(*args, **kwargs)
                    exec_ms = (time.perf_counter() - start_time) * 1000.0
                    tracker.record_call(
                        call_id=call_id,
                        function_name=tool_name,
                        execution_time_ms=exec_ms,
                        status="FAULT_INJECTED",
                        fault_type=fault_type,
                        input_args=(args, kwargs),
                        output_data=result
                    )
                    return result
                except Exception as ex:
                    exec_ms = (time.perf_counter() - start_time) * 1000.0
                    tracker.record_call(
                        call_id=call_id,
                        function_name=tool_name,
                        execution_time_ms=exec_ms,
                        status="UNHANDLED_FAILURE",
                        fault_type=fault_type,
                        error_message=str(ex),
                        input_args=(args, kwargs)
                    )
                    raise

            elif fault_type in (FaultType.HTTP_502.value, FaultType.HTTP_503.value, FaultType.HTTP_429.value):
                status_code = int(fault_type.split("_")[1])
                exc = ChaosHTTPError(status_code=status_code)
                exec_ms = (time.perf_counter() - start_time) * 1000.0
                tracker.record_call(
                    call_id=call_id,
                    function_name=tool_name,
                    execution_time_ms=exec_ms,
                    status="FAULT_INJECTED",
                    fault_type=fault_type,
                    error_message=str(exc),
                    input_args=(args, kwargs)
                )
                raise exc

            elif fault_type == FaultType.CORRUPTED_JSON.value:
                exec_ms = (time.perf_counter() - start_time) * 1000.0
                if effective_raise:
                    exc = ChaosCorruptedJSONError()
                    tracker.record_call(
                        call_id=call_id,
                        function_name=tool_name,
                        execution_time_ms=exec_ms,
                        status="FAULT_INJECTED",
                        fault_type=fault_type,
                        error_message=str(exc),
                        input_args=(args, kwargs)
                    )
                    raise exc
                else:
                    corrupted_payload = '{"status": "success", "data": [invalid json payload ... unterminated'
                    tracker.record_call(
                        call_id=call_id,
                        function_name=tool_name,
                        execution_time_ms=exec_ms,
                        status="FAULT_INJECTED",
                        fault_type=fault_type,
                        input_args=(args, kwargs),
                        output_data=corrupted_payload
                    )
                    return corrupted_payload

            elif fault_type == FaultType.EMPTY_RESPONSE.value:
                exec_ms = (time.perf_counter() - start_time) * 1000.0
                if effective_raise:
                    exc = ChaosEmptyResponseError()
                    tracker.record_call(
                        call_id=call_id,
                        function_name=tool_name,
                        execution_time_ms=exec_ms,
                        status="FAULT_INJECTED",
                        fault_type=fault_type,
                        error_message=str(exc),
                        input_args=(args, kwargs)
                    )
                    raise exc
                else:
                    empty_payload = ""
                    tracker.record_call(
                        call_id=call_id,
                        function_name=tool_name,
                        execution_time_ms=exec_ms,
                        status="FAULT_INJECTED",
                        fault_type=fault_type,
                        input_args=(args, kwargs),
                        output_data=empty_payload
                    )
                    return empty_payload

            exec_ms = (time.perf_counter() - start_time) * 1000.0
            exc = ChaosHTTPError(status_code=500, message=f"Unknown injected fault: {fault_type}")
            tracker.record_call(
                call_id=call_id,
                function_name=tool_name,
                execution_time_ms=exec_ms,
                status="FAULT_INJECTED",
                fault_type=fault_type,
                error_message=str(exc),
                input_args=(args, kwargs)
            )
            raise exc

        wrapper = async_wrapper if is_async else sync_wrapper

        # Also preserve tool attributes for CrewAI / LangChain compatibility if object wraps tool
        if hasattr(fn, "description"):
            setattr(wrapper, "description", getattr(fn, "description"))
        if hasattr(fn, "args_schema"):
            setattr(wrapper, "args_schema", getattr(fn, "args_schema"))

        return wrapper

    # Support decorating without parentheses: @inject_chaos
    if func is not None and callable(func):
        return decorator(func)
    return decorator
