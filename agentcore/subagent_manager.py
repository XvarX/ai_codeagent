"""AgentManager — manages multiple AgentController instances."""

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path

from agentcore.config import AgentConfig
from agentcore.controller import AgentController, EventHandler, _build_registry, _build_provider
from agentcore.agent_definitions import AgentDefinition


@dataclass
class SubagentState:
    """Runtime state for one subagent."""
    id: str
    name: str
    definition: AgentDefinition
    controller: AgentController
    message_queue: "AgentMessageQueue | None" = None
    status: str = "pending"
    result: str = ""
    error: str = ""
    background_task: asyncio.Task | None = None
    turn_count: int = 0
    est_tokens: int = 0
    keep_alive: bool = False
    debug_events: list = field(default_factory=list)  # captured debug entries


def _build_provider_for_agent(config: AgentConfig, definition: AgentDefinition):
    """Build a provider for a specific agent definition.

    Uses agent definition's provider override, or falls back to default config.
    """
    if definition.provider:
        provider_name = definition.provider.lower()
        # Check config.yaml for provider type
        import yaml
        config_path = Path(__file__).parent.parent / "config.yaml"
        if not config_path.exists():
            return _build_provider(config)

        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}

        provider_type = cfg.get("provider_types", {}).get(provider_name, "").lower()
        api_key = cfg.get("api_keys", {}).get(provider_name, config.api_key or "")
        base_url = cfg.get("base_urls", {}).get(provider_name, config.base_url or "")
        model = definition.model or cfg.get("models", {}).get(provider_name, config.model or "")

        if provider_type == "anthropic" or (not provider_type and provider_name == "anthropic"):
            from agentcore.providers.anthropic import AnthropicProvider
            return AnthropicProvider(model=model, api_key=api_key, base_url=base_url)
        else:
            from agentcore.providers.openai_compat import OpenAICompatProvider
            return OpenAICompatProvider(
                provider=provider_name, model=model,
                api_key=api_key, base_url=base_url,
            )

    return _build_provider(config)


def _build_tool_registry_for_agent(config: AgentConfig, definition: AgentDefinition, parent_registry=None):
    """Build a ToolRegistry for an agent, applying tool restrictions.

    If definition.tools is None, all tools are inherited.
    If definition.tools is a list, only those tools are included (minus disallowed).
    """
    base_registry, skills_text = _build_registry(config.cwd)

    if definition.tools is None:
        return base_registry, skills_text

    from agentcore.tools.registry import ToolRegistry
    filtered = ToolRegistry()
    allowed = set(definition.tools)
    disallowed = set(definition.disallowed_tools or [])
    for tool in base_registry.list_all():
        if tool.name in disallowed:
            continue
        if tool.name in allowed:
            filtered.register(tool)
    return filtered, skills_text


