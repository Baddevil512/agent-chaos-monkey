"""
Telemetry and Token Burn Tracker for Agent Chaos Monkey.
Tracks tool invocations, fault injections, retry loops, token consumption, and calculates resilience scores.
"""

import time
import math
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import threading

from .config import FaultType, ChaosConfig, get_global_config


@dataclass
class CallLogRecord:
    """Represents a single tool invocation log entry."""
    call_id: str
    function_name: str
    timestamp: str
    execution_time_ms: float
    status: str  # "SUCCESS", "FAULT_INJECTED", "FALLBACK_HANDLED", "UNHANDLED_FAILURE"
    fault_type: Optional[str] = None
    error_message: Optional[str] = None
    input_args_summary: str = ""
    output_summary: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    is_retry: bool = False


class TelemetryTracker:
    """Thread-safe singleton/instance to track chaos metrics across test executions."""
    
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(TelemetryTracker, cls).__new__(cls)
                cls._instance.reset()
            return cls._instance

    def reset(self):
        """Resets all tracked metrics for a new test run."""
        with self._lock:
            self.call_logs: List[CallLogRecord] = []
            self.fault_counts: Dict[str, int] = {f.value: 0 for f in FaultType}
            self.function_call_history: Dict[str, int] = {}
            self.total_invocations: int = 0
            self.successful_invocations: int = 0
            self.faults_injected_count: int = 0
            self.unhandled_failures_count: int = 0
            self.fallback_handled_count: int = 0
            self.total_prompt_tokens: int = 0
            self.total_completion_tokens: int = 0
            self.wasted_prompt_tokens: int = 0
            self.wasted_completion_tokens: int = 0
            self.retry_count: int = 0

    def estimate_tokens(self, text_input: str, text_output: str) -> Tuple[int, int]:
        """
        Estimates LLM token usage using rough word/char heuristic (1 token ~ 4 chars or 0.75 words).
        Used when exact model tokenizer is not available.
        """
        in_chars = len(str(text_input or ""))
        out_chars = len(str(text_output or ""))
        prompt_tokens = max(1, math.ceil(in_chars / 4.0))
        completion_tokens = max(1, math.ceil(out_chars / 4.0))
        return prompt_tokens, completion_tokens

    def record_call(
        self,
        call_id: str,
        function_name: str,
        execution_time_ms: float,
        status: str,
        fault_type: Optional[str] = None,
        error_message: Optional[str] = None,
        input_args: Any = None,
        output_data: Any = None,
        override_prompt_tokens: Optional[int] = None,
        override_completion_tokens: Optional[int] = None
    ) -> CallLogRecord:
        """Records a tool call invocation and updates telemetry counters."""
        with self._lock:
            self.total_invocations += 1
            
            # Detect retries by tracking call frequency per function
            prev_calls = self.function_call_history.get(function_name, 0)
            self.function_call_history[function_name] = prev_calls + 1
            is_retry = prev_calls > 0 and status in ("FAULT_INJECTED", "UNHANDLED_FAILURE", "FALLBACK_HANDLED")
            if is_retry:
                self.retry_count += 1

            # Summarize inputs and outputs for telemetry report
            input_summary = str(input_args)[:150] if input_args is not None else ""
            output_summary = str(output_data)[:150] if output_data is not None else ""

            # Estimate or record tokens
            if override_prompt_tokens is not None and override_completion_tokens is not None:
                p_tok, c_tok = override_prompt_tokens, override_completion_tokens
            else:
                p_tok, c_tok = self.estimate_tokens(input_summary, output_summary or error_message or "")

            tot_tok = p_tok + c_tok
            self.total_prompt_tokens += p_tok
            self.total_completion_tokens += c_tok

            # Categorize status and token waste
            if fault_type:
                self.faults_injected_count += 1
                self.fault_counts[fault_type] = self.fault_counts.get(fault_type, 0) + 1

            if status == "SUCCESS":
                self.successful_invocations += 1
            elif status == "FALLBACK_HANDLED":
                self.fallback_handled_count += 1
            elif status == "UNHANDLED_FAILURE":
                self.unhandled_failures_count += 1
                # Wasted tokens on unhandled failure or retries
                self.wasted_prompt_tokens += p_tok
                self.wasted_completion_tokens += c_tok

            if is_retry:
                self.wasted_prompt_tokens += p_tok
                self.wasted_completion_tokens += c_tok

            record = CallLogRecord(
                call_id=call_id,
                function_name=function_name,
                timestamp=datetime.now().strftime("%H:%M:%S.%f")[:-3],
                execution_time_ms=round(execution_time_ms, 2),
                status=status,
                fault_type=fault_type,
                error_message=error_message,
                input_args_summary=input_summary,
                output_summary=output_summary,
                prompt_tokens=p_tok,
                completion_tokens=c_tok,
                total_tokens=tot_tok,
                is_retry=is_retry
            )
            self.call_logs.append(record)
            return record

    def calculate_resilience_score(self) -> float:
        """
        Calculates Overall Agent Resilience Score (0 to 100).
        Evaluates fault tolerance, retry loop efficiency, and token waste ratio.
        """
        if self.total_invocations == 0:
            return 100.0

        # Component 1: Fault Survival & Handling (0 - 40 pts)
        if self.faults_injected_count == 0:
            handling_score = 40.0
        else:
            handled_or_recovered = self.fallback_handled_count + (self.total_invocations - self.faults_injected_count - self.unhandled_failures_count)
            handled_ratio = max(0.0, min(1.0, handled_or_recovered / self.total_invocations))
            # Penalty for unhandled exceptions
            unhandled_ratio = self.unhandled_failures_count / max(1, self.faults_injected_count)
            handling_score = max(0.0, 40.0 * (1.0 - unhandled_ratio))

        # Component 2: Retry Loop Efficiency (0 - 30 pts)
        if self.faults_injected_count == 0:
            retry_score = 30.0
        else:
            # High ratio of retries to injected faults indicates infinite looping
            retry_ratio = self.retry_count / max(1, self.faults_injected_count)
            if retry_ratio <= 1.0:
                retry_score = 30.0
            elif retry_ratio <= 2.5:
                retry_score = 15.0
            else:
                retry_score = 0.0

        # Component 3: Token Waste Efficiency (0 - 30 pts)
        total_tok = self.total_prompt_tokens + self.total_completion_tokens
        wasted_tok = self.wasted_prompt_tokens + self.wasted_completion_tokens
        if total_tok == 0:
            waste_score = 30.0
        else:
            waste_ratio = wasted_tok / total_tok
            waste_score = max(0.0, 30.0 * (1.0 - waste_ratio))

        total_score = handling_score + retry_score + waste_score
        return round(max(0.0, min(100.0, total_score)), 1)

    def calculate_financial_metrics(self) -> Dict[str, float]:
        """Calculates token costs and estimated monthly financial leak risk."""
        cfg = get_global_config()
        
        # Immediate wasted cost in test run
        prompt_cost = (self.wasted_prompt_tokens / 1000.0) * cfg.token_cost_prompt
        completion_cost = (self.wasted_completion_tokens / 1000.0) * cfg.token_cost_completion
        total_waste_usd = prompt_cost + completion_cost

        # Total cost of run
        total_prompt_cost = (self.total_prompt_tokens / 1000.0) * cfg.token_cost_prompt
        total_comp_cost = (self.total_completion_tokens / 1000.0) * cfg.token_cost_completion
        total_run_usd = total_prompt_cost + total_comp_cost

        # Estimated monthly financial leak risk (extrapolated based on volume multiplier)
        if self.total_invocations > 0:
            waste_per_call = total_waste_usd / self.total_invocations
            monthly_leak_risk = waste_per_call * cfg.monthly_call_volume_multiplier
        else:
            monthly_leak_risk = 0.0

        return {
            "total_run_cost_usd": round(total_run_usd, 4),
            "wasted_cost_usd": round(total_waste_usd, 4),
            "monthly_leak_risk_usd": round(monthly_leak_risk, 2)
        }

    def get_summary(self) -> Dict[str, Any]:
        """Returns complete summary dictionary for reporting."""
        fin = self.calculate_financial_metrics()
        resilience_score = self.calculate_resilience_score()

        return {
            "resilience_score": resilience_score,
            "total_invocations": self.total_invocations,
            "successful_invocations": self.successful_invocations,
            "faults_injected_count": self.faults_injected_count,
            "unhandled_failures_count": self.unhandled_failures_count,
            "fallback_handled_count": self.fallback_handled_count,
            "retry_count": self.retry_count,
            "total_tokens": self.total_prompt_tokens + self.total_completion_tokens,
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "wasted_tokens": self.wasted_prompt_tokens + self.wasted_completion_tokens,
            "wasted_prompt_tokens": self.wasted_prompt_tokens,
            "wasted_completion_tokens": self.wasted_completion_tokens,
            "fault_counts": self.fault_counts,
            "wasted_cost_usd": fin["wasted_cost_usd"],
            "total_run_cost_usd": fin["total_run_cost_usd"],
            "monthly_leak_risk_usd": fin["monthly_leak_risk_usd"],
            "call_logs": self.call_logs
        }


# Convenience instance access function
def get_tracker() -> TelemetryTracker:
    return TelemetryTracker()