class _AgentHandler(EventHandler):
    """EventHandler that captures subagent events and optionally forwards to app pipeline.

    When forwarding IS wired (active agent): events go through app._on_* methods
    which write to debug drawer and chat view identically to master.
    When forwarding is NOT wired (inactive): events are stored in debug_events
    for replay when the user switches to this agent.
    """

    def __init__(self, manager: "AgentManager", agent_id: str):
        super().__init__()
        self.manager = manager
        self.agent_id = agent_id
        self._pending_tools = 0  # track tool calls to distinguish [Response] vs [Final Response]
        self._fwd_thinking: callable | None = None
        self._fwd_text_delta: callable | None = None
        self._fwd_tool_use: callable | None = None
        self._fwd_tool_result: callable | None = None
        self._fwd_response_done: callable | None = None
        self._fwd_done: callable | None = None
        self._fwd_error: callable | None = None
        self._fwd_compact_call: callable | None = None
        self._fwd_compact: callable | None = None
        self._fwd_snip: callable | None = None
        self._fwd_subagent_done: callable | None = None
        self._fwd_enqueued: callable | None = None
        self._fwd_request: callable | None = None

    @property
    def _is_forwarding(self):
        return self._fwd_tool_use is not None

    def _wire_forwarding(self, handler: EventHandler):
        """Wire forwarding so events flow through handler to WebSocket."""
        self._fwd_thinking = handler.on_thinking
        self._fwd_text_delta = handler.on_text_delta
        self._fwd_tool_use = handler.on_tool_use
        self._fwd_tool_result = handler.on_tool_result
        self._fwd_response_done = handler.on_response_done
        self._fwd_done = handler.on_done
        self._fwd_error = handler.on_error
        self._fwd_compact_call = handler.on_compact_call
        self._fwd_compact = handler.on_compact
        self._fwd_snip = handler.on_snip
        self._fwd_subagent_done = handler.on_subagent_done
        self._fwd_enqueued = handler.on_enqueued
        self._fwd_request = handler.on_request

    def _clear_forwarding(self):
        """Clear all forwarding callbacks."""
        for attr in ('_fwd_thinking', '_fwd_text_delta', '_fwd_tool_use',
                     '_fwd_tool_result', '_fwd_response_done', '_fwd_done',
                     '_fwd_error', '_fwd_compact_call',
                     '_fwd_compact', '_fwd_snip', '_fwd_subagent_done',
                     '_fwd_enqueued', '_fwd_request'):
            setattr(self, attr, None)

    def _record(self, prefix: str, message: str, color: str = "#94A3B8",
                event_data: dict | None = None, group_key: str | None = None):
        """Store event for later replay (only when NOT forwarding to app)."""
        if self._is_forwarding:
            return  # app._on_* methods already write to debug drawer
        state = self.manager.agents.get(self.agent_id)
        if state:
            state.debug_events.append({
                "prefix": prefix, "message": message, "color": color,
                "event_data": event_data, "group_key": group_key,
            })

    async def on_request(self, text: str, msg_count: int, est_tokens: int,
                         tools_count: int, model: str = ""):
        msg_lines = [
            f"Messages: {msg_count}  |  ~{est_tokens} tokens  |  {tools_count} tools",
            f"  [new] user: {text[:200]}",
        ]
        self._record("[Request]", "\n".join(msg_lines), "#569cd6",
                     event_data={
                         "type": "Request",
                         "model": model,
                         "message_count": msg_count,
                         "est_tokens": est_tokens,
                         "tools_count": tools_count,
                         "user_message": text,
                         "formatted": "\n".join(msg_lines),
                     },
                     group_key="user")
        if self._fwd_request:
            self._fwd_request(text, msg_count, est_tokens, tools_count, model)

    async def on_thinking(self):
        # _fwd_thinking handles sync + thinking animation; no debug entry needed
        if self._fwd_thinking:
            self._fwd_thinking()

    async def on_text_delta(self, token: str, reasoning: bool = False):
        if self._fwd_text_delta:
            self._fwd_text_delta(token, reasoning)

    async def on_tool_use(self, name: str, input_dict: dict, tool_use_id: str = ""):
        self._pending_tools += 1
        self._record(f"[Tool] {name}",
                     ", ".join(f"{k}={str(v)[:50]}" for k, v in input_dict.items()),
                     "#22C55E",
                     group_key=f"tool:{tool_use_id}" if tool_use_id else None)
        if self._fwd_tool_use:
            self._fwd_tool_use(name, input_dict, tool_use_id)

    async def on_tool_result(self, name: str, result: str, is_error: bool, duration_ms: float = 0, tool_use_id: str = ""):
        if self._pending_tools > 0:
            self._pending_tools -= 1
        color = "#EF4444" if is_error else "#8B5CF6"
        event_data = {
            "type": "Tool",
            "name": name,
            "result": result,
            "is_error": is_error,
            "formatted": f"Tool: {name}\nStatus: {'ERROR' if is_error else 'OK'}\n\n{result[:2000]}",
            "raw_json": json.dumps({"tool": name, "result": result, "is_error": is_error},
                                   ensure_ascii=False, indent=2),
        }
        self._record("[Send Tool Result]", f"{name}  |  {result[:200]}", color,
                     event_data=event_data,
                     group_key=f"tool:{tool_use_id}" if tool_use_id else None)
        if self._fwd_tool_result:
            self._fwd_tool_result(name, result, is_error, duration_ms, tool_use_id)

    async def on_response_done(self, raw: dict):
        has_tools = self._pending_tools > 0
        self._pending_tools = 0

        # Normalize usage (same logic as FletApp._normalize_usage)
        orig_usage = raw.get("usage", {})
        if not orig_usage:
            norm_usage = {}
        elif "prompt_tokens" not in orig_usage and "input_tokens" in orig_usage:
            input_total = (
                (orig_usage.get("input_tokens") or 0)
                + (orig_usage.get("cache_creation_input_tokens") or 0)
                + (orig_usage.get("cache_read_input_tokens") or 0)
            )
            output = orig_usage.get("output_tokens") or 0
            cache_tokens = orig_usage.get("cache_read_input_tokens") or 0
            norm_usage = {
                "prompt_tokens": input_total,
                "completion_tokens": output,
                "total_tokens": input_total + output,
                "prompt_tokens_details": {"cached_tokens": cache_tokens},
            }
        else:
            norm_usage = dict(orig_usage)
            if "total_tokens" not in norm_usage:
                norm_usage["total_tokens"] = norm_usage.get("prompt_tokens", 0) + norm_usage.get("completion_tokens", 0)

        req = raw.get("_request", {})
        msgs = req.get("messages", [])
        model = req.get("model", "?")
        prompt_tokens = norm_usage.get("prompt_tokens", "?")
        completion_tokens = norm_usage.get("completion_tokens", "?")
        total_tokens = norm_usage.get("total_tokens", "?")
        pt_details = norm_usage.get("prompt_tokens_details") or {}
        cache_read = pt_details.get("cached_tokens", 0) if isinstance(pt_details, dict) else 0

        tool_blocks = raw.get("_tool_use_blocks", [])
        final_text = raw.get("_text", "")

        resp_lines = [f"Msgs: {len(msgs)}"]
        resp_lines.append(f"prompt={prompt_tokens}, completion={completion_tokens}, total={total_tokens}")
        if cache_read:
            pt = prompt_tokens if isinstance(prompt_tokens, int) else 1
            resp_lines.append(f"cache hit: {cache_read} tokens ({cache_read * 100 // max(pt, 1)}%)")
        if tool_blocks:
            resp_lines.append("Tool calls: " + ", ".join(t["tool_name"] for t in tool_blocks))
        else:
            text_preview = final_text[:20].replace("\n", " ")
            if len(final_text) > 20:
                text_preview += "..."
            resp_lines.append(f"Text: {text_preview}")

        prefix = "[Final Response]" if not has_tools else "[Response]"
        color = "#059669" if not has_tools else "#10B981"

        # Detail dialog shows full text; entry message shows truncated preview
        detail_lines = list(resp_lines)
        if final_text and not has_tools:
            detail_lines[-1] = f"Text:\n{final_text}"

        resp_only = {k: v for k, v in raw.items() if k not in ("_request",)}
        event_data = {
            "type": "Response",
            "model": model,
            "raw_json": json.dumps(resp_only, ensure_ascii=False, indent=2),
            "formatted": "\n".join(detail_lines),
            "text": final_text,
        }
        group_key = f"asst:{raw.get('id', '')}" if raw.get("id") else None

        self._record(prefix, "\n".join(resp_lines), color,
                     event_data=event_data, group_key=group_key)
        if self._fwd_response_done:
            self._fwd_response_done(raw)

    async def on_error(self, message: str):
        state = self.manager.agents.get(self.agent_id)
        if state:
            state.error = message
        self._record("[Error]", message, "#EF4444",
                     event_data={
                         "type": "Error",
                         "formatted": message,
                         "raw_json": json.dumps({"error": message}, ensure_ascii=False),
                     })
        if self._fwd_error:
            self._fwd_error(message)

    async def on_done(self, final_text: str):
        state = self.manager.agents.get(self.agent_id)
        if state:
            state.result = final_text
        if self._fwd_done:
            self._fwd_done(final_text)

    async def on_compact_call(self, old_msg_count: int, pre_tokens: int):
        if self._fwd_compact_call:
            self._fwd_compact_call(old_msg_count, pre_tokens)

    async def on_compact(self, pre_tokens: int, post_tokens: int, trigger: str, summary: str = ""):
        if self._fwd_compact:
            self._fwd_compact(pre_tokens, post_tokens, trigger, summary)

    async def on_snip(self, groups_removed: int, tokens_before: int, tokens_after: int):
        if self._fwd_snip:
            self._fwd_snip(groups_removed, tokens_before, tokens_after)

    async def on_subagent_done(self, agent_id: str, status: str, result: str):
        if self._fwd_subagent_done:
            self._fwd_subagent_done(agent_id, status, result)

    async def on_enqueued(self, from_name: str, message: str, source: str):
        self._record(f"[Msg from {from_name}]", message[:200], "#A855F7",
                     event_data={
                         "type": "InboxMessage",
                         "from": from_name,
                         "message": message,
                         "formatted": f"From: {from_name}\n\n{message[:2000]}",
                     },
                     group_key="user")
        if self._fwd_enqueued:
            self._fwd_enqueued(from_name, message, source)


class AgentManager:
    """Manages the lifecycle of all agents (master + subagents)."""

    def __init__(self, config: AgentConfig,
                 user_agents: dict[str, AgentDefinition] | None = None):
        self.config = config
        self.user_agents = user_agents or {}
        self.agents: dict[str, SubagentState] = {}
        self.active_id: str = "master"
        self.on_change = None  # set by UI to refresh sidebar
        self.on_spawn = None   # set externally: async fn(agent_id, state) for persistence

        self._create_master()
        # master_handler exposed for _run_background notifications
        self.master_handler = self.agents["master"].controller.handler

    @staticmethod
    async def _emit_request(controller, text: str):
        """Emit on_request for an inactive agent's send_message call."""
        agent = controller.agent
        handler = controller.handler
        msg_count = len(agent.messages) + 1
        est_tokens = agent.est_tokens() + len(text) // 2
        tools_count = len(agent.registry.get_schemas())
        model = agent.provider.model or ""
        await handler.on_request(text, msg_count, est_tokens, tools_count, model)

    def _create_master(self):
        """Create the master agent controller."""
        handler = _AgentHandler(self, "master")
        controller = AgentController(self.config, handler)
        state = SubagentState(
            id="master",
            name="Master",
            definition=AgentDefinition(
                name="Master", description="Main agent",
                agent_type="built-in", system_prompt="",
                tools=None, source="built-in",
            ),
            controller=controller,
            message_queue=None,
            status="running",
        )
        self.agents["master"] = state
        from agentcore.agent_message_queue import AgentMessageQueue
        queue = AgentMessageQueue(controller)
        state.message_queue = queue
        controller.agent._agent_manager = self
        controller.agent._agent_id = "master"

        # Register Agent tool and SendMessage tool on master
        from agentcore.tools.agent_tool import AgentTool
        agent_tool = AgentTool(self, self.user_agents)
        controller.registry.register(agent_tool)
        from agentcore.tools.send_message_tool import SendMessageTool
        send_tool = SendMessageTool(self, "master")
        controller.registry.register(send_tool)

    async def spawn(self, definition: AgentDefinition, prompt: str,
                    background: bool = False, keep_alive: bool = False,
                    name: str = "") -> str:
        """Spawn a new subagent. Returns agent_id."""
        import time
        agent_id = f"{definition.name.lower()}-{int(time.time() * 1000)}"

        # Create state first so we can wire inbox
        state = SubagentState(
            id=agent_id,
            name=name or definition.name,
            definition=definition,
            controller=None,  # wired below
            message_queue=None,
            status="running" if background else "pending",
            keep_alive=keep_alive,
        )

        provider = _build_provider_for_agent(self.config, definition)
        registry, skills_text = _build_tool_registry_for_agent(self.config, definition)

        handler = _AgentHandler(self, agent_id)
        controller = AgentController(self.config, handler)
        controller.provider = provider
        controller.registry = registry
        controller.agent.provider = provider
        controller.agent.registry = registry
        controller.agent.skills_text = skills_text
        from agentcore.agent_message_queue import AgentMessageQueue
        queue = AgentMessageQueue(controller)
        state.message_queue = queue
        controller.agent._agent_manager = self
        controller.agent._agent_id = agent_id

        # Wire controller back to state
        state.controller = controller
        self.agents[agent_id] = state

        # Register SendMessage tool on this agent
        from agentcore.tools.send_message_tool import SendMessageTool
        send_tool = SendMessageTool(self, agent_id)
        controller.registry.register(send_tool)

        # Persist subagent BEFORE execution — so bind_session is active during run
        if self.on_spawn:
            try:
                await self.on_spawn(agent_id, state)
            except Exception:
                import sys, traceback
                print(f"[AgentMgr] on_spawn failed for {agent_id}: {traceback.format_exc()}",
                      file=sys.stderr, flush=True)

        if background:
            state.background_task = asyncio.create_task(
                self._run_background(agent_id, prompt)
            )
        else:
            state.status = "running"
            try:
                await self._emit_request(controller, prompt)
                async with controller._agent_lock:
                    await controller.send_message(prompt)
                assistant_msgs = [
                    m.content for m in controller.agent.messages
                    if m.role == "assistant" and m.content
                ]
                state.result = "\n".join(assistant_msgs) if assistant_msgs else "(no response)"
                state.status = "completed"
            except Exception as e:
                state.error = str(e)
                state.status = "failed"

            # Auto-cleanup if not keep_alive
            if not keep_alive:
                await self._cleanup_agent(agent_id)

            # Notify master of completion (updates persisted meta + frontend)
            try:
                await self.master_handler.on_subagent_done(
                    agent_id, state.status, state.result)
            except Exception:
                pass
        if self.on_change:
            try:
                self.on_change()
            except Exception:
                pass
        return agent_id

    async def _run_background(self, agent_id: str, prompt: str):
        """Run a subagent in the background."""
        import sys
        state = self.agents[agent_id]
        print(f"[AgentMgr] {agent_id} background starting", file=sys.stderr, flush=True)
        try:
            state.status = "running"
            await self._emit_request(state.controller, prompt)
            async with state.controller._agent_lock:
                await state.controller.send_message(prompt)
            assistant_msgs = [
                m.content for m in state.controller.agent.messages
                if m.role == "assistant" and m.content
            ]
            state.result = "\n".join(assistant_msgs) if assistant_msgs else "(no response)"
            state.status = "completed"
            print(f"[AgentMgr] {agent_id} done: {state.result[:80]}", file=sys.stderr, flush=True)
        except asyncio.CancelledError:
            state.status = "killed"
            print(f"[AgentMgr] {agent_id} killed", file=sys.stderr, flush=True)
        except Exception as e:
            state.error = str(e)
            state.status = "failed"
            import traceback
            print(f"[AgentMgr] {agent_id} FAILED: {e}\n{traceback.format_exc()}", file=sys.stderr, flush=True)
        finally:
            state.background_task = None
            self._update_est_tokens(agent_id)
            # Auto-cleanup if not keep_alive
            if not state.keep_alive:
                await self._cleanup_agent(agent_id)
            try:
                await self.master_handler.on_subagent_done(
                    agent_id, state.status, state.result)
            except Exception:
                pass
            if self.on_change:
                try:
                    self.on_change()
                except Exception:
                    pass

    async def _cleanup_agent(self, agent_id: str):
        """Remove a completed agent and notify master."""
        state = self.agents.get(agent_id)
        if not state or agent_id == "master":
            return
        # Cancel any pending task
        if state.background_task and not state.background_task.done():
            state.background_task.cancel()
        # Remove from agents dict
        del self.agents[agent_id]
        # Clean up snapshot/replay tracking
        if hasattr(self, '_debug_snapshots'):
            self._debug_snapshots.pop(agent_id, None)
        if hasattr(self, '_replay_idx'):
            self._replay_idx.pop(agent_id, None)

    def _update_est_tokens(self, agent_id: str):
        state = self.agents.get(agent_id)
        if state:
            state.est_tokens = state.controller.agent.est_tokens()

    async def kill(self, agent_id: str):
        """Kill a running subagent."""
        if agent_id == "master":
            return
        state = self.agents.get(agent_id)
        if not state:
            return
        await state.controller.cancel()
        if state.background_task and not state.background_task.done():
            state.background_task.cancel()
        state.status = "killed"

    def switch(self, agent_id: str) -> SubagentState | None:
        """Switch the active agent view."""
        if agent_id not in self.agents:
            return None
        self.active_id = agent_id
        return self.agents[agent_id]

    def get_active(self) -> SubagentState:
        """Get current active agent state."""
        return self.agents[self.active_id]

    def get_alive_agents_text(self, for_agent_id: str = "master") -> str:
        """Return alive agent info for injection into LLM context."""
        alive = [
            s for aid, s in self.agents.items()
            if aid != for_agent_id and (s.keep_alive or aid == "master")
        ]
        if not alive:
            return ""
        lines = ["Alive agents (use SendMessage to communicate):"]
        for s in alive:
            running = s.controller.agent._loop_running if s.controller else False
            status = "working" if running else "idle"
            desc = s.definition.description or s.definition.name
            if len(desc) > 80:
                desc = desc[:77] + "..."
            lines.append(f"  - {s.name}: {status} | {desc}")
        return "\n".join(lines)

    async def send_message_to_agent(self, from_id: str, to_name_or_id: str, message: str):
        """Send a message from one agent to another via message queue."""
        from_state = self.agents.get(from_id)
        from_name_lower = from_state.name.lower() if from_state else ""
        if (to_name_or_id == from_id or
                to_name_or_id.lower() == from_name_lower):
            raise ValueError(f"Cannot send message to yourself ('{to_name_or_id}')")

        target_id = None
        for aid, st in self.agents.items():
            if aid == to_name_or_id or st.name.lower() == to_name_or_id.lower():
                target_id = aid
                break
        if target_id is None:
            raise ValueError(f"Agent '{to_name_or_id}' not found")

        from_name = from_state.name if from_state else "unknown"
        target_state = self.agents[target_id]
        if not target_state.message_queue:
            raise ValueError(f"Agent '{to_name_or_id}' has no message queue")
        formatted = f"[Message from {from_name}]\n{message}"
        target_state.message_queue.enqueue(formatted, source="agent")

    def list_subagents(self) -> list[SubagentState]:
        """Return all subagents (excluding master)."""
        return [s for aid, s in self.agents.items() if aid != "master"]
